import logging
from urllib.parse import urljoin

from django.conf import settings
from django.db import connection
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_mailbox.models import Message
from django_mailbox.signals import message_received

from ..models import (
    Campaign, CampaignProblems, CampaignSettings, CampaignStatus, EmailStage, LeadGenerationRequest, Participation,
    ParticipationStatus, Step, StepProblems, TrackingInfo, TrackingType
)
from ..providers.models import CoolMailbox
from ..tasks import process_lead_generation_request

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Campaign)
def _create_user_profile(sender, instance: Campaign, created: bool, **kwargs) -> None:
    if created:
        CampaignSettings.objects.create(campaign=instance)


@receiver(post_save, sender=Campaign)
def _change_status_with_paused(sender, instance: Campaign, **kwargs) -> None:
    if instance.status == CampaignStatus.DRAFT:
        if instance.problems:
            return
        for step in instance.steps.all():
            if step.problems:
                return
        instance.status = CampaignStatus.PAUSED
        instance.save(update_fields=('status',))


@receiver(post_save, sender=Step)
def _campaign_problem_check_on_steps_creation(sender, instance: Step, created: bool, **kwargs) -> None:
    if created:
        modified = False
        campaign = instance.campaign
        campaign.refresh_from_db(fields=['problems', ])
        if CampaignProblems.NO_STEPS in campaign.problems:
            campaign.problems.remove(CampaignProblems.NO_STEPS)
            modified = True
        if CampaignProblems.EMPTY_STEP not in campaign.problems:
            campaign.problems.append(CampaignProblems.EMPTY_STEP)
            modified = True

        if modified:
            campaign.save(update_fields=('problems',))


@receiver(post_delete, sender=Step)
def _campaign_problem_check_on_steps_deletion(sender, instance: Step, **kwargs) -> None:
    campaign = instance.campaign
    campaign.refresh_from_db(fields=['problems', ])

    modified = False
    if CampaignProblems.NO_STEPS not in campaign.problems:
        if not campaign.steps.exists():
            campaign.problems.append(CampaignProblems.NO_STEPS)
            modified = True
            if CampaignProblems.EMPTY_STEP in campaign.problems:
                campaign.problems.remove(CampaignProblems.EMPTY_STEP)
        elif not campaign.steps.filter(emails=None).exists():
            campaign.problems.remove(CampaignProblems.EMPTY_STEP)
            modified = True

    if modified:
        campaign.save(update_fields=('problems',))


@receiver(post_save, sender=EmailStage)
def _campaign_problem_check_on_email_stage_creation(sender, instance: EmailStage, created: bool, **kwarg) -> None:
    step = instance.step
    step.refresh_from_db(fields=['problems', ])
    if StepProblems.EMPTY_STEP in step.problems:
        step.problems.remove(StepProblems.EMPTY_STEP)
        step.save(update_fields=('problems',))
    campaign = step.campaign
    campaign.refresh_from_db(fields=['problems', ])
    if CampaignProblems.EMPTY_STEP in campaign.problems:
        if not campaign.steps.filter(emails=None).exists():
            campaign.problems.remove(CampaignProblems.EMPTY_STEP)
            campaign.save(update_fields=('problems',))


@receiver(post_delete, sender=EmailStage)
def _campaign_problem_check_on_email_stage_deletion(sender, instance: EmailStage, **kwargs) -> None:
    step = instance.step
    if not step.emails.exists() and not step.texts.exists():
        campaign = step.campaign
        campaign.refresh_from_db(fields=['problems', ])
        if CampaignProblems.EMPTY_STEP not in campaign.problems:
            campaign.problems.append(CampaignProblems.EMPTY_STEP)
            campaign.save(update_fields=['problems', ])
        step.refresh_from_db(fields=['problems', ])
        if StepProblems.EMPTY_STEP not in step.problems:
            step.problems.append(StepProblems.EMPTY_STEP)
            step.save(update_fields=['problems', ])


@receiver(post_save, sender=Participation)
def _campaign_problem_check_on_participation_creation(sender, instance: Participation,
                                                      created: bool, **kwarg) -> None:
    if created:
        campaign = instance.campaign
        campaign.refresh_from_db(fields=['problems', ])
        if CampaignProblems.NO_CONTACTS in campaign.problems:
            campaign.problems.remove(CampaignProblems.NO_CONTACTS)
            campaign.save(update_fields=['problems', ])


@receiver(post_delete, sender=Participation)
def _campaign_problem_check_on_participation_deletion(sender, instance: Participation, **kwargs) -> None:
    campaign = instance.campaign
    if CampaignProblems.NO_CONTACTS not in campaign.problems:
        campaign.refresh_from_db(fields=['problems', ])
        if not campaign.participation_set.exists():
            campaign.problems.append(CampaignProblems.NO_CONTACTS)
            campaign.save(update_fields=('problems',))


@receiver(message_received)
def _try_match_message(sender: CoolMailbox, message: Message, **kwarg) -> None:
    if not message.outgoing:
        return
    in_reply_to = message.in_reply_to
    if in_reply_to is None:
        # todo: should submit task for more complicated comparation
        return

    scheduled = in_reply_to.scheduled
    if scheduled is None:
        return

    campaign = scheduled.stage.step.campaign

    participation = scheduled.contact.participation_set.get(campaign=campaign)
    participation.status = ParticipationStatus.RESPOND
    participation.save(update_fields=('status',))


@receiver(post_save, sender=TrackingInfo)
def _resend_tracking_info_signals(sender, instance: TrackingInfo,
                                  created: bool, **kwargs: dict) -> None:
    if not created:
        return

    from ..notifications.models import Notification

    campaign = instance.email.scheduled.stage.step.campaign
    contact = instance.email.scheduled.contact
    owner = campaign.owner

    extra_context = dict(
        contact_link=urljoin(settings.FRONTEND_BASE_URL, 'contacts/%s' % contact.id),
        contact_name=contact.full_name,
        company_name=contact.company_name,
        phone_number=contact.phone_number,
        campaign_link=urljoin(settings.FRONTEND_BASE_URL, 'campaigns/%s' % campaign.id),
        campaign_title=campaign.name,
    )

    if TrackingType.OPEN == instance.type:
        Notification.send(owner, 'email_opened', extra_context)
    elif TrackingType.LINK_CLICKED == instance.type:
        Notification.send(owner, 'email_link_clicked', extra_context)
    else:
        logger.error('Unsupported tracking type: %s', instance.type)


@receiver(post_save, sender=LeadGenerationRequest)
def _lead_generation_requested(sender, instance: LeadGenerationRequest,
                               created: bool, **kwargs: dict) -> None:
    if created:
        process_lead_generation_request.delay(connection.tenant.id, instance.id)
