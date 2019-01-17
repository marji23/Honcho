import time

from django.conf import settings
from django.db import models


class TenantDataQuerySet(models.QuerySet):
    def try_create_default(self, **kwargs):
        domain = settings.ZONE

        unique_id = time.time()
        name = '%s-%d' % (settings.TENANTS_PREFIX, unique_id,)
        schema_name = '%s_%d' % (settings.TENANTS_PREFIX, unique_id,)

        tenant, created = self.get_or_create(
            defaults=kwargs,
            domain_url='%s.%s' % (name, domain),
            schema_name=schema_name,
        )
        return tenant if created else None


TenantDataManager = TenantDataQuerySet.as_manager
