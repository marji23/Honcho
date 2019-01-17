import rest_framework_bulk
from pinax.notifications.models import NoticeType
from rest_framework import serializers

from common.serializers import PhoneNumberField
from .models import Notification


class NoticeMediaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True)

    notice_types = serializers.PrimaryKeyRelatedField(many=True, default=[], queryset=NoticeType.objects.all())


class NoticeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoticeType
        fields = (
            'id',
            'label', 'display', 'description',
        )


class NotificationSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    read = serializers.BooleanField(required=False, write_only=True, )

    contact_name = serializers.CharField(read_only=True, source='extra_context.contact_name')
    company_name = serializers.CharField(read_only=True, source='extra_context.company_name')

    phone_number = PhoneNumberField(read_only=True,
                                    region=lambda field: field.context['request'].user.profile.country.code,
                                    source='extra_context.phone_number')
    context = serializers.JSONField(read_only=True, source='extra_context')

    class Meta:
        model = Notification
        fields = (
            'id',
            'created', 'action', 'read', 'read_datetime',

            'context',
            'contact_name',
            'company_name',
            'phone_number',
        )

        read_only_fields = ('created', 'action', 'read_datetime',)

        list_serializer_class = rest_framework_bulk.BulkListSerializer

    def update(self, instance: Notification, validated_data: dict) -> Notification:
        read = validated_data.pop('read', None)
        instance = super().update(instance, validated_data)
        if read is True:
            instance.mark_as_read()

        return instance
