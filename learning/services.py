"""Learning session flow, following the activity diagram (Appendix B.4).

start_session  -> retrieve learner's level, ask the AI/NLP service for cards (in the background)
next_card      -> display a flashcard (picture + word choices)
answer         -> record the attempt; every 3 attempts, the adaptive engine
                  raises, lowers or keeps the level
finish_session -> save the progress summary (accuracy, new level)
"""
import logging
import random
import threading

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from . import ai
from .engine import CHECK_EVERY, CHOICES_PER_LEVEL, evaluate
from .models import Attempt, Flashcard, LearningSession

log = logging.getLogger(__name__)

AI_CARDS_PER_SESSION = 4
MAX_RESPONSE_MS = 10 * 60 * 1000


class SessionError(Exception):
    pass


def start_session(teacher, learner, *, audio_enabled, sensory_mode, planned_cards):
    level = learner.current_level
    session = LearningSession.objects.create(
        teacher=teacher,
        learner=learner,
        audio_enabled=audio_enabled,
        sensory_mode=sensory_mode,
        planned_cards=planned_cards,
        start_level=level,
        current_level=level,
    )
    request_ai_cards(session)
    return session


_ai_busy = threading.Lock()  # one generation at a time: the local model uses the whole CPU


def request_ai_cards(session):
    """Ask the AI service for new cards at the session's level, without making the learner wait.

    In the background (the default) the session starts at once with the cards
    already in the bank; new cards join the bank when the model finishes and
    can appear later in this session or the next one.
    """
    if not ai.is_configured():
        return
    if not _ai_busy.acquire(blocking=False):
        return  # a generation is already running; this session uses the bank as it is
    _set_ai_status(session.pk, LearningSession.AIStatus.PENDING)
    session.ai_status = LearningSession.AIStatus.PENDING
    if settings.AI_FLASHCARDS_BACKGROUND:
        threading.Thread(target=_generate, args=(session.pk, session.start_level), daemon=True).start()
    else:
        _generate(session.pk, session.start_level)
        session.refresh_from_db(fields=["ai_status", "ai_cards_added"])


def _generate(session_pk, level):
    try:
        try:
            cards = ai.add_new_cards(level=level, count=AI_CARDS_PER_SESSION)
        except ai.AIUnavailable as e:
            cards = []
            log.warning("AI flashcards unavailable, using built-in cards: %s", e)
        if cards:
            _set_ai_status(session_pk, LearningSession.AIStatus.USED, len(cards))
        else:
            _set_ai_status(session_pk, LearningSession.AIStatus.UNAVAILABLE)
    except Exception:  # never let a background failure go unnoticed or break the app
        log.exception("AI flashcard generation failed")
        _set_ai_status(session_pk, LearningSession.AIStatus.UNAVAILABLE)
    finally:
        _ai_busy.release()
        if settings.AI_FLASHCARDS_BACKGROUND:
            connections.close_all()  # this thread's own database connection


def _set_ai_status(session_pk, status, added=None):
    fields = {"ai_status": status}
    if added is not None:
        fields["ai_cards_added"] = added
    LearningSession.objects.filter(pk=session_pk).update(**fields)


def _pick_card(session):
    used = session.attempts.values_list("flashcard_id", flat=True)
    level = session.current_level
    pool = list(Flashcard.objects.filter(is_active=True, difficulty=level).exclude(id__in=used))
    if not pool:  # every card at this level used: allow repeats rather than stop
        pool = list(Flashcard.objects.filter(is_active=True, difficulty=level))
    if not pool:
        raise SessionError(f"No flashcards available at level {level}.")
    # Prefer fresh AI cards a little, so newly generated cards are actually seen
    ai_cards = [c for c in pool if c.source == Flashcard.Source.AI]
    return random.choice(ai_cards if ai_cards and random.random() < 0.5 else pool)


def _choices_for(card, level):
    n = CHOICES_PER_LEVEL[level]
    others = Flashcard.objects.filter(is_active=True).exclude(id=card.id)
    # Level 5 is harder: choices come from the same category (e.g. all animals)
    same = others.filter(category=card.category) if level == 5 else others.filter(difficulty=level)
    labels = list(same.values_list("label", flat=True))
    if len(labels) < n - 1:
        labels = list(others.values_list("label", flat=True))
    choices = random.sample(labels, n - 1) + [card.label]
    random.shuffle(choices)
    return choices


def card_payload(session):
    card = session.current_card
    return {
        "number": session.total_attempts + 1,
        "total": session.planned_cards,
        "level": session.current_level,
        "symbol": card.symbol,
        "image_url": card.image_url,
        "choices": session.current_choices,
    }


@transaction.atomic
def next_card(session):
    """Return the card to show, or None when the session is over.

    Calling it again before answering returns the same card (e.g. after a page reload).
    """
    session = LearningSession.objects.select_for_update().get(pk=session.pk)
    if session.is_finished or session.total_attempts >= session.planned_cards:
        return None
    if session.current_card_id is None:
        card = _pick_card(session)
        session.current_card = card
        session.current_choices = _choices_for(card, session.current_level)
        session.shown_at = timezone.now()
        session.save(update_fields=["current_card", "current_choices", "shown_at"])
    return card_payload(session)


@transaction.atomic
def answer(session, chosen_label, response_time_ms=None):
    """Record the learner's answer and apply the adaptive rule every 3 attempts."""
    # Lock only the session row: PostgreSQL can't lock across the optional current_card join.
    session = LearningSession.objects.select_for_update().get(pk=session.pk)
    if session.is_finished:
        raise SessionError("This session has ended.")
    card = session.current_card
    if card is None:
        raise SessionError("There is no card on screen.")
    if chosen_label not in session.current_choices:
        raise SessionError("That answer isn't one of the choices.")

    if response_time_ms is None:
        response_time_ms = int((timezone.now() - session.shown_at).total_seconds() * 1000)
    response_time_ms = max(0, min(int(response_time_ms), MAX_RESPONSE_MS))

    is_correct = chosen_label == card.label
    level_before = session.current_level
    session.total_attempts += 1
    session.correct_count += int(is_correct)
    session.attempts_since_check += 1

    attempt = Attempt.objects.create(
        session=session, flashcard=card, number=session.total_attempts, chosen_label=chosen_label,
        is_correct=is_correct, response_time_ms=response_time_ms, level=level_before, level_after=level_before,
    )

    # Activity diagram: "3 attempts since last check?" -> evaluate the last three
    if session.attempts_since_check >= CHECK_EVERY:
        last_three = list(session.attempts.order_by("-number").values_list("is_correct", flat=True)[:CHECK_EVERY])
        session.current_level = evaluate(last_three, level_before)
        session.attempts_since_check = 0
        attempt.level_after = session.current_level
        attempt.save(update_fields=["level_after"])
        learner = session.learner
        learner.current_level = session.current_level
        learner.save(update_fields=["current_level"])

    session.current_card = None
    session.current_choices = []
    session.shown_at = None
    session.save()

    done = session.total_attempts >= session.planned_cards
    if done:
        finish_session(session)

    change = session.current_level - level_before
    return {
        "correct": is_correct,
        "correct_label": card.label,
        "level": session.current_level,
        "level_change": "up" if change > 0 else "down" if change < 0 else "same",
        "done": done,
        "number": session.total_attempts,
        "total": session.planned_cards,
    }


def finish_session(session):
    """Save the progress summary. Safe to call twice."""
    if session.is_finished:
        return session
    session.ended_at = timezone.now()
    session.end_level = session.current_level
    session.current_card = None
    session.current_choices = []
    session.save(update_fields=["ended_at", "end_level", "current_card", "current_choices"])
    return session
