from allauth.socialaccount.providers.oauth.urls import default_urlpatterns

from .provider import YahooOAuth2Provider

urlpatterns = default_urlpatterns(YahooOAuth2Provider)
