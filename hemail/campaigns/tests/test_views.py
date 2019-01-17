import datetime
import json
from unittest.mock import patch
from urllib.parse import urljoin

from django.core import mail
from django.core.mail.backends.locmem import EmailBackend as LocmemEmailBackend
from django.test import modify_settings
from django_mailbox.models import Message
from rest_framework import reverse, status
from rest_framework.test import ForceAuthClientHandler
from rest_framework_extensions.utils import compose_parent_pk_kwarg_name
from tenant_schemas.test.client import TenantClient

from tenancy.test.cases import TenantsAPIRequestFactory, TenantsTestCase
from ..contacts.models import Contact
from ..models import (
    Campaign, CampaignProblems, CampaignStatus, EmailStage, Participation, ParticipationStatus, Step,
    StepProblems, Weekdays)
from ..providers.models import EmailAccount
from ..tests.test_utils import _generate_email_account_kwargs
from ..views import (
    CampaignSettingsViewSet, CampaignsParticipationViewSet, CampaignsViewSet, EmailStageViewSet,
    NestedContactEmailMessageViewSet, StepViewSet
)


class CampaignsViewsTestCase(TenantsTestCase):
    tenants_names = ['one', 'two', ]
    auto_create_schema = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.users = [
            cls.create_superuser(name, name + 'test@one.com', name + '-secret',
                                 first_name=name.capitalize(), last_name='Smith',
                                 tenant=tenant) for name, tenant in [
                ('first', 0),
                ('second', 0),
                ('third', 1),
            ]
        ]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.set_tenant(0)
        cls.users[0].delete()
        cls.users[1].delete()
        cls.set_tenant(1)
        cls.users[2].delete()
        super().tearDownClass()

    def test_steps_validation_during_patching(self) -> None:
        self.set_tenant(0)
        user = self.users[0]
        campaign = Campaign.objects.create(name='start/stop validation', owner=user)
        step = Step.objects.create(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30))

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.patch('', data=dict(timezone='UTC-0300'))
        response = StepViewSet.as_view({'patch': 'partial_update'})(request, **{
            compose_parent_pk_kwarg_name('campaign'): campaign.id,
            'pk': step.pk
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        step_data = response.data
        self.assertEqual(step.id, step_data['id'])
        self.assertEqual('UTC-0300', step_data['timezone'])

    def test_campaign_state_default(self) -> None:
        self.set_tenant(0)
        user = self.users[0]

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.post('', data=dict(name='testing settings'))
        response = CampaignsViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.data))
        campaign_data = response.data
        campaign = Campaign.objects.get(id=campaign_data['id'])
        self.assertEqual(CampaignStatus.DRAFT, campaign.status)
        self.assertEqual(CampaignStatus.DRAFT.value, campaign_data['status'])

    def test_settings_view(self) -> None:
        self.set_tenant(0)
        user = self.users[0]

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.post('', data=dict(name='testing settings'))
        response = CampaignsViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.data))
        campaign_data = response.data
        campaign = Campaign.objects.get(id=campaign_data['id'])
        self.assertTrue(campaign.settings)

        request = factory.get('')
        response = CampaignSettingsViewSet.as_view({'get': 'retrieve_single'})(request, campaign=campaign_data['id'])
        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))

        response.render()  # render just in case
        settings_data = response.data
        self.assertEqual(campaign.settings.step_max_number, settings_data['step_max_number'])

        email_send_delay = datetime.timedelta(**dict(zip(
            ['hours', 'minutes', 'seconds'],
            map(int, settings_data['email_send_delay'].split(':', 2))
        )))
        self.assertEqual(campaign.settings.email_send_delay, email_send_delay)

    def test_campaign_with_steps_creation_responses(self) -> None:
        self.set_tenant(0)

        user = self.users[0]
        campaign = Campaign.objects.create(name='this gonna be great', owner=user)

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.get('')
        response = CampaignsViewSet.as_view({'get': 'list'})(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        campaigns_data = response.data
        self.assertEqual(1, len(campaigns_data))
        campaign_data = campaigns_data[0]

        self.assertEqual(campaign.id, campaign_data['id'])
        self.assertEqual(campaign.name, campaign_data['name'])
        self.assertEqual(user.id, campaign_data['owner'])

        contact = Contact.objects.create(email='target@email.client')
        Participation.objects.create(campaign=campaign, contact=contact)

        request = factory.get('')
        response = CampaignsViewSet.as_view({'get': 'retrieve'})(request, pk=campaign_data['id'])

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        campaign_data = response.data
        self.assertEqual(1, campaign_data['contacts_count'])

        step = Step.objects.create(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30))
        request = factory.get('')
        response = CampaignsViewSet.as_view({'get': 'retrieve'})(request, pk=campaign_data['id'])
        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        campaign_data = response.data
        steps_data = campaign_data['steps']
        self.assertEqual(1, len(steps_data))
        step_data = steps_data[0]
        self.assertEqual(step.pk, step_data)

    def test_unable_to_set_different_tenant_user_as_campaign_owner(self) -> None:
        self.set_tenant(0)
        user = self.users[0]
        campaign = Campaign.objects.create(name='this gonna be great', owner=user)

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.get('')
        response = CampaignsViewSet.as_view({'get': 'retrieve'})(request, pk=campaign.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))

        other_user = self.users[2]
        self.assertNotEqual(other_user.profile.tenant, user.profile.tenant)
        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.patch('', data=dict(owner=other_user.pk))
        response = CampaignsViewSet.as_view({'patch': 'partial_update'})(request, pk=campaign.pk)

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code, str(response.data))
        self.assertDictEqual({'owner': [
            'Invalid pk "%s" - object does not exist.' % other_user.pk
        ]}, response.data)

    def test_bulk_post_participation(self) -> None:
        self.set_tenant(0)

        user = self.users[0]
        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')

        campaign = Campaign.objects.create(name='cool campaign', owner=user)

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = user
        self.assertTrue(t_client.login(username=user.username, password='first-secret'), 'Test user was not logged in')

        url = reverse.reverse('api:campaigns-contacts-list', args=[campaign.pk, ])
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            response = t_client.post(url,
                                     json.dumps([
                                         dict(contact=first_contact.id),
                                         dict(contact=second_contact.id),
                                     ]),
                                     content_type='application/json',
                                     )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.content))
        self.assertEqual(2, Participation.objects.filter(
            campaign=campaign,
            contact_id__in=(first_contact.id, second_contact.id,),
        ).count())
        contacts = campaign.contacts.all()
        self.assertListEqual([first_contact, second_contact, ], list(contacts))

    def test_bulk_delete_participation(self) -> None:
        self.set_tenant(0)

        user = self.users[0]
        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')

        campaign = Campaign.objects.create(name='cool campaign', owner=user)

        Participation.objects.bulk_create([
            Participation(campaign=campaign, contact=first_contact),
            Participation(campaign=campaign, contact=second_contact),
        ])

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = user
        self.assertTrue(t_client.login(username=user.username, password='first-secret'), 'Test user was not logged in')

        url = reverse.reverse('api:campaigns-contacts-list', args=[campaign.pk, ])
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            response = t_client.delete(urljoin(url, '?contact__in=%s' % str(first_contact.id)),
                                       content_type='application/json',
                                       )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, str(response.content))
        participation = Participation.objects.get(campaign=campaign)
        self.assertEqual(second_contact, participation.contact)

    def test_sample_emails_preview(self) -> None:
        self.set_tenant(0)

        user = self.users[0]
        kwargs = _generate_email_account_kwargs()
        provider = EmailAccount.objects.create(user=user, email='asd@mnb.fg', **kwargs)

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')

        campaign = Campaign.objects.create(name='cool campaign', owner=user, provider=provider, )
        step = Step.objects.create(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30))
        EmailStage.objects.create(
            step=step,
            name='first email for second campaign',
            subject='My dear {{ first_name|default:"cousin" }}!',
            html_content='Please, send me some money, <b>{{ first_name|default:"dude" }}</b>!')

        Participation.objects.bulk_create([
            Participation(campaign=campaign, contact=first_contact),
            Participation(campaign=campaign, contact=second_contact),
        ])

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.get('', data=dict(contact=second_contact.id))
        response = CampaignsViewSet.as_view({'get': 'preview'})(request, pk=campaign.id)
        self.assertEqual(status.HTTP_200_OK, response.status_code, str(response.data))

        emails_list = response.data
        self.assertEqual(1, len(emails_list))
        email_data = emails_list[0]
        self.assertEqual(second_contact.id, email_data['contact'])
        self.assertEqual(step.id, email_data['step'])
        self.assertListEqual([second_contact.email], email_data['to'])
        self.assertEqual('Please, send me some money, <b>Second</b>!',
                         email_data['html_message'])
        self.assertEqual('My dear Second!', email_data['subject'])

    def test_email_sending(self) -> None:
        self.set_tenant(0)
        user = self.users[0]

        kwargs = _generate_email_account_kwargs()
        EmailAccount.objects.create(user=user, email='asd@mnb.fg', **kwargs)

        contact = Contact.objects.create(email='bob@example.com', first_name='Bob', last_name='Smith')

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.post('', data=dict(
            subject='single email',
            sender='some name',
            html_content='{{first_name}}, <b>thank</b> you for reply!',
            track_opening=True
        ))

        with patch(
            'campaigns.providers.models.SmtpConnectionSettings.get_connection'
        ) as mocked_get_connection:
            mocked_get_connection.return_value = LocmemEmailBackend()
            response = NestedContactEmailMessageViewSet.as_view(
                {'post': 'create'}
            )(request, **{compose_parent_pk_kwarg_name('contact'): contact.id})

        self.assertEqual(status.HTTP_201_CREATED, response.status_code, str(response.data))

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual('single email', msg.subject)
        self.assertEqual('some name <asd@mnb.fg>', msg.from_email)
        self.assertListEqual(['bob@example.com'], msg.to)

        msg_id = msg.extra_headers.get('Message-ID')
        self.assertIsNotNone(msg_id)
        inbox_message = Message.objects.get(message_id=msg_id)

        email_data = response.data
        self.assertEqual('single email', email_data['subject'])
        self.assertEqual('some name <asd@mnb.fg>', email_data['from_header'])
        self.assertEqual('bob@example.com', email_data['to_header'])
        self.assertEqual(inbox_message.id, email_data['id'])
        self.assertTrue(email_data['outgoing'])
        self.assertIsNone(email_data['in_reply_to'])

        r = r'<html><body>Bob, <b>thank</b> you for reply!<img src="http://127.0.0.1:8000/.*"></body></html>'
        self.assertRegex(email_data['html_content'], r)

    def test_contact_by_campaign_filtering(self) -> None:
        self.set_tenant(0)
        user = self.users[0]

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')
        Contact.objects.create(email='third@example.com', first_name='Third', last_name='Smith')
        fourth_contact = Contact.objects.create(email='fourth@example.com', first_name='Fourth', last_name='Smith')

        first_campaign = Campaign.objects.create(name='first campaign for filtering test', owner=user)
        second_campaign = Campaign.objects.create(name='second campaign for filtering test', owner=user)

        Participation.objects.bulk_create([
            Participation(campaign=first_campaign, contact=first_contact),
            Participation(campaign=second_campaign, contact=second_contact),
            Participation(campaign=first_campaign, contact=fourth_contact),
            Participation(campaign=second_campaign, contact=fourth_contact),
        ])

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = user
        self.assertTrue(t_client.login(username=user.username, password='first-secret'), 'Test user was not logged in')

        url = reverse.reverse('api:contacts-list')
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?campaigns__in=%s' % ','.join(map(str, [first_campaign.id, second_campaign.id]))
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        contacts_data = response.data
        self.assertEqual(3, len(contacts_data))
        self.assertSetEqual({first_contact.id, second_contact.id, fourth_contact.id},
                            {c['id'] for c in contacts_data})

        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?campaigns=' + ','.join(map(str, [first_campaign.id, second_campaign.id]))
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        contacts_data = response.data
        self.assertEqual(1, len(contacts_data))
        self.assertEqual(fourth_contact.id, contacts_data[0]['id'])

        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?campaigns=%s' % second_campaign.id
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        contacts_data = response.data
        self.assertEqual(1, len(contacts_data))
        self.assertEqual(second_contact.id, contacts_data[0]['id'])

    def campaign_move_out_of_drafts(self) -> None:
        self.set_tenant(0)
        user = self.users[0]

        factory = TenantsAPIRequestFactory(force_authenticate=user)
        request = factory.post('', data=dict(name='testing settings'))
        response = CampaignsViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.data))
        campaign_data = response.data
        self.assertSetEqual({CampaignProblems.NO_CONTACTS.value, CampaignProblems.NO_STEPS.value},
                            {p['code'] for p in campaign_data['problems']})
        campaign = Campaign.objects.get(id=campaign_data['id'])
        self.assertSetEqual({CampaignProblems.NO_CONTACTS, CampaignProblems.NO_STEPS},
                            set(campaign.problems))

        contact = Contact.objects.create(email='testing@example.com')
        request = factory.post('', data=dict(contact=contact.id))
        response = CampaignsParticipationViewSet.as_view({'post': 'create'})(
            request, **{compose_parent_pk_kwarg_name('campaign'): campaign_data['id']}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.data))
        participation_data = response.data
        self.assertEqual(ParticipationStatus.ACTIVE.value, participation_data['status'])

        campaign.refresh_from_db()
        self.assertListEqual([CampaignProblems.NO_STEPS], campaign.problems)

        request = factory.post('', data=dict(
            weekdays=[Weekdays.Monday.value, ],
            start=datetime.time(8, 0, 0, 0),
            end=datetime.time(18, 0, 0, 0),
        ))
        response = StepViewSet.as_view({'post': 'create'})(
            request, **{compose_parent_pk_kwarg_name('campaign'): campaign.id, }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.data))
        step_data = response.data
        self.assertListEqual([StepProblems.EMPTY_STEP.value], [p['code'] for p in step_data['problems']])

        campaign.refresh_from_db()
        self.assertListEqual([CampaignProblems.EMPTY_STEP], campaign.problems)

        request = factory.post('', data=dict(
            subject='Hi {{first_name}}',
            html_content='{{first_name|default:"Human"}}, where are you? ',
        ))
        response = EmailStageViewSet.as_view({'post': 'create'})(
            request, **{
                compose_parent_pk_kwarg_name('step__campaign'): campaign.id,
                compose_parent_pk_kwarg_name('step'): step_data['id'],
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(response.data))

        campaign.refresh_from_db()
        self.assertFalse(campaign.problems)
        self.assertFalse(any([s.problems for s in campaign.steps.all()]))
        self.assertEqual(CampaignStatus.PAUSED, campaign.status)

    def test_email_stage_template_validation(self) -> None:
        self.set_tenant(0)

        user = self.users[0]

        campaign = Campaign.objects.create(name='some campaign', owner=user)
        step = Step.objects.create(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30))

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = user
        self.assertTrue(t_client.login(username=user.username, password='first-secret'), 'Test user was not logged in')

        url = reverse.reverse('api:campaigns-steps-email-list', args=[campaign.pk, step.pk, ])
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            response = t_client.post(url,
                                     json.dumps(dict(
                                         subject='Hello good fellow',
                                         html_content='Some invalid email template to {{First name}}!',
                                     )),
                                     content_type='application/json',
                                     )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, str(response.content))
        error_data = response.data
        self.assertTrue("Could not parse" in error_data['html_content'][0])
