from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # Workouts
    path("workouts/", views.workout_list, name="workouts"),
    path("workouts/new/", views.workout_form, name="workout_new"),
    path("workouts/<int:pk>/", views.workout_detail, name="workout_detail"),
    path("workouts/<int:pk>/edit/", views.workout_form, name="workout_edit"),
    path("workouts/<int:pk>/delete/", views.workout_delete, name="workout_delete"),
    path("workouts/<int:pk>/repeat/", views.workout_repeat, name="workout_repeat"),
    # Nutrition
    path("nutrition/", views.nutrition, name="nutrition"),
    path("nutrition/new/", views.meal_form, name="meal_new"),
    path("nutrition/quick-add/", views.meal_quick_add, name="meal_quick_add"),
    path("nutrition/<int:pk>/edit/", views.meal_form, name="meal_edit"),
    path("nutrition/<int:pk>/delete/", views.meal_delete, name="meal_delete"),
    # Body
    path("body/", views.body, name="body"),
    path("body/<int:pk>/edit/", views.measurement_edit, name="measurement_edit"),
    path("body/<int:pk>/delete/", views.measurement_delete, name="measurement_delete"),
    # Habits
    path("habits/", views.habits, name="habits"),
    path("habits/water/", views.water_add, name="water_add"),
    path("habits/water/undo/", views.water_undo, name="water_undo"),
    # Goals
    path("goals/", views.goals, name="goals"),
    path("goals/new/", views.goal_form, name="goal_new"),
    path("goals/<int:pk>/edit/", views.goal_form, name="goal_edit"),
    path("goals/<int:pk>/archive/", views.goal_archive, name="goal_archive"),
    path("goals/<int:pk>/delete/", views.goal_delete, name="goal_delete"),
    # Reports
    path("reports/", views.reports, name="reports"),
    path("reports/export/<str:kind>.csv", views.export_csv, name="export"),
]
