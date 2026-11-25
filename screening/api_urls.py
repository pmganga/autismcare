from django.urls import path

from . import api_views as v

urlpatterns = [
    path("screening/questionnaire/", v.QuestionnaireView.as_view(), name="api-questionnaire"),
    path("screenings/", v.ScreeningCreateView.as_view(), name="api-screening-create"),
    path("screenings/<uuid:pk>/", v.ScreeningResultView.as_view(), name="api-screening-result"),
    path("screenings/<uuid:pk>/report/", v.ScreeningReportView.as_view(), name="api-screening-report"),
]
