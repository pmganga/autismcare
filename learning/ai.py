"""AI/NLP service for flashcard generation (activity diagram: "Generate flashcard set for that level").

Calls Claude through the official Anthropic SDK (SRS 3.3: authenticated HTTPS
POST with JSON). The call has a 5-second timeout (SRS 3.4). Any failure
(no key, timeout, network error, refusal, invalid output) raises
AIUnavailable, and the session falls back to the built-in card bank.

Every card the model returns is checked before use: a simple lowercase word,
a real emoji, an allowed category, nothing on the not-child-safe list, and
not a duplicate.
"""
import json
import logging
import os
import re

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import MAX_LEVEL, MIN_LEVEL, Flashcard

try:
    import anthropic
except ImportError:  # SDK not installed: AI generation is simply off
    anthropic = None

log = logging.getLogger(__name__)

CATEGORIES = [c.value for c in Flashcard.Category]
LABEL_RE = re.compile(r"^[a-z]+(?: [a-z]+)?$")
NOT_CHILD_SAFE = {
    "knife", "gun", "pistol", "rifle", "sword", "dagger", "bomb", "weapon", "blood", "skull", "ghost",
    "zombie", "devil", "coffin", "poison", "cigarette", "beer", "wine", "alcohol", "syringe", "needle", "pill",
}

LEVEL_GUIDE = {
    1: "very common objects a 3-year-old knows (e.g. ball, cat, apple)",
    2: "common everyday objects (e.g. bus, shoe, banana)",
    3: "familiar household, food, animal and transport objects (e.g. chair, goat, bicycle)",
    4: "less common but concrete objects (e.g. giraffe, umbrella, pineapple)",
    5: "less common concrete objects that a learner must tell apart from others in the same category "
       "(e.g. zebra vs donkey, tractor vs lorry)",
}

SYSTEM_PROMPT = (
    "You create picture-word flashcards for autistic children aged 3 to 10 in special education "
    "classrooms in East Africa. Each card shows one emoji and the learner picks the matching word. "
    "Choose concrete, everyday objects that are familiar in East African homes, schools and markets. "
    "Every card must be calm and child-safe: no weapons, injuries, scary or medical items, and no "
    "people, faces or body parts. The emoji must clearly show exactly that one object."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Lowercase English word, one or two words."},
                    "emoji": {"type": "string", "description": "A single emoji showing the object."},
                    "category": {"type": "string", "enum": CATEGORIES},
                },
                "required": ["label", "emoji", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}


class AIUnavailable(Exception):
    pass


def is_configured():
    return bool(settings.AI_FLASHCARDS_ENABLED and anthropic is not None and os.getenv("ANTHROPIC_API_KEY"))


def _is_emoji(s):
    s = s.strip()
    return 0 < len(s) <= 8 and not any(ch.isascii() and ch.isalnum() for ch in s) and any(ord(ch) > 0x2000 for ch in s)


def validate_cards(raw_cards, avoid=()):
    """Keep only cards that pass every check. `avoid` = labels already in use."""
    avoid = {a.lower() for a in avoid}
    seen, valid = set(), []
    for c in raw_cards:
        label = str(c.get("label", "")).strip()
        emoji = str(c.get("emoji", "")).strip()
        category = c.get("category")
        if not (LABEL_RE.match(label) and len(label) <= 20):
            continue
        if label in avoid or label in seen or set(label.split()) & NOT_CHILD_SAFE:
            continue
        if not _is_emoji(emoji) or category not in CATEGORIES:
            continue
        seen.add(label)
        valid.append({"label": label, "emoji": emoji, "category": category})
    return valid


def generate_cards(*, level, count, avoid=(), timeout=None):
    """Ask Claude for `count` new cards at `level`. Returns validated cards or raises AIUnavailable."""
    if not is_configured():
        raise AIUnavailable("AI flashcards are not configured (no ANTHROPIC_API_KEY).")
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValueError("level must be 1-5")
    timeout = timeout or settings.EXTERNAL_API_TIMEOUT_SECONDS

    avoid_list = ", ".join(sorted(avoid)[:150])
    prompt = (
        f"Create {count} new flashcards for difficulty level {level} of 5: {LEVEL_GUIDE[level]}.\n"
        "Rules: the label is a lowercase English word (one or two words), the emoji shows exactly that "
        "object, and the category is one of the allowed values.\n"
        f"Do not use any of these labels, which already exist: {avoid_list}."
    )

    client = anthropic.Anthropic(timeout=timeout, max_retries=0)
    try:
        response = client.beta.messages.create(
            model=settings.AI_FLASHCARDS_MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if the model declines, the API retries on a fallback model
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APITimeoutError as e:
        raise AIUnavailable(f"timed out after {timeout}s") from e
    except anthropic.RateLimitError as e:
        raise AIUnavailable("rate limited") from e
    except anthropic.APIStatusError as e:
        raise AIUnavailable(f"API error {e.status_code}") from e
    except anthropic.APIConnectionError as e:
        raise AIUnavailable("network error") from e

    if response.stop_reason == "refusal":
        raise AIUnavailable("the model declined the request")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        raw = json.loads(text).get("cards", [])
    except (ValueError, AttributeError) as e:
        raise AIUnavailable("the model returned invalid JSON") from e

    cards = validate_cards(raw, avoid=avoid)[:count]
    if not cards:
        raise AIUnavailable("no usable cards in the response")
    log.info("AI generated %d cards at level %d (request %s)", len(cards), level, response._request_id)
    return cards


def save_cards(cards, level):
    """Store validated cards as AI-sourced flashcards at this level. Returns how many were added."""
    added = 0
    for c in cards:
        try:
            with transaction.atomic():  # a clash rolls back only this card
                Flashcard.objects.create(
                    label=c["label"], symbol=c["emoji"], category=c["category"],
                    difficulty=level, source=Flashcard.Source.AI,
                )
            added += 1
        except IntegrityError:  # label taken meanwhile
            continue
    return added
