from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_countries.fields import CountryField

from common.fields import ImageField, TimeZoneField
from hemail.storage import storages
from tenancy.models import TenantData


def get_upload_path(instance: 'Profile', filename: str) -> str:
    return '/'.join([
        'avatars',
        str(instance.id),
        filename,
    ])


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tenant = models.ForeignKey(TenantData, on_delete=models.SET_NULL, blank=True, null=True, related_name='users')

    timezone = TimeZoneField(default='US/Pacific')
    country = CountryField(blank=True)

    avatar = ImageField(_('Avatar'), upload_to=get_upload_path, storage=storages['default'], null=True, blank=True)

    def __unicode__(self):
        return "{}'s profile".format(self.user.username)

    @property
    def account_verified(self):
        if not self.user.is_authenticated:
            return False
        try:
            return EmailAddress.objects.get(email=user_email(self.user)).verified
        except EmailAddress.MultipleObjectsReturned:
            # todo: log incorrect config - no unique email
            return False
        except EmailAddress.DoesNotExist:
            return False
