from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _


def array_unique_elements_validator(array):
    if len(array) != len(set(array)):
        raise ValidationError(_('Array should not contain duplicated values'), )
