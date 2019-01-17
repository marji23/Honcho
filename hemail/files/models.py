import datetime
import enum
from contextlib import contextmanager
from typing import Optional
from uuid import uuid4

from django.conf import settings
from django.core.files import File
from django.db import models
from django.db.models.fields import files
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from enumfields import EnumField

from hemail.storage import storages
from users.utils import tenant_users
from .managers import FileUploadManager


def get_upload_path(instance: 'FileUpload', filename: str) -> str:
    """Overriding to store the original filename"""
    if not instance.name:
        instance.name = filename  # set original filename

    filename = '{name}.{ext}'.format(name=uuid4().hex,
                                     ext=filename.split('.')[-1])
    current_dt = now()
    return '/'.join([
        'uploaded_files',
        str(current_dt.year),
        str(current_dt.month),
        str(current_dt.day),
        filename,
    ])


class FileUploader(enum.Enum):
    USER = 'USER'
    SYSTEM = 'SYSTEM'


class FileUpload(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    file = models.FileField(_('File'), upload_to=get_upload_path, storage=storages['file-storage'])
    name = models.CharField(_('Name'), max_length=255, help_text=_("The original filename"), editable=False)
    mimetype = models.TextField(max_length=255, default='', blank=True)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              verbose_name=_('Owner'), related_name='uploaded_files',
                              limit_choices_to=tenant_users)
    uploader = EnumField(FileUploader, max_length=32, default=FileUploader.USER)
    ttl = models.DurationField(_('TTL'),
                               blank=True, null=True,
                               default=datetime.timedelta(weeks=1),
                               help_text=_('How long file with be stored'))

    objects = FileUploadManager()

    def __str__(self) -> str:
        return self.name

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        self.file.delete(save=False)
        return result

    @contextmanager
    def open(self, mode='rb') -> files.FieldFile:
        self.file.open(mode=mode)
        try:
            yield self.file
        finally:
            self.file.close()

    @property
    def url(self):
        return self.file.url

    @property
    def expiration_datetime(self) -> Optional[datetime.datetime]:
        if self.updated:
            return self.updated + self.ttl
        return None

    def as_file(self) -> File:
        return File(self.file, self.name)

    @contextmanager
    def move(self) -> File:
        try:
            yield self.as_file()
        finally:
            self.file.close()
        self.delete()
