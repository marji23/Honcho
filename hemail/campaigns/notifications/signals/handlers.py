from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import ugettext_noop as _
from pinax.notifications import models as notifications

from ..models import Notification


@receiver(post_save, sender=Notification)
def _resend_tracking_info_signals(sender, instance: Notification,
                                  created: bool, **kwargs: dict) -> None:
    if not created:
        return

    extra_context = dict(message=instance.pk)
    extra_context.update(instance.extra_context)

    notifications.send([instance.user], instance.action.label, extra_context)


def create_notice_types(sender, **kwargs) -> None:
    assert "pinax.notifications" in settings.INSTALLED_APPS

    notifications.NoticeType.create('email_opened',
                                    _("Email Opened"),
                                    _("contact opened you email"))

    notifications.NoticeType.create('email_link_clicked',
                                    _("Email was forwarded"),
                                    _("an invitation you sent has been accepted"))

    notifications.NoticeType.create('email_replied',
                                    _("Email was replied"),
                                    _("an invitation you sent has been accepted"))

    # TODO: has no idea how to find this out
    # notifications.NoticeType.create('email_forwarded',
    #                                 _("Email was forwarded"),
    #                                 _("an invitation you sent has been accepted"))

    # TODO: I guess this can be handled only in case of link instead of attachment
    # notifications.NoticeType.create('email_attachment_opened',
    #                                 _("Email was forwarded"),
    #                                 _("an invitation you sent has been accepted"))
