from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    path("", views.catalogue, name="catalogue"),
    path("<slug:code>/", views.exam_detail, name="exam_detail"),
]
