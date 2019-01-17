import django_filters
from django_mailbox.models import Message

from common.filters import NumberInAnyFilter, SearchFilter
from .models import ContactLead, Participation


class ParticipationFilter(django_filters.FilterSet):
    campaign__in = NumberInAnyFilter(name='campaign')
    contact__in = NumberInAnyFilter(name='contact')

    class Meta:
        model = Participation
        fields = dict(
            id=['exact', 'in'],
            campaign=['exact'],
            contact=['exact'],
            status=['exact', 'in'],
            activation=['exact', 'lt', 'gt', 'range', 'isnull'],
        )


class MessageFilter(django_filters.FilterSet):
    search = SearchFilter()

    class Meta:
        model = Message
        fields = dict(
            id=['exact', 'in'],
            message_id=['exact'],
        )


class ContactLeadFilter(django_filters.FilterSet):
    generator__in = NumberInAnyFilter(name='generator')

    class Meta:
        model = ContactLead
        fields = dict(
            id=['exact', 'in'],
            generator=['exact'],

            city=['exact', 'icontains'],
            state=['exact', 'icontains'],
            country=['exact', 'icontains'],
            street_address=['exact', 'icontains'],
            zip_code=['exact', 'startswith'],

            email=['exact', 'icontains', 'startswith'],

            first_name=['exact', 'icontains'],
            last_name=['exact', 'icontains'],
            title=['exact', 'icontains'],

            company_name=['exact', 'icontains'],
            company_employee_count=['exact', 'in'],
            company_revenue=['exact', 'in'],
            department=['exact', 'in'],
            level=['exact', 'in'],
        )
