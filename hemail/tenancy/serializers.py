from rest_framework import serializers

from .models import TenantData


class TenantDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantData
        fields = ('domain_url', 'schema_name', 'description', 'created_on',)
