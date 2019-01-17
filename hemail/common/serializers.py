from typing import Callable, Optional

import phonenumbers
from django.core import validators
from django.utils.translation import ugettext_lazy as _
from phonenumber_field.phonenumber import PhoneNumber
from rest_framework import serializers
from rest_framework.compat import unicode_to_repr
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404


class ContextualDefault(object):
    def __init__(self, generator: Callable) -> None:
        super().__init__()
        self.generator = generator
        self.field = None

    def __call__(self, *args, **kwargs):
        assert self.field
        return self.generator(self.field)

    def set_context(self, field) -> None:
        self.field = field

    def __repr__(self) -> str:
        return unicode_to_repr('%s()' % self.__class__.__name__)


def nested_view_contextual_default(queryset, key_for_pk=None) -> ContextualDefault:
    from rest_framework_extensions.mixins import NestedViewSetMixin

    def get_object(field):
        pk_key = field.field_name if key_for_pk is None else key_for_pk
        view = field.context['view']
        assert isinstance(view, NestedViewSetMixin)
        return get_object_or_404(queryset, pk=view.get_parents_query_dict().get(pk_key))

    return ContextualDefault(get_object)


class EnumByNameField(serializers.ChoiceField):
    def __init__(self, enum, choices=None, **kwargs) -> None:
        super().__init__([(
            e.name, e.name,
        ) for e in enum] if choices is None else choices, **kwargs)
        self.enum = enum

    def to_representation(self, obj):
        value = obj.name
        return super().to_representation(value)

    def to_internal_value(self, data):
        name = super().to_internal_value(data)
        return self.enum[name]


class EnumField(serializers.ChoiceField):
    def __init__(self, enum, choices=None, **kwargs) -> None:
        super().__init__([(
            e, e.name,
        ) for e in enum] if choices is None else choices, **kwargs)
        self.enum = enum

    def to_representation(self, obj):
        value = obj.value
        return super().to_representation(value)

    def to_internal_value(self, data):
        if isinstance(data, str):  # TODO: in case of allow blank we shouldn't look for it in Enum
            try:
                value = self.enum(data)
            except ValueError:
                raise self.fail('invalid_choice', input=data)

            return super().to_internal_value(value)
        if isinstance(data, self.enum):
            value = super().to_internal_value(data)
            return self.enum(value)

        # Fallback (will likely just raise):
        return super().to_internal_value(data)


class ContextualPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    queryset_filter = None

    def __init__(self, **kwargs) -> None:
        queryset_filter = kwargs.pop('queryset_filter', self.queryset_filter)
        if queryset_filter is not None and not callable(queryset_filter):
            raise ValueError('Filter should callable and accept')
        super().__init__(**kwargs)
        self.queryset_filter = queryset_filter

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.queryset_filter:
            queryset = self.queryset_filter(queryset, self.context)
        return queryset


class PhoneNumberField(serializers.CharField):
    default_error_messages = {
        'invalid': _('Enter a valid phone number.'),
    }

    def __init__(self, **kwargs) -> None:
        region = kwargs.pop('region', None)
        super().__init__(**kwargs)
        self.region = region

    def to_internal_value(self, data) -> PhoneNumber:
        phone_number = self._to_python(data)
        if phone_number and not phone_number.is_valid():
            raise ValidationError(self.error_messages['invalid'])
        return phone_number

    def _to_python(self, value) -> Optional[PhoneNumber]:
        if value in validators.EMPTY_VALUES:  # None or ''
            return value
        if value and isinstance(value, str):
            try:
                region = self.region(self) if callable(self.region) else self.region
                return PhoneNumber.from_string(phone_number=value, region=region)
            except phonenumbers.NumberParseException:
                # the string provided is not a valid PhoneNumber.
                return PhoneNumber(raw_input=value)
        if isinstance(value, phonenumbers.PhoneNumber) and not isinstance(value, PhoneNumber):
            phone_number = PhoneNumber()
            phone_number.merge_from(value)
            return phone_number
        if isinstance(value, PhoneNumber):
            return value
        return None
