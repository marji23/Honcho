from typing import List, Optional

from allauth.account.models import EmailAddress
from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider


class YahooOAuth2Account(ProviderAccount):
    def get_profile_url(self) -> str:
        return self.account.extra_data.get('image', {}).get('imageUrl')

    def get_avatar_url(self) -> Optional[str]:
        return self.account.extra_data.get('profileUrl')

    def to_str(self) -> str:
        dflt = super().to_str()
        return self.account.extra_data.get('nickname', dflt)


class YahooOAuth2Provider(OAuth2Provider):
    id = 'yahoo'
    name = 'Yahoo'
    account_class = YahooOAuth2Account

    def extract_uid(self, data: dict) -> str:
        return data['guid']

    def extract_common_fields(self, data: dict) -> dict:
        emails = [email for email in data.get('emails', []) if 'handle' in email]
        emails.sort(key=lambda e: e.get('primary', False), reverse=True)

        extracted = dict(
            name=data.get('nickname'),
            last_name=data.get('familyName'),
            first_name=data.get('givenName'),
        )
        if emails:
            extracted['email'] = emails[0]['handle']
        return extracted

    def extract_email_addresses(self, data: dict) -> List[EmailAddress]:
        emails = [email for email in data.get('emails', []) if 'handle' in email]
        emails.sort(key=lambda e: e.get('primary', False), reverse=True)

        return [
            EmailAddress(
                email=email['handle'],
                verified=True,
                primary=True
            ) for email in emails if email.get('primary', False)
        ]


provider_classes = [YahooOAuth2Provider]
