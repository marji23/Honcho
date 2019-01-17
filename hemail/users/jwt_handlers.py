import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext as _
from rest_framework import exceptions
from rest_framework_jwt.settings import api_settings


def get_user_secret_key(user):
    # todo: add some sessions info which will be cleaned on user's logout
    return settings.SECRET_KEY + user.email


def jwt_get_secret_key(payload: dict = None) -> str:
    """
    This is copy of rest_framework_jwt.utils.jwt_get_secret_key with loyal behaviour of nonexistent user.
    """
    if api_settings.JWT_GET_USER_SECRET_KEY and payload:
        user_id = payload.get('user_id')
        if user_id:
            UserModel = get_user_model()
            try:
                user = UserModel.objects.get(pk=user_id)
            except UserModel.DoesNotExist:
                msg = _('Invalid signature.')
                raise exceptions.AuthenticationFailed(msg)
            key = str(api_settings.JWT_GET_USER_SECRET_KEY(user))
            return key
    return api_settings.JWT_SECRET_KEY


def jwt_decode_handler(token: str) -> dict:
    """
    We have to copy rest_framework_jwt.utils.jwt_decode_handler because we can not override secret key getter.
    """
    options = {
        'verify_exp': api_settings.JWT_VERIFY_EXPIRATION,
    }
    # get user from token, BEFORE verification, to get user secret key
    unverified_payload = jwt.decode(token, None, False)
    secret_key = jwt_get_secret_key(unverified_payload)
    return jwt.decode(
        token,
        api_settings.JWT_PUBLIC_KEY or secret_key,
        api_settings.JWT_VERIFY,
        options=options,
        leeway=api_settings.JWT_LEEWAY,
        audience=api_settings.JWT_AUDIENCE,
        issuer=api_settings.JWT_ISSUER,
        algorithms=[api_settings.JWT_ALGORITHM]
    )


def jwt_encode_handler(payload: dict):
    """
    We have to copy rest_framework_jwt.utils.jwt_encode_handler because we can not override secret key getter.
    """
    key = api_settings.JWT_PRIVATE_KEY or jwt_get_secret_key(payload)
    return jwt.encode(
        payload,
        key,
        api_settings.JWT_ALGORITHM
    ).decode('utf-8')
