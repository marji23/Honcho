import datetime
import enum
import logging
from collections import namedtuple
from email.utils import make_msgid
from typing import List, Optional, Sequence, Tuple
from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.core.mail import DNS_NAME, EmailMultiAlternatives
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import connection as db_connection, models, transaction
from django.template import Context, Template
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django_mailbox.models import Message as InboxMessage
from enumfields import EnumField
from phonenumber_field.modelfields import PhoneNumberField
from post_office import mail, models as post_office_models
from pytracking import TrackingResult
from pytracking.django import get_configuration_from_settings
from pytracking.html import adapt_html

from common.fields import EnumSetField, TimeZoneField
from common.utils import time_delta
from hemail.storage import storages
from users.utils import tenant_users
from .contacts.models import Address, Contact
from .managers import ParticipationManager
from .providers.models import EmailAccount, Priority, ProviderEmailMessage

logger = logging.getLogger(__name__)


@enum.unique
class CampaignStatus(enum.Enum):
    DRAFT = 'DRAFT'
    PAUSED = 'PAUSED'
    ACTIVE = 'ACTIVE'
    # QUEUED = 'Queued for sending'
    # SCHEDULED = 'SCHEDULED'
    # SENDING = 'SENDING'
    FAILED = 'FAILED'


@enum.unique
class ProblemSeverity(enum.IntEnum):
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10


@enum.unique
class CampaignProblems(str, enum.Enum):
    def __new__(cls, value: str, severity: ProblemSeverity, description: str):
        instance = str.__new__(cls, value)
        instance._value_ = value

        instance.severity = severity
        instance.description = description
        return instance

    NO_CONTACTS = 'no_contacts', ProblemSeverity.INFO, _('Campaign does not contain any contact.')
    NO_STEPS = 'no_steps', ProblemSeverity.INFO, _('Campaign does not contain any stages.')
    EMPTY_STEP = 'empty_steps', ProblemSeverity.INFO, _('Some of campaign stages are empty')


class Campaign(models.Model):
    """
    A campaign is an outbound marketing project that user want to plan, manage, and track.
    """

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    name = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, limit_choices_to=tenant_users)
    provider = models.ForeignKey(EmailAccount, on_delete=models.SET_NULL, null=True, blank=True)
    status = EnumField(CampaignStatus, max_length=32, default=CampaignStatus.DRAFT)

    contacts = models.ManyToManyField(
        Contact,
        through='Participation',
        through_fields=('campaign', 'contact'),
        related_name='campaigns',
    )

    problems = EnumSetField(CampaignProblems, default=[
        CampaignProblems.NO_STEPS,
        CampaignProblems.NO_CONTACTS,
    ], editable=False)

    class ReportBuilder:
        exclude = ('status',)  # Lists or tuple of excluded fields
        # fields = ()   # Explicitly allowed fields
        # extra = ()    # List extra fields (useful for methods)

    def __str__(self) -> str:
        return self.name or super().__str__()

    def clean(self) -> None:
        if self.provider and self.provider.user != self.owner:
            raise ValidationError({'provider': 'Provider must belong to the owner of the company'})

    def get_provider(self) -> EmailAccount:
        if self.provider:
            return self.provider
        return EmailAccount.get_default(self.owner)


class CampaignSettings(models.Model):
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name='settings')

    step_max_number = models.PositiveIntegerField(default=100,
                                                  validators=[
                                                      MinValueValidator(1),
                                                      MaxValueValidator(200),
                                                  ],
                                                  help_text=_('Max number of step emails per day'))
    email_send_delay = models.DurationField(default=datetime.timedelta(seconds=10),
                                            validators=[],
                                            help_text=_('Delay between each email send (seconds)'))
    track_opening = models.BooleanField(default=True,
                                        help_text=_('Enables/disables emails opens tracking'))
    track_links = models.BooleanField(default=True,
                                      help_text=_('Enables/disables links clicks tracking'))
    personalize_to_filed = models.BooleanField(default=False,
                                               help_text=_("Include the contact's name in the recipients "
                                                           "field to make it more personalized "))
    stop_sending_on_reply = models.BooleanField(default=True,
                                                help_text=_("Stop contact participation in campaign on reply"))


@enum.unique
class Weekdays(enum.Enum):
    """
    Order is important and correspond to ISO weekday format
    https://en.wikipedia.org/wiki/ISO_week_date

    Sunday has to be first because Monday should has index one.
    """

    Sunday = 'SUN'
    Monday = 'MON'
    Tuesday = 'TUE'
    Wednesday = 'WED'
    Thursday = 'THU'
    Friday = 'FRI'
    Saturday = 'SAT'


class Schedule(models.Model):
    start = models.TimeField()
    end = models.TimeField()

    weekdays = EnumSetField(Weekdays, default=list(Weekdays), blank=True, )

    timezone = TimeZoneField(blank=True, )

    class Meta:
        abstract = True

    def clean(self) -> None:
        if self.start >= self.end:
            raise ValidationError(dict(
                start=_("Start of the event should be earlier than it's end")
            ))
        # todo: check that minimal duration is greater than tick time (we should set it to constant)
        if time_delta(self.start, self.end) > datetime.timedelta(minutes=10):
            raise ValidationError(
                _("We need at least 10 minutes different between 'start' and 'end' for email sending")
            )


@enum.unique
class ParticipationStatus(enum.Enum):
    PAUSED = 'PAUSED'
    ACTIVE = 'ACTIVE'
    RESPOND = 'RESPOND'
    FAILED = 'FAILED'


class Participation(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    status = EnumField(ParticipationStatus, max_length=32, default=ParticipationStatus.ACTIVE)

    activation = models.DateTimeField(editable=False, blank=True, null=True)

    passed_steps = models.ManyToManyField(
        'Step',
        through='PassedStageResult',
        through_fields=('participation', 'step'),
        related_name='participations',
    )

    objects = ParticipationManager()

    class Meta:
        unique_together = (('contact', 'campaign'),)

    def update_activation(self) -> None:
        if not self.activation and self.status == ParticipationStatus.ACTIVE:
            self.activation = now()
        elif self.activation and self.status != ParticipationStatus.ACTIVE:
            self.activation = None

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        self.update_activation()

        super().save(force_insert, force_update, using, update_fields)

    def get_latest_and_next_step(self) -> Tuple[Optional['Step'], Optional['Step']]:
        steps = self.passed_steps.filter(campaign=self.campaign)
        latest_step = steps.last()
        if not latest_step:
            return None, self.campaign.steps.first()

        try:
            return latest_step, latest_step.get_next_in_order()
        except latest_step.DoesNotExist:
            return latest_step, None

    def get_next_step_and_send_datetime(self) -> Optional[Tuple['Step', datetime.datetime]]:
        latest_step, next_step = self.get_latest_and_next_step()
        if not next_step:
            return None

        if latest_step is None:
            activation = self.activation
            if not activation:
                logger.error('Activation was not set properly')
                activation = self.created
            return next_step, (activation + next_step.timedelta_offset)

        sent_dates = self.contact.scheduled_emails.filter(
            stage__step=latest_step
        ).filter(
            email__status=post_office_models.STATUS.sent,
        ).values_list('sent', flat=True)

        if not sent_dates:
            # this is weird but can happened if stage has no emails
            return next_step, (now() + next_step.timedelta_offset)

        if len(sent_dates) == 1:
            return next_step, (sent_dates[0] + next_step.timedelta_offset)

        logger.error("We have sent %s emails during step '%s' to single contact '%s'" % (
            len(sent_dates),
            latest_step,
            self.contact,
        ))
        return next_step, (max(sent_dates) + next_step.timedelta_offset)


class PassedStageResult(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    participation = models.ForeignKey(Participation, on_delete=models.CASCADE)
    step = models.ForeignKey('Step', on_delete=models.CASCADE)

    def clean(self) -> None:
        if self.step.campaign != self.participation.campaign:
            raise ValidationError(
                _("Step must belong to the same campaign as participation")
            )


TemplateContext = namedtuple('TemplateContext', ['contact', 'campaign', 'user', ])
RenderedEmailContext = namedtuple('RenderedEmailContext', ['subject', 'message', 'html_message'])


def render_email(
    subject: str,
    message: str,
    html_message: str,
    context: Optional[TemplateContext] = None
) -> RenderedEmailContext:
    from .serializers import TemplateContextSerializer

    context = TemplateContext(None, None, None) if context is None else context
    context_data = TemplateContextSerializer(instance=context).data

    template_context = Context(context_data)

    subject = Template(subject).render(template_context)
    message = Template(message).render(template_context)
    html_message = Template(html_message).render(template_context)

    return RenderedEmailContext(subject, message, html_message)


def add_tracking_info(email: post_office_models.Email,
                      click_tracking: bool = False,
                      open_tracking: bool = False) -> post_office_models.Email:
    msg_id = email.headers.get('Message-ID', None)

    # TODO: add expectation

    html_message = adapt_html(
        '<html><body>%s</body></html>' % email.html_message,
        extra_metadata={
            'tenant': db_connection.tenant.id,
            'id': msg_id,
        },
        click_tracking=click_tracking,
        open_tracking=open_tracking,
        configuration=get_configuration_from_settings(),
    )

    email.html_message = html_message

    if email.id:
        email.save()

    return email


def generate_email(sender: str,
                   email_context: RenderedEmailContext,
                   to: Optional[List[str]] = None,
                   cc: Optional[List[str]] = None,
                   bcc: Optional[List[str]] = None,
                   in_reply_to: Optional[InboxMessage] = None) -> post_office_models.Email:
    msg_id = make_msgid(domain=DNS_NAME)  # TODO: try use ZONE from settings or even provider server name

    headers = {
        'Message-ID': msg_id
    }
    if in_reply_to:
        headers['In-Reply-To'] = in_reply_to.message_id
        headers['References'] = in_reply_to.message_id

    return mail.send(commit=False,
                     recipients=to,
                     sender=sender,
                     subject=email_context.subject,
                     message=email_context.message,
                     html_message=email_context.html_message,
                     headers=headers,
                     context=None,
                     cc=cc,
                     bcc=bcc,
                     )


def prepare_email_message(email: post_office_models.Email,
                          provider: EmailAccount) -> EmailMultiAlternatives:
    assert hasattr(email, '_cached_email_message')

    msg = provider.create_email(
        subject=email.subject, body=email.message, html_body=email.html_message,
        to=email.to, cc=email.cc, bcc=email.bcc,
        from_email=email.from_email,
        headers=email.headers,
    )

    # todo: support unsaved emails
    for attachment in email.attachments.all():
        msg.attach(attachment.name, attachment.file.read(), mimetype=attachment.mimetype or None)
        attachment.file.close()

    email._cached_email_message = msg
    return msg


def dispatch(email: post_office_models.Email,
             log_level: Optional[int] = None,
             disconnect_after_delivery: bool = True, commit: bool = True) -> Optional[InboxMessage]:
    assert hasattr(email, '_cached_email_message')
    email_message = email.email_message()
    assert isinstance(email_message, ProviderEmailMessage)

    status = email.dispatch(log_level, disconnect_after_delivery, commit)

    if status == post_office_models.STATUS.sent:
        inbox_message = email_message.incoming_message
        assert inbox_message is not None
        return inbox_message

    return None


class ScheduledEmail(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    email = models.OneToOneField(post_office_models.Email, on_delete=models.CASCADE, related_name='scheduled')
    inbox_message = models.OneToOneField(InboxMessage, on_delete=models.CASCADE, related_name='scheduled', null=True)
    stage = models.ForeignKey('EmailStage', on_delete=models.CASCADE, related_name='scheduled')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='scheduled_emails')
    sent = models.DateTimeField(null=True,
                                editable=False,
                                help_text=_('Time when message was successfully sent'))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cached_email_message = None

    def __str__(self) -> str:
        return "Email to '%s'" % (str(self.email),)

    def dispatch(self, log_level: Optional[int] = None,
                 disconnect_after_delivery: bool = True, commit: bool = True) -> Optional[InboxMessage]:

        assert hasattr(self.email, '_cached_email_message')
        email_message = self.email_message()
        self.email._cached_email_message = email_message

        inbox_message = dispatch(self.email,
                                 log_level=log_level,
                                 disconnect_after_delivery=disconnect_after_delivery,
                                 commit=commit)

        if inbox_message:
            self.inbox_message = inbox_message
            self.sent = now()
            self.save(update_fields=('inbox_message', 'sent',))

        return inbox_message

    def prepare_email_message(self) -> EmailMultiAlternatives:
        provider = self.stage.get_provider()

        self._cached_email_message = prepare_email_message(self.email, provider)
        return self._cached_email_message

    def email_message(self) -> EmailMultiAlternatives:
        if self._cached_email_message:
            return self._cached_email_message

        return self.prepare_email_message()


@enum.unique
class TrackingType(enum.Enum):
    OPEN = 'OPEN'
    LINK_CLICKED = 'LINK_CLICKED'


class TrackingInfo(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    email = models.ForeignKey(InboxMessage, on_delete=models.CASCADE, related_name='tracked')
    type = EnumField(TrackingType, max_length=32)
    meta = JSONField(_('Meta'), blank=True, null=True)

    @classmethod
    def create_from(cls, type: TrackingType, email: InboxMessage,
                    tracking_result: TrackingResult) -> 'TrackingInfo':
        return cls.objects.create(
            email=email,
            type=type,
            meta=dict(
                metadata=tracking_result.metadata,
                request_data=tracking_result.request_data
            ),
        )


@enum.unique
class StepProblems(str, enum.Enum):
    def __new__(cls, value: str, severity: ProblemSeverity, description: str) -> 'StepProblems':
        instance = str.__new__(cls, value)
        instance._value_ = value

        instance.severity = severity
        instance.description = description
        return instance

    EMPTY_STEP = 'empty_step', ProblemSeverity.INFO, _("Step does not contain any stages")


class Step(Schedule, models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='steps')
    offset = models.DurationField(default=datetime.timedelta(days=1), validators=[
        MinValueValidator(datetime.timedelta(minutes=15))
    ])

    problems = EnumSetField(StepProblems, default=[
        StepProblems.EMPTY_STEP,
    ], editable=False)

    # emails
    # texts
    # tasks
    # voices
    # socials

    class Meta:
        order_with_respect_to = 'campaign'

    def __str__(self) -> str:
        return "Campaign '%s' %s step" % (self.campaign.name, self._order,)

    @property
    def timedelta_offset(self) -> datetime.timedelta:
        return self.offset

    def submit_emails(self, contacts_filter_kwargs: Optional[dict] = None,
                      priority: Priority = Priority.MEDIUM) -> Sequence[ScheduledEmail]:
        created_emails = []

        with transaction.atomic():
            contacts = self.campaign.contacts.exclude(blacklisted=True)
            if contacts_filter_kwargs:
                contacts = contacts.filter(**contacts_filter_kwargs)
            email_stages = self.emails.all()

            # todo: need to add something more cleaver to try keep all variant number the same
            email_stages = email_stages.annotate(already_sent=models.Count('scheduled')).order_by('-already_sent')
            # diffs = [email_stages[-1].already_sent - es.already_sent for es in email_stages]
            # limit = len(contacts)
            #
            # def split(diffs, limit):
            #     m = min(limit, diffs[0])
            #     limit -= m
            #     yield 0, m
            #
            #     if limit < 1:
            #         return
            #
            #     for k in range(1, len(diffs)):
            #         for i in range(1, diffs[k] + 1):
            #             for j in range(k, -1, -1):
            #                 limit -= 1
            #                 yield j, 1
            #
            #                 if limit < 1:
            #                     return
            #
            # groupby(sorted(split(diffs, limit), key=lambda x: x[0])

            # we are splitting contacts equally between all email stages for A/B testing
            ab_splitting = {email_stages[i]: contacts[i::len(email_stages)] for i in range(len(email_stages))}
            for email_stage, contacts in ab_splitting.items():
                created_emails += email_stage.create_emails(contacts)

            # store information that we passed current campaign's step
            PassedStageResult.objects.bulk_create([PassedStageResult(
                participation=contact.participation_set.get(campaign=self.campaign),
                step=self,
            ) for contact in contacts])

        if priority == Priority.NOW:
            for scheduled_email in created_emails:
                scheduled_email.dispatch()

        return created_emails


class EmailStage(post_office_models.EmailTemplate):
    step = models.ForeignKey(Step, on_delete=models.CASCADE, related_name='emails')
    provider = models.ForeignKey(EmailAccount, on_delete=models.SET_NULL, null=True, blank=True)
    sender_name = models.TextField(blank=True)

    def __str__(self) -> str:
        return u"Email stage '%s' of '%s'" % (self.name or '<none>', self.step.campaign.name,)

    def get_provider(self) -> EmailAccount:
        if self.provider:
            return self.provider
        return self.step.campaign.get_provider()

    def generate_emails(self,
                        contacts: Sequence[Contact]) -> Sequence[Tuple[int, post_office_models.Email]]:

        provider = self.get_provider()
        sender_name = provider.from_email(self.sender_name)

        emails = []
        for contact in contacts:
            email_context = render_email(self.subject, self.content, self.html_content,
                                         TemplateContext(contact, self.step.campaign, self.step.campaign.owner))

            email = generate_email(
                sender_name,
                email_context,
                to=[contact.email, ],
            )
            emails.append((contact.id, email,))

        return emails

    def create_emails(self, contacts: Sequence[Contact]) -> Sequence[ScheduledEmail]:

        campaign_settings = self.step.campaign.settings

        contacts_emails = self.generate_emails(contacts)

        recipient_to_contact_id = {}
        emails = []
        for contact_id, generated_email in contacts_emails:
            recipient = generated_email.to[0]
            assert recipient not in contacts_emails
            recipient_to_contact_id[recipient] = contact_id

            tracked_email = add_tracking_info(
                generated_email,
                click_tracking=campaign_settings.track_links,
                open_tracking=campaign_settings.track_opening,
            )

            emails.append(tracked_email)

        emails = post_office_models.Email.objects.bulk_create(emails)

        attachments = self.attachments.all()
        if attachments:

            attachments = []
            for generated_email in emails:  # todo: should be a better way to do that in bulk
                generated_email.attachments.add(*attachments)

        return ScheduledEmail.objects.bulk_create([
            ScheduledEmail(
                email=generated_email,
                stage=self,
                contact_id=recipient_to_contact_id[generated_email.to[0]]
            ) for generated_email in emails
        ])


class TextStage(models.Model):
    step = models.ForeignKey(Step, on_delete=models.CASCADE, related_name='texts')


def get_upload_path(instance: 'Attachment', filename: str) -> str:
    """Overriding to store theS original filename"""
    if not instance.name:
        instance.name = filename  # set original filename

    # todo: use data content for hash
    filename = '{name}.{ext}'.format(name=uuid4().hex,
                                     ext=filename.split('.')[-1])

    return 'campaigns_materials/' + filename


class Attachment(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    file = models.FileField(_('File'), upload_to=get_upload_path, storage=storages['private-attachments'])

    name = models.CharField(_('Name'), max_length=255, help_text=_("The original filename"))
    emails = models.ManyToManyField(EmailStage, related_name='attachments',
                                    verbose_name=_('Email stages'))

    mimetype = models.TextField(max_length=255, default='', blank=True)

    def convert_to_public(self):
        # todo: convert this private attachments to public attachments
        return mail.create_attachments({self.name: self})


@enum.unique
class LeadGenerationRequestStatus(enum.Enum):
    CREATED = 'CREATED'
    PROCESSED = 'PROCESSED'
    WORKING = 'WORKING'


@enum.unique
class CompanyEmployeeCountLevel(enum.Enum):
    IN_0_25 = 'IN_0_25'
    IN_25_100 = 'IN_25_100'
    IN_100_250 = 'IN_100_250'
    IN_250_1000 = 'IN_250_1000'
    IN_1K_10K = 'IN_1K_10K'
    IN_10K_50K = 'IN_10K_50K'
    IN_50K_100K = 'IN_50K_100K'
    OVER_100K = 'OVER_100K'


@enum.unique
class CompanyRevenue(enum.Enum):
    IN_0_1M = 'IN_0_1M'
    IN_1M_10M = 'IN_1M_10M'
    IN_10M_50M = 'IN_10M_50M'
    IN_50M_100M = 'IN_50M_100M'
    IN_100M_250M = 'IN_100M_250M'
    IN_250M_500M = 'IN_250M_500M'
    IN_500M_1B = 'IN_500M_1B'
    OVER_1B = 'OVER_1B'


@enum.unique
class LeadLevel(enum.Enum):
    C_LEVEL = 'C_LEVEL'
    VP_LEVEL = 'VP_LEVEL'
    DIRECTOR_LEVEL = 'DIRECTOR_LEVEL'
    MANAGER_LEVEL = 'MANAGER_LEVEL'
    STAFF = 'STAFF'
    OTHER = 'OTHER'


@enum.unique
class LeadEmailDeliverability(enum.Enum):
    OVER_90 = 'OVER_90'
    OVER_80 = 'OVER_80'
    ANY = 'ANY'


@enum.unique
class LeadDepartment(enum.Enum):
    ENGINEERING = 'ENGINEERING'
    FINANCE_ADMINISTRATION = 'FINANCE_ADMINISTRATION'
    HUMAN_RESOURCES = 'HUMAN_RESOURCES'
    IT_IS = 'IT_IS'
    MARKETING = 'MARKETING'
    OPERATIONS = 'OPERATIONS'
    SALES = 'SALES'
    SUPPORT = 'SUPPORT'
    OTHER = 'OTHER'


class LeadGenerationRequest(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)

    company_name = models.TextField(blank=True)
    company_industry_name = models.TextField(blank=True, null=True)  # can it be a select?
    company_sic_code = models.IntegerField(blank=True, null=True)
    company_employee_count = EnumSetField(CompanyEmployeeCountLevel, default=[])
    company_revenue = EnumSetField(CompanyRevenue, default=[])

    name = models.TextField(blank=True)
    title = models.TextField(blank=True)
    department = EnumSetField(LeadDepartment, default=[])
    level = EnumSetField(LeadLevel, default=[])

    email_deliverability = EnumField(LeadEmailDeliverability, max_length=32, default=LeadEmailDeliverability.ANY)

    city = models.TextField(verbose_name=_('city'), blank=True)
    state = models.TextField(verbose_name=_('state'), blank=True)
    country = models.TextField(verbose_name=_('country'), blank=True)
    zip_code = models.TextField(verbose_name=_('zip code'), blank=True)

    status = EnumField(LeadGenerationRequestStatus, max_length=32, default=LeadGenerationRequestStatus.CREATED)
    import_per_day = models.PositiveIntegerField(default=100)
    last_update = models.DateTimeField(blank=True, null=True)


@enum.unique
class ContactLeadStatus(enum.Enum):
    CREATED = 'CREATED'
    PROCESSED = 'PROCESSED'
    DUPLICATES = 'DUPLICATES'


class ContactLead(Address, models.Model):
    generator = models.ForeignKey(LeadGenerationRequest, on_delete=models.CASCADE, related_name='leads')

    email = models.EmailField(unique=True,
                              verbose_name=_('e-mail address'))
    phone_number = PhoneNumberField(blank=True)

    first_name = models.TextField(verbose_name=_('first name'), blank=True)
    last_name = models.TextField(verbose_name=_('last name'), blank=True)
    title = models.TextField(blank=True)

    timezone = TimeZoneField(blank=True)

    company_name = models.TextField(blank=True)
    company_employee_count = EnumField(CompanyEmployeeCountLevel, max_length=32)
    company_revenue = EnumField(CompanyRevenue, max_length=32)
    department = EnumField(LeadDepartment, max_length=32)
    level = EnumField(LeadLevel, max_length=32)

    status = EnumField(ContactLeadStatus, max_length=32, default=ContactLeadStatus.CREATED)

    def to_contact(self) -> Contact:
        return Contact(
            city=self.city,
            state=self.state,
            country=self.country,
            street_address=self.street_address,
            zip_code=self.zip_code,

            email=self.email,
            first_name=self.first_name,
            last_name=self.last_name,
            timezone=self.timezone,
            company_name=self.timezone,
            title=self.title,
            phone_number=self.phone_number,
        )
