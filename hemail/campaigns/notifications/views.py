from django.http import Http404
from django_filters import rest_framework
from pinax.notifications.hooks import hookset
from pinax.notifications.models import NoticeSetting, NoticeType
from pinax.notifications.utils import load_media_defaults
from rest_framework import filters, permissions, viewsets
from rest_framework.response import Response
from rest_framework.serializers import ALL_FIELDS

from .filters import NotificationsFilter
from .models import Notification
from .serializers import NoticeMediaSerializer, NoticeTypeSerializer, NotificationSerializer

NOTICE_MEDIA, NOTICE_MEDIA_DEFAULTS = load_media_defaults()


class NoticeSettingsViewSet(viewsets.ViewSet):
    """
    Restful version of pinax.notifications.views.NoticeSettingsView
    """

    queryset = NoticeSetting.objects.none()
    serializer_class = NoticeMediaSerializer
    permission_classes = (permissions.DjangoModelPermissions,)

    scoping = None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lookup_field = 'pk'
        self.lookup_url_kwarg = None

    def setting_for_user(self, notice_type: NoticeType, medium_id: int) -> NoticeSetting:
        return hookset.notice_setting_for_user(
            self.request.user,
            notice_type,
            medium_id,
            scoping=self.scoping
        )

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def get_serializer_class(self):
        assert self.serializer_class is not None, (
            "'%s' should either include a `serializer_class` attribute, "
            "or override the `get_serializer_class()` method."
            % self.__class__.__name__
        )

        return self.serializer_class

    def get_serializer_context(self) -> dict:
        return {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }

    def get_pk(self) -> int:
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert lookup_url_kwarg in self.kwargs
        pk = self.kwargs[lookup_url_kwarg]
        return int(pk)

    def get_medium_data(self, medium_id: int, medium_display: str, notice_types) -> dict:
        medium_data = dict(id=medium_id, label=medium_display, notice_types=[])
        for notice_type in notice_types:
            setting = self.setting_for_user(notice_type, medium_id)
            if setting.send:
                medium_data['notice_types'].append(notice_type)

        return medium_data

    def list(self, request, *args, **kwargs) -> Response:
        data = []

        notice_types = NoticeType.objects.all()
        for medium_id, medium_display in NOTICE_MEDIA:
            data.append(self.get_medium_data(medium_id, medium_display, notice_types))

        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs) -> Response:
        pk = self.get_pk()

        for medium_id, medium_display in NOTICE_MEDIA:
            if medium_id == pk:
                notice_types = NoticeType.objects.all()
                data = self.get_medium_data(medium_id, medium_display, notice_types)
                serializer = self.get_serializer(data)
                return Response(serializer.data)

        raise Http404

    def update(self, request, *args, **kwargs) -> Response:
        partial = kwargs.pop('partial', False)

        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        medium_id = self.get_pk()

        notice_types_ids = {nt.id for nt in serializer.validated_data.get('notice_types', [])}
        for notice_type in NoticeType.objects.all():
            settings = self.setting_for_user(notice_type, medium_id)
            settings.send = notice_type.id in notice_types_ids
            settings.save(update_fields=['send'])

        # TODO: should be simplified
        return self.retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs) -> Response:
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    # todo: add bulk operations


class NoticeTypesViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NoticeType.objects.all()
    serializer_class = NoticeTypeSerializer
    permission_classes = (permissions.DjangoModelPermissions,)


class NotificationsViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = (permissions.DjangoModelPermissions,)
    filter_backends = (rest_framework.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = NotificationsFilter
    ordering_fields = ALL_FIELDS
