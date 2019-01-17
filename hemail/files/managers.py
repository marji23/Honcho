from typing import Tuple

from django.db import models
from django.db.models import DateTimeField, F
from django.db.models.functions import Cast
from django.utils.timezone import now


class FileUploadQuerySet(models.QuerySet):
    def out_of_dated(self) -> 'FileUploadQuerySet':
        return self.annotate(
            expiration_datetime=Cast(F('updated') + F('ttl'), output_field=DateTimeField())
        ).filter(
            expiration_datetime__lt=now()
        )

    def delete_expired(self) -> Tuple[int, dict]:
        return self.out_of_dated().delete()


FileUploadManager = FileUploadQuerySet.as_manager
