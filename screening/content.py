"""Text shown to parents. Kept in one place so it is easy to review and translate."""
from .models import RiskTier

# NFR 7: shown on every screening screen.
DISCLAIMER = (
    "This tool provides preliminary developmental risk indicators for triage purposes "
    "and does not constitute a certified medical diagnosis."
)

MIN_AGE_MONTHS = 16
MAX_AGE_MONTHS = 30

AGE_MESSAGE = (
    f"This questionnaire is designed for children aged {MIN_AGE_MONTHS} to {MAX_AGE_MONTHS} months. "
    "For a child outside this age range, please speak to a therapist directly. "
    "You can find one near you in the therapist directory."
)

TIER_GUIDANCE = {
    RiskTier.LOW: {
        "heading": "Low likelihood",
        "summary": "Your answers show few early signs that are usually linked with autism.",
        "next_steps": [
            "Keep watching your child's development and enjoy everyday play and talk together.",
            "If your child is under 24 months, screen again after their second birthday.",
            "If you are still worried, speak to a health worker or therapist. Your concerns matter.",
        ],
    },
    RiskTier.MEDIUM: {
        "heading": "Medium likelihood",
        "summary": "Some of your answers show early signs that are worth looking at more closely.",
        "next_steps": [
            "A follow-up conversation with a health worker or therapist is recommended.",
            "Write down examples of the behaviours you noticed so you can share them.",
            "Screen again in 1 to 2 months if you can't see someone sooner.",
        ],
    },
    RiskTier.HIGH: {
        "heading": "High likelihood",
        "summary": "Several of your answers show early signs that are often linked with autism.",
        "next_steps": [
            "Please arrange an assessment with a qualified therapist or child development specialist soon.",
            "Early support makes a real difference, and you don't need to wait for a diagnosis to start.",
            "Use the therapist directory to find verified therapists near you.",
        ],
    },
}
