from django.urls import path

from . import views

app_name = "institutes"

urlpatterns = [
    path("register/", views.institute_registration_page, name="register"),
    path("dashboard/super-admin/", views.super_admin_dashboard, name="super_admin_dashboard"),
    path(
        "dashboard/super-admin/institutes/<uuid:pk>/<str:action>/",
        views.review_institute,
        name="review_institute",
    ),
]
