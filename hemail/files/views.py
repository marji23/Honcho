from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from . import serializers
from .models import FileUpload


class FileUploadViewSet(mixins.CreateModelMixin,
                        mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    queryset = FileUpload.objects.none()
    serializer_class = serializers.FileUploadSerializer
    permission_classes = (permissions.DjangoModelPermissions,)

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return self.request.user.uploaded_files.all()
        return self.queryset

    @detail_route()
    def url(self, request, pk):
        file_upload = self.get_object()
        response = Response(status=status.HTTP_303_SEE_OTHER)
        response['Location'] = file_upload.url
        return response
