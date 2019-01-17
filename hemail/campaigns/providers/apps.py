from django.apps import AppConfig


class ProvidersConfig(AppConfig):
    name = 'campaigns.providers'
    icon = '<i class="material-icons">import_export</i>'

    def ready(self):
        # noinspection PyUnresolvedReferences
        from .signals import handlers  # noqa
