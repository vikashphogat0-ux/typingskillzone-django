from django.urls import path

from . import views

app_name = "typing_sessions"

urlpatterns = [
    path("simulators/<slug:exam_code>/start/", views.start_selected_typing_session, name="start_selected"),
    path("simulators/<slug:exam_code>/passages/<str:passage_id>/start/", views.start_typing_session, name="start"),
    path("<uuid:session_id>/", views.typing_session, name="session"),
    path("<uuid:session_id>/activate/", views.activate_typing_session, name="activate"),
    path("<uuid:session_id>/cancel/", views.cancel_typing_session, name="cancel"),
    path("<uuid:session_id>/submit/", views.submit_typing_session, name="submit"),
    path("<uuid:session_id>/draft/", views.save_typing_draft, name="draft"),
]
