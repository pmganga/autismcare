"""FR 2.2: PDF guidance report for a screening result.

Contents: the result and score, the indicators (answers that showed early
signs), the suggested next steps, the rescreen reminder, the full answer list
for a clinician, and the medical disclaimer (NFR 7).
"""
from django.db.models import F
from django.utils import timezone
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .content import DISCLAIMER, TIER_GUIDANCE
from .models import GuidanceReport
from .rescreen import rescreen_advice
from .scoring import ScoredItem

# The built-in PDF fonts can't show curly quotes or long dashes, so swap them.
_REPLACEMENTS = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "·": "-", "•": "-"}


def _latin1(text):
    for a, b in _REPLACEMENTS.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


class _Report(FPDF):
    TEXT = (38, 50, 58)
    MUTED = (86, 99, 107)
    PRIMARY = (61, 107, 106)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*self.MUTED)
        self.cell(0, 6, _latin1(f"AutismCare screening report - page {self.page_no()}"), align="C")

    def heading(self, text, size=13):
        self.ln(3)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*self.PRIMARY)
        self.multi_cell(0, size * 0.55, _latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*self.TEXT)
        self.ln(1)

    def para(self, text, size=11, style="", color=None, h=6):
        self.set_font("Helvetica", style, size)
        self.set_text_color(*(color or self.TEXT))
        self.multi_cell(0, h, _latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet(self, text, marker="-"):
        self.set_font("Helvetica", size=11)
        self.set_text_color(*self.TEXT)
        self.cell(8, 6, _latin1(marker))
        self.multi_cell(0, 6, _latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def get_or_create_report(result):
    guidance = TIER_GUIDANCE[result.tier]
    report, _ = GuidanceReport.objects.get_or_create(
        result=result, defaults={"next_steps": "\n".join(guidance["next_steps"])}
    )
    return report


def build_pdf(session, directory_url=None, compress=True):
    """Return (pdf_bytes, GuidanceReport). compress=False keeps text readable for tests."""
    result = session.result
    guidance = TIER_GUIDANCE[result.tier]
    report = get_or_create_report(result)
    answers = list(session.answers.select_related("question").order_by("question__number"))
    flagged = [
        a for a in answers
        if ScoredItem(a.value, a.question.weight, a.question.is_reverse_scored).is_risk
    ]
    screened_on = timezone.localtime(result.calculated_at).date()
    advice = rescreen_advice(session.child_age_months, result.tier, screened_on)

    pdf = _Report(format="A4")
    pdf.set_compression(compress)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    pdf.para("AutismCare", 10, "B", pdf.PRIMARY)
    pdf.para("Screening guidance report", 20, "B", h=10)
    pdf.para(
        f"Screened on {screened_on:%d %B %Y}  |  Child's age: {session.child_age_months} months  |  "
        f"Report ID: {str(report.id)[:8].upper()}",
        9, color=pdf.MUTED,
    )

    pdf.heading(f"Result: {guidance['heading']}  (score {result.score} of 20)", 15)
    pdf.para(guidance["summary"])

    pdf.heading("Suggested next steps")
    for i, step in enumerate(guidance["next_steps"], 1):
        pdf.bullet(step, f"{i}.")
    if directory_url and result.tier != "LOW":
        pdf.ln(1)
        pdf.para(f"Find verified therapists near you: {directory_url}", 10, "B")

    if advice.text:
        pdf.heading("When to screen again")
        pdf.para(advice.text)

    pdf.heading(f"Indicators: answers that showed early signs ({len(flagged)})")
    if flagged:
        for a in flagged:
            pdf.bullet(f"Q{a.question.number}. {a.question.text}  -  answered {'Yes' if a.value else 'No'}")
    else:
        pdf.para("None of the answers showed early signs.")

    pdf.heading("For the health worker or therapist: all answers")
    pdf.set_font("Helvetica", size=9)
    with pdf.table(col_widths=(10, 120, 18, 22), text_align=("CENTER", "LEFT", "CENTER", "CENTER"),
                   line_height=5) as table:
        row = table.row()
        for h in ("#", "Question", "Answer", "Early sign"):
            row.cell(h)
        for a in answers:
            row = table.row()
            row.cell(str(a.question.number))
            row.cell(_latin1(a.question.text))
            row.cell("Yes" if a.value else "No")
            row.cell("Yes" if a in flagged else "")
    pdf.para(
        "Scoring: 0-2 low, 3-7 medium, 8-20 high (M-CHAT-R/F scoring rules, Robins et al., 2014).",
        8, color=pdf.MUTED,
    )

    pdf.ln(4)
    pdf.set_fill_color(228, 235, 242)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(44, 74, 102)
    pdf.multi_cell(0, 6, _latin1("Important: " + DISCLAIMER), fill=True, padding=3, align="L",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    GuidanceReport.objects.filter(pk=report.pk).update(download_count=F("download_count") + 1)
    return bytes(pdf.output()), report


def report_filename(session):
    return f"autismcare-screening-{timezone.localtime(session.created_at):%Y-%m-%d}.pdf"
