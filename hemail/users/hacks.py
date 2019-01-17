import logging

logger = logging.getLogger(__name__)


def monkeypatch_allauth():
    from allauth.account.adapter import get_adapter
    from allauth.socialaccount.models import SocialLogin

    _original_state_from_request = SocialLogin.state_from_request

    def state_from_request(cls, request):
        state = _original_state_from_request(request)
        if 'next' not in state:
            adapter = get_adapter(request)
            get_next_redirect_url = getattr(adapter, 'get_next_redirect_url', None)
            if callable(get_next_redirect_url):
                next_url = get_next_redirect_url(request)
                if next_url:
                    state['next'] = next_url
            else:
                logger.error("if adapter implements 'get_next_redirect_url' it should be callable")
        return state

    SocialLogin.state_from_request = classmethod(state_from_request)
