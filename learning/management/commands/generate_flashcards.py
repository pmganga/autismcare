"""Add AI-made cards to the bank ahead of time, e.g. before a class or a demo. Needs Ollama running."""
from django.core.management.base import BaseCommand, CommandError

from learning import ai


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
            try:
                cards = ai.add_new_cards(level=lv, count=count)
            except ai.AIUnavailable as e:
                raise CommandError(f"AI unavailable: {e}")
            total += len(cards)
            shown = ", ".join(f"{c['emoji']} {c['label']}" for c in cards)
            self.stdout.write(f"Level {lv}: added {len(cards)}" + (f" ({shown})" if shown else ""))
        self.stdout.write(self.style.SUCCESS(f"Done: {total} new AI cards in the bank."))
