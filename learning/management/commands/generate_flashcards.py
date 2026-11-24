"""Fill the card bank with AI-generated cards ahead of time (e.g. before a class or a demo).

    python manage.py generate_flashcards               # 4 cards for each level 1-5
    python manage.py generate_flashcards --level 2 --count 6

Needs Ollama running locally with the model in AI_FLASHCARDS_MODEL (default qwen3.5:2b).
"""
from django.core.management.base import BaseCommand, CommandError

from learning import ai
from learning.models import Flashcard


class Command(BaseCommand):
    help = "Generate new picture cards with the local AI model (Ollama) and add them to the bank."

    def add_arguments(self, parser):
        parser.add_argument("--level", type=int, choices=range(1, 6), help="Only this level (default: all 1-5).")
        parser.add_argument("--count", type=int, default=4, help="Cards to add per level (default 4).")

    def handle(self, *args, level, count, **opts):
        if not ai.is_configured():
            raise CommandError("AI is turned off: set OLLAMA_URL and AI_FLASHCARDS_ENABLED=True.")
        total = 0
        for lv in [level] if level else range(1, 6):
            existing = set(Flashcard.objects.values_list("label", flat=True))
            try:
                cards = ai.generate_cards(level=lv, count=count, avoid=existing)
            except ai.AIUnavailable as e:
                self.stdout.write(self.style.WARNING(f"Level {lv}: no cards ({e})."))
                continue
            added = ai.save_cards(cards, lv)
            total += added
            shown = ", ".join(f"{c['emoji']} {c['label']}" for c in cards)
            self.stdout.write(f"Level {lv}: added {added} ({shown})")
        self.stdout.write(self.style.SUCCESS(f"Done: {total} new AI cards in the bank."))
