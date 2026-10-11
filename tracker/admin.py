from django.contrib import admin

from .models import BodyMeasurement, DailyLog, Exercise, Goal, Meal, WaterLog, Workout


class ExerciseInline(admin.TabularInline):
    model = Exercise
    extra = 0


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "workout_type", "date", "duration_min", "calories_burned")
    list_filter = ("workout_type", "intensity", "date")
    search_fields = ("title", "user__username", "notes")
    date_hierarchy = "date"
    inlines = [ExerciseInline]


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "meal_type", "date", "calories", "protein_g", "carbs_g", "fat_g")
    list_filter = ("meal_type", "date")
    search_fields = ("name", "user__username")
    date_hierarchy = "date"


@admin.register(BodyMeasurement)
class BodyMeasurementAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "weight_kg", "body_fat_pct", "waist_cm", "resting_hr")
    list_filter = ("date",)
    search_fields = ("user__username",)


@admin.register(DailyLog)
class DailyLogAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "steps", "sleep_hours", "mood")
    list_filter = ("mood", "date")
    search_fields = ("user__username",)


@admin.register(WaterLog)
class WaterLogAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "amount_ml", "created_at")
    list_filter = ("date",)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "target_value", "deadline", "achieved_at", "archived")
    list_filter = ("kind", "archived")
    search_fields = ("title", "user__username")
