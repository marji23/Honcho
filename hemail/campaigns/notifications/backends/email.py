import logging
from typing import Dict, Optional, Sequence

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext
from pinax.notifications.backends.base import BaseBackend
from post_office import mail

logger = logging.getLogger(__file__)


class EmailBackend(BaseBackend):
    spam_sensitivity = 2

    def __init__(self, medium_id, spam_sensitivity=None) -> None:
        super().__init__(medium_id, spam_sensitivity)

    def can_send(self, user, notice_type, scoping) -> bool:
        can_send = super(EmailBackend, self).can_send(user, notice_type, scoping)
        if can_send and user.email:
            return True
        return False

    def deliver(self, recipient, sender: Optional,
                notice_type: 'pinax.notifications.models.NoticeType',
                extra_context: dict) -> None:

        # TODO: require this to be passed in extra_context

        context = self.default_context()
        context.update({
            "recipient": recipient,
            "sender": sender,
            "notice": ugettext(notice_type.display),
        })
        context.update(extra_context)

        messages = self.get_formatted_messages((
            'email_subject.txt',
            'email_content.txt',
            'email_html_content.txt',
        ), notice_type.label, context)

        mail.send(
            recipients=[recipient.email],
            sender=settings.DEFAULT_FROM_EMAIL,
            context=context,

            subject="".join(messages['email_subject.txt'].splitlines()),
            message=messages['email_content.txt'],
            html_message=messages['email_html_content.txt'],

            # backend_alias='', # TODO: set separate backend for notifications
        )

    def get_formatted_messages(self, formats: Sequence[str], label: str, context: dict) -> Dict[str, str]:
        """
        Returns a dictionary with the format identifier as the key. The values are
        are fully rendered templates with the given context.
        """
        format_templates = {}
        for fmt in formats:
            format_templates[fmt] = render_to_string((
                "campaigns/notifications/{0}/{1}".format(label, fmt),
                "campaigns/notifications/{0}".format(fmt)), context)
        return format_templates
