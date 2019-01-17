import django_filters

from common.filters import OnTrueFilter
from .models import Notification


class NotificationsFilter(django_filters.FilterSet):
    unread_only = OnTrueFilter(name='read_datetime', lookup_expr='isnull')

    class Meta:
        model = Notification
        fields = {
            'id': ['exact', 'in'],
            'created': ['exact', 'gt', 'lt', 'range'],
            'action': ['exact', 'in'],
            'read_datetime': ['exact', 'gt', 'lt', 'range'],
        }
