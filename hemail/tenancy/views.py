from django.utils._os import safe_join
from django.views.static import serve as django_serve
from rest_framework import permissions, viewsets

from .models import TenantData
from .serializers import TenantDataSerializer


class TenantDataViewSet(viewsets.ModelViewSet):
    queryset = TenantData.objects.all()
    serializer_class = TenantDataSerializer
    permission_classes = (permissions.IsAdminUser,)


def serve(request, path, document_root=None, show_indexes=False):
    try:
        full_document_root = safe_join(document_root, request.tenant.domain_url)
    except AttributeError:
        full_document_root = document_root

    return django_serve(request, path, full_document_root, show_indexes)
