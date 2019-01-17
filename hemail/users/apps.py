from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        # Do allauth monkeypatches
        from .hacks import monkeypatch_allauth
        monkeypatch_allauth()

        # noinspection PyUnresolvedReferences
        from .signals import handlers  # noqa
