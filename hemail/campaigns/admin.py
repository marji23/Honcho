import datetime
from typing import Optional

from django.contrib import admin
from post_office.admin import EmailAdmin, EmailTemplateInline
from post_office.models import Email, STATUS

from campaigns.models import CampaignSettings
from .models import (
    Campaign, EmailStage, Participation, PassedStageResult, ScheduledEmail, Step,
    TrackingInfo
)

__author__ = 'yushkovskiy'


class StepInline(admin.TabularInline):
    model = Step
    extra = 0
    show_change_link = True

    readonly_fields = ('problems',)


class ParticipationInline(admin.TabularInline):
    model = Participation
    extra = 0
    show_change_link = True


class SettingsInline(admin.StackedInline):
    model = CampaignSettings
    extra = 0
    show_change_link = True
    can_delete = False


class EmailStageInline(EmailTemplateInline):
    model = EmailStage
    fields = ('subject', 'html_content', 'provider')
    formfield_overrides = {
    }
    show_change_link = True


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status',)
    inlines = [StepInline, ParticipationInline, SettingsInline, ]
    list_filter = ('owner', 'status',)
    readonly_fields = ('problems',)


class PassedStageResultInline(admin.TabularInline):
    model = PassedStageResult
    extra = 0
    show_change_link = True


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ('id', 'contact', 'campaign', 'status',)
    list_filter = ('contact', 'campaign', 'status',)
    inlines = (PassedStageResultInline,)
    readonly_fields = ('next_send',)

    def next_send(self, instance: Participation) -> Optional[datetime.datetime]:
        next_send_tuple = instance.get_next_step_and_send_datetime()
        return next_send_tuple[1] if next_send_tuple else None


def send_emails(step_admin: 'StepAdmin', request, queryset) -> None:
    total = dict(
        sent=0,
        failed=0,
        queued=0,
    )
    for step in queryset.all():
        emails = step.submit_emails()  # priority=Priority.NOW)
        for email in emails:
            for st in total.keys():
                if getattr(STATUS, st) == email.email.status:
                    total[st] = total.get(st, 0) + 1

    step_admin.message_user(request,
                            "Emails %(sent)d sent, %(failed)d failed, %(queued)d queued" % total)


send_emails.short_description = 'Send emails'


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    inlines = [EmailStageInline, ]
    actions = [send_emails, ]
    list_display = ('id', 'campaign', '_order',)
    list_filter = ('campaign',)
    readonly_fields = ('problems',)


@admin.register(TrackingInfo)
class TackingInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'created', 'email',)
    list_filter = ('type', 'created',)
    readonly_fields = ('created',)


class EmailInline(admin.TabularInline):
    model = Email


def requeue(scheduled_email_admin, request, queryset):
    """An admin action to requeue emails."""
    Email.objects.filter(id__in=queryset.values('email_id')).update(status=STATUS.queued)


requeue.short_description = 'Requeue selected emails'


def send_now(scheduled_email_admin, request, queryset):
    """An admin action to requeue emails."""
    for scheduled_email in queryset:
        scheduled_email.dispatch()


send_now.short_description = 'Immediately send selected emails'


@admin.register(ScheduledEmail)
class ScheduledEmailAdmin(admin.ModelAdmin):
    list_display = ('id', '__str__', 'email__status',)
    actions = [requeue, send_now, ]
    list_filter = ['stage', 'email__status', ]

    def email__status(self, instance):
        return dict(Email.STATUS_CHOICES).get(instance.email.status, '')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('email')


class ScheduledEmailInline(admin.TabularInline):
    model = ScheduledEmail
    extra = 0


class OverridenEmailAdmin(EmailAdmin):
    list_display = ('id', 'to_display', 'subject',
                    'status', 'last_updated')
    inlines = EmailAdmin.inlines + [ScheduledEmailInline, ]
    pass


admin.site.unregister(Email)
admin.site.register(Email, OverridenEmailAdmin)
