from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

User = settings.AUTH_USER_MODEL


def today():
    return timezone.localdate()


class OwnedModel(models.Model):
    """Base for every record that belongs to one user."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @staticmethod
    def today():
        return today()


# --- Workouts ----------------------------------------------------------------------
class Workout(OwnedModel):
    class Type(models.TextChoices):
        STRENGTH = "strength", "Strength training"
        RUNNING = "running", "Running"
        WALKING = "walking", "Walking"
        CYCLING = "cycling", "Cycling"
        SWIMMING = "swimming", "Swimming"
        HIIT = "hiit", "HIIT"
        YOGA = "yoga", "Yoga"
        SPORTS = "sports", "Sports"
        OTHER = "other", "Other"

    class Intensity(models.TextChoices):
        LOW = "low", "Easy"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "Hard"

    # Metabolic equivalents (Compendium of Physical Activities, rounded)
    MET = {
        "strength": 5.0, "running": 9.8, "walking": 3.8, "cycling": 7.5, "swimming": 7.0,
        "hiit": 8.0, "yoga": 2.5, "sports": 7.0, "other": 5.0,
    }
    INTENSITY_FACTOR = {"low": 0.8, "moderate": 1.0, "high": 1.2}

    title = models.CharField(max_length=120)
    workout_type = models.CharField("Type", max_length=12, choices=Type.choices, default=Type.STRENGTH)
    date = models.DateField(default=today)
    duration_min = models.PositiveIntegerField("Duration (min)", validators=[MinValueValidator(1), MaxValueValidator(600)])
    intensity = models.CharField(max_length=10, choices=Intensity.choices, default=Intensity.MODERATE)
    distance_km = models.DecimalField("Distance (km)", max_digits=6, decimal_places=2, null=True, blank=True,
                                      validators=[MinValueValidator(Decimal("0"))])
    calories_burned = models.PositiveIntegerField("Calories burned", null=True, blank=True,
                                                  help_text="Leave blank and we'll estimate it from type, time and your weight")
    calories_estimated = models.BooleanField(default=False, editable=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.title} ({self.date:%d %b %Y})"

    def get_absolute_url(self):
        return reverse("tracker:workout_detail", args=[self.pk])

    def estimate_calories(self, weight_kg=None):
        weight = float(weight_kg or 70)
        met = self.MET.get(self.workout_type, 5.0) * self.INTENSITY_FACTOR.get(self.intensity, 1.0)
        return round(met * weight * (self.duration_min / 60))

    def save(self, *args, **kwargs):
        if not self.calories_burned:
            latest = BodyMeasurement.objects.filter(user_id=self.user_id, date__lte=self.date).order_by("-date").first()
            self.calories_burned = self.estimate_calories(latest.weight_kg if latest else None)
            self.calories_estimated = True
        super().save(*args, **kwargs)

    @property
    def total_volume(self):
        """Total weight lifted across all sets (kg)."""
        return sum((e.volume for e in self.exercises.all()), Decimal("0"))

    @property
    def pace(self):
        """Minutes per km for distance workouts."""
        if self.distance_km and self.distance_km > 0:
            minutes = Decimal(self.duration_min) / self.distance_km
            whole = int(minutes)
            seconds = int((minutes - whole) * 60)
            return f"{whole}:{seconds:02d} /km"
        return None


class Exercise(models.Model):
    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name="exercises")
    name = models.CharField(max_length=80)
    sets = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(50)])
    reps = models.PositiveSmallIntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(500)])
    weight_kg = models.DecimalField("Weight (kg)", max_digits=6, decimal_places=1, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0"))])
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} {self.sets}×{self.reps}"

    @property
    def volume(self):
        return Decimal(self.sets * self.reps) * (self.weight_kg or Decimal("0"))


# --- Nutrition -------------------------------------------------------------------------
class Meal(OwnedModel):
    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH = "lunch", "Lunch"
        SNACK = "snack", "Snack"
        DINNER = "dinner", "Dinner"

    date = models.DateField(default=today)
    meal_type = models.CharField("Meal", max_length=10, choices=MealType.choices, default=MealType.BREAKFAST)
    name = models.CharField("Food", max_length=120)
    quantity = models.CharField(max_length=60, blank=True, help_text="e.g. 2 idlis, 1 bowl, 250 g")
    calories = models.PositiveIntegerField(validators=[MaxValueValidator(5000)])
    protein_g = models.DecimalField("Protein (g)", max_digits=5, decimal_places=1, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0"))])
    carbs_g = models.DecimalField("Carbs (g)", max_digits=5, decimal_places=1, default=Decimal("0"),
                                  validators=[MinValueValidator(Decimal("0"))])
    fat_g = models.DecimalField("Fat (g)", max_digits=5, decimal_places=1, default=Decimal("0"),
                                validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        ordering = ["date", "created_at"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.name} – {self.calories} kcal"


# --- Body -------------------------------------------------------------------------------
class BodyMeasurement(OwnedModel):
    date = models.DateField(default=today)
    weight_kg = models.DecimalField("Weight (kg)", max_digits=5, decimal_places=1,
                                    validators=[MinValueValidator(Decimal("25")), MaxValueValidator(Decimal("350"))])
    body_fat_pct = models.DecimalField("Body fat (%)", max_digits=4, decimal_places=1, null=True, blank=True,
                                       validators=[MinValueValidator(Decimal("2")), MaxValueValidator(Decimal("70"))])
    waist_cm = models.DecimalField("Waist (cm)", max_digits=5, decimal_places=1, null=True, blank=True,
                                   validators=[MinValueValidator(Decimal("40")), MaxValueValidator(Decimal("200"))])
    resting_hr = models.PositiveSmallIntegerField("Resting heart rate (bpm)", null=True, blank=True,
                                                  validators=[MinValueValidator(30), MaxValueValidator(150)])
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="one_measurement_per_day")]

    def __str__(self):
        return f"{self.weight_kg} kg on {self.date:%d %b %Y}"


# --- Daily habits ---------------------------------------------------------------------------
class WaterLog(OwnedModel):
    date = models.DateField(default=today)
    amount_ml = models.PositiveIntegerField(validators=[MinValueValidator(50), MaxValueValidator(3000)])

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.amount_ml} ml"


class DailyLog(OwnedModel):
    """One row per day for steps, sleep and how you felt."""

    class Mood(models.IntegerChoices):
        ROUGH = 1, "Rough"
        LOW = 2, "Low"
        OKAY = 3, "Okay"
        GOOD = 4, "Good"
        GREAT = 5, "Great"

    date = models.DateField(default=today)
    steps = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(100000)])
    sleep_hours = models.DecimalField("Sleep (hours)", max_digits=3, decimal_places=1, null=True, blank=True,
                                      validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    mood = models.PositiveSmallIntegerField(choices=Mood.choices, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="one_daily_log_per_day")]

    def __str__(self):
        return f"Log for {self.date:%d %b %Y}"


# --- Goals ------------------------------------------------------------------------------------
class Goal(OwnedModel):
    class Kind(models.TextChoices):
        TARGET_WEIGHT = "weight", "Reach a body weight"
        WORKOUTS = "workouts", "Complete a number of workouts"
        MINUTES = "minutes", "Train for a number of minutes"
        DISTANCE = "distance", "Cover a distance (km)"
        STEPS = "steps", "Walk a number of steps"

    UNITS = {"weight": "kg", "workouts": "workouts", "minutes": "min", "distance": "km", "steps": "steps"}

    title = models.CharField(max_length=120)
    kind = models.CharField("Goal type", max_length=10, choices=Kind.choices)
    target_value = models.DecimalField("Target", max_digits=9, decimal_places=1, validators=[MinValueValidator(Decimal("0.1"))])
    start_value = models.DecimalField(max_digits=9, decimal_places=1, null=True, blank=True, editable=False)
    start_date = models.DateField(default=today)
    deadline = models.DateField(null=True, blank=True)
    achieved_at = models.DateField(null=True, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["achieved_at", "deadline", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def unit(self):
        return self.UNITS.get(self.kind, "")
