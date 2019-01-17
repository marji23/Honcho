import mimetypes

from django.db.models.signals import pre_save
from django.dispatch import receiver

from ..models import FileUpload


@receiver(pre_save, sender=FileUpload)
def _guess_mimetype(instance: FileUpload, **kwargs):
    if instance.mimetype:
        return

    # trust extension
    mime = mimetypes.guess_type(instance.file.url)
    if mime[0]:
        instance.mimetype = mime[0]
        return

    try:
        import magic
        mime = magic.from_buffer(instance.file.read(1024), mime=True)
        if mime:
            instance.mimetype = mime
    except ImportError:
        pass
