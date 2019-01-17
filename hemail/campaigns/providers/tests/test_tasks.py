from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from tenancy.test.cases import TenantsTestCase
from ..configuration import UsernameTemplates
from ..serializers import ProviderConfigurationSerializer
from ..tasks import create_default_provider, guess_configuration


def mock_guessing_response(mock_requests) -> None:
    from ..isp.test_parser import _sample_response

    mock_response = MagicMock()
    mock_response.status_code = requests.codes.ok
    mock_response.headers = {'content-type': 'text/xml'}
    mock_response.content = _sample_response

    mock_requests.return_value = mock_response


class TestConfigurationGuessing(SimpleTestCase):
    @patch('requests.get')
    def test_common_provider_find_email_in_isp(self, mock_requests):
        mock_guessing_response(mock_requests)

        email = 'fff@gmail.com'
        config_data, error = guess_configuration(email)
        self.assertIsNotNone(config_data)
        self.assertIsNone(error)
        serializer = ProviderConfigurationSerializer(data=config_data)
        self.assertTrue(serializer.is_valid(raise_exception=True))
        config = serializer.save()
        self.assertEqual('GMail', config.name)
        self.assertEqual(UsernameTemplates.EMAILADDRESS.value, config.incoming.username_or_template)
        self.assertEqual(UsernameTemplates.EMAILADDRESS.value, config.outgoing.username_or_template)


class TestEmailAccounts(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@gmail.com', 'p', tenant=0)

    @classmethod
    def tearDownClass(cls):
        cls.user.delete()
        super().tearDownClass()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch('smtplib.SMTP.connect')
    @patch('requests.get')
    def test_default_provider_creation(self, mock_requests, mock_connect):
        mock_guessing_response(mock_requests)
        mock_connect.return_value = (220, 'Test mock response',)

        email_account_id, error = ~create_default_provider(self.user)

        self.assertIsNone(error)
        self.set_tenant(0)
        email_account = self.user.email_accounts.get()
        self.assertEqual(email_account_id, email_account.id)
        self.assertTrue(email_account.default)
