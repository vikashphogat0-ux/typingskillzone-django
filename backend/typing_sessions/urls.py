from django.urls import path

from . import views

app_name = "typing_sessions"

urlpatterns = [
    path("reports/delhi-police-hcm/", views.delhi_police_hcm_dashboard, name="dphcm_dashboard"),
    path("simulators/<slug:exam_code>/passages/<str:passage_id>/start/", views.start_typing_session, name="start"),
    path("<uuid:session_id>/", views.typing_session, name="session"),
    path("<uuid:session_id>/submit/", views.submit_typing_session, name="submit"),
]
