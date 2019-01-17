from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NotificationsConfig(AppConfig):
    name = 'campaigns.notifications'
    icon = '<i class="material-icons">notifications</i>'

    def ready(self) -> None:
        # noinspection PyUnresolvedReferences
        from .signals import handlers  # noqa

        post_migrate.connect(handlers.create_notice_types, sender=self)
