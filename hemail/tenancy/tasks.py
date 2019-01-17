from __future__ import absolute_import, unicode_literals

from celery import chain, shared_task
from celery.exceptions import Reject
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import OperationalError
from tenant_schemas.utils import tenant_context

from .models import TenantData
from .signals import tenant_prepared

logger = get_task_logger(__name__)


@shared_task(bind=True)
def create_tenant_task(self, user_id) -> int:
    tenant = TenantData.objects.try_create_default()
    if not tenant:
        logger.warn("Failed to create tenant because of not unique name was generated")
        raise self.retry(exc=OperationalError('Failed to create tenant because of raise'))

    UserModel = get_user_model()
    try:
        profile = UserModel.objects.get(id=user_id).profile
    except (UserModel.MultipleObjectsReturned, UserModel.DoesNotExist) as ex:
        tenant.delete(force_drop=True)
        raise Reject(ex, requeue=False) from ex

    if profile.tenant:
        tenant.delete(force_drop=True)
        raise Reject('Tenant already created for user', requeue=False)

    try:
        profile.tenant = tenant
        profile.save()
    except BaseException:
        tenant.delete(force_drop=True)
        raise

    return tenant.id


@shared_task
def create_schema_task(tenant_id) -> None:
    try:
        tenant = TenantData.objects.get(id=tenant_id)
    except (TenantData.MultipleObjectsReturned, TenantData.DoesNotExist) as ex:
        raise Reject(ex, requeue=False)

    try:
        tenant.create_schema(check_if_exists=True)

        with tenant_context(tenant):
            call_command('installwatson')

    except BaseException:
        # We failed creating the tenant, delete what we created and
        # re-raise the exception
        tenant.delete(force_drop=True)
        raise

    tenant_prepared.send_robust(sender=TenantData, tenant=tenant)


prepare_tenant_task = chain(create_tenant_task.s() | create_schema_task.s())
