import enum
from typing import Optional

from .utils import get_email_local_path


@enum.unique
class AuthenticationType(enum.Enum):
    NONE = 'none'  # No authentication
    BASIC = 'plain'  # Send password in the clear (dangerous, if SSL isn't used either)
    OAUTH2 = 'oauth2'


@enum.unique
class EncryptionType(enum.Enum):
    NONE = 'plain'  # no encryption
    SSL = 'ssl'  # SSL 3 or TLS 1 on SSL-specific port
    STARTTLS = 'STARTTLS'  # on normal plain port and mandatory upgrade to TLS via STARTTLS


@enum.unique
class UsernameTemplates(enum.Enum):
    EMAILADDRESS = '%EMAILADDRESS%'
    EMAILLOCALPART = '%EMAILLOCALPART%'

    @staticmethod
    def replace_template_in(configuration_data: dict, email: str) -> None:

        def replace_template(conf: dict):
            if conf.get('username') == UsernameTemplates.EMAILADDRESS.value:
                conf['username'] = email
            elif conf.get('username') == UsernameTemplates.EMAILLOCALPART.value:
                conf['username'] = get_email_local_path(email)

        incoming = configuration_data.get('incoming', {})
        replace_template(incoming)

        outgoing = configuration_data.get('outgoing', {})
        replace_template(outgoing)


class BasicConfiguration(object):
    def __init__(self, host: str, port: int, encryption: EncryptionType,
                 username_or_template: str, authentication: AuthenticationType,
                 provider: Optional[str] = None) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.encryption = encryption
        self.username_or_template = username_or_template
        self.authentication = authentication
        self.provider = provider


class IncomingConfiguration(BasicConfiguration):
    pass


class OutgoingConfiguration(BasicConfiguration):
    pass


class ProviderConfiguration(object):
    def __init__(self, name: Optional[str], incoming: IncomingConfiguration, outgoing: OutgoingConfiguration) -> None:
        super().__init__()
        self.name = name
        self.incoming = incoming
        self.outgoing = outgoing
