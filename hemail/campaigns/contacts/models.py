from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from common.fields import TimeZoneField


class Address(models.Model):
    city = models.TextField(verbose_name=_('city'), blank=True)
    state = models.TextField(verbose_name=_('state'), blank=True)
    country = models.TextField(verbose_name=_('country'), blank=True)
    street_address = models.TextField(verbose_name=_('street address'), blank=True)
    zip_code = models.TextField(verbose_name=_('zip code'), blank=True)

    class Meta:
        abstract = True


class Contact(Address, models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    email = models.EmailField(unique=True,
                              verbose_name=_('e-mail address'))
    first_name = models.TextField(verbose_name=_('first name'), blank=True)
    last_name = models.TextField(verbose_name=_('last name'), blank=True)
    timezone = TimeZoneField(blank=True)
    company_name = models.TextField(blank=True)
    title = models.TextField(blank=True)
    phone_number = PhoneNumberField(blank=True)
    blacklisted = models.BooleanField(default=False)

    def __str__(self) -> str:
        return ' '.join(filter(None, [str(self.email), self.first_name, self.last_name]))

    @property
    def full_name(self):
        return ' '.join(filter(None, [self.title, self.first_name, self.last_name]))


class ContactList(models.Model):
    name = models.TextField(unique=True)
    contacts = models.ManyToManyField(Contact, related_name='lists', blank=True)

    class Meta:
        verbose_name = _('ContactList')
        verbose_name_plural = _('ContactLists')

    def __str__(self) -> str:
        return self.name


class Note(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    topic = models.TextField(_('Topic'), blank=True)
    content = models.TextField(_('Content'))
    private = models.BooleanField(_('Private'), default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)

    class Meta:
        verbose_name = _('Note')
        verbose_name_plural = _('Notes')
