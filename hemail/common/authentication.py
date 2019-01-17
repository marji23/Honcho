import logging

from django.conf import settings
from django.contrib.auth import get_user
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import decorator_from_middleware
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject
from django.utils.module_loading import import_string
from django.utils.six import text_type

logger = logging.getLogger(__file__)


def _get_authorization_header(request):
    """
    Return request's 'Authorization:' header, as a bytestring.
    Hide some test client ickyness where the header can be unicode.
    """
    auth = request.META.get('HTTP_AUTHORIZATION', b'')
    if isinstance(auth, text_type):
        # Work around django test client oddness
        auth = auth.encode('utf-8')
    return auth


def get_authorization_header_token(request, auth_type_name):
    auth = _get_authorization_header(request).split(None, 2)
    if len(auth) != 2 or auth[0].lower() != auth_type_name:
        return None
    return auth[1]


class AuthorizationMiddleware(MiddlewareMixin):
    """
    Append user to request like 'django.contrib.auth.middleware.AuthenticationMiddleware',
    but use list of AUTHORIZATION_PROCESSORS from settings.

    """

    def __init__(self, get_response=None) -> None:
        super(AuthorizationMiddleware, self).__init__(get_response)
        authorization_processors = []
        for middleware_path in settings.AUTHORIZATION_PROCESSORS:
            ap_class = import_string(middleware_path)
            ap_instance = ap_class()
            authorization_processors.append(ap_instance)

        self.authorization_processors = authorization_processors

    def process_request(self, request) -> None:

        def func():
            for authorization_processor in self.authorization_processors:
                result = authorization_processor.get_user(request)
                if result is not None:
                    return result
            return AnonymousUser()

        request.user = SimpleLazyObject(func)


class SessionAuthorizationProcessor(object):
    def get_user(self, request):
        user = get_user(request)
        return None if user.is_anonymous else user


class AbstractRestFrameworkAuthorizationProcessor(object):
    authenticator_class = None

    def __init__(self, authenticator_class):
        super().__init__()
        self.authenticator_class = authenticator_class

    def get_user(self, request):

        from rest_framework import exceptions
        try:
            user_auth_tuple = self.authenticator_class().authenticate(request)
            return user_auth_tuple[0] if user_auth_tuple else None
        except (ObjectDoesNotExist, exceptions.AuthenticationFailed) as e:
            logger.debug(e)
            return None


class JWTAuthorizationProcessor(AbstractRestFrameworkAuthorizationProcessor):
    def __init__(self) -> None:
        from rest_framework_jwt.authentication import JSONWebTokenAuthentication
        super(JWTAuthorizationProcessor, self).__init__(JSONWebTokenAuthentication)


class BasicAuthorizationProcessor(AbstractRestFrameworkAuthorizationProcessor):
    def __init__(self) -> None:
        from rest_framework.authentication import BasicAuthentication
        super().__init__(BasicAuthentication)

        self.authenticator_class = BasicAuthentication


class RestFrameworkAuthorizationProcessor(object):
    def __init__(self) -> None:
        super().__init__()

        from rest_framework.settings import api_settings
        self.authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES

    def get_user(self, request):
        from rest_framework import exceptions
        from rest_framework.request import Request
        from rest_framework.authentication import SessionAuthentication

        class DummyRequest(Request):
            def __init__(self):
                super().__init__(request)

            def _authenticate(self):
                pass

        r = DummyRequest()
        for authentication_class in self.authentication_classes:
            if authentication_class == SessionAuthentication:
                # adding custom behavior for SessionAuthentication to remove circular dependency
                # which produce stack overflow
                user = SessionAuthorizationProcessor().get_user(request)
                if user:
                    return user
                continue

            authenticator = authentication_class()
            try:
                user_auth_tuple = authenticator.authenticate(r)
                if user_auth_tuple is not None:
                    user, auth = user_auth_tuple
                    return user
            except (ObjectDoesNotExist, exceptions.AuthenticationFailed) as e:
                logger.debug(e)
                continue
            except exceptions.APIException:
                raise

        return None


authorization = decorator_from_middleware(AuthorizationMiddleware)


@authorization
def _get_user(request):
    return request.user


def get_scope_user(scope):
    if "_cached_user" not in scope:
        # We need to fake a request so the auth code works
        scope['method'] = "FAKE"
        from channels.http import AsgiRequest
        fake_request = AsgiRequest(scope, b'')
        fake_request.session = scope["session"]

        scope["_cached_user"] = _get_user(fake_request)
    return scope["_cached_user"]


class AuthorizationProcessorBasedMiddleware:
    """
    Middleware which populates scope["user"] from authorization middleware.
    """

    def __init__(self, inner):
        self.inner = inner

    def __call__(self, scope):
        # Make sure we have a session
        if "session" not in scope:
            raise ValueError(
                "AuthorizationProcessorBasedMiddleware cannot find session in scope. "
                "SessionMiddleware must be above it."
            )
        # Add it to the scope if it's not there already
        if "user" not in scope:
            scope["user"] = SimpleLazyObject(lambda: get_scope_user(scope))
        # Pass control to inner application
        return self.inner(scope)


def AuthorizationProcessorBasedMiddlewareStack(inner):
    """ Handy shortcut for applying all three layers at once """
    from channels.sessions import CookieMiddleware, SessionMiddleware

    return CookieMiddleware(SessionMiddleware(AuthorizationProcessorBasedMiddleware(inner)))
