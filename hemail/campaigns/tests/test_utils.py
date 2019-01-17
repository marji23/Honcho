import datetime
from typing import Dict, Union
from unittest.mock import MagicMock, PropertyMock, patch

from django.core.mail.backends.locmem import EmailBackend as LocmemEmailBackend
from django.utils.timezone import now
from post_office.models import Email, STATUS

from tenancy.test.cases import TenantsTestCase
from .. import utils
from ..contacts.models import Contact
from ..models import Campaign, CampaignStatus, EmailStage, Participation, ParticipationStatus, Priority, Step
from ..providers.configuration import (
    AuthenticationType, EncryptionType, IncomingConfiguration, OutgoingConfiguration
)
from ..providers.models import CoolMailbox, EmailAccount, SmtpConnectionSettings


def _generate_email_account_kwargs() -> Dict[str, Union[CoolMailbox, SmtpConnectionSettings]]:
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


class EmailsSubmittingTestCase(TenantsTestCase):
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

    def test_campaign_emails_submitting(self) -> None:
        self.set_tenant(0)
        user = self.user

        EmailAccount.objects.create(user=user, email='asgds@yty.bfd', **_generate_email_account_kwargs())

        contact1 = Contact.objects.create(email='first_target@email.client', title='Miss')
        contact2 = Contact.objects.create(email='bob.the.second@gmggg.moc', first_name='Bob')

        campaign1 = Campaign.objects.create(name='testing get next stage from participation',
                                            owner=user,
                                            status=CampaignStatus.ACTIVE)

        current_time = now()
        start = (current_time - datetime.timedelta(minutes=15)).time()
        if start > current_time.time():
            start = datetime.time.min
        end = (current_time + datetime.timedelta(hours=1)).time()
        if end < current_time.time():
            end = datetime.time.max
        assert start < current_time.time() < end

        kwargs = dict(campaign=campaign1, start=start, end=end, timezone=current_time.tzinfo, )
        step1 = Step.objects.create(**kwargs)
        step2 = Step.objects.create(**kwargs)
        step3 = Step.objects.create(**kwargs)

        campaign1.set_step_order([step2.pk, step3.pk, step1.pk, ])

        stage11 = EmailStage.objects.create(
            step=step1,
            name='first variant',
            subject='You should do that, {{ title|default:"man" }}!',
            html_content='Welcome home, <b>{{ first_name|default:"dude" }}</b>!')
        stage21 = EmailStage.objects.create(
            step=step2,
            name='second stage email',
            subject='{{ first_name }} answer now!',
            html_content='<strong>Dear {{ first_name|default:"all" }}</strong>! Help us to save...')
        stage31 = EmailStage.objects.create(
            step=step3,
            name='third stage email',
            subject='Last chance for {{ first_name|default:"you" }}!',
            html_content=(
                '<p>I need to add an image here <br/>'
                '{{ title| default:"Mr" }} {{ second_name|default:"all" }}</strong>! <br/> Regards')
        )

        Participation.objects.create(campaign=campaign1, contact=contact1, activation=current_time),
        Participation.objects.create(campaign=campaign1, contact=contact2, activation=current_time),

        with patch(
            'campaigns.models.Step.timedelta_offset', new_callable=PropertyMock
        ) as mocked_timedelta_offset, patch(
            'campaigns.providers.models.SmtpConnectionSettings.get_connection'
        ) as mocked_get_connection:

            mocked_get_connection.return_value = LocmemEmailBackend()
            mocked_timedelta_offset.return_value = datetime.timedelta()
            emails = utils.submit_emails(priority=Priority.NOW)

        self.assertEqual(2, len(emails))
        self.assertSetEqual({contact1, contact2, }, {e.contact for e in emails})
        for email in emails:
            self.assertEqual(stage21, email.stage)

        campaign2 = Campaign.objects.create(name='another campaign', owner=user, status=CampaignStatus.ACTIVE)
        kwargs = dict(campaign=campaign2, start=start, end=end, timezone=current_time.tzinfo, )
        step4 = Step.objects.create(**kwargs)
        step5 = Step.objects.create(**kwargs)

        stage41 = EmailStage.objects.create(
            step=step4,
            name='first email for second campaign',
            subject='My dear {{ first_name|default:"cousin" }}!',
            html_content='Please, send me some money, <b>{{ first_name|default:"dude" }}</b>!')
        stage51 = EmailStage.objects.create(
            step=step5,
            name='second stage email for second campaign',
            subject="I'm out of ideas...",
            html_content='<strong> {{ first_name|default:"all" }}</strong>, you have two weeks more')

        Participation.objects.create(campaign=campaign2, contact=contact1, activation=current_time),
        Participation.objects.create(campaign=campaign2, contact=contact2, activation=current_time),

        contact2.blacklisted = True
        contact2.save()

        with patch(
            'campaigns.models.Step.timedelta_offset', new_callable=PropertyMock
        ) as mocked_timedelta_offset, patch(
            'campaigns.providers.models.SmtpConnectionSettings.get_connection'
        ) as mocked_get_connection:

            mocked_get_connection.return_value = LocmemEmailBackend()
            mocked_timedelta_offset.return_value = datetime.timedelta()
            emails = utils.submit_emails(priority=Priority.NOW)

        self.assertEqual(2, len(emails))
        self.assertSetEqual({stage31, stage41, }, {e.stage for e in emails})
        for email in emails:
            self.assertEqual(contact1, email.contact)

        contact2.blacklisted = False
        contact2.save()

        with patch(
            'campaigns.models.Step.timedelta_offset', new_callable=PropertyMock
        ) as mocked_timedelta_offset, patch(
            'campaigns.providers.models.SmtpConnectionSettings.get_connection'
        ) as mocked_get_connection:

            mocked_get_connection.return_value = LocmemEmailBackend()
            mocked_timedelta_offset.return_value = datetime.timedelta()
            emails = utils.submit_emails(priority=Priority.NOW)

        self.assertEqual(4, len(emails))

        grouped_emails = dict()
        for e in emails:
            grouped_emails.setdefault(e.contact, []).append(e)

        self.assertIn(contact1, grouped_emails)
        emails = grouped_emails[contact1]
        self.assertEqual(2, len(emails))
        self.assertSetEqual({stage11, stage51, }, {e.stage for e in emails})

        self.assertIn(contact2, grouped_emails)
        emails = grouped_emails[contact2]
        self.assertEqual(2, len(emails))
        self.assertSetEqual({stage31, stage41, }, {e.stage for e in emails})

        with patch(
            'campaigns.models.Step.timedelta_offset', new_callable=PropertyMock
        ) as mocked_timedelta_offset, patch(
            'campaigns.providers.models.SmtpConnectionSettings.get_connection'
        ) as mocked_get_connection:

            mocked_get_connection.return_value = LocmemEmailBackend()
            mocked_timedelta_offset.return_value = datetime.timedelta()
            emails = utils.submit_emails(priority=Priority.NOW)

        self.assertEqual(2, len(emails))
        self.assertSetEqual({stage11, stage51, }, {e.stage for e in emails})
        for email in emails:
            self.assertEqual(contact2, email.contact)

        self.assertListEqual([ParticipationStatus.ACTIVE, ParticipationStatus.ACTIVE, ],
                             [p.status for p in contact1.participation_set.all()])

        queued_emails = Email.objects.filter(status=STATUS.sent)
        self.assertEqual(10, queued_emails.count())
        grouped_emails = dict()
        for e in queued_emails:
            grouped_emails.setdefault(e.scheduled.contact, []).append(e)

        self.assertIn(contact1, grouped_emails)
        self.assertIn(contact2, grouped_emails)
        self.assertEqual(2, len(grouped_emails))

        emails = grouped_emails[contact1]
        self.assertEqual(5, len(emails))
        for email in emails:
            self.assertListEqual([contact1.email], email.to)

        emails = grouped_emails[contact2]
        self.assertEqual(5, len(emails))
        for email in emails:
            self.assertListEqual([contact2.email], email.to)
