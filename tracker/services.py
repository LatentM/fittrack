"""
Calculations behind the dashboard, goals and reports.

Views stay thin: they ask this module for numbers and hand them to templates.
"""
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from .models import BodyMeasurement, DailyLog, Goal, Meal, WaterLog, Workout, today

ZERO = Decimal("0")


def _sum(qs, field):
    return qs.aggregate(v=Coalesce(Sum(field), ZERO if field.endswith(("_g", "_km", "_kg")) else 0))["v"]


def week_start(day):
    return day - timedelta(days=day.weekday())


# --- One day ----------------------------------------------------------------------------------
def day_summary(user, day):
    meals = Meal.objects.filter(user=user, date=day)
    workouts = Workout.objects.filter(user=user, date=day)
    log = DailyLog.objects.filter(user=user, date=day).first()
    return {
        "date": day,
        "calories_in": _sum(meals, "calories"),
        "protein": _sum(meals, "protein_g"),
        "carbs": _sum(meals, "carbs_g"),
        "fat": _sum(meals, "fat_g"),
        "calories_burned": _sum(workouts, "calories_burned"),
        "workouts": workouts.count(),
        "minutes": _sum(workouts, "duration_min"),
        "water_ml": _sum(WaterLog.objects.filter(user=user, date=day), "amount_ml"),
        "steps": log.steps if log else 0,
        "sleep": log.sleep_hours if log else None,
        "mood": log.get_mood_display() if log and log.mood else None,
        "log": log,
    }


def pct(value, target):
    if not target:
        return 0
    return max(0, min(100, round(float(value) / float(target) * 100)))


# --- Consistency ---------------------------------------------------------------------------------
def active_dates(user, since):
    return set(Workout.objects.filter(user=user, date__gte=since).values_list("date", flat=True))


def streaks(user):
    """Current and best streak of consecutive days with at least one workout."""
    dates = sorted(set(Workout.objects.filter(user=user).values_list("date", flat=True)))
    if not dates:
        return {"current": 0, "best": 0}
    best = run = 1
    for prev, cur in zip(dates, dates[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    current = 0
    day = today()
    date_set = set(dates)
    if day not in date_set:
        day -= timedelta(days=1)  # today isn't over yet, so yesterday still counts
    while day in date_set:
        current += 1
        day -= timedelta(days=1)
    return {"current": current, "best": best}


def heatmap(user, weeks=16):
    """Grid of the last N weeks (columns) × 7 weekdays (rows) shaded by training minutes."""
    end = today()
    start = week_start(end) - timedelta(weeks=weeks - 1)
    minutes = {
        row["date"]: row["m"]
        for row in Workout.objects.filter(user=user, date__gte=start, date__lte=end)
        .values("date").annotate(m=Sum("duration_min"))
    }

    def level(m):
        if not m:
            return 0
        if m < 20:
            return 1
        if m < 45:
            return 2
        if m < 75:
            return 3
        return 4

    columns, active, total = [], 0, 0
    for w in range(weeks):
        col = []
        for d in range(7):
            day = start + timedelta(weeks=w, days=d)
            m = minutes.get(day, 0)
            future = day > end
            if m and not future:
                active += 1
                total += m
            col.append({"date": day, "minutes": m, "level": level(m), "future": future})
        columns.append({"days": col, "month": col[0]["date"].strftime("%b") if col[0]["date"].day <= 7 else ""})
    return {"columns": columns, "active_days": active, "total_minutes": total, "start": start, "end": end}


def week_progress(user):
    start = week_start(today())
    qs = Workout.objects.filter(user=user, date__gte=start, date__lte=today())
    target = user.profile.weekly_workout_target
    done = qs.count()
    return {"done": done, "target": target, "remaining": max(0, target - done), "pct": pct(done, target),
            "minutes": _sum(qs, "duration_min"),
            "days": sorted(set(qs.values_list("date", flat=True)))}


# --- Chart series ------------------------------------------------------------------------------------
def weight_series(user, days=90):
    since = today() - timedelta(days=days)
    rows = BodyMeasurement.objects.filter(user=user, date__gte=since).order_by("date")
    return {"labels": [r.date.strftime("%d %b") for r in rows], "values": [float(r.weight_kg) for r in rows]}


def energy_series(user, days=7):
    """Calories eaten vs burned for each of the last N days."""
    end = today()
    start = end - timedelta(days=days - 1)
    eaten = dict(Meal.objects.filter(user=user, date__range=(start, end)).values_list("date").annotate(s=Sum("calories")))
    burned = dict(Workout.objects.filter(user=user, date__range=(start, end)).values_list("date").annotate(s=Sum("calories_burned")))
    labels, ins, outs = [], [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d.strftime("%a") if days <= 7 else d.strftime("%d %b"))
        ins.append(eaten.get(d, 0) or 0)
        outs.append(burned.get(d, 0) or 0)
    return {"labels": labels, "eaten": ins, "burned": outs}


def weekly_minutes_series(user, weeks=8):
    end = today()
    first = week_start(end) - timedelta(weeks=weeks - 1)
    rows = Workout.objects.filter(user=user, date__gte=first, date__lte=end).values_list("date", "duration_min")
    buckets = OrderedDict((first + timedelta(weeks=i), 0) for i in range(weeks))
    for d, m in rows:
        buckets[week_start(d)] += m
    return {"labels": [k.strftime("%d %b") for k in buckets], "values": list(buckets.values())}


def type_breakdown(user, start, end):
    rows = (Workout.objects.filter(user=user, date__range=(start, end))
            .values("workout_type").annotate(n=Count("id"), minutes=Sum("duration_min"), kcal=Sum("calories_burned"))
            .order_by("-minutes"))
    labels = dict(Workout.Type.choices)
    return [{"type": labels.get(r["workout_type"], r["workout_type"]), "key": r["workout_type"], "count": r["n"],
             "minutes": r["minutes"] or 0, "kcal": r["kcal"] or 0} for r in rows]


# --- Goals ------------------------------------------------------------------------------------------------
def goal_progress(goal):
    """Returns current value, percent complete and a short status for a goal."""
    user = goal.user
    window_end = min(goal.deadline, today()) if goal.deadline else today()
    workouts = Workout.objects.filter(user=user, date__gte=goal.start_date, date__lte=window_end)
    target = goal.target_value

    if goal.kind == Goal.Kind.TARGET_WEIGHT:
        latest = BodyMeasurement.objects.filter(user=user).order_by("-date").first()
        current = latest.weight_kg if latest else goal.start_value
        start = goal.start_value if goal.start_value is not None else current
        if current is None:
            percent = 0
        elif start == target:
            percent = 100 if current == target else 0
        else:
            percent = pct(start - current, start - target)  # works for losing or gaining
    elif goal.kind == Goal.Kind.WORKOUTS:
        current = workouts.count()
        percent = pct(current, target)
    elif goal.kind == Goal.Kind.MINUTES:
        current = _sum(workouts, "duration_min")
        percent = pct(current, target)
    elif goal.kind == Goal.Kind.DISTANCE:
        current = _sum(workouts, "distance_km")
        percent = pct(current, target)
    else:  # steps
        current = _sum(DailyLog.objects.filter(user=user, date__gte=goal.start_date, date__lte=window_end), "steps")
        percent = pct(current, target)

    days_left = (goal.deadline - today()).days if goal.deadline else None
    if goal.achieved_at or percent >= 100:
        status = "achieved"
    elif days_left is not None and days_left < 0:
        status = "missed"
    elif days_left is not None and goal.deadline > goal.start_date:
        elapsed = (today() - goal.start_date).days / (goal.deadline - goal.start_date).days * 100
        status = "on_track" if percent + 10 >= elapsed else "behind"
    else:
        status = "on_track"
    return {"current": current, "percent": percent, "status": status, "days_left": days_left}


def refresh_goal(goal):
    """Stamp a goal as achieved the first time it reaches 100%."""
    progress = goal_progress(goal)
    if progress["percent"] >= 100 and not goal.achieved_at:
        goal.achieved_at = today()
        goal.save(update_fields=["achieved_at", "updated_at"])
        progress["status"] = "achieved"
        progress["just_achieved"] = True
    return progress


# --- Reports ---------------------------------------------------------------------------------------------------
def period_report(user, start, end):
    days = (end - start).days + 1
    workouts = Workout.objects.filter(user=user, date__range=(start, end))
    meals = Meal.objects.filter(user=user, date__range=(start, end))
    logs = DailyLog.objects.filter(user=user, date__range=(start, end))
    water = WaterLog.objects.filter(user=user, date__range=(start, end))
    weights = list(BodyMeasurement.objects.filter(user=user, date__range=(start, end)).order_by("date"))
    meal_days = meals.values("date").distinct().count()
    log_days = logs.exclude(steps=0).count()
    sleep_rows = [l.sleep_hours for l in logs if l.sleep_hours is not None]
    water_days = water.values("date").distinct().count()
    return {
        "start": start, "end": end, "days": days,
        "workouts": workouts.count(),
        "active_days": workouts.values("date").distinct().count(),
        "minutes": _sum(workouts, "duration_min"),
        "calories_burned": _sum(workouts, "calories_burned"),
        "distance": _sum(workouts, "distance_km"),
        "avg_calories_in": round(_sum(meals, "calories") / meal_days) if meal_days else None,
        "avg_protein": round(_sum(meals, "protein_g") / meal_days) if meal_days else None,
        "avg_steps": round(_sum(logs, "steps") / log_days) if log_days else None,
        "avg_sleep": round(sum(sleep_rows) / len(sleep_rows), 1) if sleep_rows else None,
        "avg_water": round(_sum(water, "amount_ml") / water_days) if water_days else None,
        "weight_start": weights[0].weight_kg if weights else None,
        "weight_end": weights[-1].weight_kg if weights else None,
        "weight_change": (weights[-1].weight_kg - weights[0].weight_kg) if len(weights) > 1 else None,
        "breakdown": type_breakdown(user, start, end),
        "energy": energy_series_range(user, start, end),
    }


def energy_series_range(user, start, end):
    eaten = dict(Meal.objects.filter(user=user, date__range=(start, end)).values_list("date").annotate(s=Sum("calories")))
    burned = dict(Workout.objects.filter(user=user, date__range=(start, end)).values_list("date").annotate(s=Sum("calories_burned")))
    labels, ins, outs = [], [], []
    d = start
    while d <= end:
        labels.append(d.strftime("%d %b"))
        ins.append(eaten.get(d, 0) or 0)
        outs.append(burned.get(d, 0) or 0)
        d += timedelta(days=1)
    return {"labels": labels, "eaten": ins, "burned": outs}
