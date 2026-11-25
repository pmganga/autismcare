"""Load the built-in flashcard bank, so every installation (and every test run) has it."""
from django.db import migrations


def load_cards(apps, schema_editor):
    from learning.cards import BUILTIN_CARDS

    Flashcard = apps.get_model("learning", "Flashcard")
    for label, symbol, difficulty, category in BUILTIN_CARDS:
        Flashcard.objects.update_or_create(
            label=label,
            defaults={"symbol": symbol, "difficulty": difficulty, "category": category, "source": "BUILTIN"},
        )


def remove_cards(apps, schema_editor):
    from learning.cards import BUILTIN_CARDS

    Flashcard = apps.get_model("learning", "Flashcard")
    Flashcard.objects.filter(label__in=[c[0] for c in BUILTIN_CARDS], source="BUILTIN").delete()


class Migration(migrations.Migration):
    dependencies = [("learning", "0001_initial")]
    operations = [migrations.RunPython(load_cards, remove_cards)]
