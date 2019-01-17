import logging
from typing import Optional
from urllib.parse import urlencode, urljoin, urlparse

from allauth.account import app_settings as account_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress, EmailConfirmation
from allauth.account.utils import get_login_redirect_url, perform_login, user_email, user_username
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.socialaccount.providers.base import AuthError, AuthProcess
from allauth.utils import build_absolute_uri
from django.conf import settings
from django.core.exceptions import DisallowedRedirect, PermissionDenied
from django.http import HttpRequest, HttpResponseRedirect
from django.http.request import split_domain_port, validate_host
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch

from .utils import (
    AuthAction, AuthProvider, MagicLinkMailer,
    get_login_token_with_auth_info, get_signup_token, get_social_next_from_referer_url
)

logger = logging.getLogger(__name__)


class AccountAdapter(DefaultAccountAdapter):
    def get_next_redirect_url(self, request: HttpRequest) -> Optional[str]:
        user = getattr(request, 'user', None)
        if user.is_authenticated:
            self.logout(request)

        next_url = get_social_next_from_referer_url(request)
        next_url = build_absolute_uri(request, next_url)
        r = urlparse(next_url)
        host = r.netloc
        domain, port = split_domain_port(host)
        allowed_hosts = settings.ALLOWED_HOSTS
        if domain and validate_host(domain, allowed_hosts):
            return next_url
        raise DisallowedRedirect("Attempted access from '%s' denied." % next_url)

    def send_confirmation_mail(self, request: HttpRequest,
                               email_confirmation: EmailConfirmation, signup: bool) -> None:
        email = email_confirmation.email_address.email

        if 'socialaccount_original_next' not in request.session:
            raise PermissionDenied()  # todo better error handling

        url, provider = request.session['socialaccount_original_next']
        token = get_signup_token(email, AuthProvider.SOCIAL, provider)
        activate_url = urljoin(url, '?key=' + token)
        success = MagicLinkMailer.send_signup(request, email, activate_url)
        if not success:
            raise PermissionDenied()

    def respond_email_verification_sent(self, request: HttpRequest, user):
        # called right after send_confirmation_mail
        assert 'socialaccount_original_next' in request.session

        url, provider = request.session['socialaccount_original_next']
        redirect_url = urljoin(url, '?status=checkEmail')
        return HttpResponseRedirect(redirect_url)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    token_param_name = 'token'

    trusted_providers = [
        'google',
        'windowslive',  # todo: this is not really trusted
        'yahoo',
    ]
    """ This list of providers which are allowed to be connected into existing user. """

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        user = sociallogin.user
        process = sociallogin.state.get('process')

        if not user.id:
            if sociallogin.account.provider not in self.trusted_providers:
                return
            # todo: we can additionally check if email from social is verified if provider grabs such info
            try:
                email_address = EmailAddress.objects.get(email=user.email)
            except EmailAddress.DoesNotExist:
                pass
            else:
                existing_user = email_address.user
                sociallogin.state['process'] = AuthProcess.CONNECT
                perform_login(request, existing_user, account_settings.EmailVerificationMethod.NONE)
        elif (process == AuthProcess.LOGIN and
              sociallogin.is_existing and
              request.user.is_authenticated and
              sociallogin.user != request.user):

            raise self.authentication_error(
                request,
                sociallogin.account.provider,
                error=AuthError.DENIED,
                exception=Exception('The social account is already connected to a different account.')
            )

        if process == AuthProcess.CONNECT:
            return

        referer_url = sociallogin.state.get('next')
        if referer_url:
            request.session['socialaccount_original_next'] = (referer_url, sociallogin.account.provider,)

            assert user.is_authenticated
            token = get_login_token_with_auth_info(
                user,
                AuthAction.LOGIN if user.id else AuthAction.REGISTRATION,
                AuthProvider.SOCIAL,
                sociallogin.account.provider)

            sociallogin.state['next'] = urljoin(referer_url, '?' + self.token_param_name + '=' + token)

    def get_connect_redirect_url(self, request: HttpRequest, socialaccount: SocialAccount):
        try:
            return super().get_connect_redirect_url(request, socialaccount)
        except NoReverseMatch:
            return get_login_redirect_url(request)

    def populate_user(self, request: HttpRequest, sociallogin: SocialLogin, data: dict):
        user = super().populate_user(request, sociallogin, data)
        if not user_username(user):
            user_username(user, user_email(user))
        return user

    def authentication_error(self,
                             request: HttpRequest,
                             provider_id: str,
                             error: AuthError = None,
                             exception: Exception = None,
                             extra_context: dict = None):
        logger.exception("Error '%s' in '%s' provider [%s]", error, provider_id, str(extra_context))

        url = resolve_url(settings.SOCIAL_AUTHENTICATION_ERROR_REDIRECT_URL)
        redirect_url = urljoin(url, '?' + urlencode(dict(error=str(error), details=str(exception))))
        raise ImmediateHttpResponse(HttpResponseRedirect(redirect_url))
