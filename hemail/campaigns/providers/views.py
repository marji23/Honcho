import logging
from urllib.parse import quote_plus, urlencode, urljoin

from allauth.socialaccount import providers as social_providers
from allauth.socialaccount.providers.base import AuthProcess
from rest_framework import exceptions, generics, permissions, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from common.exceptions import UnprocessableEntity
from common.views import CachedDelay
from users.utils import get_social_next_from_referer_url
from .configuration import AuthenticationType, UsernameTemplates
from .models import EmailAccount
from .serializers import EmailAccountSerializer, GuessingProviderConfigurationSerializer
from .tasks import guess_configuration
from .utils import get_email_parts

logger = logging.getLogger(__name__)


class ProviderConfigurationView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    serializer_class = GuessingProviderConfigurationSerializer

    cache = CachedDelay('providers-isp-configurations')

    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        local_path, domain = get_email_parts(email)

        configuration_data = self.cache.get(domain, lambda: guess_configuration.delay(email))

        def replace_template(conf):
            if conf.get('username') == UsernameTemplates.EMAILADDRESS.value:
                conf['username'] = email
            elif conf.get('username') == UsernameTemplates.EMAILLOCALPART.value:
                conf['username'] = local_path

        incoming = configuration_data.get('incoming', {})
        replace_template(incoming)

        outgoing = configuration_data.get('outgoing', {})
        replace_template(outgoing)

        return Response(configuration_data)


class EmailAccountViewSet(viewsets.ModelViewSet):
    queryset = EmailAccount.objects.none()
    serializer_class = EmailAccountSerializer
    permission_classes = (permissions.DjangoModelPermissions,)

    class C(CachedDelay):
        def failure(self):
            raise UnprocessableEntity()

    cache = C('providers-isp-configurations')

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return self.request.user.email_accounts.all()
        return self.queryset

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        incoming = serializer.validated_data.get('incoming')
        outgoing = serializer.validated_data.get('outgoing')

        if incoming is not None and outgoing is not None:
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        if incoming is not None and outgoing is None:
            raise exceptions.ValidationError('You have to specify outgoing if you set incoming')
        if incoming is None and outgoing is not None:
            raise exceptions.ValidationError('You have to specify incoming if you set outgoing')

        local_path, domain = get_email_parts(email)

        configuration_data_result = self.cache.get(domain, lambda: guess_configuration.delay(email))

        if configuration_data_result is None:
            raise UnprocessableEntity()
        configuration_data, error = configuration_data_result
        if error:
            raise UnprocessableEntity(detail=error)

        UsernameTemplates.replace_template_in(configuration_data, email)

        def copy_conf(part, **kwargs):
            result = {k: v for k, v in configuration_data.get(part, {}).items() if
                      k in ['host', 'port', 'encryption', 'username', 'authentication', 'provider', ]}
            result.update(kwargs)
            return result

        other = {}
        if 'default_password' in serializer.validated_data:
            other['password'] = serializer.validated_data.get('default_password')

        data = request.data.copy()
        data['incoming'] = copy_conf('incoming', **other)
        data['outgoing'] = copy_conf('outgoing', **other)

        serializer = self.get_serializer(data=data)
        if not serializer.is_valid(raise_exception=False):
            # we figured out provider settings but they are incorrect
            return Response(dict(
                errors=serializer.errors,
                data=serializer.data,
            ), status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @detail_route()
    def oauth2(self, request, pk):
        email_account = self.get_object()

        providers = set()
        incoming = email_account.incoming
        if incoming.authentication == AuthenticationType.OAUTH2 and incoming.provider:
            providers.add(incoming.provider)
        outgoing = email_account.outgoing
        if outgoing.authentication == AuthenticationType.OAUTH2 and outgoing.provider:
            providers.add(incoming.provider)

        if len(providers) < 1:
            raise NotFound('Authentication type is not oauth2')

        if len(providers) == 1:
            provider_id = next(iter(providers))
        else:
            logger.error(
                'Invalid configuration [user: %s, email account: %s]: '
                'incoming and outgoing oauth2 authentications have different providers: %s',
                email_account.user.id,
                email_account.id,
                providers
            )
            for provider_id in sorted(providers):
                try:
                    social_providers.registry.by_id(provider_id, request)
                    break
                except KeyError:
                    pass
            else:
                raise NotFound('Authentication type is not oauth2')

        response = Response(status=status.HTTP_303_SEE_OTHER)

        params = urlencode(dict(
            next=get_social_next_from_referer_url(request),
            process=AuthProcess.CONNECT,
        ), quote_via=quote_plus)
        url = urljoin(reverse(provider_id + '_login'), '?' + params)
        response['Location'] = url
        return response


class EmailAccountPresetsListView(generics.ListAPIView):
    """
    view with presets
    """
    domains = [
        'gmail.com',
        'yahoo.com',
        'outlook.com',
        # 'exchange.com',
    ]

    queryset = None
    serializer_class = None
    permission_classes = (permissions.IsAuthenticated,)

    cache = CachedDelay('providers-isp-configurations')

    def list(self, request, *args, **kwargs):
        configurations = self.cache.get_many(self.domains, lambda domain: guess_configuration.delay('user@' + domain))
        return Response(configurations.values())
