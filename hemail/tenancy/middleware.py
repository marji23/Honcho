from tenant_schemas.middleware import BaseTenantMiddleware
from tenant_schemas.utils import get_public_schema_name

from .models import TenantData


class UserBasedTenantMiddleware(BaseTenantMiddleware):
    _fake_tenant = TenantData(
        domain_url='localhost',
        schema_name=get_public_schema_name()
    )

    def get_tenant(self, model, hostname, request):
        user = request.user
        if user and user.is_authenticated:
            tenant = user.profile.tenant if hasattr(user, 'profile') else None
            if tenant:
                return tenant

        return self._fake_tenant
