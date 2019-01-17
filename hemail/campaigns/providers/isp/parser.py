import logging
from typing import List, Optional, TypeVar
from xml.etree import ElementTree

from allauth.socialaccount import providers
from django.core.exceptions import ImproperlyConfigured

from campaigns.providers.configuration import (
    AuthenticationType, BasicConfiguration, EncryptionType, IncomingConfiguration,
    OutgoingConfiguration, ProviderConfiguration
)

logger = logging.getLogger(__name__)


class SkipConfiguration(Exception):
    @staticmethod
    def throw():
        raise SkipConfiguration()


class Skipable(object):
    def __init__(self, e: ElementTree.Element) -> None:
        super().__init__()
        self.e = e

    def find(self, path: str) -> ElementTree.Element:
        r = self.e.find(path)
        if r is None:
            raise SkipConfiguration()
        return r

    def findtext(self, path: str) -> str:
        r = self.e.findtext(path)
        if r is None:
            raise SkipConfiguration()
        return r

    def findall(self, path: str) -> List[ElementTree.Element]:
        r = self.e.findall(path)
        if not r:
            raise SkipConfiguration()
        return r


_TBasicConfiguration = TypeVar('_TBasicConfiguration', covariant=True, bound=BasicConfiguration)


def _choose_best_configuration(configurations: List[_TBasicConfiguration]) -> _TBasicConfiguration:
    def authentication(conf: _TBasicConfiguration):
        priority = [
            AuthenticationType.BASIC,
            AuthenticationType.OAUTH2,
        ] if conf.provider else [
            AuthenticationType.OAUTH2,
            AuthenticationType.BASIC,
        ]
        return priority.index(conf.authentication)

    def encryption(conf):
        return [
            EncryptionType.STARTTLS,
            EncryptionType.SSL,
        ].index(conf.encryption)

    return sorted(configurations, key=lambda conf: encryption(conf) + 10 * authentication(conf))[-1]


def _choose_best_incoming(incoming_configurations: List[IncomingConfiguration]) -> IncomingConfiguration:
    return _choose_best_configuration(incoming_configurations)


def _choose_best_outgoing(outgoing_configurations: List[OutgoingConfiguration]) -> OutgoingConfiguration:
    return _choose_best_configuration(outgoing_configurations)


def _create_isp_providers_mapping():
    mapping = {
        'googlemail.com': 'google',
    }

    unknown_providers = set(mapping.values()) - set(dict(providers.registry.as_choices()).keys())
    if unknown_providers:
        raise ImproperlyConfigured('Unknown providers: ' + unknown_providers)
    return mapping


isp_providers_mapping = _create_isp_providers_mapping()


def parse_provider(identifier: str) -> Optional[str]:
    provider = isp_providers_mapping.get(identifier, None)
    if not provider:
        return None
    if provider in dict(providers.registry.as_choices()):
        return provider
    return provider


def parse_configuration(xml_string: str) -> Optional[ProviderConfiguration]:
    try:
        client_config = ElementTree.fromstring(xml_string)
        if client_config.get('version') != '1.1':
            return None

        email_provider = client_config.find('emailProvider')
        name = email_provider.findtext('displayShortName') or email_provider.findtext('displayName') or None
        conf = Skipable(email_provider)

        isp_provider = email_provider.get('id')
        provider = parse_provider(isp_provider) if isp_provider else None

        incoming_servers = conf.findall("incomingServer[@type='imap']")
        incoming_configurations = [c for conf in incoming_servers for c in
                                   _parse_incoming_configuration(conf, provider)]
        incoming_configuration = _choose_best_incoming(incoming_configurations)

        outgoing_servers = conf.findall("outgoingServer[@type='smtp']")
        outgoing_configurations = [c for conf in outgoing_servers for c in
                                   _parse_outgoing_configuration(conf, provider)]
        outgoing_configuration = _choose_best_outgoing(outgoing_configurations)

        return ProviderConfiguration(name, incoming_configuration, outgoing_configuration)
    except SkipConfiguration:
        return None


def _parse_outgoing_configuration(outgoing_server: ElementTree.Element,
                                  provider: Optional[str] = None) -> List[OutgoingConfiguration]:
    conf = Skipable(outgoing_server)
    authentications = [_parse_authentication(e.text) for e in conf.findall('authentication')]
    return [
        OutgoingConfiguration(
            host=conf.findtext('hostname'),
            port=int(conf.findtext('port')),
            encryption=_parse_socket_type(conf.findtext('socketType')),
            username_or_template=conf.findtext('username'),
            authentication=authentication,
            provider=provider,
        ) for authentication in authentications
    ]


def _parse_incoming_configuration(incoming_server: ElementTree.Element,
                                  provider: Optional[str] = None) -> List[IncomingConfiguration]:
    conf = Skipable(incoming_server)
    authentications = [_parse_authentication(e.text) for e in conf.findall('authentication')]
    return [
        IncomingConfiguration(
            host=conf.findtext('hostname'),
            port=int(conf.findtext('port')),
            encryption=_parse_socket_type(conf.findtext('socketType')),
            username_or_template=conf.findtext('username'),
            authentication=authentication,
            provider=provider,
        ) for authentication in authentications
    ]


def _parse_socket_type(socket_type: str) -> EncryptionType:
    return (
        {
            "plain": EncryptionType.NONE,
            "SSL": EncryptionType.SSL,
            "STARTTLS": EncryptionType.STARTTLS
        }.get(socket_type) or SkipConfiguration.throw()
    )


def _parse_authentication(authentication: str) -> AuthenticationType:
    """
    "password-cleartext", "plain" (deprecated):
        Send password in the clear (dangerous, if SSL isn't used either).
        AUTH PLAIN, LOGIN or protocol-native login.
    "password-encrypted", "secure" (deprecated):
        A secure encrypted password mechanism.
        Can be CRAM-MD5 or DIGEST-MD5. Not NTLM.
    "NTLM":
        Use NTLM (or NTLMv2 or successors), the Windows login mechanism.
    "GSSAPI":
        Use Kerberos / GSSAPI, a single-signon mechanism used for big sites.
    "client-IP-address":
        The server recognizes this user based on the IP address.
        No authentication needed, the server will require no username nor password.
    "TLS-client-cert":
        On the SSL/TLS layer, the server requests a client certificate and the client sends
        one (possibly after letting the user select/confirm one), if available.
    "none":
           No authentication
    """
    return (
        {
            "none": AuthenticationType.NONE,
            "password-cleartext": AuthenticationType.BASIC,
            "OAuth2": AuthenticationType.OAUTH2,
        }.get(authentication) or SkipConfiguration.throw()
    )
