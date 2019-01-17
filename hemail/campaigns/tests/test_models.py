import datetime
from unittest.mock import MagicMock

from django.core import mail
from django.core.mail.backends.locmem import EmailBackend as LocmemEmailBackend
from post_office.models import Email, STATUS

from tenancy.test.cases import TenantsTestCase
from ..contacts.models import Contact
from ..models import (
    Campaign, CampaignProblems, CampaignStatus, EmailStage, Participation, Priority, Step, StepProblems
)
from ..providers.configuration import (
    AuthenticationType, EncryptionType, IncomingConfiguration, OutgoingConfiguration
)
from ..providers.models import CoolMailbox, EmailAccount, SmtpConnectionSettings


def _generate_email_account_kwargs():
    in_conf = IncomingConfiguration(
        'imap.gmail.com', 993,
        EncryptionType.SSL,
        'username@gmail.com',
        AuthenticationType.BASIC,
    )
    incoming = CoolMailbox.objects.create(
        name='testing',
        uri=(CoolMailbox.get_uri_from(in_conf, 'secret')))

    out_conf = OutgoingConfiguration(
        'smtp.localhost',
        9876,
        EncryptionType.SSL,
        'resu',
        AuthenticationType.BASIC,
    )
    outgoing = SmtpConnectionSettings.objects.create(uri=SmtpConnectionSettings.get_uri_from(out_conf, 'secret'))
    outgoing.get_connection = MagicMock(return_value=LocmemEmailBackend())

    return dict(incoming=incoming, outgoing=outgoing)


class EmailsSendingTestCase(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@one.com', 'secret',
                                        first_name='First', last_name='Smith',
                                        tenant=0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.set_tenant(0)
        cls.user.delete()
        super().tearDownClass()

    def test_draft_to_pause_auto_transition(self) -> None:
        self.set_tenant(0)
        user = self.user

        campaign = Campaign.objects.create(name='draft to pause auto transition', owner=user)
        self.assertEqual(CampaignStatus.DRAFT, campaign.status)
        self.assertSetEqual({CampaignProblems.NO_CONTACTS, CampaignProblems.NO_STEPS, }, set(campaign.problems))

        step = Step.objects.create(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30))
        self.assertEqual(CampaignStatus.DRAFT, campaign.status)
        self.assertSetEqual({CampaignProblems.NO_CONTACTS, CampaignProblems.EMPTY_STEP, }, set(campaign.problems))
        self.assertSetEqual({StepProblems.EMPTY_STEP, }, set(step.problems))

        contact = Contact.objects.create(email='target@email.client')
        Participation.objects.create(campaign=campaign, contact=contact)
        campaign.refresh_from_db()
        self.assertEqual(CampaignStatus.DRAFT, campaign.status)
        self.assertSetEqual({CampaignProblems.EMPTY_STEP, }, set(campaign.problems))

        EmailStage.objects.create(step=step,
                                  name='single variant',
                                  subject='You should do that, {{ title }}!',
                                  html_content='Welcome home, <b>{{ first_name|default:"dude" }}</b>!')
        step.refresh_from_db()
        self.assertFalse(step.problems)
        campaign.refresh_from_db()
        self.assertFalse(campaign.problems)
        self.assertEqual(CampaignStatus.PAUSED, campaign.status)

    def test_send_email(self) -> None:
        self.set_tenant(0)
        user = self.user

        kwargs = _generate_email_account_kwargs()
        provider = EmailAccount.objects.create(user=user, email='asd@mnb.fg', **kwargs)

        campaign = Campaign.objects.create(name='this gonna be great', owner=user, provider=provider)
        contact = Contact.objects.create(email='target@email.client', title='Mr')
        Participation.objects.create(campaign=campaign, contact=contact)
        step = Step(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30),
                    timezone="UTC-0300")
        step.full_clean()  # validates against pytz.common_timezones
        step.save()  # values stored in DB as strings
        stage = EmailStage.objects.create(step=step,
                                          name='first variant',
                                          subject='You should do that, {{ title }}!',
                                          html_content='Welcome home, <b>{{ first_name|default:"dude" }}</b>!')

        step.submit_emails(priority=Priority.NOW)
        kwargs['outgoing'].get_connection.assert_called_with()
        email = Email.objects.first()
        self.assertEqual(stage, email.scheduled.stage)
        # TODO: move utc parsing check into separate test
        self.assertEqual('UTC-0300', step.timezone.zone)
        self.assertEqual(datetime.timedelta(0, hours=-3), step.timezone.utcoffset(None))
        self.assertEqual(contact, email.scheduled.contact)
        self.assertEqual(email.status, STATUS.sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'You should do that, Mr!')

    def test_get_next_stage(self) -> None:
        self.set_tenant(0)
        user = self.user

        EmailAccount.objects.create(user=user, email='asd@mnb.fg', **_generate_email_account_kwargs())

        campaign = Campaign.objects.create(name='testing get next stage from participation', owner=user)

        kwargs = dict(campaign=campaign, start=datetime.time(9, 45), end=datetime.time(18, 30))
        step1 = Step.objects.create(**kwargs)
        step2 = Step.objects.create(**kwargs)
        step3 = Step.objects.create(**kwargs)

        campaign.set_step_order([step2.pk, step3.pk, step1.pk, ])

        contact = Contact.objects.create(email='target@email.client')
        participation = Participation.objects.create(campaign=campaign, contact=contact)

        prev, step = participation.get_latest_and_next_step()
        self.assertIsNone(prev)
        self.assertEquals(step2, step)

        step.submit_emails()

        prev, step = participation.get_latest_and_next_step()
        self.assertEquals(step2, prev)
        self.assertEquals(step3, step)

        step.submit_emails()

        prev, step = participation.get_latest_and_next_step()
        self.assertEquals(step3, prev)
        self.assertEquals(step1, step)

        step.submit_emails()

        prev, step = participation.get_latest_and_next_step()
        self.assertEquals(step1, prev)
        self.assertIsNone(step)
