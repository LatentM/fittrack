import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods

from tracker.models import BodyMeasurement

from .forms import DeleteAccountForm, LoginForm, OnboardingForm, ProfileForm, SignUpForm, UserUpdateForm

security_log = logging.getLogger("accounts.security")


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")


def _lockout_key(request, username):
    return f"login-fail:{(username or '').strip().lower()}:{_client_ip(request)}"


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("tracker:dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
        security_log.info("New account created: %s", user.username)
        messages.success(request, f"Welcome to Momentum, {user.first_name}. Let's set up your profile.")
        return redirect("accounts:onboarding")
    return render(request, "accounts/signup.html", {"form": form})


class LoginView(auth_views.LoginView):
    """Login with 'remember me' and a lockout after repeated failed attempts."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        key = _lockout_key(request, request.POST.get("username"))
        attempts = cache.get(key, 0)
        if attempts >= settings.LOGIN_MAX_ATTEMPTS:
            minutes = settings.LOGIN_LOCKOUT_SECONDS // 60
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, f"Too many failed attempts. Wait {minutes} minutes, or reset your password.")
            security_log.warning("Locked-out login attempt for %s", request.POST.get("username"))
            return self.render_to_response(self.get_context_data(form=form, locked=True), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = _lockout_key(self.request, self.request.POST.get("username"))
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, settings.LOGIN_LOCKOUT_SECONDS)
        remaining = settings.LOGIN_MAX_ATTEMPTS - attempts
        if 0 < remaining <= 2:
            form.add_error(None, f"{remaining} attempt{'s' if remaining > 1 else ''} left before a temporary lockout.")
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(_lockout_key(self.request, self.request.POST.get("username")))
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)  # ends when the browser closes
        user = form.get_user()
        messages.success(self.request, f"Welcome back, {user.first_name or user.username}.")
        return response


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    messages.info(request, "You've signed out.")
    return redirect("accounts:login")


@login_required
@require_http_methods(["GET", "POST"])
def onboarding(request):
    profile = request.user.profile
    form = OnboardingForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            profile = form.save(commit=False)
            profile.onboarded = True
            profile.save()
            BodyMeasurement.objects.update_or_create(
                user=request.user, date=BodyMeasurement.today(),
                defaults={"weight_kg": form.cleaned_data["starting_weight"]},
            )
        messages.success(request, f"All set. Your daily target is {profile.daily_calorie_target:,} kcal.")
        return redirect("tracker:dashboard")
    return render(request, "accounts/onboarding.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def account_settings(request):
    user_form = UserUpdateForm(request.POST or None, instance=request.user, prefix="user")
    profile_form = ProfileForm(request.POST or None, instance=request.user.profile, prefix="profile")
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, "Settings saved.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {
        "user_form": user_form, "profile_form": profile_form, "profile": request.user.profile,
    })


class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:settings")
    success_message = "Password changed. You're still signed in on this device."


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    form = DeleteAccountForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        username = user.username
        logout(request)
        user.delete()
        security_log.info("Account deleted: %s", username)
        messages.info(request, "Your account and all of its data have been deleted.")
        return redirect("tracker:home")
    return render(request, "accounts/delete_account.html", {"form": form})
