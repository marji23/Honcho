from typing import Optional

import rest_framework_bulk
from django_countries import countries
from rest_framework import serializers
from rest_framework.fields import CurrentUserDefault, Field, empty

from common.serializers import PhoneNumberField, nested_view_contextual_default
from .models import Contact, ContactList, Note


def get_region(field: Field) -> Optional[str]:
    request = field.context['request']
    if request.user.profile.country:
        return request.user.profile.country.code
    if field.parent.instance and field.parent.instance.country:
        code = countries.by_name(field.parent.instance.country)
        if code:
            return code
    if hasattr(request, 'geo_data') and not request.geo_data.is_unknown:
        return request.geo_data.country_code
    return None


class ContactSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    lists = serializers.PrimaryKeyRelatedField(many=True, queryset=ContactList.objects.all(), default=[])
    phone_number = PhoneNumberField(allow_blank=True,
                                    required=False,
                                    region=get_region)

    class Meta:
        model = Contact
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id',
            'email',
            'title', 'first_name', 'last_name',
            'phone_number',
            'blacklisted',
            'company_name',
            'timezone',
            'city', 'state', 'country', 'street_address', 'zip_code',
            'lists',
            'campaigns',
        )

    @classmethod
    def many_init(cls, *args, **kwargs):
        class BulkContactSerializer(cls):
            """
            We need to override `email` field to remove UniqueValidator from it
            and be sure that it should be required.
            """
            email = serializers.EmailField()

        return super(ContactSerializer, BulkContactSerializer).many_init(*args, **kwargs)


class ContactListSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    contacts_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContactList
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = ('id', 'name', 'contacts_count', 'contacts')


class NestedContactListContactSerializer(ContactSerializer):

    def __init__(self, instance=None, data=empty, **kwargs) -> None:
        target_list = kwargs.pop('target_list', kwargs.get('context', {}).get('target_list'))
        assert target_list
        super().__init__(instance, data, **kwargs)
        self.target_list = target_list

    def create(self, validated_data) -> Contact:
        instance = super().create(validated_data)
        self.target_list.contacts.add(instance)
        return instance

    def update(self, instance, validated_data) -> Contact:
        instance = super().update(instance, validated_data)
        self.target_list.contacts.add(instance)
        return instance


class NestedContactNoteSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    contact = serializers.HiddenField(default=nested_view_contextual_default(Contact))
    author = serializers.HiddenField(default=CurrentUserDefault())

    class Meta:
        model = Note
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id', 'created', 'updated',
            'topic', 'content', 'private', 'author',
            'contact',
        )
        read_only_fields = ('created', 'updated',)
