import rest_framework_bulk
from rest_framework import serializers
from rest_framework.fields import CurrentUserDefault, empty

from common.serializers import EnumField
from .models import EmailTemplate, EmailTemplateSharingStatus, Folder


class FolderSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    templates_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Folder
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id',
            'name',
            'created', 'updated',
            'templates_count',
        )
        read_only_fields = ('created', 'updated',)


class EmailTemplateSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    sharing = EnumField(EmailTemplateSharingStatus, default=EmailTemplateSharingStatus.PERSONAL)

    class Meta:
        model = EmailTemplate
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id',
            'name', 'description',
            'created', 'last_updated',
            'subject', 'html_content',
            'owner', 'sharing', 'folder',
        )

        read_only_fields = ('created', 'last_updated', 'owner',)
        extra_kwargs = {
            'owner': {'default': CurrentUserDefault()}
        }


class NestedFolderEmailTemplateSerializer(EmailTemplateSerializer):

    def __init__(self, instance=None, data=empty, **kwargs) -> None:
        target_folder = kwargs.pop('target_folder', kwargs.get('context', {}).get('target_folder'))
        assert target_folder
        super().__init__(instance, data, **kwargs)
        self.target_folder = target_folder

    def create(self, validated_data) -> EmailTemplate:
        instance = super().create(validated_data)
        self.target_folder.templates.add(instance)
        return instance

    def update(self, instance, validated_data) -> EmailTemplate:
        instance = super().update(instance, validated_data)
        self.target_folder.templates.add(instance)
        return instance
