from django.urls import path

from . import views

app_name = "passages"

urlpatterns = [
    path("<slug:exam_code>/passages/", views.simulator_passage_list, name="simulator-list"),
    path("<slug:exam_code>/passages/<str:passage_id>/", views.simulator_passage_detail, name="simulator-detail"),
    path("<slug:exam_code>/passages/<str:passage_id>/pdf/", views.simulator_passage_pdf, name="simulator-pdf"),
]
