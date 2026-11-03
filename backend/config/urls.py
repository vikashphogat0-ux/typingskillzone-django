from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("institutes/", include("institutes.urls")),\n    path("accounts/", include("accounts.urls")),
]
