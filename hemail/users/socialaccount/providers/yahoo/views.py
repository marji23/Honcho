import requests
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)

from .provider import YahooOAuth2Provider


class YahooOAuth2Adapter(OAuth2Adapter):
    provider_id = YahooOAuth2Provider.id
    access_token_url = 'https://api.login.yahoo.com/oauth2/get_token'
    authorize_url = 'https://api.login.yahoo.com/oauth2/request_auth'
    profile_url = 'https://social.yahooapis.com/v1/user/me/profile'

    def complete_login(self, request, app, token, **kwargs):
        resp = requests.get(self.profile_url,
                            params={'format': 'json'},
                            headers={'Authorization': 'Bearer ' + token.token})
        resp.raise_for_status()
        extra_data = resp.json()['profile']
        login = self.get_provider().sociallogin_from_response(request, extra_data)
        return login


oauth_login = OAuth2LoginView.adapter_view(YahooOAuth2Adapter)
oauth_callback = OAuth2CallbackView.adapter_view(YahooOAuth2Adapter)
