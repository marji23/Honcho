import datetime
import sys
import traceback
from collections import OrderedDict, namedtuple
from functools import wraps
from typing import Any, NamedTuple, Optional, Tuple, TypeVar

from allauth.account.utils import user_email
from celery import chain, shared_task
from celery.exceptions import Reject
from celery.schedules import schedule
from celery.task import periodic_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model
from tenant_schemas.utils import tenant_context

from tenancy.utils import map_task_per_tenants, tenant_context_or_raise_reject
from .configuration import UsernameTemplates
from .models import ConnectionStatus, EmailAccount
from .serializers import EmailAccountSerializer, ProviderConfigurationSerializer
from .utils import get_email_domain

logger = get_task_logger(__name__)

T = TypeVar("T")
E = TypeVar("E")
TaskResult = NamedTuple('TaskResult', [('result', Optional[T]), ('error', Optional[E])])


def err(value: E) -> TaskResult:
    return TaskResult(None, value)


def ok(value: T) -> TaskResult:
    return TaskResult(value, None)


def wrap_result(func):
    def handle(arg: Any) -> Tuple[bool, Any]:
        if not isinstance(arg, (tuple, list,)):
            return False, arg
        if len(arg) != 2:
            return False, arg

            # todo: add meta information for validation
        if arg[0] is not None and arg[1] is not None:
            return False, arg
        if arg[0] is None and arg[1] is None:
            return False, arg

        if arg[0] is not None and arg[1] is None:
            return False, arg[0]
        if arg[0] is None and arg[1] is not None:
            return True, err(arg[1])

        return True, err("Unexpected argument format: %s" % str(arg))

    @wraps(func)
    def wrapper(*args, **kwargs):
        unwrapped_args = []
        for arg in args:
            is_terminated, unwrapped_arg = handle(arg)
            if is_terminated:
                return unwrapped_arg
            unwrapped_args.append(unwrapped_arg)

        unwrapped_kwargs = OrderedDict()
        for name, value in kwargs.items():
            is_terminated, unwrapped_value = handle(value)
            if is_terminated:
                return unwrapped_value

            unwrapped_kwargs[name] = unwrapped_value

        try:
            return func(*unwrapped_args, **unwrapped_kwargs)
        except Exception:
            logger.exception("Exception during task execution")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            formatted_exception = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            return err(formatted_exception)

    return wrapper


@shared_task
@wrap_result
def _create_email_account_task(configuration_data: Optional[dict], user_id: int) -> TaskResult:
    if configuration_data is None:
        return err("Failed to guess email provider configuration based on user email")

    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(pk=user_id)
    except UserModel.DoesNotExist as ex:
        return err(str(ex))

    tenant = user.profile.tenant
    if not tenant:
        return err("User %s has no tenant" % user.pk)

    with tenant_context(tenant):
        if user.email_accounts.filter(default=True).exists():
            return err("User %s already configured a default email provider" % user_id)

        email = user_email(user)  # type: str
        UsernameTemplates.replace_template_in(configuration_data, email)

        def copy_conf(part):
            return {k: v for k, v in configuration_data.get(part, {}).items() if k in [
                'host', 'port', 'encryption', 'username', 'authentication', 'provider',
            ]}

        data = dict(
            user=user_id,
            email=email,
            default=True,
            incoming=copy_conf('incoming'),
            outgoing=copy_conf('outgoing'),
            # default_password='google',  # todo: add provider dectection and set it into correct field
        )

        request = namedtuple('FakeRequest', 'user')(user)
        serializer = EmailAccountSerializer(data=data, context={'request': request})
        if not serializer.is_valid(raise_exception=False):
            raise Reject('Email provider can not be filled automatically: %s' % str(serializer.errors), requeue=False)

        instance = serializer.save()
        return ok(instance.id)


@shared_task
@wrap_result
def verify_email_account_task(email_account_id: int, user_id: int) -> TaskResult:
    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(pk=user_id)
    except UserModel.DoesNotExist as e:
        return err(str(e))

    tenant = user.profile.tenant
    if not tenant:
        return err("User %s has no tenant" % user.pk)

    try:
        with tenant_context(tenant):
            email_account = EmailAccount.objects.get(pk=email_account_id, user=user)
            email_account.verify_connections()
    except EmailAccount.DoesNotExist as e:
        return err(str(e))

    return ok(email_account_id)


@shared_task
@wrap_result
def verify_email_accounts_task(user_id: int) -> TaskResult:
    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(pk=user_id)
    except UserModel.DoesNotExist as e:
        return err(str(e))

    tenant = user.profile.tenant
    if not tenant:
        return err("User %s has no tenant" % user.pk)

    with tenant_context(tenant):
        accounts_ids = user.email_accounts.filter(incoming__active=True).values_list('id', flat=True)
        for email_account_id in accounts_ids:
            verify_email_account_task.delay(email_account_id, user_id)

    return ok(None)


@shared_task
@wrap_result
def get_configurations_from_isp_task(email: str) -> TaskResult:
    import requests
    from .isp import parser

    try:
        r = requests.get('https://autoconfig.thunderbird.net/v1.1/' + get_email_domain(email), timeout=5)
    except requests.exceptions.ConnectionError as e:
        raise err(str(e))

    if r.status_code == requests.codes.ok:
        if r.headers.get('content-type') == 'text/xml':
            configuration = parser.parse_configuration(r.content)
            if configuration is None:
                return ok(None)
            serializer = ProviderConfigurationSerializer(instance=configuration)
            return ok(serializer.data)

    return ok(None)


@shared_task
def get_configurations_trying_common_server_names_task(email: str) -> TaskResult:
    """
    Trying to get configuration by testing common names and ports.
    """
    return ok(None)


@shared_task
def get_configurations_from_existing_task(email: str) -> TaskResult:
    """
    This could be cool improvement. As we already have a db of active configuration we could try to find
    the email domain in it
    """
    return ok(None)


# todo: should be chained when other ways will be implemented
guess_configuration = get_configurations_from_isp_task


def create_default_provider(user) -> chain:
    email = user_email(user)  # type: str
    return guess_configuration.s(email) | _create_email_account_task.s(user.id) | verify_email_account_task.s(user.id)


@periodic_task(run_every=schedule(run_every=datetime.timedelta(minutes=30)))
def verify_email_account_task_from_tenants() -> TaskResult:
    UserModel = get_user_model()
    # TODO: we can also check last_login not to verify all account
    for user_id in UserModel.objects.filter(is_active=True).values_list('id', flat=True):
        verify_email_accounts_task.delay(user_id)

    return ok(None)


@shared_task
def get_new_mail(tenant_id: int) -> TaskResult:
    with tenant_context_or_raise_reject(tenant_id) as tenant:
        total = 0
        accounts = EmailAccount.objects.filter(
            incoming__status=ConnectionStatus.SUCCESS,
            incoming__active=True,
        )
        for account in accounts:
            total += len(account.get_new_mail())

        logger.info("[%d: %s]: %s messages received", tenant_id, tenant.schema_name, total)
        return ok(total)


@periodic_task(run_every=schedule(run_every=datetime.timedelta(minutes=10)))
def get_new_mail_from_tenants() -> TaskResult:
    map_task_per_tenants(get_new_mail)
    return ok(None)
