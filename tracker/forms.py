from django import forms
from django.forms import inlineformset_factory

from .models import BodyMeasurement, DailyLog, Exercise, Goal, Meal, WaterLog, Workout, today


class DateInput(forms.DateInput):
    input_type = "date"


class UserOwnedForm(forms.ModelForm):
    """ModelForm that knows the current user (for per-user uniqueness checks)."""

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_date(self):
        value = self.cleaned_data.get("date")
        if value and value > today():
            raise forms.ValidationError("You can't log something in the future.")
        return value


class WorkoutForm(UserOwnedForm):
    class Meta:
        model = Workout
        fields = ("title", "workout_type", "date", "duration_min", "intensity", "distance_km", "calories_burned", "notes")
        widgets = {
            "date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "How did it feel? Anything to remember next time?"}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Push day, Marina beach run"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An estimated value shouldn't stick when the duration changes, so start blank.
        if self.instance.pk and self.instance.calories_estimated:
            self.initial["calories_burned"] = None


class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ("name", "sets", "reps", "weight_kg")
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. Bench press", "list": "exercise-suggestions"})}


ExerciseFormSet = inlineformset_factory(
    Workout, Exercise, form=ExerciseForm, extra=1, can_delete=True, max_num=30, validate_max=True,
)


class MealForm(UserOwnedForm):
    class Meta:
        model = Meal
        fields = ("date", "meal_type", "name", "quantity", "calories", "protein_g", "carbs_g", "fat_g")
        widgets = {
            "date": DateInput(),
            "name": forms.TextInput(attrs={"placeholder": "e.g. Masala dosa", "list": "food-suggestions"}),
        }
        labels = {"calories": "Calories (kcal)"}

    def clean(self):
        cleaned = super().clean()
        p, c, f = (cleaned.get(k) or 0 for k in ("protein_g", "carbs_g", "fat_g"))
        kcal = cleaned.get("calories")
        if kcal and (p or c or f):
            from_macros = float(p) * 4 + float(c) * 4 + float(f) * 9
            if from_macros > kcal * 1.5 + 50:
                self.add_error("calories", f"Your macros add up to about {round(from_macros)} kcal. Check the numbers.")
        return cleaned


class MeasurementForm(UserOwnedForm):
    class Meta:
        model = BodyMeasurement
        fields = ("date", "weight_kg", "body_fat_pct", "waist_cm", "resting_hr", "notes")
        widgets = {"date": DateInput()}

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get("date")
        if day and self.user:
            clash = BodyMeasurement.objects.filter(user=self.user, date=day).exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("date", "You already have an entry for this day. Edit that one instead.")
        return cleaned


class DailyLogForm(UserOwnedForm):
    class Meta:
        model = DailyLog
        fields = ("date", "steps", "sleep_hours", "mood", "notes")
        widgets = {"date": DateInput(), "mood": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mood"].choices = [c for c in self.fields["mood"].choices if c[0] != ""]
        self.fields["mood"].label = "How did you feel?"


class WaterForm(forms.ModelForm):
    class Meta:
        model = WaterLog
        fields = ("amount_ml",)
        labels = {"amount_ml": "Amount (ml)"}


class GoalForm(UserOwnedForm):
    class Meta:
        model = Goal
        fields = ("title", "kind", "target_value", "start_date", "deadline")
        widgets = {
            "start_date": DateInput(),
            "deadline": DateInput(),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Run 50 km before Pongal"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, deadline = cleaned.get("start_date"), cleaned.get("deadline")
        if start and deadline and deadline <= start:
            self.add_error("deadline", "The deadline has to be after the start date.")
        if cleaned.get("kind") == Goal.Kind.TARGET_WEIGHT and self.user:
            if not BodyMeasurement.objects.filter(user=self.user).exists():
                self.add_error("kind", "Log your weight once first, so progress has a starting point.")
        return cleaned


class ReportRangeForm(forms.Form):
    start = forms.DateField(widget=DateInput())
    end = forms.DateField(widget=DateInput())

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end:
            if start > end:
                raise forms.ValidationError("The start date must be before the end date.")
            if (end - start).days > 366:
                raise forms.ValidationError("Pick a range of one year or less.")
        return cleaned
