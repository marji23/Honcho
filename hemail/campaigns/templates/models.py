import enum

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from enumfields import EnumField
from post_office import models as post_office_models

from users.utils import tenant_users


@enum.unique
class EmailTemplateSharingStatus(enum.Enum):
    PERSONAL = 'PERSONAL'
    TEAM = 'TEAM'


class Folder(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    name = models.TextField()

    def __str__(self) -> str:
        return self.name


class EmailTemplate(post_office_models.EmailTemplate):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, limit_choices_to=tenant_users)
    sharing = EnumField(EmailTemplateSharingStatus, max_length=32, default=EmailTemplateSharingStatus.PERSONAL,
                        help_text=_('Template sharing level'))

    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='templates', )
    # TODO: add tags
