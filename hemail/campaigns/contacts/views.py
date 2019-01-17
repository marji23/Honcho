import rest_framework_bulk
from django.db import models
from django_filters import rest_framework
from rest_framework import filters, permissions
from rest_framework.decorators import list_route
from rest_framework.generics import get_object_or_404
from rest_framework.serializers import ALL_FIELDS
from rest_framework_csv import renderers
from rest_framework_extensions.mixins import NestedViewSetMixin

from .filters import ContactsFilter, NotesFilter
from .models import Contact, ContactList, Note
from .serializers import (
    ContactListSerializer, ContactSerializer,
    NestedContactListContactSerializer, NestedContactNoteSerializer
)


class ContactViewSet(rest_framework_bulk.BulkModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = ContactsFilter
    ordering_fields = ALL_FIELDS

    @list_route(
        renderer_classes=(renderers.CSVRenderer,)
    )
    def reports(self, request):
        response = self.list(request)
        response['Content-Disposition'] = 'attachment; filename=contacts.csv'
        return response


class ContactListViewSet(rest_framework_bulk.BulkModelViewSet):
    queryset = ContactList.objects.annotate(contacts_count=models.Count('contacts'))
    serializer_class = ContactListSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ('name', 'contacts_count')
    ordering = ('name',)


class NestedContactNotesViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NestedContactNoteSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = NotesFilter
    ordering_fields = ALL_FIELDS


class NestedContactListContactViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = NestedContactListContactSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = ContactsFilter
    ordering_fields = ALL_FIELDS

    def get_parents_query_dict(self, remove_parent=True) -> dict:
        query_dict = super().get_parents_query_dict()
        if remove_parent and self.request.method not in ('GET',):
            del query_dict['lists']
        return query_dict

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        context['target_list'] = self.target_list
        return context

    def perform_destroy(self, instance) -> None:
        """
        this view won't destroy object but it will only remove them from the list
        """
        contact_list = self.target_list
        contact_list.contacts.remove(instance)

    @property
    def target_list(self) -> ContactList:
        target_list_id = self.get_parents_query_dict(remove_parent=False).get('lists', None)
        target_list = get_object_or_404(ContactList, pk=target_list_id)
        return target_list
