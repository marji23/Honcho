import logging

from django.contrib import admin
from django.utils.text import Truncator
from django.utils.translation import ugettext_lazy as _

from .models import EmailTemplate, Folder

__author__ = 'yushkovskiy'

logger = logging.getLogger(__name__)


class EmailTemplateInline(admin.TabularInline):
    model = EmailTemplate
    fields = ('name', 'subject', 'html_content', 'owner', 'sharing',)
    extra = 0
    show_change_link = True


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    icon = '<i class="material-icons">folder_open</i>'
    list_display = ('id', 'name', 'created',)
    inlines = [EmailTemplateInline, ]


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    icon = '<i class="material-icons">archive</i>'
    list_display = ('id', 'name', 'description_shortened', 'subject', 'created', 'folder',)
    list_filter = ('folder', 'owner', 'sharing',)
    search_fields = ('name', 'description', 'subject', 'html_content',)
    fieldsets = [
        (None, {
            'fields': ('name', 'description', 'owner', 'folder', 'sharing',),
        }),
        (_('Content'), {
            'fields': ('subject', 'html_content'),
        }),
    ]

    def get_queryset(self, request):
        return self.model.objects.filter(default_template__isnull=True)

    def description_shortened(self, instance):
        return Truncator(instance.description.split('\n')[0]).chars(200)

    description_shortened.short_description = _("Description")
    description_shortened.admin_order_field = 'description'
