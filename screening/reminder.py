"""Calendar reminder (.ics) for the rescreen date. It contains no personal data."""
from datetime import timedelta

from django.utils import timezone


def build_ics(due, text, url):
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    end = due + timedelta(days=1)

    def esc(s):
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AutismCare//Screening reminder//EN",
        "BEGIN:VEVENT",
        f"UID:{stamp}-{due:%Y%m%d}@autismcare",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end:%Y%m%d}",
        "SUMMARY:AutismCare: time to screen again",
        f"DESCRIPTION:{esc(text + ' ' + url)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
