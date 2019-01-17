import copy
from enum import Enum
from typing import List, Type

import pytz
from django.contrib.postgres.validators import ArrayMaxLengthValidator
from django.core import checks
from django.core.exceptions import ValidationError
from django.db import models as fields
from django_postgres_extensions import models as models_extensions
from enumfields import EnumField
from enumfields.forms import EnumMultipleChoiceField
from timezone_utils.fields import TimeZoneField as OriginalTimeZoneField

from .utils import FixedOffset
from .validators import array_unique_elements_validator


class EnumSetField(models_extensions.ArrayField):
    def __init__(self, enum: Type[Enum], **kwargs):
        self.default_validators = self.default_validators[:]
        self.default_validators.append(array_unique_elements_validator)
        size = kwargs.pop('size', len(enum))
        super().__init__(
            EnumField(enum, max_length=max(len(e.value) for e in enum)),
            size=size,
            **kwargs)

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        if self.size > len(self.base_field.enum):
            errors.append(
                checks.Error(
                    'Size for set cannot be larger than size of enum.',
                    obj=self,
                    id='common.E001'
                )
            )
        return errors

    def formfield(self, **kwargs):
        class FField(EnumMultipleChoiceField):
            def __init__(self, base_field, max_length, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.validators.append(ArrayMaxLengthValidator(int(max_length)))
                self.validators.append(array_unique_elements_validator)

            def prepare_value(self, value):
                return value

        defaults = {
            'form_class': FField,
            'choices': self.base_field.choices,
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, list):
            value = [self.base_field.to_python(val) for val in value]
        # TODO: it should return set
        return value

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs['enum'] = self.base_field.enum
        del kwargs['size']
        del kwargs['base_field']
        return name, path, args, kwargs

    def get_default(self):
        """
        The default implementation on models.Field calls return lists as is.
        So any instance can modify the default value of the model field.
        """
        if self.has_default() and not callable(self.default):
            return copy.deepcopy(self.default)
        return super().get_default()


class TimeZoneField(OriginalTimeZoneField):
    def to_python(self, value):
        """Returns a datetime.tzinfo instance for the value."""
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

    def formfield(self, **kwargs):
        """Returns a custom form field for the TimeZoneField."""

        from . import forms
        defaults = {'form_class': forms.TimeZoneField}
        defaults.update(**kwargs)
        return super(TimeZoneField, self).formfield(**defaults)


def get_image_dimensions(file_or_path, close=False):
    from wand.image import Image

    filepos = None
    if hasattr(file_or_path, 'read'):
        arg_name = 'file'
        file = True
        if hasattr(file_or_path, 'tell'):
            filepos = file_or_path.tell()
            file_or_path.seek(0)
        else:
            filepos = 0
    else:
        arg_name = 'filename'
        file = False

    try:
        image = Image(**{arg_name: file_or_path})
        return image.size
    finally:
        if file and filepos is not None:
            if close:
                file_or_path.close()
            else:
                file_or_path.seek(filepos)


class ImageField(fields.ImageField):
    """
    Use WAND instead of Pillow
    """

    from django.db.models.fields import files

    class ImageFieldFile(files.ImageFieldFile):
        def __init__(self, instance, field, name):
            super(ImageField.ImageFieldFile, self).__init__(instance, field, name)

        def _get_image_dimensions(self):
            if not hasattr(self, '_dimensions_cache'):
                close = self.closed
                self.open()
                self._dimensions_cache = get_image_dimensions(self, close=close)
            return self._dimensions_cache

    attr_class = ImageFieldFile

    def __init__(self, verbose_name=None, name=None, width_field=None, height_field=None, **kwargs) -> None:
        super(ImageField, self).__init__(verbose_name, name, width_field, height_field, **kwargs)

    def _check_image_library_installed(self) -> List[checks.Error]:
        try:
            from wand.image import Image  # NOQA
        except ImportError:
            return [
                checks.Error(
                    'Cannot use ImageField because Wand is not installed.',
                    hint=('Get wand at https://pypi.python.org/pypi/Wand '
                          'or run command "pip install Wand".'),
                    obj=self,
                    id='fields.E210',
                )
            ]
        else:
            return []
