"""Rule-based card service: new picture cards from the word bank in the database, without an AI model.

Used where no AI model can run, such as the free cloud server. It answers in milliseconds.
"""
import random

from . import ai
from .models import Flashcard, WordBankEntry


def add_new_cards(*, level, count):
    """Add up to `count` words the bank hasn't used yet at this level. Returns the cards added."""
    existing = set(Flashcard.objects.values_list("label", flat=True))
    pool = [{"label": w.label, "emoji": w.emoji, "category": w.category}
            for w in WordBankEntry.objects.filter(level=level).exclude(label__in=existing)]
    random.shuffle(pool)
    cards = ai.validate_cards(pool, avoid=existing)  # same picture and safety checks as AI cards
    added = []
    for c in cards:
        if len(added) >= count:
            break
        if ai.save_cards([c], level, source=Flashcard.Source.WORDBANK):
            added.append(c)
    return added
