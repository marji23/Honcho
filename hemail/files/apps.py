from django.apps import AppConfig


class FilesConfig(AppConfig):
    name = 'files'
    icon = '<i class="material-icons">description</i>'

    def ready(self):
        # noinspection PyUnresolvedReferences
        from .signals import handlers  # noqa
