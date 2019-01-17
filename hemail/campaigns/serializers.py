import typing

import rest_framework_bulk
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from django_mailbox.models import Message
from post_office.models import Email, Log
from post_office.validators import validate_template_syntax
from rest_framework import serializers
from rest_framework.fields import CurrentUserDefault

from common.exceptions import UnprocessableEntity
from common.serializers import (
    ContextualDefault, ContextualPrimaryKeyRelatedField, EnumByNameField, EnumField, PhoneNumberField,
    nested_view_contextual_default
)
from users.fields import TenantUsersPrimaryKeyRelatedField
from .contacts.models import Contact
from .models import (
    Attachment, Campaign, CampaignProblems, CampaignSettings, CampaignStatus, CompanyEmployeeCountLevel,
    CompanyRevenue, ContactLead, ContactLeadStatus, EmailStage, LeadDepartment, LeadEmailDeliverability,
    LeadGenerationRequest, LeadGenerationRequestStatus, LeadLevel, Participation, ParticipationStatus,
    ProblemSeverity, Step, TemplateContext, Weekdays,
    add_tracking_info, dispatch, generate_email, prepare_email_message, render_email
)
from .providers.models import EmailAccount
from .providers.utils import get_default_signature

if typing.TYPE_CHECKING:
    pass

_UserModel = get_user_model()


class ProblemsSerializer(serializers.ListField):
    class ChildField(EnumField):
        severity_serializer = EnumByNameField(ProblemSeverity)

        def to_representation(self, obj) -> dict:
            severity = self.severity_serializer.to_representation(obj.severity)
            return dict(code=obj.value, severity=severity)

    def __init__(self, enum, **kwargs) -> None:
        kwargs.update(dict(
            read_only=True,
            child=self.ChildField(enum),
            max_length=len(enum),
        ))
        super().__init__(**kwargs)


class EmailStageSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    step = serializers.HiddenField(default=nested_view_contextual_default(Step))
    html_content = serializers.CharField(allow_blank=True, default=ContextualDefault(
        lambda field: get_default_signature(field.context['request'].user)
    ), validators=[validate_template_syntax, ])

    class Meta:
        model = EmailStage
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id', 'step',
            'created', 'last_updated',
            'subject', 'html_content',
            'sender_name',
        )
        read_only_fields = ('created', 'last_updated',)


class StepSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    campaign = serializers.HiddenField(default=nested_view_contextual_default(Campaign))
    weekdays = serializers.ListField(
        child=EnumField(Weekdays),
        max_length=7,
        min_length=1,
        allow_empty=False,
    )
    emails = serializers.PrimaryKeyRelatedField(many=True, default=[], queryset=EmailStage.objects.all())
    problems = ProblemsSerializer(CampaignProblems)

    default_error_messages = {
        'invalid_time_frame': _("'end' must occur after 'start'")
    }

    class Meta:
        model = Step
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id', 'campaign',
            'start', 'end', 'weekdays', 'timezone', 'offset',
            'emails', 'problems',
        )
        read_only_fields = ('created', 'last_updated',)

    def validate(self, data: dict) -> dict:
        start = data.get('start', self.instance.start if self.instance else None)
        end = data.get('end', self.instance.end if self.instance else None)
        if start and end and start >= end:
            raise self.fail('invalid_time_frame')
        return data


class CampaignSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignSettings
        fields = (
            'step_max_number', 'email_send_delay',
            'track_opening', 'track_links',
            'personalize_to_filed', 'stop_sending_on_reply',
        )


class NestedCampaignSettingsSerializer(CampaignSettingsSerializer):
    campaign = serializers.HiddenField(default=nested_view_contextual_default(Campaign))

    class Meta(CampaignSettingsSerializer.Meta):
        fields = CampaignSettingsSerializer.Meta.fields + (
            'campaign',
        )


class CampaignSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    owner = TenantUsersPrimaryKeyRelatedField(default=CurrentUserDefault())
    steps = serializers.PrimaryKeyRelatedField(many=True, default=[], queryset=Step.objects.all())
    status = EnumField(CampaignStatus, required=False)
    contacts_count = serializers.IntegerField(read_only=True)
    settings = CampaignSettingsSerializer(required=False)
    problems = ProblemsSerializer(CampaignProblems)

    sent_emails_count = serializers.IntegerField(read_only=True)
    opened_emails_count = serializers.IntegerField(read_only=True)
    link_clicked_in_emails_count = serializers.IntegerField(read_only=True)
    replied_emails_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Campaign
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id',
            'created', 'updated',
            'name', 'owner', 'status',
            # 'provider', # TODO: support provider (don't forget to add validate_provider method)
            'contacts_count', 'steps',
            'settings', 'problems',
            'sent_emails_count', 'opened_emails_count', 'link_clicked_in_emails_count', 'replied_emails_count',
        )

    # noinspection PyMethodMayBeStatic
    def validate_status(self, status: CampaignStatus) -> CampaignStatus:
        if status == CampaignStatus.DRAFT:
            raise serializers.ValidationError('You can not set campaign status to DRAFT')
        return status

    @transaction.atomic
    def create(self, validated_data: dict) -> Campaign:
        steps_data = validated_data.get('steps')
        settings_data = validated_data.pop('settings', None)
        with transaction.atomic():
            instance = super().create(validated_data)
            if settings_data is not None:
                # it is possible that settings record was already created by post-save signal
                settings_serializer = CampaignSettingsSerializer(
                    instance=getattr(instance, 'settings', None),
                    data={},
                    context=self.context
                )
                settings_serializer.is_valid(raise_exception=True)
                validated_data['settings'] = settings_serializer.save(campaign=instance, **settings_data)
            if steps_data is not None:
                instance.set_step_order([s.pk for s in steps_data])
            return instance

    @transaction.atomic
    def update(self, instance: Campaign, validated_data: dict) -> Campaign:
        steps_data = validated_data.get('steps')

        settings_data = validated_data.pop('settings', None)
        with transaction.atomic():
            if settings_data is not None:
                settings_serializer = CampaignSettingsSerializer(
                    instance=getattr(instance, 'settings', None),
                    data={},
                    context=self.context
                )
                settings_serializer.is_valid(raise_exception=True)
                instance.settings = settings_serializer.save(campaign=instance, **settings_data)

            instance = super().update(instance, validated_data)
            if steps_data is not None:
                instance.set_step_order([s.pk for s in steps_data])
            instance.save()

        return instance


class BaseParticipationSerializer(rest_framework_bulk.BulkSerializerMixin, serializers.ModelSerializer):
    status = EnumField(ParticipationStatus, default=ParticipationStatus.ACTIVE)

    sent_emails_count = serializers.IntegerField(read_only=True)
    opened_emails_count = serializers.IntegerField(read_only=True)
    link_clicked_in_emails_count = serializers.IntegerField(read_only=True)
    replied_emails_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Participation
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'id', 'contact', 'campaign', 'status', 'activation',
            'sent_emails_count', 'opened_emails_count', 'link_clicked_in_emails_count', 'replied_emails_count',
        )


class NestedCampaignParticipationSerializer(BaseParticipationSerializer):
    contact = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all())
    campaign = serializers.HiddenField(default=nested_view_contextual_default(Campaign))


class NestedContactParticipationSerializer(BaseParticipationSerializer):
    contact = serializers.HiddenField(default=nested_view_contextual_default(Contact))
    campaign = serializers.PrimaryKeyRelatedField(queryset=Campaign.objects.all())


class TemplateCampaignContextSerializer(serializers.Serializer):
    title = serializers.CharField(source='name')


class TemplateContextSerializer(serializers.Serializer):
    """
    This serializer provides information context for templates renderer
    """
    email = serializers.EmailField(source='contact.email')
    title = serializers.CharField(source='contact.title')
    first_name = serializers.CharField(source='contact.first_name')
    last_name = serializers.CharField(source='contact.last_name')

    phone_number = PhoneNumberField(source='contact.phone_number')

    company_name = serializers.CharField(source='contact.last_name')
    timezone = serializers.CharField(source='contact.timezone')
    city = serializers.CharField(source='contact.city')
    state = serializers.CharField(source='contact.state')
    country = serializers.CharField(source='contact.country')
    street_address = serializers.CharField(source='contact.street_address')
    zip_code = serializers.CharField(source='contact.zip_code')

    campaign = TemplateCampaignContextSerializer()


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = (
            'created',
            'updated',
            'file',
            'name',
            'emails',
            'mimetype',
            'thumbnail',
        )


class PreviewQuerySerializer(serializers.Serializer):
    # TODO: may be limit to campaign only contacts and steps
    contact = serializers.PrimaryKeyRelatedField(required=False, queryset=Contact.objects.all())
    step = serializers.PrimaryKeyRelatedField(required=False, queryset=Step.objects.all())


class PreviewEmailSerializer(serializers.ModelSerializer):
    to = serializers.ListSerializer(child=serializers.CharField())
    cc = serializers.ListSerializer(child=serializers.CharField(), allow_empty=True)
    bcc = serializers.ListSerializer(child=serializers.CharField(), allow_empty=True)

    class Meta:
        model = Email
        fields = (
            'from_email',
            'to', 'cc', 'bcc',
            'subject', 'html_message',

            # TODO: attachments
        )


def filter_user_inbox(qs, context):
    request = context['request']
    if request.user.is_authenticated:
        mailboxes = request.user.email_accounts.values_list('incoming_id', flat=True)
        return qs.filter(mailbox_id__in=mailboxes)
    return qs.none()


def filter_user_active_email_provider(qs, context):
    request = context['request']
    if request.user.is_authenticated:
        return qs.filter(user=request.user, incoming__active=True)
    return qs.none()


class EmailMessageSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=CurrentUserDefault())
    provider = ContextualPrimaryKeyRelatedField(
        queryset=EmailAccount.objects.all(),
        queryset_filter=filter_user_active_email_provider,
        write_only=True,
        required=False)
    sender = serializers.CharField(write_only=True)

    to = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(),
        write_only=True)

    html_content = serializers.CharField(source='html')

    in_reply_to = ContextualPrimaryKeyRelatedField(
        queryset=Message.objects.none(),
        queryset_filter=filter_user_inbox,
        allow_null=True,
        required=False,
    )
    track_links = serializers.BooleanField(write_only=True, required=False)
    track_opening = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Message
        fields = (
            'user',
            'id',
            'subject',
            'sender',
            'to',
            'from_header',
            'to_header',
            'outgoing',
            'html_content',
            'in_reply_to',
            'track_links',
            'track_opening',
        )

        read_only_fields = (
            'id',
            'from_header', 'to_header',
            'outgoing',)

    def create(self, validated_data: dict):
        in_reply_to = validated_data.get('in_reply_to', None)  # type: typing.Optional[Message]
        provider = validated_data.get('provider', None)  # type: typing.Optional[EmailAccount]

        contact = validated_data['to']  # type: Contact
        campaign = None  # type: typing.Optional[Campaign]
        user = validated_data['user']
        bcc = None
        if in_reply_to:
            loop_protection = []
            inbox_msg = in_reply_to
            while inbox_msg and inbox_msg.message_id not in loop_protection:
                loop_protection.append(inbox_msg.message_id)
                if inbox_msg.outgoing:
                    scheduled_email = inbox_msg.scheduled  # type: typing.Optional[ScheduledEmail]
                    if scheduled_email:
                        campaign = scheduled_email.stage.step.campaign
                        validated_data.setdefault('track_links', campaign.settings.track_links)
                        validated_data.setdefault('track_opening', campaign.settings.track_opening)
                        if not provider:
                            provider = scheduled_email.stage.get_provider()

                        break

                inbox_msg = inbox_msg.in_reply_to

        if not provider:
            provider = EmailAccount.get_default(user)

        email_context = render_email(validated_data['subject'],
                                     '',
                                     validated_data['html'],
                                     TemplateContext(contact, campaign, user))

        generated_email = generate_email(
            sender=provider.from_email(validated_data['sender']),
            email_context=email_context,
            to=[contact.email, ],
            cc=None,
            bcc=bcc,
            in_reply_to=in_reply_to
        )

        tracked_email = add_tracking_info(
            generated_email,
            click_tracking=validated_data.get('track_links', False),
            open_tracking=validated_data.get('track_opening', False),
        )

        tracked_email.save()

        email_msg = prepare_email_message(tracked_email, provider)

        assert email_msg

        # todo: change to async api
        recorded_email = dispatch(tracked_email)
        if not recorded_email:
            try:
                log = tracked_email.logs.latest('date')
            except Log.DoesNotExist:
                log = None

            details = log.message if log else None
            if not details:
                details = 'Internal error during sending'
            raise UnprocessableEntity(detail=details)

        return recorded_email

    def update(self, instance, validated_data):
        raise NotImplementedError(
            "Current implementation do not allow to update instances. "
            "We expect them to be immutable."
        )


class NestedEmailMessageSerializer(EmailMessageSerializer):
    to = serializers.HiddenField(default=nested_view_contextual_default(Contact, key_for_pk='contact'))


class ContactLeadSerializer(serializers.ModelSerializer):
    generator = serializers.HiddenField(default=nested_view_contextual_default(Contact, key_for_pk='generator'))

    company_employee_count = EnumByNameField(CompanyEmployeeCountLevel)
    company_revenue = EnumByNameField(CompanyRevenue)
    department = EnumByNameField(LeadDepartment)
    level = EnumByNameField(LeadLevel)

    status = EnumField(ContactLeadStatus)

    class Meta:
        model = ContactLead
        list_serializer_class = rest_framework_bulk.BulkListSerializer
        fields = (
            'generator',
            'id',

            'city',
            'state',
            'country',
            'street_address',
            'zip_code',

            'email',
            'phone_number',

            'first_name',
            'last_name',
            'title',

            'timezone',

            'company_name',
            'company_employee_count',
            'company_revenue',
            'department',
            'level',

            'status',
        )


class LeadGenerationRequestSerializer(serializers.ModelSerializer):
    company_employee_count = serializers.ListField(
        child=EnumField(CompanyEmployeeCountLevel),
        max_length=len(CompanyEmployeeCountLevel),
        allow_empty=True,
        default=[]
    )
    company_revenue = serializers.ListField(
        child=EnumField(CompanyRevenue),
        max_length=len(CompanyRevenue),
        allow_empty=True,
        default=[]
    )
    department = serializers.ListField(
        child=EnumField(LeadDepartment),
        max_length=len(LeadDepartment),
        allow_empty=True,
        default=[]
    )
    level = serializers.ListField(
        child=EnumField(LeadLevel),
        max_length=len(LeadLevel),
        allow_empty=True,
        default=[]
    )

    email_deliverability = EnumField(LeadEmailDeliverability, default=LeadEmailDeliverability.ANY)

    status = EnumField(LeadGenerationRequestStatus, default=LeadGenerationRequestStatus.CREATED)
    approve = serializers.BooleanField(required=False, write_only=True, )

    class Meta:
        model = LeadGenerationRequest
        fields = (
            'id',
            'campaign',
            'company_name',
            'company_industry_name',
            'company_sic_code',
            'company_employee_count',
            'company_revenue',

            'name',
            'title',
            'department',
            'level',

            'email_deliverability',

            'city',
            'state',
            'country',
            'zip_code',

            # 'exclude_leads',
            # 'exclude_inactive_leads',
            'status',
            'approve',
            'import_per_day',
        )
        read_only_fields = (
            'status',
        )

    def create(self, validated_data: dict) -> LeadGenerationRequest:
        if 'approve' in validated_data:
            raise serializers.ValidationError(dict(read='Only existed requests can be approved'))
        return super().create(validated_data)

    def update(self, instance: LeadGenerationRequest, validated_data: dict) -> LeadGenerationRequest:
        approve = validated_data.pop('approve', None)
        instance = super().update(instance, validated_data)
        if approve is True:
            instance.status = LeadGenerationRequestStatus.WORKING
            instance.save()

        return instance
