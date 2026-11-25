"""Makes new flashcards with a local AI model (Qwen, run by Ollama) (SRS 3.3).

The model runs on this computer, so no learner data leaves it. It is slow on a
laptop, so services.py runs it in the background. If anything fails, the
built-in cards are used. Every card is checked before use (see validate_cards).
"""
import json
import logging
import random
import re
import unicodedata

import requests
from django.conf import settings
from django.db import IntegrityError, transaction

from .models import MAX_LEVEL, MIN_LEVEL, Flashcard

log = logging.getLogger(__name__)

CATEGORIES = [c.value for c in Flashcard.Category]
LABEL_RE = re.compile(r"^[a-z]+(?: [a-z]+)?$")
NOT_CHILD_SAFE = {
    "knife", "gun", "pistol", "rifle", "sword", "dagger", "bomb", "weapon", "blood", "skull", "ghost",
    "zombie", "devil", "coffin", "poison", "cigarette", "beer", "wine", "alcohol", "syringe", "needle", "pill",
}
JOINERS = {0xFE0F, 0xFE0E, 0x200D}  # variation selectors and zero-width joiner

LEVEL_GUIDE = {
    1: "very common objects a 3-year-old knows",
    2: "common everyday objects",
    3: "familiar household, food, animal and transport objects",
    4: "less common but concrete objects",
    5: "less common concrete objects that must be told apart from others in the same category",
}

SYSTEM_PROMPT = (
    "You make picture-word flashcards for young autistic children in special education classrooms in "
    "East Africa. Each card shows one emoji and the child picks the matching word. "
    "The label is the plain English name of the object the emoji shows, in lowercase, for example \"goat\". "
    "Never use words like card, flashcard, level, or numbers in a label. "
    "Choose calm, child-safe, concrete objects familiar in East African homes, schools and markets: "
    "no weapons, injuries, scary or medical items, and no people, faces or body parts."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "emoji": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                },
                "required": ["label", "emoji", "category"],
            },
        }
    },
    "required": ["cards"],
}

# One topic per request gives more new objects.
# Without it, a small model keeps suggesting cat, dog and banana.
THEMES = {
    "animals": ["farm animals", "wild animals of the savannah", "animals that live in water", "birds", "insects and small creatures"],
    "food": ["fruits sold at the market", "vegetables", "foods eaten at breakfast", "drinks and snacks"],
    "transport": ["vehicles on the road", "vehicles that fly or float", "vehicles that work on farms or building sites"],
    "home": ["things in the kitchen", "things in a classroom", "furniture", "toys and games", "tools"],
    "nature": ["weather and the sky", "plants and flowers", "things at the lake or beach"],
    "clothes": ["clothes", "shoes and hats", "things you wear or carry"],
}

EXAMPLE = json.dumps({"cards": [
    {"label": "cow", "emoji": "\U0001F404", "category": "animals"},
    {"label": "bread", "emoji": "\U0001F35E", "category": "food"},
]}, ensure_ascii=False)


class AIUnavailable(Exception):
    pass


def is_configured():
    return bool(settings.AI_FLASHCARDS_ENABLED and settings.OLLAMA_URL)


def _is_emoji(s):
    s = s.strip()
    return 0 < len(s) <= 8 and not any(ch.isascii() and ch.isalnum() for ch in s) and any(ord(ch) > 0x2000 for ch in s)


def emoji_name(emoji):
    """Official Unicode name of the emoji's main character, e.g. '🚌' -> 'BUS'."""
    chars = [ch for ch in emoji.strip() if ord(ch) not in JOINERS]
    try:
        return unicodedata.name(chars[0])
    except (IndexError, ValueError):
        return ""


def picture_matches(label, emoji):
    """True if every word of the label is in the emoji's Unicode name.

    'bus' + 🚌 (BUS) passes. 'water' + 💧 (DROPLET) fails.
    """
    name_words = set(emoji_name(emoji).lower().split())
    return bool(name_words) and all(w in name_words or w + "s" in name_words for w in label.split())


def validate_cards(raw_cards, avoid=()):
    """Keep only safe, simple cards whose picture matches the word. `avoid`: labels already used."""
    avoid = {a.lower() for a in avoid}
    seen, valid = set(), []
    for c in raw_cards:
        if not isinstance(c, dict):
            continue
        label = str(c.get("label", "")).strip()
        emoji = str(c.get("emoji", "")).strip()
        category = c.get("category")
        if not (LABEL_RE.match(label) and len(label) <= 20):
            continue
        if label in avoid or label in seen or set(label.split()) & NOT_CHILD_SAFE:
            continue
        if not _is_emoji(emoji) or category not in CATEGORIES:
            continue
        if not picture_matches(label, emoji):
            continue
        seen.add(label)
        valid.append({"label": label, "emoji": emoji, "category": category})
    return valid


def generate_cards(*, level, count, avoid=(), timeout=None, category=None, theme=None):
    """Ask the model for new cards at this level. Returns checked cards or raises AIUnavailable."""
    if not is_configured():
        raise AIUnavailable("AI flashcards are turned off (no OLLAMA_URL).")
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValueError("level must be 1-5")
    timeout = timeout or settings.AI_FLASHCARDS_TIMEOUT_SECONDS
    category = category or random.choice(CATEGORIES)
    theme = theme or random.choice(THEMES[category])

    taken = sorted(a for a in avoid if a)[:80]
    prompt = (
        f"Make {count + 4} flashcards. Topic: {theme}. Difficulty level {level} of 5: {LEVEL_GUIDE[level]}.\n"
        "Each card is a different object, with the category that fits it.\n"
        f"Example of the format: {EXAMPLE}\n"
        f"These words are already used, so pick other objects: {', '.join(taken)}."
    )
    try:
        r = requests.post(
            settings.OLLAMA_URL.rstrip("/") + "/api/chat",
            json={
                "model": settings.AI_FLASHCARDS_MODEL,
                "stream": False,
                "think": False,
                "format": OUTPUT_SCHEMA,  # the reply must follow this JSON format
                "keep_alive": "30m",      # keep the model loaded for 30 minutes (loading takes ~30 s)
                "options": {"temperature": 0.8, "num_predict": 600},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=timeout,
        )
        r.raise_for_status()
        text = r.json()["message"]["content"]
    except requests.Timeout as e:
        raise AIUnavailable(f"timed out after {timeout}s") from e
    except requests.ConnectionError as e:
        raise AIUnavailable("Ollama is not running") from e
    except requests.HTTPError as e:
        raise AIUnavailable(f"Ollama error {e.response.status_code}") from e
    except (ValueError, KeyError, TypeError) as e:
        raise AIUnavailable("unexpected reply from Ollama") from e

    try:
        raw = json.loads(text).get("cards", [])
    except (ValueError, AttributeError) as e:
        raise AIUnavailable("the model returned invalid JSON") from e

    cards = validate_cards(raw, avoid=avoid)[:count]
    if not cards:
        raise AIUnavailable("no usable cards in the response")
    log.info("AI generated %d of %d cards at level %d", len(cards), len(raw), level)
    return cards


def add_new_cards(*, level, count, max_requests=3):
    """Make and save up to `count` new cards, asking the model up to `max_requests` times.

    Raises AIUnavailable if the model can't be reached.
    """
    saved = []
    for _ in range(max_requests):
        if len(saved) >= count:
            break
        existing = set(Flashcard.objects.values_list("label", flat=True))
        try:
            cards = generate_cards(level=level, count=count - len(saved), avoid=existing)
        except AIUnavailable as e:
            if isinstance(e.__cause__, requests.RequestException):
                raise  # model not reachable: stop
            continue   # no usable cards this time: ask again
        for c in cards:
            if save_cards([c], level):
                saved.append(c)
    return saved


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
