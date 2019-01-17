from rest_framework import generics, mixins, viewsets


class RetrieveSingleModelMixin(object):
    retrieve_single = mixins.RetrieveModelMixin.retrieve


class UpdateSingleModelMixin(object):
    update_single = mixins.UpdateModelMixin.update
    perform_update = mixins.UpdateModelMixin.perform_update

    def partial_update_single(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update_single(request, *args, **kwargs)


class GenericSingleViewSet(viewsets.GenericViewSet):
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())

        obj = generics.get_object_or_404(queryset)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj


class RetrieveUpdateSingleModelViewSet(RetrieveSingleModelMixin,
                                       UpdateSingleModelMixin,
                                       GenericSingleViewSet):
    pass
