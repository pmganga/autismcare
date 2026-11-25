"""Licence documents are kept in the database, so they survive server restarts.

The free Render server has a temporary disk that is wiped on every restart.
"""
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DatabaseStorage(Storage):
    def _open(self, name, mode="rb"):
        from .models import StoredFile
        try:
            return ContentFile(StoredFile.objects.get(name=name).content, name=name)
        except StoredFile.DoesNotExist:
            raise FileNotFoundError(name)

    def _save(self, name, content):
        from .models import StoredFile
        data = b"".join(content.chunks())
        StoredFile.objects.create(name=name, content=data, size=len(data))
        return name

    def exists(self, name):
        from .models import StoredFile
        return StoredFile.objects.filter(name=name).exists()

    def delete(self, name):
        from .models import StoredFile
        StoredFile.objects.filter(name=name).delete()

    def size(self, name):
        from .models import StoredFile
        return StoredFile.objects.values_list("size", flat=True).get(name=name)

    def url(self, name):
        raise NotImplementedError("Licence documents have no public URL; staff open them through the admin.")
