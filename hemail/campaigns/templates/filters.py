import django_filters

from common.filters import SearchFilter
from .models import EmailTemplate, Folder


class FolderFilter(django_filters.FilterSet):
    class Meta:
        model = Folder
        fields = dict(
            id=['exact', 'in'],
            name=['exact', 'icontains'],
        )


class EmailTemplateFilter(django_filters.FilterSet):
    search = SearchFilter()

    class Meta:
        model = EmailTemplate
        fields = dict(
            id=['exact', 'in'],
            owner=['exact', 'in'],
            name=['exact', 'icontains'],
            description=['exact', 'icontains'],
            subject=['exact', 'icontains'],
            html_content=['exact', 'icontains'],
            sharing=['exact'],
            folder=['exact', 'in'],
            created=['exact', 'lt', 'gt', 'range'],
            last_updated=['exact', 'lt', 'gt', 'range'],
        )
