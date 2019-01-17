import logging
import os

from django.contrib.staticfiles.storage import StaticFilesStorage
from django.core.exceptions import SuspiciousOperation
from django.core.files.storage import FileSystemStorage
from django.db import connection
from django.utils._os import safe_join
from storages.backends.s3boto3 import S3Boto3Storage
from storages.utils import safe_join as s3_safe_join

_logger = logging.getLogger(__name__)


class PrivateMediaRootTenancyS3BotoStorage(S3Boto3Storage):
    location = 'media'
    default_acl = 'private'

    def _normalize_name(self, name):
        tenant_name = getattr(connection, 'schema_name', None)
        if tenant_name is None:
            raise SuspiciousOperation("Attempted access to '%s' with tenant information." % name)

        try:
            return s3_safe_join(self.location, tenant_name, name)
        except ValueError:
            raise SuspiciousOperation("Attempted access to '%s' denied." % name)


class TenantStorageMixin(object):
    """
    Like tenant_schemas.storage.TenantStorageMixin but use domain_url as a prefix.
    """

    def __init__(self, **kwarg: dict) -> None:
        location = kwarg.get('location', None)
        if isinstance(location, tuple):
            media_root, relative_location = location
            kwarg['location'] = safe_join(media_root, relative_location)
        else:
            media_root = location
            relative_location = '.'
        super().__init__(**kwarg)
        self._media_root = media_root
        self._relative_location = relative_location

    def path(self, name):
        """
        Look for files in subdirectory of MEDIA_ROOT using the tenant's
        domain_url value as the specifier.
        """
        if name is None:
            name = ''
        try:
            location = safe_join(self._media_root, connection.tenant.domain_url, self._relative_location)
        except AttributeError:
            location = self.location
        try:
            path = safe_join(location, name)
        except ValueError:
            raise SuspiciousOperation("Attempted access to '%s' denied." % name)

        return os.path.normpath(path)


class TenantFileSystemStorage(TenantStorageMixin, FileSystemStorage):
    """
    Implementation that extends core Django's FileSystemStorage.
    """


class TenantStaticFilesStorage(TenantStorageMixin, StaticFilesStorage):
    """
    Implementation that extends core Django's StaticFilesStorage.
    """
