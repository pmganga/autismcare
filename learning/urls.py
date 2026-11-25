from django.urls import path

from . import api_views, views

urlpatterns = [
    path("teach/register/", views.teacher_register, name="teacher-register"),
    path("teach/", views.classroom, name="teach"),
    path("teach/learners/<uuid:pk>/remove/", views.learner_remove, name="teach-learner-remove"),
    path("teach/learners/<uuid:pk>/start/", views.session_setup, name="teach-start"),
    path("teach/sessions/<uuid:pk>/play/", views.play, name="teach-play"),
    path("teach/sessions/<uuid:pk>/summary/", views.summary, name="teach-summary"),
    path("api/learning/sessions/<uuid:pk>/next/", api_views.NextCardView.as_view(), name="api-learning-next"),
    path("api/learning/sessions/<uuid:pk>/answer/", api_views.AnswerView.as_view(), name="api-learning-answer"),
    path("api/learning/sessions/<uuid:pk>/end/", api_views.EndSessionView.as_view(), name="api-learning-end"),
]
