import csv
import json
from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from . import services
from .forms import (DailyLogForm, ExerciseFormSet, GoalForm, MealForm, MeasurementForm, ReportRangeForm,
                    WaterForm, WorkoutForm)
from .models import BodyMeasurement, DailyLog, Goal, Meal, WaterLog, Workout, today


# --- Helpers ------------------------------------------------------------------------------------
def member_required(view):
    """Login required, and first-run setup finished."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.profile.onboarded:
            return redirect("accounts:onboarding")
        return view(request, *args, **kwargs)

    return wrapper


def parse_date(value, default=None):
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def back_or(request, fallback):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(fallback)


def as_json(data):
    return json.dumps(data, default=str)


# --- Public pages ------------------------------------------------------------------------------------
def home(request):
    if request.user.is_authenticated:
        return redirect("tracker:dashboard")
    # A made-up 26-week grid for the landing page illustration (deterministic, so it never flickers).
    columns, i = [], 0
    for w in range(26):
        col = []
        for d in range(7):
            seed = (w * 7 + d) * 2654435761 % 97
            ramp = min(4, w // 6 + 1)
            level = 0 if seed % 5 in (0, 1) and w < 16 else min(4, (seed % ramp) + (1 if w > 14 else 0))
            if d == 6 and w % 3:
                level = 0
            col.append({"level": level, "i": i})
            i += 1
        columns.append(col)
    return render(request, "tracker/home.html", {"demo_columns": columns})


def error_404(request, exception):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)


# --- Dashboard ----------------------------------------------------------------------------------------
@member_required
def dashboard(request):
    user, profile = request.user, request.user.profile
    day = today()
    summary = services.day_summary(user, day)
    macro_targets = profile.macro_targets
    goals = []
    for goal in Goal.objects.filter(user=user, archived=False, achieved_at__isnull=True)[:4]:
        progress = services.refresh_goal(goal)
        if progress.get("just_achieved"):
            messages.success(request, f"Goal achieved: {goal.title}. Brilliant work.")
        goals.append((goal, progress))
    heat = services.heatmap(user, weeks=26)
    from django.utils import timezone
    hour = timezone.localtime().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    context = {
        "greeting": greeting,
        "summary": summary,
        "profile": profile,
        "calorie_target": profile.daily_calorie_target,
        "calories_left": profile.daily_calorie_target - summary["calories_in"] + summary["calories_burned"],
        "pct_calories": services.pct(summary["calories_in"], profile.daily_calorie_target),
        "pct_water": services.pct(summary["water_ml"], profile.water_target_ml),
        "pct_steps": services.pct(summary["steps"], profile.steps_target),
        "macros": [
            ("Protein", summary["protein"], macro_targets["protein"], "protein"),
            ("Carbs", summary["carbs"], macro_targets["carbs"], "carbs"),
            ("Fat", summary["fat"], macro_targets["fat"], "fat"),
        ],
        "streak": services.streaks(user),
        "heat": heat,
        "week": services.week_progress(user),
        "goals": goals,
        "recent_workouts": Workout.objects.filter(user=user)[:5],
        "water_form": WaterForm(),
        "charts": as_json({
            "weight": services.weight_series(user, 90),
            "energy": services.energy_series(user, 7),
            "weekly": services.weekly_minutes_series(user, 8),
        }),
    }
    return render(request, "tracker/dashboard.html", context)


@member_required
@require_POST
def water_add(request):
    form = WaterForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        log.user = request.user
        log.date = today()
        log.save()
        total = services.day_summary(request.user, today())["water_ml"]
        messages.success(request, f"Added {log.amount_ml} ml of water. {total:,} ml today.")
    else:
        messages.error(request, "Enter an amount between 50 and 3000 ml.")
    return back_or(request, "tracker:dashboard")


@member_required
@require_POST
def water_undo(request):
    last = WaterLog.objects.filter(user=request.user, date=today()).order_by("-created_at").first()
    if last:
        amount = last.amount_ml
        last.delete()
        messages.info(request, f"Removed the last {amount} ml entry.")
    else:
        messages.info(request, "There's no water logged today to remove.")
    return back_or(request, "tracker:dashboard")


# --- Workouts ----------------------------------------------------------------------------------------------
@member_required
def workout_list(request):
    qs = Workout.objects.filter(user=request.user).prefetch_related("exercises")
    q = request.GET.get("q", "").strip()
    wtype = request.GET.get("type", "")
    start = parse_date(request.GET.get("from"))
    end = parse_date(request.GET.get("to"))
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(notes__icontains=q) | Q(exercises__name__icontains=q)).distinct()
    if wtype in Workout.Type.values:
        qs = qs.filter(workout_type=wtype)
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    totals = {"count": qs.count(), "minutes": services._sum(qs, "duration_min"), "kcal": services._sum(qs, "calories_burned")}
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "tracker/workout_list.html", {
        "page": page, "totals": totals, "types": Workout.Type.choices, "filters": {
            "q": q, "type": wtype, "from": request.GET.get("from", ""), "to": request.GET.get("to", ""),
        }, "querystring": params.urlencode(), "filtered": bool(q or wtype or start or end),
    })


def _exercise_suggestions(user):
    names = (Workout.objects.filter(user=user).values_list("exercises__name", flat=True)
             .exclude(exercises__name__isnull=True).distinct()[:40])
    defaults = ["Bench press", "Squat", "Deadlift", "Overhead press", "Pull-up", "Barbell row", "Lunges",
                "Push-up", "Plank", "Bicep curl", "Lat pulldown", "Leg press", "Surya namaskar"]
    return sorted(set(list(names) + defaults))


@member_required
@require_http_methods(["GET", "POST"])
def workout_form(request, pk=None):
    workout = get_object_or_404(Workout, pk=pk, user=request.user) if pk else Workout(user=request.user)
    form = WorkoutForm(request.POST or None, instance=workout, user=request.user)
    formset = ExerciseFormSet(request.POST or None, instance=workout, prefix="ex")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            workout = form.save(commit=False)
            workout.user = request.user
            workout.calories_estimated = False
            if not form.cleaned_data.get("calories_burned"):
                workout.calories_burned = None  # model.save() re-estimates it
            workout.save()
            formset.instance = workout
            exercises = formset.save(commit=False)
            for i, ex in enumerate(exercises):
                ex.order = i
                ex.save()
            for ex in formset.deleted_objects:
                ex.delete()
        messages.success(request, f"Workout {'updated' if pk else 'saved'}: {workout.title}.")
        return redirect(workout)
    return render(request, "tracker/workout_form.html", {
        "form": form, "formset": formset, "workout": workout if pk else None,
        "suggestions": _exercise_suggestions(request.user),
    })


@member_required
def workout_detail(request, pk):
    workout = get_object_or_404(Workout.objects.prefetch_related("exercises"), pk=pk, user=request.user)
    best = (Workout.objects.filter(user=request.user, workout_type=workout.workout_type)
            .aggregate(longest=Max("duration_min"), most_kcal=Max("calories_burned")))
    return render(request, "tracker/workout_detail.html", {"workout": workout, "best": best})


@member_required
@require_http_methods(["GET", "POST"])
def workout_delete(request, pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if request.method == "POST":
        title = workout.title
        workout.delete()
        messages.success(request, f"Deleted workout: {title}.")
        return redirect("tracker:workouts")
    return render(request, "tracker/confirm_delete.html", {
        "object": workout, "kind": "workout", "cancel_url": workout.get_absolute_url(),
    })


@member_required
@require_POST
def workout_repeat(request, pk):
    """Copy a past workout (with its exercises) to today."""
    original = get_object_or_404(Workout.objects.prefetch_related("exercises"), pk=pk, user=request.user)
    with transaction.atomic():
        copy = Workout.objects.create(
            user=request.user, title=original.title, workout_type=original.workout_type, date=today(),
            duration_min=original.duration_min, intensity=original.intensity, distance_km=original.distance_km,
            calories_burned=None if original.calories_estimated else original.calories_burned,
        )
        for ex in original.exercises.all():
            ex.pk = None
            ex.workout = copy
            ex.save()
    messages.success(request, "Copied to today. Adjust anything that changed.")
    return redirect("tracker:workout_edit", pk=copy.pk)


# --- Nutrition ------------------------------------------------------------------------------------------------
INDIAN_FOODS = [
    # name, quantity, kcal, protein, carbs, fat (typical home portions)
    ("Idli", "2 pieces", 116, 4, 24, 0.4), ("Plain dosa", "1 medium", 168, 4, 29, 4),
    ("Masala dosa", "1 medium", 387, 7, 52, 16), ("Sambar", "1 bowl", 130, 6, 18, 4),
    ("Coconut chutney", "2 tbsp", 70, 1, 3, 6), ("Upma", "1 bowl", 250, 6, 36, 9),
    ("Pongal", "1 bowl", 280, 8, 40, 10), ("Poha", "1 plate", 250, 5, 42, 7),
    ("Chapati", "1 piece", 104, 3, 18, 3), ("Steamed rice", "1 cup", 205, 4, 45, 0.4),
    ("Dal tadka", "1 bowl", 180, 9, 22, 6), ("Rajma", "1 bowl", 210, 11, 30, 5),
    ("Chole", "1 bowl", 240, 11, 32, 8), ("Paneer bhurji", "100 g", 300, 17, 6, 23),
    ("Chicken curry", "1 bowl", 290, 26, 6, 18), ("Egg bhurji", "2 eggs", 200, 13, 3, 15),
    ("Boiled eggs", "2 eggs", 155, 13, 1, 11), ("Curd", "1 cup", 98, 11, 3, 4),
    ("Chicken biryani", "1 plate", 490, 24, 58, 17), ("Banana", "1 medium", 105, 1, 27, 0.4),
    ("Whey protein", "1 scoop", 120, 24, 3, 1.5), ("Filter coffee", "1 cup", 90, 3, 10, 4),
    ("Masala chai", "1 cup", 105, 3, 14, 4), ("Sprouts salad", "1 bowl", 120, 9, 18, 1),
]


@member_required
def nutrition(request):
    day = parse_date(request.GET.get("date"), today())
    if day > today():
        day = today()
    meals = Meal.objects.filter(user=request.user, date=day)
    profile = request.user.profile
    summary = services.day_summary(request.user, day)
    targets = profile.macro_targets
    groups = []
    for key, label in Meal.MealType.choices:
        items = [m for m in meals if m.meal_type == key]
        groups.append({"key": key, "label": label, "items": items, "kcal": sum(m.calories for m in items)})
    recent = (Meal.objects.filter(user=request.user).exclude(date=day)
              .values("name", "quantity", "calories", "protein_g", "carbs_g", "fat_g")
              .annotate(times=Count("id")).order_by("-times", "name")[:6])
    meal_type = _guess_meal_type()
    form = MealForm(user=request.user, initial={"date": day, "meal_type": meal_type})
    return render(request, "tracker/nutrition.html", {
        "day": day, "prev_day": day - timedelta(days=1), "next_day": day + timedelta(days=1) if day < today() else None,
        "is_today": day == today(), "groups": groups, "summary": summary, "target": profile.daily_calorie_target,
        "pct_calories": services.pct(summary["calories_in"], profile.daily_calorie_target),
        "macros": [
            ("Protein", summary["protein"], targets["protein"], "protein"),
            ("Carbs", summary["carbs"], targets["carbs"], "carbs"),
            ("Fat", summary["fat"], targets["fat"], "fat"),
        ],
        "recent": recent, "quick_meal_type": meal_type, "form": form, "foods": INDIAN_FOODS, "foods_json": as_json(INDIAN_FOODS),
    })


def _guess_meal_type():
    from django.utils import timezone
    hour = timezone.localtime().hour
    if hour < 11:
        return "breakfast"
    if hour < 16:
        return "lunch"
    if hour < 19:
        return "snack"
    return "dinner"


@member_required
@require_http_methods(["GET", "POST"])
def meal_form(request, pk=None):
    meal = get_object_or_404(Meal, pk=pk, user=request.user) if pk else Meal(user=request.user)
    initial = {}
    if not pk:
        initial = {"date": parse_date(request.GET.get("date"), today()),
                   "meal_type": request.GET.get("type") or _guess_meal_type()}
    form = MealForm(request.POST or None, instance=meal, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        meal = form.save(commit=False)
        meal.user = request.user
        meal.save()
        messages.success(request, f"{'Updated' if pk else 'Logged'} {meal.name} ({meal.calories} kcal).")
        return redirect(f"{reverse('tracker:nutrition')}?date={meal.date.isoformat()}")
    return render(request, "tracker/meal_form.html", {
        "form": form, "meal": meal if pk else None, "foods": INDIAN_FOODS, "foods_json": as_json(INDIAN_FOODS),
    })


@member_required
@require_POST
def meal_quick_add(request):
    """Re-log a frequent food in one click."""
    form = MealForm(request.POST, user=request.user)
    if form.is_valid():
        meal = form.save(commit=False)
        meal.user = request.user
        meal.save()
        messages.success(request, f"Logged {meal.name} ({meal.calories} kcal).")
        return redirect(f"{reverse('tracker:nutrition')}?date={meal.date.isoformat()}")
    messages.error(request, "That food couldn't be logged. Open the full form to check it.")
    return redirect("tracker:nutrition")


@member_required
@require_http_methods(["GET", "POST"])
def meal_delete(request, pk):
    meal = get_object_or_404(Meal, pk=pk, user=request.user)
    target = f"{reverse('tracker:nutrition')}?date={meal.date.isoformat()}"
    if request.method == "POST":
        meal.delete()
        messages.success(request, f"Removed {meal.name}.")
        return redirect(target)
    return render(request, "tracker/confirm_delete.html", {"object": meal, "kind": "meal", "cancel_url": target})


# --- Body measurements ------------------------------------------------------------------------------------
@member_required
@require_http_methods(["GET", "POST"])
def body(request):
    entries = BodyMeasurement.objects.filter(user=request.user)
    existing_today = entries.filter(date=today()).first()
    form = MeasurementForm(request.POST or None, user=request.user,
                           initial={"date": today(), "weight_kg": request.user.profile.latest_weight})
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.user = request.user
        entry.save()
        messages.success(request, f"Logged {entry.weight_kg} kg for {entry.date:%d %b}.")
        return redirect("tracker:body")
    show_all = request.GET.get("all") == "1"
    total_entries = entries.count()
    rows = list(entries[: (366 if show_all else 21)])
    for i, row in enumerate(rows):
        row.change = row.weight_kg - rows[i + 1].weight_kg if i + 1 < len(rows) else None
    profile = request.user.profile
    first = entries.order_by("date").first()
    return render(request, "tracker/body.html", {
        "form": form, "rows": rows, "profile": profile, "existing_today": existing_today,
        "first": first, "latest": rows[0] if rows else None,
        "change_total": (rows[0].weight_kg - first.weight_kg) if rows and first and rows[0].pk != first.pk else None,
        "total_entries": total_entries, "show_all": show_all,
        "chart": as_json(services.weight_series(request.user, 365)),
    })


@member_required
@require_http_methods(["GET", "POST"])
def measurement_edit(request, pk):
    entry = get_object_or_404(BodyMeasurement, pk=pk, user=request.user)
    form = MeasurementForm(request.POST or None, instance=entry, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Measurement updated.")
        return redirect("tracker:body")
    return render(request, "tracker/simple_form.html", {
        "form": form, "title": f"Edit measurement for {entry.date:%d %b %Y}", "cancel_url": reverse("tracker:body"),
        "submit": "Save measurement",
    })


@member_required
@require_http_methods(["GET", "POST"])
def measurement_delete(request, pk):
    entry = get_object_or_404(BodyMeasurement, pk=pk, user=request.user)
    if request.method == "POST":
        entry.delete()
        messages.success(request, "Measurement deleted.")
        return redirect("tracker:body")
    return render(request, "tracker/confirm_delete.html", {
        "object": entry, "kind": "measurement", "cancel_url": reverse("tracker:body"),
    })


# --- Daily habits (steps, sleep, mood, water) ------------------------------------------------------------------
@member_required
@require_http_methods(["GET", "POST"])
def habits(request):
    day = parse_date(request.GET.get("date") or request.POST.get("date"), today())
    if day > today():
        day = today()
    log = DailyLog.objects.filter(user=request.user, date=day).first() or DailyLog(user=request.user, date=day)
    form = DailyLogForm(request.POST or None, instance=log, user=request.user, initial={"date": day})
    if request.method == "POST" and form.is_valid():
        log = form.save(commit=False)
        log.user = request.user
        existing = DailyLog.objects.filter(user=request.user, date=log.date).exclude(pk=log.pk).first()
        if existing:  # date was changed to a day that already has a log: update that one instead
            log.pk = existing.pk
        log.save()
        messages.success(request, f"Saved your check-in for {log.date:%d %b}.")
        return redirect("tracker:habits")

    profile = request.user.profile
    start = today() - timedelta(days=13)
    logs = {l.date: l for l in DailyLog.objects.filter(user=request.user, date__gte=start)}
    water = {}
    for w in WaterLog.objects.filter(user=request.user, date__gte=start):
        water[w.date] = water.get(w.date, 0) + w.amount_ml
    rows, labels, steps, sleep, water_series = [], [], [], [], []
    for i in range(14):
        d = today() - timedelta(days=i)
        l = logs.get(d)
        rows.append({"date": d, "log": l, "water": water.get(d, 0)})
    for r in reversed(rows):
        labels.append(r["date"].strftime("%d %b"))
        steps.append(r["log"].steps if r["log"] else 0)
        sleep.append(float(r["log"].sleep_hours) if r["log"] and r["log"].sleep_hours is not None else None)
        water_series.append(r["water"])
    return render(request, "tracker/habits.html", {
        "form": form, "day": day, "rows": rows, "profile": profile, "water_form": WaterForm(),
        "today_water": water.get(today(), 0),
        "pct_water": services.pct(water.get(today(), 0), profile.water_target_ml),
        "chart": as_json({"labels": labels, "steps": steps, "sleep": sleep, "water": water_series,
                          "steps_target": profile.steps_target, "sleep_target": float(profile.sleep_target_hours)}),
    })


# --- Goals -------------------------------------------------------------------------------------------------------
@member_required
def goals(request):
    active, done = [], []
    for goal in Goal.objects.filter(user=request.user, archived=False):
        progress = services.refresh_goal(goal)
        (done if goal.achieved_at else active).append((goal, progress))
    archived = Goal.objects.filter(user=request.user, archived=True)
    return render(request, "tracker/goals.html", {"active": active, "done": done, "archived": archived})


@member_required
@require_http_methods(["GET", "POST"])
def goal_form(request, pk=None):
    goal = get_object_or_404(Goal, pk=pk, user=request.user) if pk else Goal(user=request.user)
    form = GoalForm(request.POST or None, instance=goal, user=request.user)
    if request.method == "POST" and form.is_valid():
        goal = form.save(commit=False)
        goal.user = request.user
        if goal.kind == Goal.Kind.TARGET_WEIGHT:
            if not pk or "kind" in form.changed_data or "start_date" in form.changed_data:
                start = (BodyMeasurement.objects.filter(user=request.user, date__lte=goal.start_date).order_by("-date").first()
                         or BodyMeasurement.objects.filter(user=request.user).order_by("date").first())
                goal.start_value = start.weight_kg if start else None
        else:
            goal.start_value = None
        if pk and {"target_value", "kind", "start_date", "deadline"} & set(form.changed_data):
            goal.achieved_at = None  # re-evaluate after changes
        goal.save()
        services.refresh_goal(goal)
        messages.success(request, f"Goal {'updated' if pk else 'created'}: {goal.title}.")
        return redirect("tracker:goals")
    return render(request, "tracker/goal_form.html", {"form": form, "goal": goal if pk else None})


@member_required
@require_POST
def goal_archive(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    goal.archived = not goal.archived
    goal.save(update_fields=["archived", "updated_at"])
    messages.info(request, f"{'Archived' if goal.archived else 'Restored'}: {goal.title}.")
    return redirect("tracker:goals")


@member_required
@require_http_methods(["GET", "POST"])
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        goal.delete()
        messages.success(request, f"Deleted goal: {goal.title}.")
        return redirect("tracker:goals")
    return render(request, "tracker/confirm_delete.html", {
        "object": goal, "kind": "goal", "cancel_url": reverse("tracker:goals"),
    })


# --- Reports & export ----------------------------------------------------------------------------------------------
PRESETS = {"7": 7, "30": 30, "90": 90, "365": 365}


def _report_range(request):
    preset = request.GET.get("range", "30")
    if preset == "custom":
        form = ReportRangeForm(request.GET)
        if form.is_valid():
            return form.cleaned_data["start"], form.cleaned_data["end"], "custom", form
        return today() - timedelta(days=29), today(), "custom", form
    days = PRESETS.get(preset, 30)
    end = today()
    start = end - timedelta(days=days - 1)
    return start, end, str(days), ReportRangeForm(initial={"start": start, "end": end})


@member_required
def reports(request):
    start, end, preset, form = _report_range(request)
    report = services.period_report(request.user, start, end)
    previous = services.period_report(request.user, start - timedelta(days=report["days"]), start - timedelta(days=1))
    return render(request, "tracker/reports.html", {
        "report": report, "previous": previous, "preset": preset, "form": form,
        "chart": as_json({"energy": report["energy"],
                          "types": {"labels": [b["type"] for b in report["breakdown"]],
                                    "values": [b["minutes"] for b in report["breakdown"]]}}),
        "export_query": f"start={start.isoformat()}&end={end.isoformat()}",
    })


EXPORTS = {
    "workouts": (Workout, ["date", "title", "workout_type", "duration_min", "intensity", "distance_km", "calories_burned", "notes"]),
    "meals": (Meal, ["date", "meal_type", "name", "quantity", "calories", "protein_g", "carbs_g", "fat_g"]),
    "measurements": (BodyMeasurement, ["date", "weight_kg", "body_fat_pct", "waist_cm", "resting_hr", "notes"]),
    "habits": (DailyLog, ["date", "steps", "sleep_hours", "mood", "notes"]),
}


@member_required
def export_csv(request, kind):
    if kind not in EXPORTS:
        return redirect("tracker:reports")
    model, fields = EXPORTS[kind]
    start = parse_date(request.GET.get("start"), date(2000, 1, 1))
    end = parse_date(request.GET.get("end"), today())
    rows = model.objects.filter(user=request.user, date__range=(start, end)).order_by("date")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="momentum-{kind}-{start}-to-{end}.csv"'
    response.write("﻿")  # BOM so Excel opens UTF-8 correctly
    writer = csv.writer(response)
    writer.writerow([model._meta.get_field(f).verbose_name.capitalize() for f in fields])
    for row in rows.values_list(*fields):
        writer.writerow(["" if v is None else v for v in row])
    return response
