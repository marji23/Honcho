import pytz
from django.core.exceptions import ValidationError
from timezone_utils.forms import TimeZoneField as OriginalTimeZoneField

from .utils import FixedOffset


class TimeZoneField(OriginalTimeZoneField):
    def to_python(self, value):
        value = super(OriginalTimeZoneField, self).to_python(value)

        if not value:
            return value

        try:
            return pytz.timezone(str(value))
        except pytz.UnknownTimeZoneError:
            try:
                fixed = FixedOffset.parse(str(value))
                if fixed:
                    return fixed

            except ValueError:
                pass

            raise ValidationError(
                message=self.error_messages['invalid'],
                code='invalid',
                params={'value': value}
            )
