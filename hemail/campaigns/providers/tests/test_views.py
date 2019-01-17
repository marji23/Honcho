from unittest.mock import patch

from tenancy.test.cases import TenantsAPIRequestFactory, TenantsTestCase
from ..models import EmailAccount
from ..tasks import TaskResult
from ..views import EmailAccountViewSet


class EmailAccountViewsTestCase(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@one.com', 'p',
                                        first_name='Pretty', last_name='Smart',
                                        tenant=0)

    @classmethod
    def tearDownClass(cls):
        cls.set_tenant(0)
        cls.user.delete()
        super().tearDownClass()

    @patch('common.views.CachedDelay.get')
    def test_simple_email_provider_view(self, mock_cached_delay_call):
        config_data = {
            'name': 'GMail',
            'incoming': {
                'host': 'imap.gmail.com',
                'port': 993,
                'encryption': 'SSL',
                'username': '%EMAILADDRESS%',
                'authentication': 'OAUTH2',
                'provider': 'google',
            },
            'outgoing': {
                'host': 'smtp.gmail.com',
                'port': 465,
                'encryption': 'SSL',
                'username': '%EMAILADDRESS%',
                'authentication': 'OAUTH2',
                'provider': 'google',
            }
        }
        mock_cached_delay_call.return_value = TaskResult(config_data, None)

        factory = TenantsAPIRequestFactory(force_authenticate=self.user)

        test_data = {'email': 'test@gmail.com'}
        request = factory.post('/api/whatever/', test_data, format='json')

        response = EmailAccountViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, 201, str(response.data))
        account = response.data

        self.assertEqual(test_data['email'], account['email'])
        self.assertEqual('Pretty Smart', account['sender_name'])
        self.assertIn('Pretty Smart', account['signature'])
        # self.assertTrue(account['default'])

        for conf in ('incoming', 'outgoing',):
            test_dir = config_data[conf]
            account_dir = account[conf]
            for name in ('host', 'port', 'encryption', 'username', 'authentication',):
                self.assertEqual(test_dir[name], account_dir[name])

        email_account = EmailAccount.objects.get(pk=account['id'])
        self.assertEqual(email_account.from_email(), "Pretty Smart <{0}>".format(test_data['email']))
        # self.assertFalse(email_account.incoming.password)
        # self.assertFalse(email_account.outgoing.password)
        # todo: check model inst
