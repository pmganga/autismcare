"""AI teaching assistant tests: FR 4.1, FR 4.2, activity diagram B.4, privacy, permissions, AI fallback."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from . import ai
from .engine import CHOICES_PER_LEVEL, evaluate
from .models import Attempt, Flashcard, Learner, LearningSession, TeacherProfile
from .services import answer, next_card, start_session

PW = "CorrectHorse-42!"


def make_teacher(email="t@school.test"):
    User = get_user_model()
    user = User.objects.create_user(email=email, password=PW, role=User.Role.TEACHER)
    return TeacherProfile.objects.create(user=user, full_name="Ms Teacher", school_name="Hope School")


class EngineTests(TestCase):
    def test_rules_from_activity_diagram(self):
        self.assertEqual(evaluate([True, True, True], 2), 3)      # 3 of 3 -> up
        self.assertEqual(evaluate([True, True, False], 2), 2)     # 2 of 3 -> keep
        self.assertEqual(evaluate([True, False, False], 2), 1)    # 1 of 3 -> down
        self.assertEqual(evaluate([False, False, False], 2), 1)   # 0 of 3 -> down

    def test_level_bounds(self):
        self.assertEqual(evaluate([True] * 3, 5), 5)
        self.assertEqual(evaluate([False] * 3, 1), 1)

    def test_needs_three(self):
        with self.assertRaises(ValueError):
            evaluate([True, True], 2)


class CardBankTests(TestCase):
    def test_builtin_bank_loaded_by_migration(self):
        self.assertEqual(Flashcard.objects.filter(source="BUILTIN").count(), 60)
        for level in range(1, 6):
            self.assertEqual(Flashcard.objects.filter(difficulty=level).count(), 12)


@override_settings(AI_FLASHCARDS_ENABLED=False)
class SessionFlowTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.learner = Learner.objects.create(teacher=self.teacher, nickname="Amani", current_level=2)

    def start(self, n=9):
        return start_session(self.teacher, self.learner, audio_enabled=True, sensory_mode="soft", planned_cards=n)

    def play(self, session, pattern):
        """Answer one card per item in pattern (True = right answer)."""
        results = []
        for ok in pattern:
            card = next_card(session)
            session.refresh_from_db()
            right = session.current_card.label
            wrong = next(c for c in card["choices"] if c != right)
            results.append(answer(session, right if ok else wrong, 1200))
        return results

    def test_card_shape_and_choice_count(self):
        session = self.start()
        card = next_card(session)
        self.assertEqual(card["level"], 2)
        self.assertEqual(len(card["choices"]), CHOICES_PER_LEVEL[2])
        self.assertEqual(len(set(card["choices"])), len(card["choices"]))
        self.assertTrue(card["symbol"])
        session.refresh_from_db()
        self.assertIn(session.current_card.label, card["choices"])

    def test_same_card_until_answered(self):
        session = self.start()
        first = next_card(session)
        self.assertEqual(next_card(session), first)

    def test_level_goes_up_after_three_correct(self):
        session = self.start()
        results = self.play(session, [True, True, True])
        self.assertEqual([r["level_change"] for r in results], ["same", "same", "up"])
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.current_level, 3)
        self.assertEqual(len(next_card(session)["choices"]), CHOICES_PER_LEVEL[3])

    def test_level_goes_down_after_one_or_fewer(self):
        session = self.start()
        results = self.play(session, [True, False, False])
        self.assertEqual(results[-1]["level"], 1)
        self.assertEqual(results[-1]["level_change"], "down")

    def test_level_kept_after_two_of_three(self):
        session = self.start()
        self.assertEqual(self.play(session, [True, False, True])[-1]["level_change"], "same")

    def test_check_happens_every_three_not_every_answer(self):
        session = self.start()
        results = self.play(session, [True, True, True, True, True])
        self.assertEqual([r["level"] for r in results], [2, 2, 3, 3, 3])

    def test_session_ends_after_planned_cards_with_summary(self):
        session = self.start(n=6)
        results = self.play(session, [True, True, True, False, True, False])
        self.assertTrue(results[-1]["done"])
        session.refresh_from_db()
        self.assertTrue(session.is_finished)
        self.assertEqual((session.total_attempts, session.correct_count), (6, 4))
        self.assertEqual(session.start_level, 2)
        self.assertEqual(session.end_level, 2)  # up to 3 after ✓✓✓, back to 2 after ✗✓✗
        self.assertEqual(session.accuracy_percent, 67)
        self.assertIsNone(next_card(session))
        self.assertEqual(Attempt.objects.filter(session=session).count(), 6)

    def test_no_repeat_cards_within_level_pool(self):
        session = self.start(n=12)
        self.play(session, [True, False, True] * 3)  # stays on level 2: 9 cards from 12
        labels = list(session.attempts.values_list("flashcard__label", flat=True))
        self.assertEqual(len(labels), len(set(labels)))

    def test_answer_must_be_a_choice(self):
        from .services import SessionError
        session = self.start()
        next_card(session)
        with self.assertRaises(SessionError):
            answer(session, "not-a-choice")

    def test_response_time_recorded(self):
        session = self.start()
        self.play(session, [True])
        self.assertEqual(session.attempts.get().response_time_ms, 1200)


@override_settings(AI_FLASHCARDS_BACKGROUND=False)
class AIFallbackTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.learner = Learner.objects.create(teacher=self.teacher, nickname="Baraka", current_level=3)

    def start(self):
        return start_session(self.teacher, self.learner, audio_enabled=False, sensory_mode="dim", planned_cards=6)

    @override_settings(AI_FLASHCARDS_ENABLED=True)
    @patch("learning.ai.is_configured", return_value=True)
    @patch("learning.ai.generate_cards", side_effect=ai.AIUnavailable("timeout"))
    def test_timeout_falls_back_to_builtin(self, _gen, _cfg):
        session = self.start()
        self.assertEqual(session.ai_status, "unavailable")
        self.assertIsNotNone(next_card(session))  # session still works

    @patch("learning.ai.is_configured", return_value=True)
    @patch("learning.ai.generate_cards", return_value=[
        {"label": "drum", "emoji": "🥁", "category": "home"},
        {"label": "kite", "emoji": "🪁", "category": "home"},
    ])
    def test_ai_cards_saved_at_session_level(self, _gen, _cfg):
        session = self.start()
        self.assertEqual((session.ai_status, session.ai_cards_added), ("used", 2))
        drum = Flashcard.objects.get(label="drum")
        self.assertEqual((drum.difficulty, drum.source, drum.symbol), (3, "AI", "🥁"))

    def test_not_configured_means_off(self):
        with patch("learning.ai.is_configured", return_value=False):
            self.assertEqual(self.start().ai_status, "off")

    @override_settings(OLLAMA_URL="")
    def test_no_ollama_url_means_off(self):
        self.assertFalse(ai.is_configured())
        self.assertEqual(self.start().ai_status, "off")

    @override_settings(AI_FLASHCARDS_BACKGROUND=True)
    @patch("learning.ai.is_configured", return_value=True)
    @patch("learning.services.threading.Thread")
    def test_background_start_does_not_wait(self, thread_cls, _cfg):
        session = self.start()
        self.assertEqual(session.ai_status, "pending")          # session returned before the model ran
        thread_cls.return_value.start.assert_called_once()
        self.assertIsNotNone(next_card(session))                 # learner can begin straight away
        from .services import _ai_busy
        _ai_busy.release()  # the patched thread never ran, so release its lock


@override_settings(AI_FLASHCARDS_ENABLED=True, OLLAMA_URL="http://ollama.test:11434", AI_FLASHCARDS_MODEL="qwen3.5:2b")
class GenerateCardsTests(TestCase):
    """Runs the real generate_cards() against a simulated Ollama reply (no model, no network)."""

    def fake_reply(self, content=None, status=200):
        from unittest.mock import MagicMock
        content = content if content is not None else json.dumps({"cards": [
            {"label": "drum", "emoji": "🥁", "category": "home"},
            {"label": "knife", "emoji": "🔪", "category": "home"},
            {"label": "water", "emoji": "💧", "category": "nature"},
            {"label": "kite", "emoji": "🪁", "category": "home"},
        ]})
        reply = MagicMock(status_code=status)
        reply.json.return_value = {"message": {"role": "assistant", "content": content}}
        return reply

    @patch("learning.ai.requests.post")
    def test_parses_and_filters(self, post):
        post.return_value = self.fake_reply()
        cards = ai.generate_cards(level=2, count=4, avoid={"ball"})
        self.assertEqual([c["label"] for c in cards], ["drum", "kite"])  # knife unsafe, water ≠ 💧 DROPLET
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        self.assertEqual(url, "http://ollama.test:11434/api/chat")
        self.assertEqual(kwargs["json"]["model"], "qwen3.5:2b")
        self.assertEqual(kwargs["json"]["format"]["required"], ["cards"])  # structured output schema
        self.assertFalse(kwargs["json"]["stream"])
        self.assertEqual(kwargs["timeout"], 120)

    @patch("learning.ai.requests.post")
    def test_ollama_not_running_raises_unavailable(self, post):
        import requests
        post.side_effect = requests.ConnectionError("refused")
        with self.assertRaises(ai.AIUnavailable):
            ai.generate_cards(level=2, count=4)

    @patch("learning.ai.requests.post")
    def test_timeout_raises_unavailable(self, post):
        import requests
        post.side_effect = requests.Timeout()
        with self.assertRaises(ai.AIUnavailable):
            ai.generate_cards(level=2, count=4)

    @patch("learning.ai.requests.post")
    def test_bad_json_raises_unavailable(self, post):
        post.return_value = self.fake_reply(content="not json")
        with self.assertRaises(ai.AIUnavailable):
            ai.generate_cards(level=2, count=4)

    @patch("learning.ai.requests.post")
    def test_add_new_cards_asks_again_after_unusable_reply(self, post):
        repeats = json.dumps({"cards": [{"label": "cat", "emoji": "🐈", "category": "animals"}]})  # in the bank
        post.side_effect = [self.fake_reply(content=repeats), self.fake_reply()]
        saved = ai.add_new_cards(level=4, count=2)
        self.assertEqual([c["label"] for c in saved], ["drum", "kite"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(Flashcard.objects.get(label="kite").difficulty, 4)

    @patch("learning.ai.requests.post")
    def test_add_new_cards_stops_when_ollama_down(self, post):
        import requests
        post.side_effect = requests.ConnectionError("refused")
        with self.assertRaises(ai.AIUnavailable):
            ai.add_new_cards(level=2, count=4)
        self.assertEqual(post.call_count, 1)  # no pointless retries

    @patch("learning.ai.requests.post")
    def test_only_bad_cards_raises_unavailable(self, post):
        post.return_value = self.fake_reply(content=json.dumps({"cards": [
            {"label": "Card 1", "emoji": "🚌", "category": "transport"}]}))
        with self.assertRaises(ai.AIUnavailable):
            ai.generate_cards(level=2, count=4)


class ValidationTests(TestCase):
    def test_rejects_bad_ai_cards(self):
        raw = [
            {"label": "drum", "emoji": "🥁", "category": "home"},          # ok
            {"label": "Drum Kit Set Extra", "emoji": "🥁", "category": "home"},  # too many words / capitals
            {"label": "knife", "emoji": "🔪", "category": "home"},         # not child-safe
            {"label": "kite", "emoji": "kite", "category": "home"},       # not an emoji
            {"label": "ball", "emoji": "⚽", "category": "home"},          # already exists
            {"label": "yak", "emoji": "🐃", "category": "pets"},           # unknown category
            {"label": "cat", "emoji": "🚌", "category": "animals"},        # picture doesn't match word
            {"label": "Card 2", "emoji": "🚌", "category": "transport"},   # not an object name
        ]
        self.assertEqual([c["label"] for c in ai.validate_cards(raw, avoid={"ball"})], ["drum"])

    def test_picture_matches_unicode_name(self):
        self.assertTrue(ai.picture_matches("bus", "🚌"))
        self.assertTrue(ai.picture_matches("shoe", "👟"))       # ATHLETIC SHOE
        self.assertTrue(ai.picture_matches("sun", "☀️"))        # variation selector ignored
        self.assertFalse(ai.picture_matches("water", "💧"))     # DROPLET
        self.assertFalse(ai.picture_matches("dog", "🐈"))


@override_settings(AI_FLASHCARDS_ENABLED=False)
class PageAndPermissionTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.other = make_teacher("other@school.test")
        self.learner = Learner.objects.create(teacher=self.teacher, nickname="Amani")

    def test_teacher_register_and_redirect(self):
        r = self.client.post(reverse("teacher-register"), {
            "full_name": "New Teacher", "school_name": "Sunrise", "email": "new@school.test",
            "password": PW, "password_confirm": PW,
        })
        self.assertRedirects(r, reverse("teach"))
        self.assertEqual(get_user_model().objects.get(email="new@school.test").role, "TEACHER")

    def test_login_sends_teacher_to_classroom(self):
        r = self.client.post(reverse("login"), {"email": "t@school.test", "password": PW})
        self.assertRedirects(r, reverse("teach"))

    def test_add_learner_nickname_only(self):
        self.client.force_login(self.teacher.user)
        self.client.post(reverse("teach"), {"nickname": "Wanjiru", "current_level": 2})
        self.assertTrue(self.teacher.learners.filter(nickname="Wanjiru", current_level=2).exists())
        field_names = {f.name for f in Learner._meta.get_fields()}
        for pii in ("surname", "last_name", "date_of_birth", "email", "phone", "address"):
            self.assertNotIn(pii, field_names)

    def test_full_flow_through_pages_and_api(self):
        self.client.force_login(self.teacher.user)
        r = self.client.post(reverse("teach-start", args=[self.learner.pk]),
                             {"audio_enabled": "on", "sensory_mode": "contrast", "planned_cards": 6})
        session = LearningSession.objects.get()
        self.assertRedirects(r, reverse("teach-play", args=[session.pk]))
        page = self.client.get(reverse("teach-play", args=[session.pk]))
        self.assertContains(page, "mode-contrast")
        self.assertContains(page, "js/play.js")

        api = APIClient(enforce_csrf_checks=False)
        api.force_authenticate(self.teacher.user)
        for _ in range(6):
            card = api.post(reverse("api-learning-next", args=[session.pk])).data["card"]
            res = api.post(reverse("api-learning-answer", args=[session.pk]),
                           {"choice": card["choices"][0], "response_time_ms": 900}, format="json")
            self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["done"])
        self.assertTrue(api.post(reverse("api-learning-next", args=[session.pk])).data["done"])
        summary = self.client.get(reverse("teach-summary", args=[session.pk]))
        self.assertContains(summary, "Session summary: Amani")
        self.assertContains(summary, "Card by card")

    def test_end_session_early(self):
        self.client.force_login(self.teacher.user)
        session = start_session(self.teacher, self.learner, audio_enabled=True, sensory_mode="soft", planned_cards=9)
        api = APIClient()
        api.force_authenticate(self.teacher.user)
        r = api.post(reverse("api-learning-end", args=[session.pk]))
        self.assertEqual(r.data["summary_url"], reverse("teach-summary", args=[session.pk]))
        session.refresh_from_db()
        self.assertTrue(session.is_finished)
        self.assertRedirects(self.client.get(reverse("teach-play", args=[session.pk])),
                             reverse("teach-summary", args=[session.pk]))

    def test_other_teacher_cannot_access(self):
        session = start_session(self.teacher, self.learner, audio_enabled=True, sensory_mode="soft", planned_cards=6)
        self.client.force_login(self.other.user)
        self.assertEqual(self.client.get(reverse("teach-start", args=[self.learner.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("teach-summary", args=[session.pk])).status_code, 404)
        api = APIClient()
        api.force_authenticate(self.other.user)
        self.assertEqual(api.post(reverse("api-learning-next", args=[session.pk])).status_code, 404)

    def test_therapist_and_anonymous_blocked(self):
        self.assertEqual(self.client.get(reverse("teach")).status_code, 302)  # to login
        User = get_user_model()
        therapist = User.objects.create_user(email="th@x.test", password=PW, role=User.Role.THERAPIST)
        self.client.force_login(therapist)
        self.assertRedirects(self.client.get(reverse("teach")), reverse("home"))
