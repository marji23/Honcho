from contextlib import contextmanager

from celery import Task
from celery.exceptions import Reject
from celery.utils.log import get_task_logger
from channels.db import DatabaseSyncToAsync
from django.db import connection
from tenant_schemas.utils import get_public_schema_name, get_tenant_model, tenant_context

logger = get_task_logger(__name__)

public_schema_name = get_public_schema_name()
TenantModel = get_tenant_model()


def map_task_per_tenants(task: Task, sequential: bool = False) -> None:
    # todo: filtering by tenant status
    tenants_ids = list(TenantModel.objects.exclude(schema_name=public_schema_name).values_list('id', flat=True))
    if sequential:
        logger.info("Submitting tasks for tenants: %s" % str(task.map(tenants_ids).apply_async()))
    else:
        logger.info("Submitting tasks for tenants: %s" % ', '.join(
            [str(task.delay(tenant_id)) for tenant_id in tenants_ids]
        ))


def get_tenant_or_raise_reject(tenant_id: int) -> TenantModel:
    try:
        tenant = TenantModel.objects.get(id=tenant_id)
    except TenantModel.DoesNotExist as ex:
        raise Reject(ex, requeue=False) from ex
    return tenant


@contextmanager
def tenant_context_or_raise_reject(tenant_id: int):
    tenant = get_tenant_or_raise_reject(tenant_id)
    with tenant_context(tenant):
        yield tenant


class TenantSyncToAsync(DatabaseSyncToAsync):
    def __init__(self, func: callable) -> None:
        super().__init__(func)
        self.tenant = connection.tenant

    def thread_handler(self, loop, *args, **kwargs):
        with tenant_context(self.tenant):
            return super().thread_handler(loop, *args, **kwargs)


tenant_sync_to_async = TenantSyncToAsync
