from django.db import models
from tenant_schemas.models import TenantMixin
from tenant_schemas.utils import schema_exists

from .managers import TenantDataManager

__author__ = 'yushkovskiy'


class TenantData(TenantMixin):
    """
    Data about tenant
    """

    auto_create_schema = False
    auto_drop_schema = True  # TODO: should be disabled in production

    description = models.TextField(max_length=200, blank=True)
    created_on = models.DateField(auto_now_add=True)

    # TODO: add plan information

    objects = TenantDataManager()

    def __str__(self):
        return '%s : %s' % (self.schema_name, self.domain_url)

    def prepared(self):
        return schema_exists(self.schema_name)
