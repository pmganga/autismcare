from django.contrib import admin
from django.urls import include, path

from .monitoring import performance

urlpatterns = [
    path("admin/performance/", performance, name="admin-performance"),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.api_urls")),
    path("api/", include("directory.api_urls")),
    path("api/", include("screening.api_urls")),
    path("", include("accounts.urls")),
    path("", include("directory.urls")),
    path("", include("screening.urls")),
    path("", include("learning.urls")),
]

admin.site.site_header = "AutismCare administration"
admin.site.site_title = "AutismCare admin"
