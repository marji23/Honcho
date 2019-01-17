import django_filters
from django import forms
from django.db.models import Count
from watson import search as watson


class SearchFilter(django_filters.CharFilter):

    def __init__(self, ranking: bool = True) -> None:
        super().__init__()
        self.ranking = ranking

    def filter(self, qs, value):
        return watson.filter(qs, value, ranking=self.ranking)


class NumberInAnyFilter(django_filters.BaseInFilter, django_filters.NumberFilter):

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault('lookup_expr', 'in')
        kwargs.setdefault('distinct', True)
        super().__init__(*args, **kwargs)


class NumberInAllFilter(django_filters.BaseInFilter, django_filters.NumberFilter):

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault('lookup_expr', 'exact')
        kwargs.setdefault('distinct', True)
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        assert isinstance(value, list)

        count_name = '_%s_count' % self.field_name
        filtered_qs = self.get_method(qs.annotate(
            **{count_name: Count(self.field_name)}
        ))(**{count_name: len(value)})
        for val in value:
            filtered_qs = super().filter(filtered_qs, val)

        return filtered_qs


class OnTrueFilter(django_filters.BooleanFilter):
    field_class = forms.BooleanField

    def filter(self, qs, value):
        if value:
            return super().filter(qs, value)
        return qs
