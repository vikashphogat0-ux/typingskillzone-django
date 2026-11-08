
from django.urls import path
from django.contrib.auth import views as auth_views

from .password_reset import ThrottledPasswordResetView
from . import views


app_name = "accounts"

urlpatterns = [
    path(
        "password-reset/",
        ThrottledPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/accounts/password-reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("student/register/", views.student_register, name="student_register"),
    path(
        "student/verify/resend/",
        views.resend_student_verification,
        name="resend_verification",
    ),
    path(
        "student/verify/<str:token>/",
        views.verify_student_email,
        name="verify_email",
    ),
    path("student/profile/", views.student_profile, name="student_profile"),
    path("student/enroll/", views.enroll_institute, name="enroll_institute"),
    path("dashboard/", views.student_dashboard, name="student_dashboard"),
    path(
        "result-history/",
        views.student_result_history,
        name="student_result_history",
    ),
    path("passage-library/", views.passage_library, name="passage_library"),
]
