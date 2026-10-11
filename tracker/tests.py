from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import BodyMeasurement, DailyLog, Goal, Meal, WaterLog, Workout, today

User = get_user_model()


def make_member(username):
    user = User.objects.create_user(username, f"{username}@example.com", "Str0ng-Passw0rd!", first_name=username.title())
    p = user.profile
    p.date_of_birth = today().replace(year=today().year - 20)
    p.sex, p.height_cm, p.onboarded = "M", Decimal("175"), True
    p.save()
    BodyMeasurement.objects.create(user=user, date=today(), weight_kg=Decimal("70"))
    return user


class OwnershipTests(TestCase):
    """One user must never see or change another user's records."""

    def setUp(self):
        self.alice, self.bob = make_member("alice"), make_member("bob")
        self.workout = Workout.objects.create(user=self.alice, title="Alice run", workout_type="running", duration_min=30)
        self.meal = Meal.objects.create(user=self.alice, name="Idli", calories=116)
        self.goal = Goal.objects.create(user=self.alice, title="Alice goal", kind="workouts", target_value=10)
        self.client.force_login(self.bob)

    def test_cannot_view_edit_or_delete_others_records(self):
        urls = [
            reverse("tracker:workout_detail", args=[self.workout.pk]),
            reverse("tracker:workout_edit", args=[self.workout.pk]),
            reverse("tracker:workout_delete", args=[self.workout.pk]),
            reverse("tracker:meal_edit", args=[self.meal.pk]),
            reverse("tracker:meal_delete", args=[self.meal.pk]),
            reverse("tracker:goal_edit", args=[self.goal.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.client.post(reverse("tracker:workout_delete", args=[self.workout.pk]))
        self.assertTrue(Workout.objects.filter(pk=self.workout.pk).exists())

    def test_lists_only_show_own_records(self):
        self.assertNotContains(self.client.get(reverse("tracker:workouts")), "Alice run")
        self.assertNotContains(self.client.get(reverse("tracker:goals")), "Alice goal")

    def test_export_only_contains_own_records(self):
        response = self.client.get(reverse("tracker:export", args=["workouts"]))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertNotIn("Alice run", response.content.decode())


class WorkoutTests(TestCase):
    def setUp(self):
        self.user = make_member("yusuf")
        self.client.force_login(self.user)

    def test_calories_are_estimated_from_met_and_weight(self):
        w = Workout.objects.create(user=self.user, title="Run", workout_type="running", duration_min=60)
        self.assertEqual(w.calories_burned, round(9.8 * 70))  # MET 9.8 × 70 kg × 1 h
        self.assertTrue(w.calories_estimated)

    def test_create_workout_with_exercises(self):
        response = self.client.post(reverse("tracker:workout_new"), {
            "title": "Push day", "workout_type": "strength", "date": today().isoformat(),
            "duration_min": "45", "intensity": "high", "distance_km": "", "calories_burned": "", "notes": "",
            "ex-TOTAL_FORMS": "2", "ex-INITIAL_FORMS": "0", "ex-MIN_NUM_FORMS": "0", "ex-MAX_NUM_FORMS": "30",
            "ex-0-name": "Bench press", "ex-0-sets": "4", "ex-0-reps": "8", "ex-0-weight_kg": "50",
            "ex-1-name": "", "ex-1-sets": "3", "ex-1-reps": "10", "ex-1-weight_kg": "0",
        })
        workout = Workout.objects.get(title="Push day")
        self.assertRedirects(response, workout.get_absolute_url())
        self.assertEqual(workout.exercises.count(), 1)
        self.assertEqual(workout.total_volume, Decimal("1600"))

    def test_future_dates_rejected(self):
        response = self.client.post(reverse("tracker:workout_new"), {
            "title": "Tomorrow", "workout_type": "running", "date": (today() + timedelta(days=1)).isoformat(),
            "duration_min": "30", "intensity": "moderate",
            "ex-TOTAL_FORMS": "0", "ex-INITIAL_FORMS": "0", "ex-MIN_NUM_FORMS": "0", "ex-MAX_NUM_FORMS": "30",
        })
        self.assertContains(response, "future")
        self.assertFalse(Workout.objects.filter(title="Tomorrow").exists())

    def test_repeat_copies_to_today(self):
        old = Workout.objects.create(user=self.user, title="Legs", workout_type="strength", duration_min=50,
                                     date=today() - timedelta(days=7))
        old.exercises.create(name="Squat", sets=4, reps=8, weight_kg=60)
        self.client.post(reverse("tracker:workout_repeat", args=[old.pk]))
        copy = Workout.objects.filter(user=self.user, date=today(), title="Legs").get()
        self.assertEqual(copy.exercises.count(), 1)

    def test_streaks(self):
        for d in (0, 1, 2, 5, 6, 7, 8):
            Workout.objects.create(user=self.user, title="x", duration_min=20, date=today() - timedelta(days=d))
        self.assertEqual(services.streaks(self.user), {"current": 3, "best": 4})


class NutritionAndHabitsTests(TestCase):
    def setUp(self):
        self.user = make_member("mubashir")
        self.client.force_login(self.user)

    def test_log_meal_and_day_totals(self):
        self.client.post(reverse("tracker:meal_new"), {
            "date": today().isoformat(), "meal_type": "breakfast", "name": "Masala dosa", "quantity": "1",
            "calories": "387", "protein_g": "7", "carbs_g": "52", "fat_g": "16",
        })
        summary = services.day_summary(self.user, today())
        self.assertEqual(summary["calories_in"], 387)
        self.assertEqual(summary["protein"], Decimal("7"))

    def test_implausible_macros_flagged(self):
        response = self.client.post(reverse("tracker:meal_new"), {
            "date": today().isoformat(), "meal_type": "lunch", "name": "Rice",
            "calories": "100", "protein_g": "50", "carbs_g": "100", "fat_g": "40",
        })
        self.assertContains(response, "Check the numbers")

    def test_water_add_and_undo(self):
        self.client.post(reverse("tracker:water_add"), {"amount_ml": "250"})
        self.client.post(reverse("tracker:water_add"), {"amount_ml": "500"})
        self.assertEqual(services.day_summary(self.user, today())["water_ml"], 750)
        self.client.post(reverse("tracker:water_undo"))
        self.assertEqual(WaterLog.objects.filter(user=self.user).count(), 1)

    def test_daily_check_in_upserts(self):
        for steps in ("6000", "9000"):
            self.client.post(reverse("tracker:habits"), {"date": today().isoformat(), "steps": steps, "sleep_hours": "7.5", "mood": "4"})
        self.assertEqual(DailyLog.objects.filter(user=self.user).count(), 1)
        self.assertEqual(DailyLog.objects.get(user=self.user).steps, 9000)

    def test_one_measurement_per_day(self):
        response = self.client.post(reverse("tracker:body"), {"date": today().isoformat(), "weight_kg": "69.5"})
        self.assertContains(response, "already have an entry")


class GoalTests(TestCase):
    def setUp(self):
        self.user = make_member("goal")
        self.client.force_login(self.user)

    def test_weight_goal_progress(self):
        self.client.post(reverse("tracker:goal_new"), {
            "title": "Get to 66", "kind": "weight", "target_value": "66", "start_date": today().isoformat(), "deadline": "",
        })
        goal = Goal.objects.get(title="Get to 66")
        self.assertEqual(goal.start_value, Decimal("70.0"))
        m = BodyMeasurement.objects.get(user=self.user, date=today())
        m.weight_kg = Decimal("68")
        m.save()
        self.assertEqual(services.goal_progress(goal)["percent"], 50)

    def test_count_goal_is_marked_achieved(self):
        goal = Goal.objects.create(user=self.user, title="3 workouts", kind="workouts", target_value=3,
                                   start_date=today() - timedelta(days=3))
        for d in range(3):
            Workout.objects.create(user=self.user, title="x", duration_min=20, date=today() - timedelta(days=d))
        self.client.get(reverse("tracker:goals"))
        goal.refresh_from_db()
        self.assertEqual(goal.achieved_at, today())


class ReportTests(TestCase):
    def test_reports_and_exports_render(self):
        user = make_member("report")
        Workout.objects.create(user=user, title="Run", workout_type="running", duration_min=30, distance_km=5)
        self.client.force_login(user)
        for query in ("", "?range=7", "?range=365", "?range=custom&start=2026-01-01&end=2026-02-01", "?range=custom&start=bad"):
            self.assertEqual(self.client.get(reverse("tracker:reports") + query).status_code, 200, query)
        for kind in ("workouts", "meals", "measurements", "habits"):
            self.assertEqual(self.client.get(reverse("tracker:export", args=[kind])).status_code, 200)
        report = services.period_report(user, today() - timedelta(days=6), today())
        self.assertEqual(report["workouts"], 1)
        self.assertEqual(report["distance"], Decimal("5"))
