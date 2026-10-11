"""
Create a demo account with ~26 weeks of realistic data, so every chart has something to show.

    python manage.py seed_demo            # user: demo / password: Momentum@2026
    python manage.py seed_demo --reset    # wipe and recreate the demo user
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.models import BodyMeasurement, DailyLog, Exercise, Goal, Meal, WaterLog, Workout, today
from tracker.views import INDIAN_FOODS

User = get_user_model()

PLAN = [  # weekday -> (title, type, minutes, intensity, distance, exercises)
    ("Push day", "strength", 60, "high", None, [("Bench press", 4, 8, 50), ("Overhead press", 3, 10, 30), ("Incline dumbbell press", 3, 12, 16), ("Tricep dips", 3, 12, 0)]),
    ("Easy run, Besant Nagar", "running", 35, "moderate", 5.2, []),
    ("Pull day", "strength", 55, "high", None, [("Deadlift", 4, 5, 90), ("Lat pulldown", 3, 12, 45), ("Barbell row", 3, 10, 45), ("Bicep curl", 3, 12, 12)]),
    ("Yoga and mobility", "yoga", 40, "low", None, [("Surya namaskar", 3, 12, 0)]),
    ("Leg day", "strength", 60, "high", None, [("Squat", 4, 8, 70), ("Leg press", 3, 12, 120), ("Lunges", 3, 12, 10), ("Calf raise", 3, 15, 40)]),
    ("Long run, ECR", "running", 70, "moderate", 11.0, []),
    ("Cricket with friends", "sports", 90, "moderate", None, []),
]


class Command(BaseCommand):
    help = "Create a demo user with realistic fitness data"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the existing demo user first")
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="Momentum@2026")

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(42)
        username = opts["username"]
        if opts["reset"]:
            User.objects.filter(username=username).delete()
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists. Use --reset to recreate it."))
            return

        user = User.objects.create_user(username=username, email=f"{username}@momentum.local",
                                        password=opts["password"], first_name="Arjun", last_name="Raman")
        profile = user.profile
        profile.date_of_birth = today().replace(year=today().year - 21, month=3, day=14)
        profile.sex = "M"
        profile.height_cm = Decimal("176")
        profile.activity_level = "moderate"
        profile.objective = "lose"
        profile.weekly_workout_target = 5
        profile.onboarded = True
        profile.save()

        start = today() - timedelta(days=26 * 7 - 1)
        weight = 82.4
        day = start
        n = 0
        while day <= today():
            progress = (day - start).days / (26 * 7)
            # Training: consistency improves over the 26 weeks
            skip_chance = 0.55 - 0.35 * progress
            plan = PLAN[day.weekday()]
            if rng.random() > skip_chance and not (day == today() and rng.random() < 0.5):
                title, wtype, minutes, intensity, distance, exercises = plan
                w = Workout.objects.create(
                    user=user, title=title, workout_type=wtype, date=day, intensity=intensity,
                    duration_min=max(15, minutes + rng.randint(-10, 10)),
                    distance_km=Decimal(str(round(distance + rng.uniform(-0.6, 0.8), 2))) if distance else None,
                    notes=rng.choice(["", "", "Felt strong today.", "Short on sleep, kept it light.", "New personal best!"]),
                )
                for i, (name, sets, reps, kg) in enumerate(exercises):
                    bump = round(kg * 0.15 * progress) if kg else 0
                    Exercise.objects.create(workout=w, name=name, sets=sets, reps=reps, weight_kg=Decimal(kg + bump), order=i)
                n += 1

            # Weigh-ins 3 times a week, trending down with noise
            weight -= 0.03
            if day.weekday() in (0, 3, 5) or day == today():
                BodyMeasurement.objects.update_or_create(user=user, date=day, defaults={
                    "weight_kg": Decimal(str(round(weight + rng.uniform(-0.35, 0.35), 1))),
                    "body_fat_pct": Decimal(str(round(22 - 4 * progress + rng.uniform(-0.3, 0.3), 1))) if day.weekday() == 0 else None,
                    "waist_cm": Decimal(str(round(90 - 4 * progress, 1))) if day.weekday() == 0 else None,
                    "resting_hr": rng.randint(62, 68) - int(5 * progress),
                })

            # Last 3 weeks: meals, habits, water
            if (today() - day).days < 21:
                picks = {
                    "breakfast": rng.choice([[0, 3, 4], [2], [6, 22], [7, 17], [16, 8, 21]]),
                    "lunch": rng.choice([[9, 10, 17], [8, 8, 11, 17], [18], [9, 14, 3]]),
                    "snack": rng.choice([[19, 20], [21], [23], [20]]),
                    "dinner": rng.choice([[8, 8, 12], [1, 1, 3], [8, 13], [9, 10, 15]]),
                }
                for meal_type, idxs in picks.items():
                    if day == today() and meal_type in ("dinner", "snack"):
                        continue
                    for idx in idxs:
                        name, qty, kcal, p, c, f = INDIAN_FOODS[idx]
                        Meal.objects.create(user=user, date=day, meal_type=meal_type, name=name, quantity=qty,
                                            calories=kcal, protein_g=Decimal(str(p)), carbs_g=Decimal(str(c)), fat_g=Decimal(str(f)))
                DailyLog.objects.create(user=user, date=day, steps=rng.randint(5200, 12500),
                                        sleep_hours=Decimal(str(round(rng.uniform(5.8, 8.4), 1))), mood=rng.choice([3, 4, 4, 5]))
                for _ in range(rng.randint(4, 8) if day != today() else 3):
                    WaterLog.objects.create(user=user, date=day, amount_ml=rng.choice([250, 250, 500]))
            day += timedelta(days=1)

        latest = BodyMeasurement.objects.filter(user=user).order_by("-date").first()
        first = BodyMeasurement.objects.filter(user=user).order_by("date").first()
        Goal.objects.create(user=user, title="Reach 75 kg by Pongal", kind="weight", target_value=Decimal("75"),
                            start_value=first.weight_kg, start_date=first.date,
                            deadline=today() + timedelta(days=95))
        Goal.objects.create(user=user, title="Run 100 km this quarter", kind="distance", target_value=Decimal("100"),
                            start_date=today() - timedelta(days=60), deadline=today() + timedelta(days=30))
        Goal.objects.create(user=user, title="40 workouts", kind="workouts", target_value=Decimal("40"),
                            start_date=start, deadline=today() + timedelta(days=14))
        Goal.objects.create(user=user, title="First 10 workouts", kind="workouts", target_value=Decimal("10"),
                            start_date=start, achieved_at=start + timedelta(days=24))

        self.stdout.write(self.style.SUCCESS(
            f"Created '{username}' (password: {opts['password']}) with {n} workouts; latest weight {latest.weight_kg} kg."
        ))
