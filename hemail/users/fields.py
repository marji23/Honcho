from django.contrib.auth import get_user_model

from common.serializers import ContextualPrimaryKeyRelatedField


class TenantUsersPrimaryKeyRelatedField(ContextualPrimaryKeyRelatedField):
    @staticmethod
    def filter_by_tenant_users(queryset, context):
        user = context['request'].user
        tenant = user.profile.tenant
        return queryset.filter(profile__in=tenant.users.all())

    queryset = get_user_model().objects.all()
    queryset_filter = filter_by_tenant_users
