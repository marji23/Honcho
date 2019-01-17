from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from tenant_schemas.utils import tenant_context

from .models import Profile

__author__ = 'yushkovskiy'


class ProfileInline(admin.TabularInline):
    model = Profile
    extra = 0


class TenantUserAdmin(UserAdmin):
    inlines = [ProfileInline, ]
    list_display = UserAdmin.list_display + ('last_login',)

    def get_actions(self, request):
        """
        We are removing delete action because we need to enter in each user's tenant to be able to
         collect objects which are going to be removed. It is not trivial because default action use queryset.
        """
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def delete_view(self, request, object_id, extra_context=None):
        from django.contrib.admin.options import TO_FIELD_VAR

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            from django.contrib.admin.exceptions import DisallowedModelAdminToField

            raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

        from django.contrib.admin.utils import unquote
        user = self.get_object(request, unquote(object_id), to_field)
        tenant = user.profile.tenant if hasattr(user, 'profile') else None
        if not tenant:
            return super().delete_view(request, object_id, extra_context)
        with tenant_context(tenant):
            return super().delete_view(request, object_id, extra_context)


admin.site.unregister(User)
admin.site.register(User, TenantUserAdmin)
