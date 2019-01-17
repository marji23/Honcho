from post_office.models import Email

from tenancy.test.cases import TenantsTestCase
from ..models import Notification


class NotificationsModelTestCase(TenantsTestCase):
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

    def test_email_backend_notice_send(self) -> None:
        self.set_tenant(0)

        extra_context = dict(
            contact_link='http://localhost.localdomain/contacts/321',
            contact_name='Billy',
            company_name="Treasure hunters", phone_number='+1324567890',
            campaign_link='http://localhost.localdomain/campaigns/123', campaign_title='Where is the map?', )
        Notification.send(self.user, 'email_link_clicked', extra_context)

        emails = Email.objects.all()

        self.assertEqual(1, len(emails))
        email = emails[0]
        self.assertListEqual([self.user.email], email.to)
        html_message = email.html_message
        skipped_keys = [k for k, v in extra_context.items() if v not in html_message]

        self.assertFalse(skipped_keys, 'Message does not contain: %s' % ', '.join(skipped_keys))
