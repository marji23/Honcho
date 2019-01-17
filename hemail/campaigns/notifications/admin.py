from django.contrib import admin

from .models import Notification

__author__ = 'yushkovskiy'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'created', 'read_datetime',)
    list_filter = ('user', 'action',)
