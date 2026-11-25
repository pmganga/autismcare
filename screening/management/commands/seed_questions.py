"""Load the 20 questionnaire items.

    python manage.py seed_questions              # placeholder items (default)
    python manage.py seed_questions --file q.json

IMPORTANT: Using M-CHAT-R/F in an app requires permission from its authors
(see the official M-CHAT website). Until permission is granted, this loads
PLACEHOLDER text with the same structure: 20 yes/no items, with items 2, 5
and 12 reverse-scored. When you have permission, put the licensed wording in
a JSON file and load it with --file:

    [{"number": 1, "text": "...", "reverse": false}, ...]
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from screening.models import Question

REVERSE_SCORED = {2, 5, 12}  # M-CHAT-R/F structure


def placeholder_items():
    return [
        {
            "number": n,
            "text": (
                f"Placeholder question {n}. Replace with licensed M-CHAT-R/F item {n}."
                + (" (Reverse-scored: 'Yes' is the risk answer.)" if n in REVERSE_SCORED else "")
            ),
            "reverse": n in REVERSE_SCORED,
        }
        for n in range(1, 21)
    ]


class Command(BaseCommand):
    help = "Load or update the screening questionnaire items."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="JSON file with licensed item text.")

    @transaction.atomic
    def handle(self, *args, file=None, **opts):
        if file:
            try:
                with open(file, encoding="utf-8") as f:
                    items = json.load(f)
            except (OSError, ValueError) as e:
                raise CommandError(f"Couldn't read {file}: {e}")
        else:
            items = placeholder_items()

        numbers = set()
        for it in items:
            n = int(it["number"])
            numbers.add(n)
            Question.objects.update_or_create(
                number=n,
                defaults={
                    "text": it["text"],
                    "is_reverse_scored": bool(it.get("reverse", n in REVERSE_SCORED)),
                    "weight": int(it.get("weight", 1)),
                    "is_active": True,
                },
            )
        retired = Question.objects.exclude(number__in=numbers).update(is_active=False)
        source = file or "placeholder text"
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(numbers)} questions from {source}." + (f" Deactivated {retired}." if retired else "")
        ))
