import logging

import rest_framework_bulk
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.http import Http404
from django_filters import rest_framework
from django_mailbox.models import Message
from pytracking import TrackingResult
from pytracking.django import ClickTrackingView, OpenTrackingView
from rest_framework import filters, metadata, mixins, permissions, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.fields import SkipField
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework_extensions.mixins import NestedViewSetMixin
from tenant_schemas.utils import get_public_schema_name, get_tenant_model, tenant_context

from common.models import SQCount
from common.viewsets import RetrieveUpdateSingleModelViewSet
from . import serializers
from .contacts.models import Contact
from .filters import ContactLeadFilter, MessageFilter, ParticipationFilter
from .models import (
    Attachment, Campaign, CampaignSettings, ContactLead, EmailStage, LeadGenerationRequest, Participation,
    ScheduledEmail, Step, TemplateContext, TrackingInfo, TrackingType
)

logger = logging.getLogger(__name__)


class CampaignsViewSet(rest_framework_bulk.BulkModelViewSet):
    queryset = Campaign.objects.annotate(
        contacts_count=models.Count('contacts', distinct=True),
        sent_emails_count=SQCount(ScheduledEmail.objects
                                  .exclude(sent=None)
                                  .filter(stage__step__campaign=models.OuterRef('pk'))
                                  .values('pk')),
        opened_emails_count=SQCount(TrackingInfo.objects
                                    .filter(type=TrackingType.OPEN,
                                            email__scheduled__stage__step__campaign=models.OuterRef('pk'))
                                    .values('pk')),
        link_clicked_in_emails_count=SQCount(TrackingInfo.objects
                                             .filter(type=TrackingType.LINK_CLICKED,
                                                     email__scheduled__stage__step__campaign=models.OuterRef('pk'))
                                             .values('pk')),
        replied_emails_count=SQCount(TrackingInfo.objects
                                     .filter(email__scheduled__stage__step__campaign=models.OuterRef('pk'))
                                     .exclude(email__in_reply_to=None)
                                     .values('pk')),
    )
    serializer_class = serializers.CampaignSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ('name', 'contacts_count')

    @detail_route()
    def preview(self, request, pk: int) -> Response:
        campaign = self.get_object()

        query_params_serializer = serializers.PreviewQuerySerializer(data=request.query_params.dict())
        query_params_serializer.is_valid(raise_exception=True)

        contacts = campaign.contacts.exclude(blacklisted=True)
        contact_lookup = query_params_serializer.validated_data.get('contact')
        if contact_lookup is not None:
            contacts = contacts.filter(id=contact_lookup.id)

        total = []
        stages = EmailStage.objects.filter(step__campaign=campaign)
        step_lookup = query_params_serializer.validated_data.get('step')
        if step_lookup is not None:
            stages = stages.filter(step=step_lookup)

        contacts_last_updated = max((int(c.updated.timestamp()) for c in contacts))
        for email_stage in stages:
            last_updated = max(int(email_stage.last_updated.timestamp()), contacts_last_updated)
            cache_key = 'campaign-preview-%d-%d-%d' % (campaign.id, email_stage.id, last_updated,)
            cached_data = cache.get(cache_key)
            if cached_data:
                total += cached_data
                continue

            generated_data = []
            emails_to_contact_id = email_stage.generate_emails(contacts)
            for contact_id, email in emails_to_contact_id:
                serializer = serializers.PreviewEmailSerializer(instance=email,
                                                                context=self.get_serializer_context())
                data = serializer.data
                data.update(step=email_stage.step_id, contact=contact_id)

                generated_data.append(data)

            total += generated_data
            cache.set(cache_key, generated_data, 60 * 60)

        return Response(total, status=status.HTTP_200_OK)


class CampaignSettingsViewSet(NestedViewSetMixin, RetrieveUpdateSingleModelViewSet):
    queryset = CampaignSettings.objects.all()
    serializer_class = serializers.NestedCampaignSettingsSerializer
    permission_classes = (permissions.DjangoObjectPermissions,)


class StepViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = Step.objects.all()
    serializer_class = serializers.StepSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class EmailStageViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = EmailStage.objects.all()
    serializer_class = serializers.EmailStageSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class BaseParticipationViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = Participation.objects.annotate(
        sent_emails_count=SQCount(ScheduledEmail.objects
                                  .exclude(sent=None)
                                  .filter(stage__step__participations=models.OuterRef('pk'))
                                  .values('pk')
                                  .distinct()),
        opened_emails_count=SQCount(TrackingInfo.objects.filter(
            type=TrackingType.OPEN,
            email__scheduled__stage__step__participations=models.OuterRef('pk')
        ).values('pk').distinct()),
        link_clicked_in_emails_count=SQCount(TrackingInfo.objects.filter(
            type=TrackingType.LINK_CLICKED,
            email__scheduled__stage__step__participations=models.OuterRef('pk')
        ).values('pk').distinct()),
        replied_emails_count=SQCount(TrackingInfo.objects
                                     .filter(email__scheduled__stage__step__participations=models.OuterRef('pk'))
                                     .exclude(email__in_reply_to=None)
                                     .values('pk')
                                     .distinct()),
    )

    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = ParticipationFilter


class ContactsParticipationViewSet(BaseParticipationViewSet):
    serializer_class = serializers.NestedContactParticipationSerializer


class CampaignsParticipationViewSet(BaseParticipationViewSet):
    serializer_class = serializers.NestedCampaignParticipationSerializer


class AttachmentViewSet(mixins.CreateModelMixin,
                        viewsets.GenericViewSet):
    queryset = Attachment.objects.all()
    serializer_class = serializers.AttachmentSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class TenancyTrackingViewMixin(object):
    tenant_queryset = get_tenant_model().objects.exclude(schema_name=get_public_schema_name())

    def notify_tracking_event(self, tracking_result: TrackingResult):
        tenant_id = tracking_result.metadata.get('tenant', None)
        msg_id = tracking_result.metadata.get('id', None)
        if not tenant_id or not msg_id:
            logger.warning('Incorrect tracking result metadata. tenant: %s; id: %s',
                           tenant_id, msg_id)
            raise Http404
        tenant = get_object_or_404(self.tenant_queryset, id=tenant_id)
        with tenant_context(tenant):
            email = get_object_or_404(Message, message_id=msg_id)
            self.create_tracking_info(email, tracking_result)

    def create_tracking_info(self, email: Message,
                             tracking_result: TrackingResult) -> None:
        raise NotImplementedError('`create_tracking_info()` must be implemented.')


class EmailOpenTrackingView(TenancyTrackingViewMixin, OpenTrackingView):
    def create_tracking_info(self, email: Message,
                             tracking_result: TrackingResult) -> None:
        TrackingInfo.create_from(TrackingType.OPEN, email, tracking_result)

    def notify_decoding_error(self, exception, request):
        logger.warning('Failed to decode open email tracking info', exception)


class EmailLinksClickTrackingView(TenancyTrackingViewMixin, ClickTrackingView):
    def create_tracking_info(self, email: Message,
                             tracking_result: TrackingResult) -> None:
        TrackingInfo.create_from(TrackingType.OPEN, email, tracking_result)

    def notify_decoding_error(self, exception, request):
        logger.warning('Failed to decode email links clicked tracking info', exception)


class EmailMessagesViewSet(mixins.RetrieveModelMixin,
                           mixins.ListModelMixin,
                           viewsets.GenericViewSet):
    queryset = Message.objects.all()
    serializer_class = serializers.EmailMessageSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = MessageFilter

    def get_queryset(self):
        if self.request.user.is_authenticated:
            mailboxes = self.request.user.email_accounts.values_list('incoming_id', flat=True)
            return self.get_queryset().filter(mailbox_id__in=mailboxes)
        return self.get_queryset().none()


class NestedContactEmailMessageViewSet(NestedViewSetMixin,
                                       mixins.CreateModelMixin,
                                       mixins.RetrieveModelMixin,
                                       mixins.ListModelMixin,
                                       viewsets.GenericViewSet):
    queryset = Message.objects.all()
    serializer_class = serializers.NestedEmailMessageSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = MessageFilter

    def filter_queryset_by_parents_lookups(self, queryset):
        parents_query_dict = self.get_parents_query_dict()
        if not parents_query_dict:
            return queryset

        contact_id = parents_query_dict.get('contact')
        contact = get_object_or_404(Contact, id=contact_id)
        return queryset.filter(
            Q(scheduled__contact_id=contact_id) |
            Q(in_reply_to__scheduled__contact_id=contact_id) |
            Q(from_header__icontains=contact.email) |
            Q(to_header__icontains=contact.email)
        )

    def get_queryset(self):
        if self.request.user.is_authenticated:
            mailboxes = self.request.user.email_accounts.values_list('incoming_id', flat=True)
            return super().get_queryset().filter(mailbox_id__in=mailboxes)
        return self.queryset.none()


class ContextVariablesViewSet(viewsets.ViewSet):
    queryset = Campaign.objects.none()  # required by DjangoModelPermissions
    serializer_class = serializers.TemplateContextSerializer
    permission_classes = (permissions.DjangoModelPermissions,)

    class Metadata(metadata.SimpleMetadata):

        def __init__(self) -> None:
            super().__init__()
            from common.serializers import PhoneNumberField
            self.label_lookup[PhoneNumberField] = 'phone'
            # TODO: add timezone
            # self.label_lookup[TimeZoneField] = 'timezone'

        def get_field_info(self, field: 'rest_framework.fields.Field'):
            field_info = super().get_field_info(field)
            if isinstance(field, Serializer):
                return field_info

            try:
                stack = []
                serializer = field.parent
                while serializer.instance is None:
                    stack.append(serializer)
                    serializer = serializer.parent
                instance = serializer.instance
                while stack:
                    serializer = stack.pop()
                    instance = serializer.get_attribute(instance)

                attribute = field.get_attribute(instance)
            except SkipField:
                return field_info

            value = field.to_representation(attribute)

            field_info['sample'] = value
            return field_info

    def list(self, request, *args, **kwargs) -> Response:
        assert request.user.is_authenticated

        metadata_class = ContextVariablesViewSet.Metadata
        metadater = metadata_class()
        serializer = self.serializer_class(instance=(TemplateContext(
            contact=Contact.objects.first(),
            campaign=Campaign.objects.first(),
            user=request.user
        )))
        info = metadater.get_serializer_info(serializer)
        return Response(info, status=status.HTTP_200_OK)


class LeadGenerationRequestViewSet(viewsets.ModelViewSet):
    queryset = LeadGenerationRequest.objects.all()
    serializer_class = serializers.LeadGenerationRequestSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class NestedContactLeadViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = ContactLead.objects.all()
    serializer_class = serializers.ContactLeadSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = ContactLeadFilter
    ordering_fields = (
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

        'company_name',
        'company_employee_count',
        'company_revenue',
        'department',
        'level',
    )
