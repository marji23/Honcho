from django.apps import AppConfig
from watson import search as watson


class ContactsConfig(AppConfig):
    name = 'campaigns.contacts'
    icon = '<i class="material-icons">account_box</i>'

    def ready(self) -> None:
        super().ready()

        Contact = self.get_model('Contact')
        watson.register(Contact, fields=(
            'email',
            'title',
            'company_name',
            'city',
            'state',
            'country',
            'street_address',
            'zip_code',
            'phone_number',
        ))

        Note = self.get_model('Note')
        watson.register(Note, fields=(
            'topic',
            'content',
        ))
