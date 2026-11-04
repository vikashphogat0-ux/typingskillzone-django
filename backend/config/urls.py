from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("institutes/", include("institutes.urls")),
    path("accounts/", include("accounts.urls")),
    path("simulators/", include("passages.urls")),
]
