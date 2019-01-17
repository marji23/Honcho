from django.contrib import admin

from .models import FileUpload

__author__ = 'yushkovskiy'


def delete_expired(file_upload_admin: 'FileUploadAdmin', request, queryset) -> None:
    deleted, _ = queryset.delete_expired()

    file_upload_admin.message_user(request,
                                   "Removed %d files" % deleted)


delete_expired.short_description = 'Delete expired files'


@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'mimetype', 'created',)
    search_fields = ('name',)
    list_filter = ('owner', 'mimetype',)

    readonly_fields = ('name', 'expiration_datetime',)

    actions = [delete_expired, ]
