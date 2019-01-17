from unittest import skip

from django.test import SimpleTestCase

from campaigns.providers.configuration import AuthenticationType
from .oauth2 import OAuth2ImapTransport


class OAuth2ImapTransportTestCase(SimpleTestCase):
    @skip('should be replaced with mock connection')
    def test_connection(self):
        connection = OAuth2ImapTransport(
            hostname='imap.gmail.com',
            port=993,
            ssl=True,
            tls=False,
            authentication=AuthenticationType.OAUTH2,
        )

        connection.connect('abrahas.23@gmail.com', '')
        pass
