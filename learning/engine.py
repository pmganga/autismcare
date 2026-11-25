"""AdaptiveEngine (FR 4.2; class diagram: evaluate(lastThree) : int).

Activity diagram B.4: after every 3 attempts, look at their accuracy:
- 3 of 3 correct      -> increase the difficulty level
- 1 or fewer correct  -> decrease the difficulty level
- otherwise (2 of 3)  -> keep the current level
Levels stay between 1 and 5.
"""
from .models import MAX_LEVEL, MIN_LEVEL

CHECK_EVERY = 3

# How many answer choices a card shows at each level
CHOICES_PER_LEVEL = {1: 2, 2: 3, 3: 3, 4: 4, 5: 4}


def evaluate(last_three, current_level):
    """last_three: the correctness (bool) of the last 3 attempts. Returns the new level."""
    if len(last_three) != CHECK_EVERY:
        raise ValueError("evaluate() needs exactly 3 attempts")
    correct = sum(1 for ok in last_three if ok)
    if correct == CHECK_EVERY:
        return min(current_level + 1, MAX_LEVEL)
    if correct <= 1:
        return max(current_level - 1, MIN_LEVEL)
    return current_level
