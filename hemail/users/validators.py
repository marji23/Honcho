from django.contrib.auth import get_user_model
from plans.validators import ModelCountValidator


class MaxUsersPerTenantValidator(ModelCountValidator):
    code = 'MAX_USERS_PER_TENANT_COUNT'

    @property
    def model(self):
        return get_user_model()

    def get_queryset(self, user):
        tenant = user.profile.tenant if hasattr(user, 'profile') else None
        if not tenant:
            return super().get_queryset(user).none()

        return super().get_queryset(user).filter(profile__tenant=tenant)


max_users_per_tenant_validator = MaxUsersPerTenantValidator()
