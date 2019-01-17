import logging
from typing import Optional
from urllib import parse
from urllib.parse import urljoin

import jwt
from allauth.account import app_settings as allauth_settings
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.account.utils import complete_signup, setup_user_email
from allauth.utils import email_address_exists
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _
from libthumbor import CryptoURL
from rest_framework import serializers, status
from rest_framework.fields import empty
from rest_framework_jwt.compat import get_username_field
from rest_framework_jwt.settings import api_settings

from common.serializers import ContextualPrimaryKeyRelatedField, EnumField
from files.models import FileUpload
from .models import Profile
from .utils import AuthAction, AuthProvider, get_login_token_with_auth_info

logger = logging.getLogger(__name__)

jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER
jwt_decode_handler = api_settings.JWT_DECODE_HANDLER
jwt_get_username_from_payload = api_settings.JWT_PAYLOAD_GET_USERNAME_HANDLER
jwt_response_payload_handler = api_settings.JWT_RESPONSE_PAYLOAD_HANDLER

_UserModel = get_user_model()

_crypto = CryptoURL(key=settings.THUMBOR_SECURITY_KEY)
_THUMBNAILING_URL = settings.THUMBOR_THUMBNAILING_URL.rstrip('/')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = _UserModel
        fields = ('id', 'email', 'first_name', 'last_name', 'is_active', 'last_login', 'date_joined',)

    def get_queryset(self):
        user = self.context['request'].user
        tenant = user.profile.tenant
        return super().get_queryset().filter(profile__tenant=tenant)


class AuthInfoSerializer(serializers.Serializer):
    action = EnumField(AuthAction)
    provider = EnumField(AuthProvider)
    social = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AvatarChangeSerializer(serializers.Serializer):
    file = ContextualPrimaryKeyRelatedField(
        queryset=FileUpload.objects.none(),
        queryset_filter=lambda qs, context: (
            context['request'].user.uploaded_files.all()
            if context['request'].user.is_authenticated
            else qs
        ),
        write_only=True,
    )


class AvatarSerializer(serializers.Serializer):
    thumbnail = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    def get_thumbnail(self, obj: Profile):
        options = dict(width=200, height=200)

        options.update(smart=True,
                       image_url=parse.quote(self.context['request'].build_absolute_uri(obj.avatar.url)))

        return urljoin(_THUMBNAILING_URL, _crypto.generate(**options))

    def get_url(self, obj: Profile):
        return self.context['request'].build_absolute_uri(obj.avatar.url)

    def to_representation(self, instance: Profile):
        if not instance.avatar:
            return None
        return super().to_representation(instance)


class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True, source='user.id')
    email = serializers.EmailField(read_only=True, source='user.email')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')

    permissions = serializers.ListField(child=serializers.CharField(),
                                        read_only=True,
                                        source='user.get_all_permissions')

    has_password = serializers.BooleanField(read_only=True,
                                            source='user.has_usable_password')

    auth_info = serializers.SerializerMethodField(required=False, allow_null=True)

    account_expired = serializers.BooleanField(read_only=True,
                                               help_text='account was expired state',
                                               source='user.userplan.is_expired', )
    account_over_quotas = serializers.BooleanField(read_only=True,
                                                   help_text='set when account is over quotas so it is not active',
                                                   source='request.user.userplan.is_active', )
    expire_in_days = serializers.IntegerField(read_only=True,
                                              help_text='number of days to account expiration',
                                              source='user.userplan.days_left', )

    avatar = AvatarSerializer(read_only=True, source='*')

    class Meta:
        model = Profile
        fields = (
            'id',
            'email', 'first_name', 'last_name',
            'permissions',
            'timezone',
            'has_password', 'auth_info',
            'account_expired', 'account_over_quotas', 'expire_in_days',
            'avatar',
        )

    def __init__(self, instance=None, data=empty, **kwargs) -> None:
        super().__init__(instance, data, **kwargs)
        request = self.context['request']

        self._auth_info = None
        from rest_framework_jwt.authentication import JSONWebTokenAuthentication
        if isinstance(request.successful_authenticator, JSONWebTokenAuthentication):
            try:
                self._auth_info = jwt_decode_handler(request.auth).get('auth_info')
            except jwt.ExpiredSignature:
                logging.warning(_('Signature has expired.'))
            except jwt.DecodeError:
                logging.warning(_('Error decoding signature.'))
            except jwt.InvalidTokenError:
                logging.exception('Unexpected decoding error.')

    def get_auth_info(self, obj: Profile) -> Optional[dict]:
        return self._auth_info

    def update(self, instance: Profile, validated_data: dict) -> Profile:
        user_data = validated_data.pop('user', None)
        if user_data:
            for attr, value in user_data.items():
                setattr(instance.user, attr, value)
            instance.user.save()

        return super().update(instance, validated_data)


class EmailLoginLinkSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance, data, **kwargs)
        request = self.context['request']
        self.adapter = get_adapter(request)

    def validate_email(self, email):
        email = self.adapter.clean_email(email)
        return email

    def create(self, validated_data):
        return validated_data['email']


class ObtainJSONWebTokenFromMagicLinkSerializer(serializers.Serializer):
    """
    Check the veracity of an access token.
    """
    token = serializers.CharField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance, data, **kwargs)
        self._request = self.context['request']

    def validate(self, attrs):
        token = attrs['token']

        payload = self._check_payload(token=token)

        username = jwt_get_username_from_payload(payload)
        if username:
            user = self._check_user(username)
            new_token = get_login_token_with_auth_info(user, AuthAction.LOGIN, AuthProvider.EMAIL)
            self.instance = dict(token=new_token, user=user)
            return self.instance

        if payload['provider'] == AuthProvider.SOCIAL.value:
            email = self._check_email(payload['email'], False)
            try:
                email_address = EmailAddress.objects.get(email=email)
            except EmailAddress.DoesNotExist:
                raise serializers.ValidationError(_("User doesn't exist."))
            ret = EmailConfirmationHMAC(email_address)
            ret.confirm(self._request)

            user = email_address.user
            new_token = get_login_token_with_auth_info(user, AuthAction.REGISTRATION,
                                                       AuthProvider.SOCIAL, payload.get('social'))
            self.instance = dict(token=new_token, user=user)
            return self.instance

        email = self._check_email(payload['email'], True)
        return dict(email=email)

    def _check_payload(self, token: str) -> dict:
        # Check payload valid (based off of JSONWebTokenAuthentication)
        try:
            return jwt_decode_handler(token)
        except jwt.ExpiredSignature:
            raise serializers.ValidationError(_('Signature has expired.'))
        except jwt.DecodeError:
            raise serializers.ValidationError(_('Error decoding signature.'))
        except jwt.InvalidTokenError:
            logging.exception('Unexpected decoding error.')
            raise serializers.ValidationError(_('Decoding error.'))

    def _check_user(self, username: str):
        username_field = get_username_field()

        # Make sure user exists
        try:
            user = _UserModel.objects.get(**{username_field: username})
        except _UserModel.DoesNotExist:
            raise serializers.ValidationError(_("User doesn't exist."))
        except _UserModel.MultipleObjectsReturned:
            logging.exception("Improperly configured username field: username should be unique")
            raise serializers.ValidationError(_("User cannot be determined."))

        if not user.is_active:
            raise serializers.ValidationError(_('User account is disabled.'))

        return user

    def _check_email(self, email: str, check_exists: bool) -> str:
        adapter = get_adapter(self._request)
        email = adapter.clean_email(email)

        if not email:
            raise serializers.ValidationError(
                _("Invalid e-mail address."))

        if check_exists and email_address_exists(email):
            raise serializers.ValidationError(
                _("A user is already registered with this e-mail address."))

        return email

    def _new_user(self, email):
        adapter = get_adapter(self._request)
        user = adapter.new_user(self._request)
        self.cleaned_data = dict(email=email)
        adapter.save_user(self._request, user, self)
        email_address = setup_user_email(self._request, user, [])
        adapter.confirm_email(self._request, email_address)

        return user

    def create(self, validated_data):
        user = self._new_user(validated_data['email'])

        respond = complete_signup(self._request, user, allauth_settings.EmailVerificationMethod.NONE, '#')
        assert respond.status_code == status.HTTP_302_FOUND

        token = get_login_token_with_auth_info(user, AuthAction.REGISTRATION, AuthProvider.EMAIL)
        return dict(token=token, user=user)

    def update(self, instance, validated_data):
        return instance

    def to_representation(self, instance):
        return jwt_response_payload_handler(instance['token'], instance['user'], self._request)
