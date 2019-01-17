from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.conf.urls import url

from campaigns.notifications import consumers as notifications_consumers
from common.authentication import AuthorizationProcessorBasedMiddlewareStack

application = ProtocolTypeRouter({

    "websocket": AllowedHostsOriginValidator(
        AuthorizationProcessorBasedMiddlewareStack(
            URLRouter([
                url(r"^nyt/$", notifications_consumers.NotificationsConsumer),
            ])
        )
    ),
})
