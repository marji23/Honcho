from unittest.mock import patch

from django.test import override_settings

from tenancy.test.cases import TenantsTestCase
from .models import TenantData
from .tasks import prepare_tenant_task


class MultiTenantSearchTestCase(TenantsTestCase):
    tenants_names = []

    @patch('campaigns.providers.tasks.guess_configuration')
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_tenant_should_be_prepared(self, mock_get_configurations_from_isp_task):
        mock_get_configurations_from_isp_task.return_value = None

        user = self.create_superuser('first', 'test@one.com', 'p')
        try:
            prepare_tenant_task.delay(user.id).get()
        except BaseException:
            raise
        else:
            tenant = TenantData.objects.get()
            self.set_tenant(tenant)
            user.delete()
            tenant.delete(force_drop=True)

    def test_tenant_wont_be_created_if_user_does_not_exists(self):
        pass

    def test_tenant_wont_be_created_if_user_already_has_one(self):
        pass

    def test_migration_wont_be_run_if_tenant_was_removed_explicitly(self):
        pass
