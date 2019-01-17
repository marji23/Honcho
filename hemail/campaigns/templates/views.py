import rest_framework_bulk
from django.db import models
from django_filters import rest_framework
from rest_framework import filters, permissions
from rest_framework.generics import get_object_or_404
from rest_framework.serializers import ALL_FIELDS
from rest_framework_extensions.mixins import NestedViewSetMixin

from .filters import EmailTemplateFilter, FolderFilter
from .models import EmailTemplate, Folder
from .serializers import EmailTemplateSerializer, FolderSerializer, NestedFolderEmailTemplateSerializer


class FoldersViewSet(rest_framework_bulk.BulkModelViewSet):
    queryset = Folder.objects.annotate(templates_count=models.Count('templates'))
    serializer_class = FolderSerializer
    permission_classes = (permissions.DjangoObjectPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = FolderFilter
    ordering_fields = ALL_FIELDS


class EmailTemplateViewSet(rest_framework_bulk.BulkModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = EmailTemplateSerializer
    permission_classes = (permissions.DjangoObjectPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = EmailTemplateFilter
    ordering_fields = ALL_FIELDS


class NestedFolderEmailTemplateViewSet(NestedViewSetMixin, rest_framework_bulk.BulkModelViewSet):
    queryset = EmailTemplate.objects.all()
    serializer_class = NestedFolderEmailTemplateSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = EmailTemplateFilter
    ordering_fields = ALL_FIELDS

    def get_parents_query_dict(self, remove_parent=True) -> dict:
        query_dict = super().get_parents_query_dict()
        if remove_parent and self.request.method not in ('GET',):
            del query_dict['folder']
        return query_dict

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        context['target_folder'] = self.target_folder
        return context

    def perform_destroy(self, instance: EmailTemplate) -> None:
        """
        this view won't destroy object but it will only set it's folder to None
        """
        self.target_folder.templates.remove(instance)

    @property
    def target_folder(self) -> Folder:
        target_folder_id = self.get_parents_query_dict(remove_parent=False).get('folder', None)
        target_folder = get_object_or_404(Folder, pk=target_folder_id)
        return target_folder
