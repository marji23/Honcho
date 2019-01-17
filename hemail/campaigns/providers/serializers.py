from allauth.socialaccount import providers
from allauth.utils import email_address_exists
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, serializers

from common.serializers import ContextualDefault, EnumByNameField
from .configuration import (
    AuthenticationType, EncryptionType, IncomingConfiguration, OutgoingConfiguration, ProviderConfiguration
)
from .models import ConnectionStatus, CoolMailbox, EmailAccount, SmtpConnectionSettings
from .utils import get_default_sender_name, get_default_signature


class GuessingProviderConfigurationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class BasicConfigurationSerializer(serializers.Serializer):
    host = serializers.CharField()
    port = serializers.IntegerField()
    encryption = EnumByNameField(EncryptionType)
    username = serializers.CharField(required=False, allow_blank=True, source='username_or_template')
    authentication = EnumByNameField(AuthenticationType)
    provider = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        instance.hostname = validated_data.get('host', instance.host)
        instance.port = validated_data.get('port', instance.port)
        instance.encryption = validated_data.get('encryption', instance.encryption)
        instance.username_or_template = validated_data.get('username', instance.username_or_template)
        instance.authentication = validated_data.get('authentication', instance.authentications)
        instance.provider = validated_data.get('provider', instance.provider)
        return instance


class IncomingConfigurationSerializer(BasicConfigurationSerializer):
    def create(self, validated_data):
        return IncomingConfiguration(**validated_data)


class OutgoingConfigurationSerializer(BasicConfigurationSerializer):
    def create(self, validated_data):
        return OutgoingConfiguration(**validated_data)


class ProviderConfigurationSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    incoming = IncomingConfigurationSerializer()
    outgoing = OutgoingConfigurationSerializer()

    def create(self, validated_data: dict) -> ProviderConfiguration:
        return ProviderConfiguration(
            validated_data.get('name'),
            IncomingConfigurationSerializer().create(validated_data['incoming']),
            OutgoingConfigurationSerializer().create(validated_data['outgoing']),
        )

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.incoming = IncomingConfigurationSerializer().update(
            instance.incoming, validated_data['incoming']
        )
        instance.outgoing = OutgoingConfigurationSerializer().update(
            instance.outgoing, validated_data['outgoing']
        )
        return instance


class IncomingMailBoxSerializer(serializers.ModelSerializer):
    host = serializers.CharField(
        source='location',
        help_text='location (domain and path) of messages'
    )
    port = serializers.IntegerField(
        help_text='port to use for fetching messages',
    )
    encryption = EnumByNameField(
        EncryptionType,
        source='encryption_type',
        help_text="whether or not this mailbox's connection uses SSL or STARTTLS",
    )
    username = serializers.CharField(
        help_text='username to use for fetching messages',
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, allow_null=True,
    )
    provider = serializers.ChoiceField(
        choices=list(providers.registry.as_choices()),
        required=False, allow_blank=True, allow_null=True,
    )
    authentication = EnumByNameField(AuthenticationType)

    status = EnumByNameField(ConnectionStatus, read_only=True)

    class Meta:
        model = CoolMailbox
        fields = ('host', 'port', 'encryption',
                  'username', 'password',
                  'provider', 'authentication',
                  'status', 'status_description',)

    @classmethod
    def remap(cls, validated_data: dict) -> dict:
        result = validated_data.copy()
        for src, dest in {
            'location': 'host',
            'encryption_type': 'encryption',
            'username': 'username_or_template',
        }.items():
            if src in result:
                result[dest] = result.pop(src)
        return result

    def validate(self, attrs: dict) -> dict:
        validated = super().validate(attrs)

        password = validated.get('password')
        provider = validated.get('provider')

        authentication = validated.get('authentication')
        if authentication == AuthenticationType.BASIC:
            if not password:
                msg = _('Password is required for basic authentication.')
                raise exceptions.ValidationError(msg)
        elif authentication == AuthenticationType.OAUTH2:
            if provider is None:
                msg = _('Provider is required for oauth2 authentication.')
                raise exceptions.ValidationError(msg)

        return attrs

    def create(self, validated_data: dict) -> CoolMailbox:
        uri = CoolMailbox.get_uri_from(
            IncomingConfiguration(
                host=validated_data.get('location'),
                port=validated_data.get('port'),
                encryption=validated_data.get('encryption_type'),
                username_or_template=validated_data.get('username'),
                authentication=validated_data.get('authentication'),
            ),
            validated_data.get('password'),
            validated_data.get('provider'),
        )
        return CoolMailbox.objects.create(uri=uri)


class OutgoingSmtpConnectionSettingsSerializer(serializers.ModelSerializer):
    host = serializers.CharField(
        source='location',
        help_text='location (domain and path) of messages'
    )
    port = serializers.IntegerField(
        help_text='port to use for fetching messages',
    )
    encryption = EnumByNameField(
        EncryptionType,
        source='encryption_type',
        help_text="whether or not this mailbox's connection uses SSL or STARTTLS",
    )
    username = serializers.CharField(
        help_text='username to use for fetching messages',
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, allow_null=True,
    )
    provider = serializers.ChoiceField(
        choices=list(providers.registry.as_choices()),
        required=False, allow_blank=True, allow_null=True,
    )
    authentication = EnumByNameField(AuthenticationType)

    status = EnumByNameField(ConnectionStatus, read_only=True)

    class Meta:
        model = SmtpConnectionSettings
        fields = ('host', 'port', 'encryption',
                  'username', 'password',
                  'provider', 'authentication',
                  'status', 'status_description',)

    @classmethod
    def remap(cls, validated_data: dict) -> dict:
        result = validated_data.copy()
        for src, dest in {
            'location': 'host',
            'encryption_type': 'encryption',
            'username': 'username_or_template',
        }.items():
            if src in result:
                result[dest] = result.pop(src)
        return result

    def validate(self, attrs: dict) -> dict:
        validated = super().validate(attrs)

        password = validated.get('password')
        provider = validated.get('provider')

        authentication = validated.get('authentication')
        if authentication == AuthenticationType.BASIC:
            if not password:
                msg = _('Password is required for basic authentication.')
                raise exceptions.ValidationError(msg)
        elif authentication == AuthenticationType.OAUTH2:
            if provider is None:
                msg = _('Provider is required for oauth2 authentication.')
                raise exceptions.ValidationError(msg)

        return attrs

    def create(self, validated_data: dict) -> SmtpConnectionSettings:
        uri = SmtpConnectionSettings.get_uri_from(
            OutgoingConfiguration(
                host=validated_data.get('location'),
                port=validated_data.get('port'),
                encryption=validated_data.get('encryption_type'),
                username_or_template=validated_data.get('username'),
                authentication=validated_data.get('authentication'),
            ),
            validated_data.get('password'),
            validated_data.get('provider'),
        )
        return SmtpConnectionSettings.objects.create(uri=uri)


class EmailAccountSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    incoming = IncomingMailBoxSerializer(required=False, allow_null=True)
    outgoing = OutgoingSmtpConnectionSettingsSerializer(required=False, allow_null=True)
    default_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        help_text='password which is used in case password fields in incoming and outgoing configurations skipped'
    )

    sender_name = serializers.CharField(default=ContextualDefault(
        lambda field: get_default_sender_name(field.context['request'].user)))
    signature = serializers.CharField(allow_blank=True, default=ContextualDefault(
        lambda field: get_default_signature(field.context['request'].user)
    ))

    class Meta:
        model = EmailAccount
        fields = ('id', 'user', 'email', 'sender_name', 'incoming', 'outgoing', 'default_password',
                  'signature', 'default',)

    def create(self, validated_data: dict) -> EmailAccount:
        incoming_data = validated_data.pop('incoming', None)
        assert incoming_data is not None, 'You can user `create` only for fully defined data'

        incoming_uri = CoolMailbox.get_uri_from(
            IncomingConfiguration(
                host=incoming_data.get('location'),
                port=incoming_data.get('port'),
                encryption=incoming_data.get('encryption_type'),
                username_or_template=incoming_data.get('username'),
                authentication=incoming_data.get('authentication'),
            ),
            incoming_data.get('password'),
            incoming_data.get('provider'),
        )
        validated_data['incoming'] = CoolMailbox.objects.create(uri=incoming_uri)

        outgoing_data = validated_data.pop('outgoing', None)
        assert outgoing_data is not None, 'You can user `create` only for fully defined data'
        outgoing_uri = SmtpConnectionSettings.get_uri_from(
            OutgoingConfiguration(
                host=outgoing_data.get('location'),
                port=outgoing_data.get('port'),
                encryption=outgoing_data.get('encryption_type'),
                username_or_template=outgoing_data.get('username'),
                authentication=outgoing_data.get('authentication'),
            ),
            outgoing_data.get('password'),
            outgoing_data.get('provider'),
        )
        validated_data['outgoing'] = SmtpConnectionSettings.objects.create(uri=outgoing_uri)

        return super().create(validated_data)

    def update(self, instance: EmailAccount, validated_data: dict) -> EmailAccount:
        default = validated_data.get('default', False)
        if default:
            validated_data.pop('default')
        incoming_data = validated_data.pop('incoming', {})
        outgoing_data = validated_data.pop('outgoing', {})

        instance = super().update(instance, validated_data)

        if default:
            instance.set_as_default()
        if incoming_data:
            mailbox = instance.incoming
            password = incoming_data.pop('password', mailbox.password)
            provider = incoming_data.pop('provider', mailbox.provider)
            incoming_configuration = mailbox.to_configuration()
            for k, v in self.fields.get('incoming').remap(incoming_data).items():
                setattr(incoming_configuration, k, v)
            mailbox.uri = CoolMailbox.get_uri_from(
                incoming_configuration,
                password=password,
                provider=provider
            )
            mailbox.drop_status()
            mailbox.save()
        if outgoing_data:
            smtp_connection_settings = instance.outgoing
            password = outgoing_data.pop('password', smtp_connection_settings.password)
            provider = outgoing_data.pop('provider', smtp_connection_settings.provider)
            outgoing_configuration = smtp_connection_settings.to_configuration()
            for k, v in self.fields.get('outgoing').remap(outgoing_data).items():
                setattr(outgoing_configuration, k, v)
            smtp_connection_settings.uri = SmtpConnectionSettings.get_uri_from(
                outgoing_configuration,
                password=password,
                provider=provider
            )
            smtp_connection_settings.drop_status()
            smtp_connection_settings.save()

        return instance

    def to_internal_value(self, data: dict) -> dict:
        if 'default_password' not in data:
            return super().to_internal_value(data)

        data = data.copy()
        default_password = data.pop('default_password')
        for path in ['incoming.password', 'outgoing.password', ]:
            if not data.get(path, None):
                data[path] = default_password

        return super().to_internal_value(data)

    def validate(self, attrs: dict) -> dict:
        if email_address_exists(attrs.get('email'), attrs.get('user')):
            raise serializers.ValidationError(
                _("A user is already registered with this e-mail address."))

        return super().validate(attrs)

    def validate_default(self, value: bool) -> bool:
        if not value and self.instance and self.instance.default:
            raise serializers.ValidationError(
                "You can not set provider to be not 'default'. Choose other one to be default."
            )
        return value
