from urllib.parse import urljoin

from django.test import modify_settings
from django.utils import timezone
from pinax.notifications.models import NoticeType
from rest_framework import reverse, status
from rest_framework.test import ForceAuthClientHandler
from tenant_schemas.test.client import TenantClient

from tenancy.test.cases import TenantsAPIRequestFactory, TenantsTestCase
from ..models import Notification
from ..views import NoticeSettingsViewSet


class NotificationsViewTestCase(TenantsTestCase):
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

    def test_settings_view(self) -> None:
        self.set_tenant(0)

        factory = TenantsAPIRequestFactory(force_authenticate=self.user)
        request = factory.get('')
        response = NoticeSettingsViewSet.as_view({'get': 'list'})(request)
        contact_data = response.data

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(contact_data))
        self.assertEqual(2, len(contact_data))

    def test_unread_only_filtering(self):
        self.set_tenant(0)

        now = timezone.now()
        action = NoticeType.objects.first()
        Notification.objects.bulk_create([
            Notification(user=self.user, created=now, action=action),
            Notification(user=self.user, created=now, action=action, read_datetime=now, extra_context=dict(mark=True)),
            Notification(user=self.user, created=now, action=action),
        ])

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = self.user
        self.assertTrue(t_client.login(username=self.user.username, password='p'), 'Test user was not logged in')

        url = reverse.reverse('api:notifications-list')
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?unread_only=true'
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        notifications_data = response.data
        self.assertEqual(2, len(notifications_data))
        notifications = Notification.objects.filter(extra_context__isnull=True).all()
        self.assertSetEqual({n.id for n in notifications}, {n['id'] for n in notifications_data})
