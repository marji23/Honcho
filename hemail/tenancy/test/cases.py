from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory as DjangoRequestFactory, TestCase
from django.utils.deprecation import MiddlewareMixin
from rest_framework.test import APIRequestFactory
from tenant_schemas.middleware import BaseTenantMiddleware
from tenant_schemas.utils import get_public_schema_name, get_tenant_model

from tenancy.middleware import UserBasedTenantMiddleware

_MODEL_OR_NAME_OR_INDEX_DEFAULT = object()


class TenantsTestCase(TestCase):
    tenants_names = ['test']
    auto_create_schema = False
    verbosity = 0

    @classmethod
    def setUpClass(cls):
        cls.sync_shared()
        cls.tenants = dict()
        TenantModel = get_tenant_model()
        for tenant in cls.tenants_names:
            tenant_domain = 'tenant.%s.com' % tenant
            tenant_instance = TenantModel(domain_url=tenant_domain, schema_name=tenant)
            tenant_instance.save(verbosity=cls.verbosity)
            if cls.auto_create_schema:
                tenant_instance.create_schema(verbosity=cls.verbosity)
            cls.tenants[tenant] = tenant_instance

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()

        for schema_name, tenant in cls.tenants.items():
            tenant.delete(force_drop=True)

    @classmethod
    def create_superuser(cls, *args, **kwargs):
        model_or_name_or_index = kwargs.pop('tenant', _MODEL_OR_NAME_OR_INDEX_DEFAULT)
        UserModel = get_user_model()

        user = UserModel.objects.create_superuser(*args, **kwargs)
        if model_or_name_or_index is not _MODEL_OR_NAME_OR_INDEX_DEFAULT:
            user.profile.tenant = cls.get_tenant(model_or_name_or_index)
            user.profile.save()

        return user

    @classmethod
    def get_tenant(cls, model_or_name_or_index=None):
        if model_or_name_or_index is None:
            return cls.get_current_tenant()

        if isinstance(model_or_name_or_index, int):
            model_or_name_or_index = cls.tenants_names[model_or_name_or_index]

        # TODO: check what is the name of basic string object for this version
        if isinstance(model_or_name_or_index, str):
            return cls.tenants[model_or_name_or_index]
        if isinstance(model_or_name_or_index, get_tenant_model()):
            return model_or_name_or_index

        raise TypeError('Invalid argument type %s' % model_or_name_or_index)

    @classmethod
    def set_tenant(cls, model_or_name_or_index):
        tenant = cls.get_tenant(model_or_name_or_index)
        connection.set_tenant(tenant)

    @classmethod
    def get_current_tenant(cls):
        return connection.tenant

    @classmethod
    def sync_shared(cls):
        call_command('migrate_schemas',
                     schema_name=get_public_schema_name(),
                     interactive=False,
                     verbosity=cls.verbosity)


class FakeAuthMiddleware(MiddlewareMixin):
    def __init__(self, user, get_response=None):
        super().__init__(get_response)
        self.user = user

    def process_request(self, request):
        request.user = self.user


class FakeTenantMiddleware(BaseTenantMiddleware):
    def __init__(self, tenant) -> None:
        super().__init__()
        self.tenant = tenant

    def get_tenant(self, model, hostname, request):
        return self.tenant


class _TenantsMixin(object):
    tm = UserBasedTenantMiddleware()

    def __init__(self, tenant=None, force_authenticate=None, middlewares=None, *args, **kwargs) -> None:
        self.middlewares = middlewares
        if self.middlewares is None:
            self.middlewares = []

            if force_authenticate:
                self.middlewares.append(FakeAuthMiddleware(force_authenticate))

            if tenant:
                self.middlewares.append(FakeTenantMiddleware(tenant))
            else:
                self.middlewares.append(self.tm)

        super().__init__(*args, **kwargs)

    def generic(self, *args, **kwargs):
        return self._process(super().generic(*args, **kwargs))

    def _process(self, request):
        for middleware in self.middlewares:
            middleware.process_request(request)
        return request


class TenantsRequestFactory(_TenantsMixin, DjangoRequestFactory):
    pass


class TenantsAPIRequestFactory(_TenantsMixin, APIRequestFactory):
    pass
