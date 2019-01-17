import json
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from pinax.notifications.hooks import hookset
from pinax.notifications.models import NoticeType
from pinax.notifications.utils import load_media_defaults
from tenant_schemas.utils import tenant_context

logger = logging.getLogger(__name__)

NOTIFICATION_CHANNEL = "nyt_all-{notification_key:s}"

NOTICE_MEDIA, NOTICE_MEDIA_DEFAULTS = load_media_defaults()
MEDIUM = 'channels'
MEDIUM_ID = {label: medium_id for medium_id, label in NOTICE_MEDIA}.get(MEDIUM, None)


def get_allowed_notice_types(user):
    if MEDIUM_ID is not None:
        notice_types = NoticeType.objects.all()
        for notice_type in notice_types:
            notice_setting = hookset.notice_setting_for_user(
                user,
                notice_type,
                MEDIUM_ID,
                scoping=None
            )
            if notice_setting.send:
                yield notice_type


class NotificationsConsumer(WebsocketConsumer):

    def connect(self) -> None:
        user = self.scope.get('user', None)
        if not user or user.is_anonymous:
            self.close()
            return

        logger.info("Adding new connection for user {}".format(user))
        tenant = user.profile.tenant
        with tenant_context(tenant):
            for notice_type in get_allowed_notice_types(user):
                group_name = NOTIFICATION_CHANNEL.format(notification_key=notice_type.label)
                async_to_sync(self.channel_layer.group_add)(group_name, self.channel_name)

        self.accept()

    def disconnect(self, close_code) -> None:
        user = self.scope.get("user", None)
        if not user or user.is_anonymous:
            return

        logger.info("Removing connection for user {} (disconnect)".format(user))

        for notice_type in get_allowed_notice_types(user):
            group_name = NOTIFICATION_CHANNEL.format(notification_key=notice_type.label)
            async_to_sync(self.channel_layer.group_discard)(group_name, self.channel_name)

    def notification_message(self, event) -> None:
        if self.scope['user'].id != event.get('recipient', None):
            return

        self.send(text_data=json.dumps(
            dict(type=event['notice'], context=event.get('context', {}))
        ))
