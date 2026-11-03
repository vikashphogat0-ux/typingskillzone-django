from django.urls import path

from . import views

app_name = "institutes"

urlpatterns = [
    path("register/", views.institute_register, name="register"),
    path("owner/login/", views.owner_login, name="owner_login"),
    path("owner/dashboard/", views.owner_dashboard, name="owner_dashboard"),
    path("owner/logout/", views.owner_logout, name="owner_logout"),
    path("dashboard/super-admin/", views.super_admin_dashboard, name="super_admin_dashboard"),
    path("dashboard/super-admin/institutes/", views.institute_list, name="institute_list"),
    path("dashboard/super-admin/institutes/<uuid:pk>/", views.institute_detail, name="institute_detail"),
    path("dashboard/super-admin/institutes/<uuid:pk>/edit/", views.institute_edit, name="institute_edit"),
    path(
        "dashboard/super-admin/institutes/<uuid:pk>/<str:action>/",
        views.review_institute,
        name="review_institute",
    ),
]
