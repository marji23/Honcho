from aiounittest import async_test
from channels.testing import WebsocketCommunicator

from tenancy.test.cases import TenantsTestCase
from tenancy.utils import tenant_sync_to_async
from ..consumers import NotificationsConsumer
from ..models import Notification


def authenticated(cls, user):
    def wrapper(scope):
        scope["user"] = user
        return cls(scope)

    return wrapper


class NotificationsConsumersTestCase(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@one.com', 'p',
                                        first_name='Pretty', last_name='Smart',
                                        tenant=0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.set_tenant(0)
        cls.user.delete()
        super().tearDownClass()

    @async_test
    async def test_consumers(self):
        self.set_tenant(0)

        communicator = WebsocketCommunicator(authenticated(NotificationsConsumer, self.user), "/nyt/")
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        extra_context = dict(
            contact_link='http://localhost.localdomain/contacts/321',
            contact_name='Billy',
            company_name="Treasure hunters", phone_number='+1324567890',
            campaign_link='http://localhost.localdomain/campaigns/123', campaign_title='Where is the map?', )
        await tenant_sync_to_async(Notification.send)(self.user, 'email_link_clicked', extra_context)

        response = await communicator.receive_json_from(timeout=100000)
        self.assertEqual('email_link_clicked', response['type'])
        self.assertDictEqual({
            'contact_name': 'Billy',
            'campaign_link': 'http://localhost.localdomain/campaigns/123',
            'message': 1,
            'contact_link': 'http://localhost.localdomain/contacts/321',
            'company_name': 'Treasure hunters',
            'campaign_title': 'Where is the map?',
            'phone_number': '+1324567890'
        }, response['context'])

        await communicator.disconnect()
