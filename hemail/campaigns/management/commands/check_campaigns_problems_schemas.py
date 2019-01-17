from tenant_schemas.management.commands import BaseTenantCommand


class Command(BaseTenantCommand):
    COMMAND_NAME = 'check_campaigns_problems'

    def execute_command(self, tenant, command_name, *args, **options):
        # TODO: temporal solution until tenant_schemas support Django 2
        options.pop('schema_name')
        options.pop('skip_public')
        return super().execute_command(tenant, command_name, *args, **options)
