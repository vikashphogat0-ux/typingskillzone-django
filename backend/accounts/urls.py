from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("student/register/", views.student_register, name="student_register"),
    path("student/verify/resend/", views.resend_student_verification, name="resend_verification"),
    path("student/verify/<str:token>/", views.verify_student_email, name="verify_email"),
    path("student/profile/", views.student_profile, name="student_profile"),
    path("student/enroll/", views.enroll_institute, name="enroll_institute"),
]
