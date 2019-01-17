from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db import connection
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.translation import ugettext_lazy as _
from tenant_schemas.utils import app_labels, get_public_schema_name, get_tenant_model, schema_context

from .models import TenantData

__author__ = 'yushkovskiy'


class TenantForm(forms.Form):
    active_tenant = forms.ModelChoiceField(
        get_tenant_model().objects.all(),
        empty_label=None,
        widget=forms.Select(attrs={"onChange": 'this.form.submit();'}),
        label=_('Tenant:'),
    )


class TenancyAppAdminMixin(object):
    @staticmethod
    def _handle_as_activate_tenant(request):
        if request.method == 'POST' and 'active_tenant' in request.POST:
            form = TenantForm(request.POST, auto_id=None)
            if form.is_valid():
                tenant = form.cleaned_data['active_tenant']
                request.session['active_tenant'] = tenant.id
                connection.set_tenant(tenant)
                return tenant
        return None

    def _get_tenant(self, request, allow_public=None):
        tenant_id = request.session.get('active_tenant')
        tenant = None
        TenantModel = get_tenant_model()
        if tenant_id is not None:
            try:
                tenant = TenantModel.objects.get(pk=tenant_id)
            except TenantModel.DoesNotExist:
                del request.session['active_tenant']
                tenant = None
        if tenant is None:
            tenant = connection.tenant

        if tenant.schema_name == get_public_schema_name():
            allow_public = allow_public if allow_public is not None else (
                self.model._meta.app_label in app_labels(settings.TENANT_APPS)
            )
            if not allow_public:
                return None
            tenant = TenantModel.objects.exclude(schema_name=get_public_schema_name()).first()
            if tenant:
                self.message_user(request,
                                  "This model does not exist in public schema."
                                  " Falling into any first tenant.",
                                  level=messages.WARNING)

        return tenant

    def delete_view(self, request, object_id, extra_context=None):
        if self._handle_as_activate_tenant(request):
            self.message_user(request,
                              "Object is not shared across tenants.",
                              level=messages.WARNING)
            # send None for object in hope nobody will use it
            return self.response_post_save_change(request, None)

        tenant = self._get_tenant(request)
        if not tenant:
            return TemplateResponse(request, 'admin/invalid_setup.html', {
                'title': _('No tenant was created'),
            })

        extra_context = extra_context or {}
        extra_context['tenancy_form'] = TenantForm(initial=dict(active_tenant=tenant))
        connection.set_tenant(tenant)
        return super().delete_view(request, object_id, extra_context)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if self._handle_as_activate_tenant(request):
            self.message_user(request,
                              "Object is not shared across tenants.",
                              level=messages.WARNING)
            # send None for object in hope nobody will use it
            return self.response_post_save_change(request, None)

        tenant = self._get_tenant(request)
        if not tenant:
            return TemplateResponse(request, 'admin/invalid_setup.html', {
                'title': _('No tenant was created'),
            })

        extra_context = extra_context or {}
        extra_context['tenancy_form'] = TenantForm(initial=dict(active_tenant=tenant))
        connection.set_tenant(tenant)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        if self._handle_as_activate_tenant(request):
            return HttpResponseRedirect(request.get_full_path())

        tenant = self._get_tenant(request)
        if not tenant:
            return TemplateResponse(request, 'admin/invalid_setup.html', {
                'title': _('No tenant was created'),
            })

        extra_context = extra_context or {}
        extra_context['tenancy_form'] = TenantForm(initial=dict(active_tenant=tenant))
        connection.set_tenant(tenant)
        return super().changelist_view(request, extra_context)


def activate_tenant(model_admin, request, queryset):
    tenant = queryset.first()
    request.session['active_tenant'] = tenant.id
    model_admin.message_user(request,
                             "Entered tenant %s" % str(tenant))


activate_tenant.short_description = 'Activate tenant'


@admin.register(TenantData)
class TenantDataAdmin(admin.ModelAdmin):
    list_display = ('schema_name', 'domain_url', 'description', 'created_on',)
    verbosity = 1

    actions = [activate_tenant, ]

    def save_model(self, request, tenant, form, change):
        # make sure that we are in `public` schema
        with schema_context(get_public_schema_name()):
            super().save_model(request, tenant, form, change)
            try:
                tenant.create_schema(check_if_exists=True, verbosity=self.verbosity)
            except BaseException:
                # We failed creating the tenant, delete what we created and
                # re-raise the exception
                tenant.delete(force_drop=True)
                raise
