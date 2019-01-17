import logging
import time

from django.contrib import admin, messages
from django_mailbox.models import Message, MessageAttachment
from django_mailbox.signals import message_received
from django_mailbox.utils import convert_header_to_unicode

from .models import CoolMailbox, EmailAccount, SmtpConnectionSettings

__author__ = 'yushkovskiy'

logger = logging.getLogger(__name__)


def get_new_mail(email_account_admin, request, queryset) -> None:
    total = 0
    start = time.time()
    for mailbox in queryset.all():
        logger.debug('Receiving mail for %s' % mailbox)
        total += len(mailbox.get_new_mail())
    elapsed = time.time() - start
    email_account_admin.message_user(request, "%s messages received in %f sec." % (total, elapsed))


get_new_mail.short_description = 'Get new mail'


def verify_connections(email_account_admin, request, queryset) -> None:
    for mailbox in queryset.all():
        logger.debug('Verifying %s connection' % mailbox)
        mailbox.verify_connections()


verify_connections.short_description = 'Verify connections'


def resend_message_received_signal(message_admin, request, queryset):
    for message in queryset.all():
        logger.debug("Resending 'message_received' signal for %s" % message)
        message_received.send(sender=message_admin, message=message)


resend_message_received_signal.short_description = 'Re-send message received signal'


def truncate_inbox_messages(mailbox_admin, request, queryset) -> None:
    total = 0
    for mailbox in queryset:
        deleted, _ = mailbox.messages.all().delete()
        total += deleted
        mailbox.last_uid = None
        mailbox.save(update_fields=['last_uid', ])

    mailbox_admin.message_user(request, "%s messages removed" % total)


truncate_inbox_messages.short_description = 'Truncate inbox messages'


class EmailAccountInline(admin.StackedInline):
    model = EmailAccount
    extra = 0


@admin.register(CoolMailbox)
class CoolMailboxAdmin(admin.ModelAdmin):
    icon = '<i class="material-icons">archive</i>'
    list_display = ('uri', 'status', 'status_description',)
    inlines = [EmailAccountInline, ]

    actions = [truncate_inbox_messages, ]


@admin.register(SmtpConnectionSettings)
class SmtpConnectionSettingsAdmin(admin.ModelAdmin):
    icon = '<i class="material-icons">unarchive</i>'
    list_display = ('uri', 'status', 'status_description',)
    inlines = [EmailAccountInline, ]


@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
    icon = '<i class="material-icons">markunread_mailbox</i>'
    list_display = ('user', 'email', 'default', 'sender_name',)

    actions = [get_new_mail, verify_connections, ]


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0


def restore_message_into_inbox(message_admin, request, queryset):
    target_folder = 'restored'
    total = 0
    for mailbox in CoolMailbox.objects.all():
        qs = mailbox.messages.filter(pk__in=queryset)
        if not qs.exists():
            continue

        connection = mailbox.get_connection()
        server = connection.server
        typ, folders = server.list(pattern=target_folder)
        if folders[0] is None:
            message_admin.message_user(
                request,
                "The '%s' folder does not exist, create it for '%s'." % (target_folder, connection),
                level=messages.ERROR,
            )
            return
        for message in qs:
            try:
                email = message.get_email_object()
                data = email.as_bytes()
            except UnicodeEncodeError as e:
                logging.exception('Failed to append email (pk=%s) into mailbox', message.pk)
                message_admin.message_user(request, str(e), level=messages.WARNING)
                continue
            except FileNotFoundError as e:
                logging.exception('Failed to append email (pk=%s) into mailbox', message.pk)
                message_admin.message_user(request, str(e), level=messages.WARNING)
                continue

            r, data = server.append(target_folder, None, None, data)
            msg = data[-1].decode('utf-8', 'replace')
            if r != 'OK':
                logging.error(msg)
                message_admin.message_user(request, msg, level=messages.WARNING)
            else:
                logging.debug(msg)
                total += 1

    message_admin.message_user(request, "%s messages restored" % total)


restore_message_into_inbox.short_description = 'Restore into inbox'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    def attachment_count(self, msg):
        return msg.attachments.count()

    def subject(self, msg):
        return convert_header_to_unicode(msg.subject)

    def envelope_headers(self, msg):
        email = msg.get_email_object()
        return '\n'.join(
            [('%s: %s' % (h, v)) for h, v in email.items()]
        )

    inlines = [
        MessageAttachmentInline,
    ]
    list_display = (
        'subject',
        'processed',
        'read',
        'mailbox',
        'outgoing',
        'attachment_count',
    )
    ordering = ['-processed']
    list_filter = (
        'mailbox',
        'outgoing',
        'processed',
        'read',
    )
    exclude = (
        'body',
    )
    raw_id_fields = (
        'in_reply_to',
    )
    readonly_fields = (
        'mailbox',
        'envelope_headers',
        'text',
        'html',
    )
    actions = [resend_message_received_signal, restore_message_into_inbox, ]
