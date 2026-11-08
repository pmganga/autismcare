"""Screening module tests: FR 1.1, FR 2.1, NFR 4, NFR 7."""
import time

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .content import DISCLAIMER
from .models import Answer, Question, RiskResult, RiskTier, ScreeningSession
from .scoring import ScoredItem, calculate_risk, tier_for

REVERSE = {2, 5, 12}


def answers_with_risks(questions, n_risks):
    """Answer every question, with exactly n_risks risk answers."""
    out = {}
    for i, q in enumerate(questions):
        risky = i < n_risks
        out[q.id] = q.is_reverse_scored if risky else not q.is_reverse_scored
    return out


class ScoringTests(TestCase):
    def test_tier_boundaries(self):
        self.assertEqual(tier_for(0), RiskTier.LOW)
        self.assertEqual(tier_for(2), RiskTier.LOW)
        self.assertEqual(tier_for(3), RiskTier.MEDIUM)
        self.assertEqual(tier_for(7), RiskTier.MEDIUM)
        self.assertEqual(tier_for(8), RiskTier.HIGH)
        self.assertEqual(tier_for(20), RiskTier.HIGH)

    def test_normal_items_no_is_risk(self):
        self.assertEqual(calculate_risk([ScoredItem(True)] * 20), (0, RiskTier.LOW))
        self.assertEqual(calculate_risk([ScoredItem(False)] * 20), (20, RiskTier.HIGH))

    def test_reverse_items_yes_is_risk(self):
        items = [ScoredItem(True, is_reverse_scored=True)] * 3 + [ScoredItem(True)] * 17
        self.assertEqual(calculate_risk(items), (3, RiskTier.MEDIUM))
        items = [ScoredItem(False, is_reverse_scored=True)] * 3 + [ScoredItem(True)] * 17
        self.assertEqual(calculate_risk(items), (0, RiskTier.LOW))

    def test_weights(self):
        self.assertEqual(calculate_risk([ScoredItem(False, weight=4)] * 2), (8, RiskTier.HIGH))


class SeedQuestionsTests(TestCase):
    def test_loads_20_with_reverse_items(self):
        call_command("seed_questions", verbosity=0)
        self.assertEqual(Question.objects.filter(is_active=True).count(), 20)
        self.assertEqual(
            set(Question.objects.filter(is_reverse_scored=True).values_list("number", flat=True)), REVERSE
        )
        call_command("seed_questions", verbosity=0)  # safe to run twice
        self.assertEqual(Question.objects.count(), 20)


class ApiTests(TestCase):
    def setUp(self):
        call_command("seed_questions", verbosity=0)
        self.questions = list(Question.objects.order_by("number"))
        self.api = APIClient()

    def submit(self, answers, age=20):
        return self.api.post(reverse("api-screening-create"), {
            "child_age_months": age,
            "answers": [{"question": k, "value": v} for k, v in answers.items()],
        }, format="json")

    def test_questionnaire_includes_disclaimer(self):
        r = self.api.get(reverse("api-questionnaire"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["questions"]), 20)
        self.assertEqual(r.data["disclaimer"], DISCLAIMER)

    def test_tiers_end_to_end(self):
        for n, tier in [(0, "LOW"), (2, "LOW"), (3, "MEDIUM"), (7, "MEDIUM"), (8, "HIGH"), (20, "HIGH")]:
            r = self.submit(answers_with_risks(self.questions, n))
            self.assertEqual(r.status_code, 201, r.data)
            self.assertEqual((r.data["score"], r.data["tier"]), (n, tier))
            self.assertEqual(r.data["disclaimer"], DISCLAIMER)

    def test_saves_answers_and_result(self):
        r = self.submit(answers_with_risks(self.questions, 5))
        s = ScreeningSession.objects.get(pk=r.data["session_id"])
        self.assertEqual(s.answers.count(), 20)
        self.assertEqual(s.result.score, 5)

    def test_within_1_5_seconds(self):
        start = time.perf_counter()
        r = self.submit(answers_with_risks(self.questions, 8))
        self.assertEqual(r.status_code, 201)
        self.assertLess(time.perf_counter() - start, 1.5)

    def test_missing_answers_rejected(self):
        answers = answers_with_risks(self.questions, 0)
        answers.pop(self.questions[4].id)
        r = self.submit(answers)
        self.assertEqual(r.status_code, 400)
        self.assertIn("5", str(r.data["answers"]))
        self.assertEqual(ScreeningSession.objects.count(), 0)

    def test_unknown_question_rejected(self):
        answers = answers_with_risks(self.questions, 0)
        answers[99999] = True
        self.assertEqual(self.submit(answers).status_code, 400)

    def test_age_range(self):
        for bad in (15, 31):
            r = self.submit(answers_with_risks(self.questions, 0), age=bad)
            self.assertEqual(r.status_code, 400)
            self.assertIn("16 to 30 months", str(r.data["child_age_months"]))
        for ok in (16, 30):
            self.assertEqual(self.submit(answers_with_risks(self.questions, 0), age=ok).status_code, 201)

    def test_result_needs_token(self):
        r = self.submit(answers_with_risks(self.questions, 3))
        url = reverse("api-screening-result", args=[r.data["session_id"]])
        self.assertEqual(self.api.get(url).status_code, 404)
        self.assertEqual(self.api.get(url, {"token": "wrong"}).status_code, 404)
        ok = self.api.get(url, {"token": r.data["token"]})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["tier"], "MEDIUM")

    def test_token_not_stored_in_plain_text(self):
        r = self.submit(answers_with_risks(self.questions, 0))
        s = ScreeningSession.objects.get(pk=r.data["session_id"])
        self.assertNotEqual(s.anonymous_token_hash, r.data["token"])


class PrivacyTests(TestCase):
    """NFR 4: no personally identifiable information is stored."""

    PII_WORDS = ("name", "email", "phone", "ip", "address", "user", "location", "lat", "lng")

    def test_models_have_no_pii_fields(self):
        for model in (ScreeningSession, Answer, RiskResult):
            for f in model._meta.get_fields():
                for word in self.PII_WORDS:
                    self.assertNotIn(word, f.name.lower().split("_"), f"{model.__name__}.{f.name}")

    def test_no_login_needed(self):
        call_command("seed_questions", verbosity=0)
        self.assertEqual(self.client.get(reverse("screening-questions")).status_code, 200)


class PageTests(TestCase):
    def setUp(self):
        call_command("seed_questions", verbosity=0)
        self.questions = list(Question.objects.order_by("number"))

    def post_form(self, answers, age="20"):
        data = {"child_age_months": age}
        for q in self.questions:
            if q.id in answers:
                data[f"q{q.id}"] = "yes" if answers[q.id] else "no"
        return self.client.post(reverse("screening-questions"), data)

    def test_disclaimer_on_every_screening_page(self):
        r = self.post_form(answers_with_risks(self.questions, 8))
        result_url = r["Location"]
        for url in (reverse("screening"), reverse("screening-questions"), result_url):
            self.assertContains(self.client.get(url), DISCLAIMER, msg_prefix=url)
        # and on a page re-shown with errors
        self.assertContains(self.post_form({}), DISCLAIMER)

    def test_form_flow_high_result_links_to_directory(self):
        r = self.post_form(answers_with_risks(self.questions, 9))
        self.assertEqual(r.status_code, 302)
        page = self.client.get(r["Location"])
        self.assertContains(page, "High likelihood")
        self.assertContains(page, reverse("find"))

    def test_low_result(self):
        r = self.post_form(answers_with_risks(self.questions, 1))
        self.assertContains(self.client.get(r["Location"]), "Low likelihood")

    def test_missing_answers_keep_given_answers(self):
        answers = answers_with_risks(self.questions, 0)
        del answers[self.questions[-1].id]
        r = self.post_form(answers)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Still to answer: 20")
        self.assertContains(r, "checked", count=19)

    def test_out_of_range_age_links_to_directory(self):
        r = self.post_form(answers_with_risks(self.questions, 0), age="40")
        self.assertContains(r, "16 to 30 months")
        self.assertContains(r, reverse("find"))

    def test_result_only_visible_to_submitting_browser(self):
        r = self.post_form(answers_with_risks(self.questions, 0))
        url = r["Location"]
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(url).status_code, 404)
