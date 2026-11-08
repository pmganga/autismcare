from django.urls import path

from . import views

urlpatterns = [
    path("screening/", views.intro, name="screening"),
    path("screening/questions/", views.questionnaire, name="screening-questions"),
    path("screening/result/<uuid:pk>/", views.result, name="screening-result"),
]
