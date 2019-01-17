import datetime
import enum
import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import urljoin

from allauth.account import app_settings as allauth_settings
from allauth.account.adapter import get_adapter
from allauth.account.utils import filter_users_by_email
from allauth.socialaccount.models import SocialApp, SocialToken
from allauth.utils import build_absolute_uri
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import resolve_url
from django.template.loader import render_to_string
from django.urls import NoReverseMatch
from django.utils import timezone
from requests import Response
from requests.adapters import HTTPAdapter
from requests_oauthlib import OAuth2Session
from rest_framework.reverse import reverse
from rest_framework_jwt.settings import api_settings

logger = logging.getLogger(__name__)

jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER


@enum.unique
class AuthAction(enum.Enum):
    LOGIN = 'login'
    REGISTRATION = 'registration'


@enum.unique
class AuthProvider(enum.Enum):
    BASIC = 'basic'
    EMAIL = 'email'
    SOCIAL = 'social'


def get_login_token_with_auth_info(user,
                                   action: AuthAction,
                                   provider: AuthProvider,
                                   social_provider: Optional[str] = None) -> str:
    from .serializers import AuthInfoSerializer
    serializer = AuthInfoSerializer(data=dict(
        action=action, provider=provider, social=social_provider,
    ))
    serializer.is_valid(raise_exception=True)
    return get_login_token(user, auth_info=serializer.data)


def get_login_token(user, **kwargs) -> str:
    payload = jwt_payload_handler(user)
    payload.update(kwargs)
    token = jwt_encode_handler(payload)
    return token


def get_signup_token(email: str, provider: AuthProvider, social_provider: Optional[str] = None) -> str:
    payload = {
        'email': email,
        'provider': provider.value,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=allauth_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS)
    }
    if social_provider:
        payload['social'] = social_provider
    token = jwt_encode_handler(payload)
    return token


def get_social_next_from_referer_url(request: HttpRequest) -> str:
    return resolve_url(
        request.META.get('HTTP_ORIGIN') or
        request.META.get('HTTP_REFERER') or
        settings.USERS_ACTIVATION_URL
    )


def get_access_url(request: HttpRequest, token: str, token_param_name: str = 'key') -> str:
    try:
        url = reverse(settings.USERS_ACTIVATION_URL, args=[token])
    except NoReverseMatch:
        origin = request.META.get('HTTP_ORIGIN')
        if origin:
            url = urljoin(origin, settings.USERS_ACTIVATION_URL)
        else:
            url = settings.USERS_ACTIVATION_URL

        url = urljoin(url, '?' + token_param_name + '=' + token)

    ret = build_absolute_uri(request, url)
    return ret


class MagicLinkMailer(object):
    signup_email_template = 'users/email/email_confirmation_signup'
    login_email_template = 'users/email/email_confirmation'

    def __init__(self, request: HttpRequest):
        self.request = request
        self.adapter = get_adapter(self.request)

    @classmethod
    def get_connection(cls):
        connection = get_connection(fail_silently=False)
        return connection

    @classmethod
    def render_mail(cls, template_prefix, ctx) -> dict:
        result = {}
        for k, suffix in {
            'subject': '_subject.txt',
            'html_content': '_message.html',
            'content': '_message.txt',
        }.items():
            template_name = '{0}{1}'.format(template_prefix, suffix)
            result[k] = render_to_string(template_name, ctx).strip()

        return result

    @classmethod
    def send_signup(cls, request: HttpRequest, email: str, activate_url: str):
        current_site = get_current_site(request)
        ctx = {
            "activate_url": activate_url,
            "current_site": current_site,
        }

        messages = cls.render_mail(cls.signup_email_template, ctx)

        try:
            connection = cls.get_connection()
            msg = EmailMultiAlternatives(
                subject=''.join(messages['subject'].splitlines()),
                body=messages['content'],
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
                connection=connection,
                alternatives=[(messages['html_content'], 'text/html'), ],
            )
            connection.send_messages([msg])
        except Exception:
            logger.exception("Failed to send signup to '%s'", email)
            return False

        return True

    def send(self, email: str) -> bool:
        current_site = get_current_site(self.request)
        users = filter_users_by_email(email)
        if not users:
            token = get_signup_token(email, AuthProvider.EMAIL)
            activate_url = get_access_url(self.request, token)
            return self.send_signup(self.request, email, activate_url)

        try:
            connection = self.get_connection()
            msgs = []
            for user in users:
                token = get_login_token(user)
                activate_url = get_access_url(self.request, token)
                ctx = {
                    "activate_url": activate_url,
                    "current_site": current_site,
                }

                messages = self.render_mail(self.login_email_template, ctx)
                msgs.append(EmailMultiAlternatives(
                    subject=''.join(messages['subject'].splitlines()),
                    body=messages['content'],
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[email],
                    connection=connection,
                    alternatives=[(messages['html_content'], 'text/html'), ],
                ))

            connection.send_messages(msgs)
        except Exception:
            logger.exception("Failed to send signup to '%s'", email)
            return False

        return True


def get_oauth2_session(social_token: SocialToken) -> OAuth2Session:
    """ Create OAuth2 session which autoupdates the access token if it has expired """

    provider = social_token.account.get_provider()
    refresh_token_url = getattr(provider, 'refresh_token_url', None)
    if refresh_token_url is None:
        refresh_token_url = provider.get_settings().get('REFRESH_TOKEN_URL')
    if refresh_token_url is None:
        raise ImproperlyConfigured("Provider '%s' should have 'refresh token url' set with attribute"
                                   " or in settings" % provider.id)

    def token_updater(updated_token):
        social_token.token = updated_token['access_token']
        refresh_token = updated_token.get('refresh_token', '')
        if refresh_token:
            social_token.token_secret = refresh_token
        social_token.expires_at = timezone.now() + timedelta(seconds=int(updated_token['expires_in']))
        social_token.save()

    client_id = social_token.app.client_id
    client_secret = social_token.app.secret

    extra = {
        'client_id': client_id,
        'client_secret': client_secret
    }
    if not social_token.expires_at:
        raise ValueError("Social token '%s' should have expiration time" % social_token.pk)
    if not social_token.token:
        raise ValueError("Social token '%s' doesn't provide access token ('token' field)")
    if not social_token.token_secret:
        raise ValueError("Social token '%s' doesn't provide refresh token ('token' field)")

    expires_in = (social_token.expires_at - timezone.now()).total_seconds()
    token = {
        'access_token': social_token.token,
        'refresh_token': social_token.token_secret,
        'token_type': 'Bearer',
        'expires_in': expires_in  # Important otherwise the token update doesn't get triggered.
    }

    session = OAuth2Session(client_id,
                            auto_refresh_url=refresh_token_url,
                            auto_refresh_kwargs=extra,
                            token=token,
                            token_updater=token_updater)

    return session


def get_oauth2_token(social_token: SocialToken) -> str:
    session = get_oauth2_session(social_token)

    class Dummy(HTTPAdapter):
        skip_url = 'https://example.com/imap/%s/' % hash(__file__)  # add some magic value to be sure that it is unique

        def send(self, request, *args, **kwargs) -> Response:
            if self.skip_url != request.url:
                return super().send(request, *args, **kwargs)
            return Response()

    dummy = Dummy()
    # we are overriding default adapter to perform only request for token refresh
    session.mount('https://', dummy)
    session.get(dummy.skip_url)
    return social_token.token


def get_social_token(provider: str, user, request=None) -> Optional[SocialToken]:
    try:
        social_token = SocialToken.objects.get(
            app=SocialApp.objects.get_current(provider, request),
            account__user=user
        )
        return social_token
    except ObjectDoesNotExist:
        return None


def tenant_users() -> Q:
    from django.db import connection
    tenant = connection.tenant
    if hasattr(tenant, 'users'):
        return Q(profile__in=tenant.users.all())
    # todo: it should be false to any filtering
    return Q(id=None)
