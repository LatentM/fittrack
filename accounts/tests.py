from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import BodyMeasurement, Workout

User = get_user_model()
PASSWORD = "Str0ng-Passw0rd!"


class SignUpTests(TestCase):
    def test_signup_creates_user_profile_and_logs_in(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "Yusuf", "username": "yusuf", "email": "Yusuf@Example.com",
            "password1": PASSWORD, "password2": PASSWORD, "agree": "on",
        })
        self.assertRedirects(response, reverse("accounts:onboarding"))
        user = User.objects.get(username="yusuf")
        self.assertEqual(user.email, "yusuf@example.com")  # normalised
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertNotEqual(user.password, PASSWORD)  # stored hashed

    def test_duplicate_email_rejected(self):
        User.objects.create_user("a", "same@example.com", PASSWORD)
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "B", "username": "b", "email": "SAME@example.com",
            "password1": PASSWORD, "password2": PASSWORD, "agree": "on",
        })
        self.assertContains(response, "already exists")
        self.assertFalse(User.objects.filter(username="b").exists())

    def test_weak_password_rejected(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "C", "username": "c", "email": "c@example.com",
            "password1": "12345678", "password2": "12345678", "agree": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="c").exists())


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("mubashir", "mubashir@example.com", PASSWORD, first_name="Mubashir")

    def test_login_with_username_or_email(self):
        for identifier in ("mubashir", "MUBASHIR@example.com"):
            response = self.client.post(reverse("accounts:login"), {"username": identifier, "password": PASSWORD})
            self.assertEqual(response.status_code, 302, identifier)
            self.client.post(reverse("accounts:logout"))

    def test_without_remember_me_session_ends_with_browser(self):
        self.client.post(reverse("accounts:login"), {"username": "mubashir", "password": PASSWORD})
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_keeps_session(self):
        self.client.post(reverse("accounts:login"), {"username": "mubashir", "password": PASSWORD, "remember_me": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    @override_settings(LOGIN_MAX_ATTEMPTS=3)
    def test_lockout_after_repeated_failures(self):
        for _ in range(3):
            self.client.post(reverse("accounts:login"), {"username": "mubashir", "password": "wrong"})
        response = self.client.post(reverse("accounts:login"), {"username": "mubashir", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many failed attempts", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProtectedPagesTests(TestCase):
    def test_pages_require_login(self):
        for name in ("tracker:dashboard", "tracker:workouts", "tracker:nutrition", "tracker:body",
                     "tracker:habits", "tracker:goals", "tracker:reports", "accounts:settings"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), response["Location"])

    def test_new_user_is_sent_to_onboarding(self):
        user = User.objects.create_user("new", "new@example.com", PASSWORD)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("tracker:dashboard")), reverse("accounts:onboarding"))

    def test_onboarding_saves_profile_and_weight(self):
        user = User.objects.create_user("new", "new@example.com", PASSWORD)
        self.client.force_login(user)
        response = self.client.post(reverse("accounts:onboarding"), {
            "date_of_birth": "2005-06-01", "sex": "M", "height_cm": "175", "starting_weight": "70",
            "activity_level": "moderate", "objective": "maintain",
        })
        self.assertRedirects(response, reverse("tracker:dashboard"))
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.onboarded)
        self.assertEqual(BodyMeasurement.objects.get(user=user).weight_kg, Decimal("70.0"))
        self.assertIsNotNone(user.profile.tdee)


class PasswordFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ali", "ali@example.com", PASSWORD)

    def test_password_reset_sends_email(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "ali@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)

    def test_password_change(self):
        self.client.force_login(self.user)
        new = "An0ther-Str0ng-One"
        response = self.client.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD, "new_password1": new, "new_password2": new,
        })
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))

    def test_delete_account_needs_password_and_removes_data(self):
        self.client.force_login(self.user)
        Workout.objects.create(user=self.user, title="Run", workout_type="running", duration_min=30, date=date.today())
        self.client.post(reverse("accounts:delete"), {"password": "wrong"})
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.client.post(reverse("accounts:delete"), {"password": PASSWORD})
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Workout.objects.exists())
