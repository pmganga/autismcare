"""Week 7 tests: FR 2.2 report, rescreen reminder, and the screening -> referral flow
(sequence diagram, Appendix B.3)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from directory.models import Clinic, LicenseVerification, Therapist

from .content import DISCLAIMER
from .models import GuidanceReport, Question, RiskTier, ScreeningSession
from .report import build_pdf
from .rescreen import add_months, rescreen_advice
from .tests import answers_with_risks


class RescreenTests(TestCase):
    def test_add_months_clamps_day(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 15), 3), date(2027, 2, 15))

    def test_rules(self):
        d = date(2026, 11, 15)
        self.assertEqual(rescreen_advice(18, RiskTier.LOW, d).due, date(2027, 5, 15))  # at 24 months
        self.assertIsNone(rescreen_advice(26, RiskTier.LOW, d).due)
        self.assertTrue(rescreen_advice(26, RiskTier.LOW, d).text)
        self.assertEqual(rescreen_advice(20, RiskTier.MEDIUM, d).due, date(2026, 12, 15))
        high = rescreen_advice(20, RiskTier.HIGH, d)
        self.assertIsNone(high.due)
        self.assertEqual(high.text, "")


class Week7Base(TestCase):
    def setUp(self):
        call_command("seed_questions", verbosity=0)
        self.questions = list(Question.objects.order_by("number"))

    def submit_form(self, n_risks, age="20"):
        data = {"child_age_months": age}
        for q_id, v in answers_with_risks(self.questions, n_risks).items():
            data[f"q{q_id}"] = "yes" if v else "no"
        r = self.client.post(reverse("screening-questions"), data)
        self.assertEqual(r.status_code, 302)
        return r["Location"], ScreeningSession.objects.latest("created_at")


class ReportTests(Week7Base):
    def test_pdf_contents(self):
        _, session = self.submit_form(9)
        pdf, report = build_pdf(session, directory_url="http://x/find/", compress=False)
        self.assertTrue(pdf.startswith(b"%PDF"))
        for text in (b"High likelihood", b"score 9 of 20", b"Indicators", b"signs \\(9\\)",
                     b"Suggested next steps", b"http://x/find/", b"does not constitute a certified medical"):
            self.assertIn(text, pdf, text)
        self.assertEqual(report.result, session.result)
        self.assertIn("assessment", report.next_steps)

    def test_low_pdf_has_rescreen_and_no_directory_link(self):
        _, session = self.submit_form(0, age="18")
        pdf, _ = build_pdf(session, directory_url="http://x/find/", compress=False)
        self.assertIn(b"None of the answers showed early signs", pdf)
        self.assertIn(b"When to screen again", pdf)
        self.assertNotIn(b"http://x/find/", pdf)

    def test_download_from_result_page(self):
        url, session = self.submit_form(4)
        r = self.client.get(reverse("screening-report", args=[session.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.client.get(reverse("screening-report", args=[session.pk]))
        report = GuidanceReport.objects.get(result=session.result)
        self.assertEqual(report.download_count, 2)
        self.assertEqual(GuidanceReport.objects.count(), 1)

    def test_report_private_to_submitting_browser(self):
        _, session = self.submit_form(4)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(reverse("screening-report", args=[session.pk])).status_code, 404)

    def test_api_report_needs_token(self):
        api = APIClient()
        r = api.post(reverse("api-screening-create"), {
            "child_age_months": 20,
            "answers": [{"question": k, "value": v} for k, v in answers_with_risks(self.questions, 8).items()],
        }, format="json")
        url = reverse("api-screening-report", args=[r.data["session_id"]])
        self.assertEqual(api.get(url).status_code, 404)
        ok = api.get(url, {"token": r.data["token"]})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok["Content-Type"], "application/pdf")
        self.assertTrue(r.data["refer_to_directory"])


class ResultPageTests(Week7Base):
    def test_high_shows_referral_search(self):
        url, _ = self.submit_form(10)
        page = self.client.get(url)
        self.assertContains(page, 'data-testid="referral"')
        self.assertContains(page, 'id="search-form"')
        self.assertContains(page, "js/find.js")
        self.assertNotContains(page, 'data-testid="rescreen"')
        self.assertContains(page, 'data-testid="report-link"')

    def test_medium_shows_guidance_and_rescreen_not_referral(self):
        url, session = self.submit_form(5)
        page = self.client.get(url)
        self.assertNotContains(page, 'data-testid="referral"')
        self.assertNotContains(page, "js/find.js")
        self.assertContains(page, 'data-testid="rescreen"')
        self.assertContains(page, reverse("screening-reminder", args=[session.pk]))

    def test_low_older_child_has_no_calendar_reminder(self):
        url, session = self.submit_form(0, age="28")
        page = self.client.get(url)
        self.assertContains(page, "No routine rescreen")
        self.assertNotContains(page, reverse("screening-reminder", args=[session.pk]))
        self.assertEqual(self.client.get(reverse("screening-reminder", args=[session.pk])).status_code, 404)

    def test_reminder_ics(self):
        _, session = self.submit_form(0, age="18")
        r = self.client.get(reverse("screening-reminder", args=[session.pk]))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("SUMMARY:AutismCare: time to screen again", body)
        self.assertIn("DTSTART;VALUE=DATE:", body)

    def test_disclaimer_still_on_result_page(self):
        url, _ = self.submit_form(10)
        self.assertContains(self.client.get(url), DISCLAIMER)

    def test_find_page_still_works_after_refactor(self):
        page = self.client.get(reverse("find"))
        self.assertContains(page, 'id="search-form"')
        self.assertContains(page, "js/find.js")


class EndToEndReferralTests(Week7Base):
    """Sequence diagram B.3, steps 1-30: questionnaire -> HIGH -> report -> nearby verified therapists."""

    def test_full_flow(self):
        user = get_user_model().objects.create_user(email="t@x.com", password="CorrectHorse-42!")
        t = Therapist.objects.create(user=user, full_name="Verified Near", phone="0700")
        clinic = Clinic.objects.create(name="Near clinic", address="Nairobi", latitude=-1.29,
                                       longitude=36.82, operating_hours="Mon-Fri")
        t.clinics.add(clinic)
        LicenseVerification.objects.create(therapist=t, license_number="L", document="licenses/x.pdf",
                                           status="APPROVED")

        # Steps 1-6: open screening, questionnaire with disclaimer
        self.assertContains(self.client.get(reverse("screening-questions")), DISCLAIMER)
        # Steps 7-14: submit anonymously, risk tier shown
        url, session = self.submit_form(12)
        self.assertEqual(session.result.tier, "HIGH")
        page = self.client.get(url)
        self.assertContains(page, "High likelihood")
        # Steps 15-20 (opt): download the report
        self.assertEqual(self.client.get(reverse("screening-report", args=[session.pk]))["Content-Type"],
                         "application/pdf")
        # Steps 21-30 (alt tier == HIGH): prompt, then location + radius search
        self.assertContains(page, "Find a therapist near you")
        r = APIClient().get(reverse("api-search"), {"lat": -1.2864, "lng": 36.8172, "radius": 10})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["full_name"] for x in r.data["results"]], ["Verified Near"])
