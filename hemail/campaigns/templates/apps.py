from django.apps import AppConfig
from watson import search as watson


class TemplatesConfig(AppConfig):
    name = 'campaigns.templates'
    icon = '<i class="material-icons">settings_ethernet</i>'

    def ready(self) -> None:
        super().ready()

        EmailTemplate = self.get_model('EmailTemplate')
        watson.register(EmailTemplate, fields=(
            'name',
            'description',
            'subject',
            'content',
            'html_content',
        ))
