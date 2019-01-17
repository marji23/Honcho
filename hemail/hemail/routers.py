import copy

from rest_framework.routers import Route
from rest_framework_extensions.compat_drf import add_trailing_slash_if_needed
from rest_framework_extensions.routers import ExtendedDefaultRouter


class ExtendedBulkRouter(ExtendedDefaultRouter):
    """
    Map http methods to actions defined on the bulk mixins.
    """
    routes = copy.deepcopy(ExtendedDefaultRouter.routes)
    routes[0].mapping.update({
        'put': 'bulk_update',
        'patch': 'partial_bulk_update',
        'delete': 'bulk_destroy',
    })
    routes.append(
        # Single route.
        Route(
            url=add_trailing_slash_if_needed(r'^{prefix}/$'),
            mapping={
                'get': 'retrieve_single',
                'put': 'update_single',
                'patch': 'partial_update_single',
                'delete': 'destroy_single'
            },
            name='{basename}-single',
            initkwargs={'suffix': 'Instance'}
        ), )
    _routs = routes[2:4] + routes[4:5] + routes[:2]
