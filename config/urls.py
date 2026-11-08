from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.api_urls")),
    path("api/", include("directory.api_urls")),
    path("", include("accounts.urls")),
    path("", include("directory.urls")),
]

admin.site.site_header = "AutismCare administration"
admin.site.site_title = "AutismCare admin"
