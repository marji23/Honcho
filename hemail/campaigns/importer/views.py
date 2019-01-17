import rest_framework_bulk
from rest_framework import mixins, permissions, response as rf_response, status, viewsets
from rest_framework.response import Response

from common.exceptions import UnprocessableEntity
from files.models import FileUpload
from .serializers import CsvContactSerializer, FileUploadSerializer, ImportResultSerializer, SniffQuerySerializer
from .uploader import ContactsCsvImporter, ParsingException
from ..contacts.models import Contact
from ..importer.serializers import SniffResultSerializer


class ContactsCsvSniffingViewSet(mixins.RetrieveModelMixin,
                                 viewsets.GenericViewSet):
    queryset = FileUpload.objects.all()
    serializer_class = SniffResultSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    contact_serializer_class = CsvContactSerializer

    def retrieve(self, request, *args, **kwargs):
        file_upload = self.get_object()

        query_serializer = SniffQuerySerializer(data=request.query_params.dict())
        query_serializer.is_valid(raise_exception=True)
        limit = query_serializer.validated_data['limit']

        importer = ContactsCsvImporter(
            contact_serializer_class=self.contact_serializer_class,
            contact_serializer_context=self.get_serializer_context(),
        )

        try:
            result = importer.sniff(
                file_upload,
                limit=limit
            )
        except ParsingException as e:
            raise UnprocessableEntity(detail=str(e)) from e

        serializer = self.get_serializer(instance=result)
        return Response(serializer.data)


class ContactsCsvViewSet(rest_framework_bulk.BulkCreateModelMixin,
                         viewsets.GenericViewSet):
    queryset = Contact.objects.none()
    serializer_class = FileUploadSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    contact_serializer_class = CsvContactSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['contact_serializer'] = self.contact_serializer_class(context=context)
        return context

    def create(self, request, *args, **kwargs):
        contact_serializer = self.contact_serializer_class(context=self.get_serializer_context())
        serializer = self.get_serializer(data=request.data, contact_serializer=contact_serializer)
        serializer.is_valid(raise_exception=True)

        file_upload = serializer.validated_data['file']
        headers = serializer.validated_data['headers']
        options = serializer.validated_data['options']

        importer = ContactsCsvImporter(
            contact_serializer_class=self.contact_serializer_class,
            contact_serializer_context=self.get_serializer_context(),
        )

        try:
            result = importer.parse_and_import(
                file_upload,
                headers,
                **options,
            )
        except ParsingException as e:
            raise UnprocessableEntity(detail=str(e)) from e

        if result.errors and not result.created and not result.updated:
            response_status = status.HTTP_400_BAD_REQUEST
        elif not result.errors and result.created and not result.updated:
            response_status = status.HTTP_201_CREATED
        elif not result.errors and not result.created and result.updated:
            response_status = status.HTTP_200_OK
        else:
            response_status = status.HTTP_207_MULTI_STATUS

        return rf_response.Response(data=ImportResultSerializer(instance=result).data,
                                    status=response_status)
