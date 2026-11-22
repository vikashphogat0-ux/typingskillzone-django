from django.contrib import admin
from django.urls import include, path

from passages import views as passage_views

urlpatterns = [
    path("", passage_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("institutes/", include("institutes.urls")),
    path("accounts/", include("accounts.urls")),
    path("simulators/", include("passages.urls")),
    path("typing/", include("typing_sessions.urls")),
]
