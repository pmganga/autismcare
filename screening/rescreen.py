"""Rescreen reminders (sequence diagram step 34: "show guidance + rescreen reminder").

- LOW, child under 24 months: screen again after the second birthday.
- LOW, 24 months or older: no routine rescreen. Screen again if new concerns appear.
- MEDIUM: screen again in about 1 month if no follow-up has happened.
- HIGH: no rescreen. The next step is an assessment with a therapist.
"""
import calendar
from dataclasses import dataclass
from datetime import date

from .models import RiskTier


@dataclass
class RescreenAdvice:
    due: date | None
    text: str


def add_months(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def rescreen_advice(child_age_months, tier, screened_on):
    if tier == RiskTier.HIGH:
        return RescreenAdvice(None, "")
    if tier == RiskTier.MEDIUM:
        due = add_months(screened_on, 1)
        return RescreenAdvice(
            due,
            f"If your child hasn't been seen by a health worker or therapist by {due:%d %B %Y}, "
            "please do the screening again.",
        )
    if child_age_months < 24:
        due = add_months(screened_on, 24 - child_age_months)
        return RescreenAdvice(
            due, f"Please screen again after your child's second birthday, around {due:%B %Y}."
        )
    return RescreenAdvice(
        None, "No routine rescreen is needed. Screen again or speak to a therapist if new concerns appear."
    )
