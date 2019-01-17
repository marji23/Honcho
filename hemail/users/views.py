import logging
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_auth.views import LoginView as RestAuthLoginView
from rest_framework import generics, permissions, status, views, viewsets
from rest_framework.response import Response
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.views import ObtainJSONWebToken

from .models import Profile
from .serializers import (
    AvatarChangeSerializer, AvatarSerializer, EmailLoginLinkSerializer, ObtainJSONWebTokenFromMagicLinkSerializer,
    ProfileSerializer, UserSerializer
)
from .utils import AuthAction, AuthProvider, MagicLinkMailer, get_login_token_with_auth_info

logger = logging.getLogger(__name__)

_UserModel = get_user_model()


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = (permissions.DjangoObjectPermissions,)

    # todo: add pending base on provider auto creation

    def get_object(self) -> Profile:
        return self.request.user.profile

    def get_queryset(self):
        return Profile.objects.none()


class AvatarUpdateView(generics.GenericAPIView):
    queryset = Profile.objects.none()
    permission_classes = (permissions.DjangoObjectPermissions,)
    serializer_class = AvatarChangeSerializer

    def get_object(self) -> Profile:
        return self.request.user.profile

    def get_queryset(self):
        return Profile.objects.none()

    def post(self, request, *args, **kwargs) -> Response:
        profile = self.get_object()

        serializer = AvatarChangeSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        file_upload = serializer.validated_data['file']
        with file_upload.move() as f:
            profile.avatar = f
            profile.save()

        serializer = AvatarSerializer(instance=profile, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs) -> Response:
        profile = self.get_object()

        profile.avatar.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = _UserModel.objects.filter()
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, 'profile'):
            return _UserModel.objects.get(pk=user.pk)

        return _UserModel.objects.filter(profile__tenant=user.profile.tenant)


class LoginView(RestAuthLoginView):
    def login(self):
        self.user = self.serializer.validated_data['user']

        if getattr(settings, 'REST_USE_JWT', False):
            self.token = get_login_token_with_auth_info(self.user, AuthAction.LOGIN, AuthProvider.BASIC)
        else:
            from rest_auth.app_settings import create_token
            self.token = create_token(self.token_model, self.user, self.serializer)

        if getattr(settings, 'REST_SESSION_LOGIN', True):
            self.process_login()


class ObtainEmailMagicLinkView(views.APIView):
    permission_classes = (permissions.AllowAny,)

    serializer_class = EmailLoginLinkSerializer
    success_response = "A login token has been sent to your email."
    failure_response = "Unable to email you a login link. Try again later."

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.save()

        success = MagicLinkMailer(request).send(email)
        if success:
            return Response({'detail': self.success_response}, status=status.HTTP_200_OK)

        return Response({'detail': self.failure_response}, status=status.HTTP_400_BAD_REQUEST)


class ObtainJSONWebTokenFromMagicLinkView(ObtainJSONWebToken):
    """
    This is a duplicate of rest_framework's own ObtainAuthToken method and
    ObtainJSONWebToken from rest_framework_jwt.

    API View that receives a POST with a token from email magic link.

    Returns a JSON Web Token that can be used for authenticated requests.
    """

    serializer_class = ObtainJSONWebTokenFromMagicLinkSerializer
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        is_signup = not serializer.instance
        instance = serializer.save()
        response = Response(serializer.data, status=status.HTTP_201_CREATED if is_signup else status.HTTP_200_OK)
        if api_settings.JWT_AUTH_COOKIE:
            expiration = (datetime.utcnow() + api_settings.JWT_EXPIRATION_DELTA)
            response.set_cookie(api_settings.JWT_AUTH_COOKIE,
                                instance['token'],
                                expires=expiration,
                                httponly=True)
        return response
