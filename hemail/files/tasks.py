import datetime

from celery import shared_task
from celery.schedules import schedule
from celery.task import periodic_task
from celery.utils.log import get_task_logger

from tenancy.utils import map_task_per_tenants, tenant_context_or_raise_reject
from .models import FileUpload

logger = get_task_logger(__name__)


@shared_task
def delete_expired_files(tenant_id: int):
    with tenant_context_or_raise_reject(tenant_id) as tenant:
        deleted, detailed = FileUpload.objects.delete_expired()
        logger.info("[%d: %s]: Removed %d expired files" % (tenant_id, tenant.schema_name, deleted,))
        return detailed


@periodic_task(run_every=schedule(run_every=datetime.timedelta(hours=6)))
def delete_expired_files_from_tenants():
    return map_task_per_tenants(delete_expired_files)
