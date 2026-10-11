from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Profile

User = get_user_model()


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=60, label="First name",
                                 widget=forms.TextInput(attrs={"autocomplete": "given-name", "autofocus": True}))
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    agree = forms.BooleanField(label="I understand Momentum gives general fitness estimates, not medical advice", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Letters, numbers and @ . + - _ only."
        self.fields["username"].widget.attrs.update({"autocomplete": "username"})
        self.fields["password1"].help_text = "At least 8 characters, not too common, not all numbers."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in instead.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is taken. Pick another one.")
        return username


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Username or email",
                               widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    remember_me = forms.BooleanField(label="Keep me signed in for 2 weeks", required=False, initial=True)

    error_messages = {
        "invalid_login": "That username/email and password don't match. Check them and try again.",
        "inactive": "This account has been deactivated.",
    }


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not email:
            raise forms.ValidationError("Email is required so you can reset your password.")
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = (
            "date_of_birth", "sex", "height_cm", "activity_level", "objective",
            "calorie_target", "water_target_ml", "steps_target", "weekly_workout_target", "sleep_target_hours",
        )
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "height_cm": "Height (cm)",
            "calorie_target": "Daily calorie target (kcal)",
            "water_target_ml": "Daily water target (ml)",
            "steps_target": "Daily steps target",
            "weekly_workout_target": "Workouts per week",
            "sleep_target_hours": "Sleep target (hours)",
            "objective": "Main goal",
        }

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if dob > today:
                raise forms.ValidationError("Date of birth can't be in the future.")
            if age < 13 or age > 110:
                raise forms.ValidationError("Enter a real date of birth (age 13–110).")
        return dob


class OnboardingForm(ProfileForm):
    """First-run setup: body stats plus the starting weight."""

    starting_weight = forms.DecimalField(label="Current weight (kg)", min_value=25, max_value=350,
                                         max_digits=5, decimal_places=1)

    class Meta(ProfileForm.Meta):
        fields = ("date_of_birth", "sex", "height_cm", "activity_level", "objective")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("date_of_birth", "sex", "height_cm"):
            self.fields[name].required = True


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label="Confirm with your password",
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("That password is incorrect.")
        return password
