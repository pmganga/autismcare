"""Risk score calculation (FR 2.1). This is a pure function with no database access.

Follows the published M-CHAT-R/F scoring rules (Robins et al., 2014):
- For most items, "No" is the risk answer. For reverse-scored items
  (2, 5 and 12 in M-CHAT-R/F), "Yes" is the risk answer.
- Each risk answer adds that question's weight (1 for M-CHAT-R/F).
- Total 0-2 = Low, 3-7 = Medium (follow-up recommended), 8-20 = High.
"""
from dataclasses import dataclass

from .models import RiskTier

MEDIUM_MIN_SCORE = 3
HIGH_MIN_SCORE = 8


@dataclass(frozen=True)
class ScoredItem:
    value: bool            # the parent's answer: True = Yes
    weight: int = 1
    is_reverse_scored: bool = False

    @property
    def is_risk(self):
        return self.value if self.is_reverse_scored else not self.value


def tier_for(score):
    if score >= HIGH_MIN_SCORE:
        return RiskTier.HIGH
    if score >= MEDIUM_MIN_SCORE:
        return RiskTier.MEDIUM
    return RiskTier.LOW


def calculate_risk(items):
    """items: iterable of ScoredItem. Returns (score, RiskTier)."""
    score = sum(i.weight for i in items if i.is_risk)
    return score, tier_for(score)
