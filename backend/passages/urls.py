from django.views.generic import RedirectView
from django.urls import path

from . import views

app_name = "passages"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="exams:catalogue", permanent=False), name="simulator-catalogue"),
    path("<slug:exam_code>/passages/", views.simulator_passage_list, name="simulator-list"),
    path("<slug:exam_code>/passages/<str:passage_id>/", views.simulator_passage_detail, name="simulator-detail"),
    path("<slug:exam_code>/passages/<str:passage_id>/pdf/", views.simulator_passage_pdf, name="simulator-pdf"),
]
