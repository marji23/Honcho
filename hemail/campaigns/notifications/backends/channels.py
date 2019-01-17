import logging
from typing import Optional

from asgiref.sync import async_to_sync
from channels import DEFAULT_CHANNEL_LAYER
from channels.layers import get_channel_layer
from django.utils.translation import ugettext
from pinax.notifications.backends.base import BaseBackend

logger = logging.getLogger(__file__)


class ChannelsBackend(BaseBackend):
    spam_sensitivity = 2
    channel_layer = DEFAULT_CHANNEL_LAYER

    def __init__(self, medium_id, spam_sensitivity=None) -> None:
        super().__init__(medium_id, spam_sensitivity)
        self.layer = get_channel_layer(self.channel_layer)
        self.group_send = async_to_sync(self.layer.group_send)

    def deliver(self, recipient, sender: Optional,
                notice_type: 'pinax.notifications.models.NoticeType',
                extra_context: dict) -> None:
        from ..consumers import NOTIFICATION_CHANNEL

        group_name = NOTIFICATION_CHANNEL.format(notification_key=notice_type.label)
        self.group_send(group_name, dict(
            type='notification.message',
            recipient=recipient.id,
            notice=ugettext(notice_type.label),
            context=extra_context,
        ))
