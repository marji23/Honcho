import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from tenant_schemas.postgresql_backend.base import _is_valid_schema_name as is_valid_schema_name
from tenant_schemas.utils import get_tenant_model

__author__ = 'yushkovskiy'


class Command(BaseCommand):
    """
    Very simple way to create tenant from shell.
    """

    help = 'Used to create tenant data.'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.TenantModel = get_tenant_model()

    def add_arguments(self, parser):
        parser.add_argument('--name', dest='name', default=None,
                            help='Name of the tenant'),
        parser.add_argument('--description', dest='description', default='',
                            help='Specifies the login for the global admin account.'),
        parser.add_argument('--create-with-schema', action='store_true', dest='with_schema', default=False,
                            help='Will automatically create schema for then new tenant.')

        parser.add_argument('--database', action='store', dest='database',
                            default=DEFAULT_DB_ALIAS, help='Specifies the database to use. Default is "default".'),

    def handle(self, *args, **options):
        verbosity = int(options.get('verbosity', 1))

        name = options.get('name')
        description = options.get('description')
        with_schema = options.get('with_schema')

        database = options.get('database')

        try:
            if name:
                if not is_valid_schema_name(name):
                    self.stderr.write("\nInvalid string used for the schema name.")
                    sys.exit(1)
                domain = settings.ZONE
                tenant, created = self.TenantModel.objects.using(database).get_or_create(
                    domain_url='%s.%s' % (name, domain),
                    schema_name=name,
                    description=description)
                if verbosity >= 1:
                    self.stdout.write(
                        "Tenant '{name}' {created_msg}.".format(
                            name=name,
                            created_msg='created successfully' if created else 'already exists (skipping)'
                        )
                    )
            else:
                tenant = self.TenantModel.objects.using(database).try_create_default(
                    description=description)

                if not tenant:
                    self.stderr.write("\nFailed to create tenant because of not unique name was generated.")
                    sys.exit(1)

                if verbosity >= 1:
                    self.stdout.write(
                        "Tenant '{name}' created successfully.".format(name=tenant.schema_name)
                    )

            if with_schema:
                tenant.create_schema(verbosity=verbosity)

        except KeyboardInterrupt:
            self.stderr.write("\nOperation cancelled.")
            sys.exit(1)
        except BaseException as e:
            self.stderr.write("Error: %s" % str(e))
            sys.exit(1)
