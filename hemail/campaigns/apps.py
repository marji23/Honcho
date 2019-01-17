from django.apps import AppConfig
from watson import search as watson


class CampaignsConfig(AppConfig):
    name = 'campaigns'
    icon = '<i class="material-icons">contact_mail</i>'

    def ready(self) -> None:
        # noinspection PyUnresolvedReferences
        from .signals import handlers  # noqa

        from django_mailbox.models import Message
        watson.register(Message, fields=(
            'subject',
            'from_header',
            'to_header',
            'html',
            'text',
        ))
