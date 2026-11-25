"""Clear the saved search lists when therapist data changes (NFR 1)."""
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import LicenseVerification, Therapist
from .search import clear_search_cache


@receiver([post_save, post_delete], sender=LicenseVerification)
@receiver([post_save, post_delete], sender=Therapist)
@receiver(m2m_changed, sender=Therapist.specializations.through)
def therapist_changed(**kwargs):
    clear_search_cache()
