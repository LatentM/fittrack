from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Momentum administration"
admin.site.site_title = "Momentum admin"
admin.site.index_title = "Manage users and fitness data"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("tracker.urls")),
]

handler404 = "tracker.views.error_404"
handler500 = "tracker.views.error_500"
