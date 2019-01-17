from __future__ import unicode_literals

import six
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers


class HeadersField(serializers.DictField):
    default_error_messages = {
        'invalid': _('Invalid headers.'),
        'max_string_length': _('String value too large.')
    }
    child = serializers.IntegerField()
    MAX_STRING_LENGTH = 1000  # Guard against malicious string inputs.

    def to_internal_value(self, data):
        if isinstance(data, six.text_type) and len(data) > self.MAX_STRING_LENGTH:
            self.fail('max_string_length')
        try:
            result = {}
            sub_strings = data.split(',')
            for sub_string in sub_strings:
                key, value = sub_string.split(':', 1)
                result[key] = int(value)
        except (ValueError, TypeError):
            self.fail('invalid')

        return super().to_internal_value(result)
