from django.urls import path

from . import views

urlpatterns = [
    path("screening/", views.intro, name="screening"),
    path("screening/questions/", views.questionnaire, name="screening-questions"),
    path("screening/result/<uuid:pk>/", views.result, name="screening-result"),
    path("screening/result/<uuid:pk>/report.pdf", views.report_pdf, name="screening-report"),
    path("screening/result/<uuid:pk>/reminder.ics", views.reminder_ics, name="screening-reminder"),
]
