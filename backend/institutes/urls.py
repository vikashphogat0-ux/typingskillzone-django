
from django.urls import path

from . import views

app_name = "institutes"

urlpatterns = [
    path(
        "register/",
        views.institute_register,
        name="register",
    ),
]
