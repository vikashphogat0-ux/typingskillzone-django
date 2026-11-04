from django.urls import path

from . import views, owner_verification

app_name = "institutes"

urlpatterns = [
    path("register/", views.institute_register, name="register"),
    path("owner/login/", views.owner_login, name="owner_login"),
    path("owner/verify/<str:token>/", owner_verification.verify_owner_email, name="verify_owner_email"),
    path("owner/verify/resend/", owner_verification.resend_owner_verification, name="resend_owner_verification"),
    path("student/login/", views.member_login, {"portal": "student"}, name="student_login"),
    path("student/dashboard/", views.member_dashboard, {"portal": "student"}, name="student_dashboard"),
    path("student/logout/", views.member_logout, {"portal": "student"}, name="student_logout"),
    path("staff/login/", views.member_login, {"portal": "staff"}, name="staff_login"),
    path("staff/dashboard/", views.member_dashboard, {"portal": "staff"}, name="staff_dashboard"),
    path("staff/logout/", views.member_logout, {"portal": "staff"}, name="staff_logout"),
    path("owner/dashboard/", views.owner_dashboard, name="owner_dashboard"),
    path("owner/logout/", views.owner_logout, name="owner_logout"),
    path("owner/institutes/<uuid:institute_id>/members/", views.owner_member_list, name="owner_member_list"),
    path("owner/institutes/<uuid:institute_id>/members/add/", views.owner_member_add, name="owner_member_add"),
    path("owner/institutes/<uuid:institute_id>/members/<int:membership_id>/<str:action>/", views.owner_member_status, name="owner_member_status"),
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
