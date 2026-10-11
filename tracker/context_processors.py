from .models import today


def app_context(request):
    nav = [
        ("tracker:dashboard", "Dashboard", "home"),
        ("tracker:workouts", "Workouts", "dumbbell"),
        ("tracker:nutrition", "Nutrition", "bowl"),
        ("tracker:body", "Body", "scale"),
        ("tracker:habits", "Habits", "drop"),
        ("tracker:goals", "Goals", "flag"),
        ("tracker:reports", "Reports", "chart"),
    ]
    match = getattr(request, "resolver_match", None)
    current = f"{match.namespace}:{match.url_name}" if match and match.namespace else ""
    section = {
        "tracker:workout_new": "tracker:workouts", "tracker:workout_detail": "tracker:workouts",
        "tracker:workout_edit": "tracker:workouts", "tracker:workout_delete": "tracker:workouts",
        "tracker:meal_new": "tracker:nutrition", "tracker:meal_edit": "tracker:nutrition",
        "tracker:meal_delete": "tracker:nutrition", "tracker:measurement_edit": "tracker:body",
        "tracker:measurement_delete": "tracker:body", "tracker:goal_new": "tracker:goals",
        "tracker:goal_edit": "tracker:goals", "tracker:goal_delete": "tracker:goals",
    }.get(current, current)
    return {"nav_items": nav, "nav_current": section, "app_name": "Momentum", "today": today()}
