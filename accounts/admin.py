from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    readonly_fields = ("created_at", "updated_at")


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "email", "first_name", "is_active", "is_staff", "date_joined", "last_login")
    list_filter = ("is_active", "is_staff", "date_joined")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "sex", "height_cm", "activity_level", "objective", "onboarded", "created_at")
    list_filter = ("sex", "activity_level", "objective", "onboarded")
    search_fields = ("user__username", "user__email")
