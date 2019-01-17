from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.signals import social_account_updated
from celery import group
from django.db.models.signals import pre_save
from django.dispatch import receiver
from tenant_schemas.utils import tenant_context

from campaigns.providers.configuration import AuthenticationType
from tenancy.models import TenantData
from tenancy.signals import tenant_prepared
from ..models import EmailAccount
from ..tasks import create_default_provider, verify_email_account_task


@receiver(pre_save, sender=EmailAccount)
def _reset_default_email_account(instance: EmailAccount, raw, using, update_fields, **kwargs) -> None:
    qs = instance.__class__.objects.filter(user=instance.user, default=True)
    if instance.id:
        qs = qs.exclude(id=instance.id)
    if instance.default:
        # If True then set all others as False
        qs.update(default=False)
    elif not qs.exists():
        # If no default object exists that isn't saved model, save as True
        instance.default = True


@receiver(tenant_prepared, sender=TenantData)
def _try_guess_user_email_provider_by_primary_email(tenant: TenantData, **kwargs) -> None:
    group(create_default_provider(user) for user in tenant.users.all()).delay()


@receiver(social_account_updated, sender=SocialLogin)
def _drop_connection_statuses(request, sociallogin: SocialLogin, **kwargs) -> None:
    user = sociallogin.user
    tenant = user.profile.tenant if hasattr(user, 'profile') else None
    if not tenant:
        return

    with tenant_context(tenant):
        provider = sociallogin.account.provider
        for email_account in user.email_accounts.all():
            changed = False

            incoming = email_account.incoming
            if incoming.authentication == AuthenticationType.OAUTH2 and incoming.provider == provider:
                incoming.drop_status()
                incoming.save()
                changed = True

            outgoing = email_account.outgoing
            if outgoing.authentication == AuthenticationType.OAUTH2 and outgoing.provider == provider:
                outgoing.drop_status()
                outgoing.save()
                changed = True

            if changed:
                verify_email_account_task.delay(email_account.id, user.id)
