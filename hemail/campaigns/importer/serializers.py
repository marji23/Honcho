from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

from common.serializers import ContextualPrimaryKeyRelatedField
from files.models import FileUpload
from ..contacts.models import ContactList
from ..contacts.serializers import ContactSerializer
from ..models import Campaign


class ImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField(help_text=_('Number of created contacts'))
    updated = serializers.IntegerField(help_text=_('Number of updated contacts'))
    skipped = serializers.IntegerField(help_text=_('Number of contacts which were skipped during importing'))
    errors = serializers.DictField(help_text=_('Error which we found during data validation'))
    failed_rows_file = serializers.PrimaryKeyRelatedField(
        queryset=FileUpload.objects.all(),
        default=None,
        allow_null=True,
    )


class SniffQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False,
                                     default=5,
                                     min_value=0)


class SniffResultSerializer(serializers.Serializer):
    options = serializers.DictField(child=serializers.CharField())
    fields = serializers.ListField(serializers.CharField())
    rows = serializers.ListField()
    headers = serializers.DictField(child=serializers.IntegerField())


class FileUploadOptionsSerializer(serializers.Serializer):
    has_headers = serializers.BooleanField(default=True)
    delimiter = serializers.CharField(default=',')
    encoding = serializers.CharField(default=settings.DEFAULT_CHARSET)
    allow_update = serializers.BooleanField(default=True)
    atomic = serializers.BooleanField(default=False)
    create_failed_rows_file = serializers.BooleanField(
        default=False,
        help_text=_('Generate and store file with rows that we failed to parse'))
    detailed_errors_limit = serializers.IntegerField(
        default=20,
        help_text=_('If case of errors response will contain only this number of detailed errors description'))
    campaign = serializers.PrimaryKeyRelatedField(
        queryset=Campaign.objects.all(),
        default=None,
        allow_null=True,
    )
    contact_list = serializers.PrimaryKeyRelatedField(
        queryset=ContactList.objects.all(),
        default=None,
        allow_null=True,
    )


class FileUploadSerializer(serializers.Serializer):
    options = FileUploadOptionsSerializer(default=dict())
    headers = serializers.DictField(child=serializers.IntegerField())
    file = ContextualPrimaryKeyRelatedField(
        queryset=FileUpload.objects.none(),
        queryset_filter=lambda qs, context: (
            context['request'].user.uploaded_files.all()
            if context['request'].user.is_authenticated
            else qs
        )
    )

    default_error_messages = {
        'invalid_headers': _('Invalid headers: {headers}.'),
        'required_headers': _('Required headers: {headers}.'),
    }

    def __init__(self, *args: list, **kwargs: dict) -> None:
        contact_serializer = kwargs.pop('contact_serializer', kwargs.get('context', {}).get('contact_serializer'))
        assert contact_serializer
        super().__init__(*args, **kwargs)
        self.contact_serializer = contact_serializer

    def validate_headers(self, value: dict) -> dict:
        fields = {name: field for name, field in self.contact_serializer.get_fields().items() if not field.read_only}

        contact_serializer_keys = fields.keys()
        headers_value = set(value.keys())
        if not headers_value.issubset(contact_serializer_keys):
            invalid_headers = ' '.join(headers_value - set(contact_serializer_keys))
            raise self.fail('invalid_headers', headers=invalid_headers)

        fields = {name: field for name, field in fields.items() if field.required}
        required_keys = fields.keys()
        if not set(required_keys).issubset(headers_value):
            required_headers = ' '.join(set(required_keys) - headers_value)
            raise self.fail('required_headers', headers=required_headers)

        return value

    def create(self, validated_data: dict) -> dict:
        return validated_data

    def update(self, instance: dict, validated_data: dict) -> dict:
        instance.update(validated_data)
        return instance


class CsvContactSerializer(ContactSerializer):
    """
    We need to override `email` field to remove UniqueValidator from it
    and be sure that it should be required.
    """
    email = serializers.EmailField()
