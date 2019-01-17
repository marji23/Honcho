import django_filters

from common.filters import NumberInAllFilter, NumberInAnyFilter, SearchFilter
from .models import Contact, Note


class ContactsFilter(django_filters.FilterSet):
    search = SearchFilter()

    campaigns__in = NumberInAnyFilter(name='campaigns')
    campaigns = NumberInAllFilter(name='campaigns')

    lists__in = NumberInAnyFilter(name='lists')
    lists = NumberInAllFilter(name='lists')

    class Meta:
        model = Contact
        fields = {
            'id': ['exact', 'in'],
            'email': ['exact', 'icontains'],
            'title': ['exact', 'icontains'], 'first_name': ['exact', 'icontains'], 'last_name': ['exact', 'icontains'],
            'blacklisted': ['exact'],
            'company_name': ['exact', 'icontains'],
            'timezone': ['exact'],
            'city': ['exact', 'icontains'],
            'state': ['exact', 'icontains'],
            'country': ['exact', 'icontains'],
            'street_address': ['exact', 'icontains'],
            'zip_code': ['exact', 'icontains'],
        }

        # TODO(pzaytsev): add filtering of 'phone_number'


class NotesFilter(django_filters.FilterSet):
    search = SearchFilter()

    class Meta:
        model = Note
        fields = {
            'id': ['exact', 'in'],
            'created': ['exact', 'lt', 'gt', 'range'],
            'updated': ['exact', 'lt', 'gt', 'range'],
            'topic': ['exact', 'icontains'],
            'content': ['exact', 'icontains'],
            'private': ['exact'],
            'author': ['exact', 'in'],
        }
