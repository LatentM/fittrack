from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Profile(models.Model):
    """Fitness profile attached to every user. Created automatically on sign-up."""

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    class ActivityLevel(models.TextChoices):
        SEDENTARY = "sedentary", "Sedentary (little or no exercise)"
        LIGHT = "light", "Lightly active (1–3 days a week)"
        MODERATE = "moderate", "Moderately active (3–5 days a week)"
        ACTIVE = "active", "Very active (6–7 days a week)"
        ATHLETE = "athlete", "Athlete (twice a day)"

    class Objective(models.TextChoices):
        LOSE = "lose", "Lose weight"
        MAINTAIN = "maintain", "Maintain weight"
        GAIN = "gain", "Build muscle / gain weight"

    ACTIVITY_MULTIPLIERS = {
        "sedentary": Decimal("1.2"),
        "light": Decimal("1.375"),
        "moderate": Decimal("1.55"),
        "active": Decimal("1.725"),
        "athlete": Decimal("1.9"),
    }

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal("90")), MaxValueValidator(Decimal("250"))],
        help_text="Your height in centimetres",
    )
    activity_level = models.CharField(max_length=12, choices=ActivityLevel.choices, default=ActivityLevel.MODERATE)
    objective = models.CharField(max_length=10, choices=Objective.choices, default=Objective.MAINTAIN)

    # Daily / weekly targets (calorie target is optional; calculated when blank)
    calorie_target = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1000), MaxValueValidator(6000)],
        help_text="Leave blank to calculate it from your body stats",
    )
    water_target_ml = models.PositiveIntegerField(default=2500, validators=[MinValueValidator(500), MaxValueValidator(8000)])
    steps_target = models.PositiveIntegerField(default=8000, validators=[MinValueValidator(1000), MaxValueValidator(50000)])
    weekly_workout_target = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1), MaxValueValidator(14)])
    sleep_target_hours = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal("8.0"),
                                             validators=[MinValueValidator(Decimal("4")), MaxValueValidator(Decimal("12"))])

    onboarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.get_username()}"

    # --- Derived figures --------------------------------------------------
    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def latest_weight(self):
        latest = self.user.bodymeasurements.order_by("-date").first()
        return latest.weight_kg if latest else None

    @property
    def bmi(self):
        weight, height = self.latest_weight, self.height_cm
        if not weight or not height:
            return None
        metres = Decimal(height) / 100
        return round(Decimal(weight) / (metres * metres), 1)

    @property
    def bmi_category(self):
        bmi = self.bmi
        if bmi is None:
            return None
        # Asian cut-offs (WHO expert consultation) suit Indian users better than the global ones.
        if bmi < Decimal("18.5"):
            return "Underweight"
        if bmi < Decimal("23"):
            return "Healthy"
        if bmi < Decimal("25"):
            return "Overweight"
        return "Obese"

    @property
    def bmr(self):
        """Basal metabolic rate (Mifflin–St Jeor)."""
        weight, height, age = self.latest_weight, self.height_cm, self.age
        if not all([weight, height, age, self.sex]):
            return None
        value = Decimal("10") * Decimal(weight) + Decimal("6.25") * Decimal(height) - 5 * age
        value += 5 if self.sex == self.Sex.MALE else -161
        return int(value)

    @property
    def tdee(self):
        """Total daily energy expenditure = BMR × activity multiplier."""
        if self.bmr is None:
            return None
        return int(self.bmr * self.ACTIVITY_MULTIPLIERS[self.activity_level])

    @property
    def daily_calorie_target(self):
        if self.calorie_target:
            return self.calorie_target
        if self.tdee is None:
            return 2000
        adjust = {"lose": -500, "maintain": 0, "gain": 300}[self.objective]
        return max(1200, self.tdee + adjust)

    @property
    def macro_targets(self):
        """Grams of protein / carbs / fat for the calorie target (30/45/25 split)."""
        kcal = self.daily_calorie_target
        return {
            "protein": round(kcal * 0.30 / 4),
            "carbs": round(kcal * 0.45 / 4),
            "fat": round(kcal * 0.25 / 9),
        }
