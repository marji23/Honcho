from allauth.account.signals import email_confirmed, user_signed_up
from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.signals import social_account_updated
from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from plans.signals import activate_user_plan
from tenant_schemas.utils import tenant_context

from tenancy.tasks import prepare_tenant_task
from ..models import Profile
from ..tasks import load_avatar


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def _create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_delete, sender=Profile)
def _post_user_delete(sender, instance, **kwargs):
    tenant = instance.tenant
    if tenant and not tenant.users.exists():
        with tenant_context(tenant):
            tenant.delete()


@receiver(email_confirmed)
def _email_confirmed(sender, request, email_address, **kwargs):
    user = email_address.user
    activate_user_plan.send(sender=None, user=user)
    if not user.profile.tenant:
        prepare_tenant_task.delay(user.id)


@receiver(user_signed_up)
def _user_signed_up(sender, request, user, **kwargs):
    activate_user_plan.send(sender=None, user=user)
    if not user.profile.tenant and user.profile.account_verified:
        prepare_tenant_task.delay(user.id)


@receiver(social_account_updated, sender=SocialLogin)
def _load_avatar_from_social_if_needed(request, sociallogin: SocialLogin, **kwargs) -> None:
    user = sociallogin.user
    if not user.profile.avatar:
        url = sociallogin.account.get_avatar_url()
        if url:
            load_avatar.delay(user.id, url)
