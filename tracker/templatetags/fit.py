from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()

TYPE_ICONS = {
    "strength": "dumbbell", "running": "run", "walking": "walk", "cycling": "bike", "swimming": "wave",
    "hiit": "bolt", "yoga": "lotus", "sports": "ball", "other": "spark",
}


@register.simple_tag
def icon(name, extra=""):
    """Inline icon from the SVG sprite in partials/icons.html."""
    return format_html('<svg class="icon {}" aria-hidden="true"><use href="#i-{}"></use></svg>', extra, name)


@register.filter
def type_icon(workout_type):
    return TYPE_ICONS.get(workout_type, "spark")


@register.filter
def signed(value, places=1):
    """+1.2 / −0.8 with a real minus sign."""
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return value
    text = f"{abs(number):.{int(places)}f}"
    if number > 0:
        return f"+{text}"
    if number < 0:
        return f"−{text}"
    return text


@register.filter(name="abs")
def absolute(value):
    try:
        return abs(value)
    except TypeError:
        return value


@register.filter
def percent_of(value, target):
    try:
        value, target = float(value or 0), float(target or 0)
    except (TypeError, ValueError):
        return 0
    if not target:
        return 0
    return max(0, min(100, round(value / target * 100)))


@register.filter
def over(value, target):
    try:
        return float(value or 0) > float(target or 0)
    except (TypeError, ValueError):
        return False


@register.filter
def initials(user):
    name = (user.get_full_name() or user.get_username() or "?").strip()
    parts = name.split()
    letters = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")) if parts else "?"
    return letters.upper()


@register.filter
def add_class(field, css):
    return field.as_widget(attrs={"class": css})


@register.filter
def minutes(value):
    """95 → '1 h 35 min'."""
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return value
    h, m = divmod(value, 60)
    if h and m:
        return f"{h} h {m} min"
    if h:
        return f"{h} h"
    return f"{m} min"


@register.filter
def num(value, places=0):
    """Thousands separators with fixed decimals (Indian grouping not needed for these ranges)."""
    if value is None or value == "":
        return "–"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    places = int(places)
    return f"{number:,.{places}f}"


@register.filter
def smart(value):
    """72.5 -> '72.5', 3.0 -> '3', 12000 -> '12,000'."""
    if value is None or value == "":
        return "–"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.1f}"
