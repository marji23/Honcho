import logging
from multiprocessing import Pool
from multiprocessing.dummy import Pool as ThreadPool
from typing import Optional, Sequence, Tuple, Union

import six
from django.db import DatabaseError, connection as db_connection
from django.db.models import Q, QuerySet
from django.utils.timezone import now
from post_office.connections import connections
from post_office.models import Email, Log, STATUS
from post_office.settings import get_batch_size, get_log_level, get_sending_order, get_threads_per_process
from post_office.utils import split_emails
from tenant_schemas.utils import tenant_context

from .models import CampaignStatus, Participation, ParticipationStatus, Priority, ScheduledEmail, Step, Weekdays

logger = logging.getLogger(__name__)


def submit_emails(priority: Priority = Priority.MEDIUM) -> Sequence[ScheduledEmail]:
    current_datetime = now()
    scheduled_emails = []

    participation_set = Participation.objects.filter(
        Q(status=ParticipationStatus.ACTIVE) | (
            Q(status=ParticipationStatus.RESPOND) & Q(campaign__settings__stop_sending_on_reply=False)
        ),
        campaign__status=CampaignStatus.ACTIVE,
        contact__blacklisted__exact=False,
    ).prefetch_related('passed_steps')

    target_steps = dict()
    for participation in participation_set:
        next_step_and_datetime = participation.get_next_step_and_send_datetime()
        if not next_step_and_datetime:
            continue

        next_step, send_datetime = next_step_and_datetime
        # todo: this check should take in account step's schedule
        if send_datetime is None or current_datetime >= send_datetime:
            target_steps.setdefault(next_step, []).append(participation.contact.id)

    # todo: can raise ProviderNotSpecified which should skip other sending for same user
    for step, contacts_ids in target_steps.items():
        try:
            scheduled_emails += step.submit_emails(contacts_filter_kwargs=dict(
                id__in=contacts_ids
            ), priority=priority)
        except BaseException:
            logger.exception("Failed to submit emails for %s", str(step))

    return scheduled_emails


def get_queued() -> Union[QuerySet, Sequence[Email]]:
    """
    Returns a list of emails that should be sent:
     - Status is queued
     - Campaign is still Active
     - Contact is not blacklisted
     - We fit into time window
    """

    current_time = now()
    steps = Step.objects.filter(
        campaign__status=CampaignStatus.ACTIVE,
    )
    steps_ids = []
    for step in steps:
        timezone = step.timezone
        if not timezone:
            timezone = step.campaign.owner.profile.timezone
        local_dt = current_time.astimezone(timezone)
        weekday = list(Weekdays)[local_dt.isoweekday() % 7]
        time = local_dt.time()
        if step.start < time < step.end and weekday in step.weekdays:
            steps_ids.append(step.id)

    if not steps_ids:
        return Email.objects.none()

    return Email.objects.filter(
        status=STATUS.queued,
        scheduled__stage__step_id__in=steps_ids,
        scheduled__contact__blacklisted=False,
    ).order_by(
        *get_sending_order()
    ).prefetch_related(
        'attachments',
        'scheduled',
    )[:get_batch_size()]


def send_campaigns_messages(processes: int = 1, log_level=None) -> Tuple[int, int]:
    """
    Sends out all queued mails that has scheduled_time less than now or None
    """
    queued_emails = get_queued()
    return send_emails(queued_emails, processes, log_level)


def send_system_messages(processes: int = 1, log_level=None) -> Tuple[int, int]:
    queued_emails = Email.objects.filter(
        status=STATUS.queued,
        scheduled=None,
    ).select_related(
        'template'
    ).filter(
        Q(scheduled_time__lte=now()) | Q(scheduled_time=None)
    ).order_by(
        *get_sending_order()
    ).prefetch_related(
        'attachments'
    )[:get_batch_size()]

    return send_emails(queued_emails, processes, log_level)


def send_queued(processes: int = 1, log_level=None) -> Tuple[int, int]:
    """
    Sends out all queued mails
    """
    result = tuple(zip(*(
        send_campaigns_messages(processes, log_level),
        send_system_messages(processes, log_level),
    )))
    return sum(result[0]), sum(result[1])


def send_emails(emails: Union[QuerySet, Sequence[Email]], processes: int = 1,
                log_level: Optional[int] = None) -> Tuple[int, int]:
    total_sent, total_failed = 0, 0
    total_email = len(emails)

    logger.info('Started sending %s emails with %s processes.',
                total_email, processes)

    if log_level is None:
        log_level = get_log_level()

    if emails:
        # Don't use more processes than number of emails
        if total_email < processes:
            processes = total_email

        if processes == 1:
            total_sent, total_failed = _send_bulk(emails,
                                                  uses_multiprocessing=False,
                                                  log_level=log_level)
        else:
            email_lists = split_emails(emails, processes)

            pool = Pool(processes)
            results = pool.map(_send_bulk, email_lists)
            pool.terminate()

            total_sent = sum([result[0] for result in results])
            total_failed = sum([result[1] for result in results])

    logger.info('%s emails attempted, %s sent, %s failed',
                total_email,
                total_sent,
                total_failed)
    return total_sent, total_failed


def _send_bulk(emails: Union[QuerySet, Sequence[Email]], uses_multiprocessing: bool = True,
               log_level: Optional[int] = None) -> Tuple[int, int]:
    # Multiprocessing does not play well with database connection
    # Fix: Close connections on forking process
    # https://groups.google.com/forum/#!topic/django-users/eCAIY9DAfG0
    if uses_multiprocessing:
        db_connection.close()

    if log_level is None:
        log_level = get_log_level()

    sent_emails = []
    failed_emails = []  # This is a list of two tuples (email, exception)
    email_count = len(emails)

    tenant = db_connection.tenant
    logger.info('Process started, sending %s emails', email_count)

    def send(email: Email):
        with tenant_context(tenant):
            try:
                scheduled = getattr(email, 'scheduled', None)
                dispatch = scheduled.dispatch if scheduled else email.dispatch

                dispatch(log_level=log_level,
                         commit=False,
                         disconnect_after_delivery=False)

                sent_emails.append(email)
                logger.debug('Successfully sent email #%d', email.id)
            except Exception as ex:
                if isinstance(ex, DatabaseError):
                    logger.exception('Failed to send email #%d', email.id)
                else:
                    logger.debug('Failed to send email #%d', email.id)
                failed_emails.append((email, ex))

    # Prepare emails before we send these to threads for sending
    # So we don't need to access the DB from within threads
    for email in emails:
        # Sometimes this can fail, for example when trying to render
        # email from a faulty Django template
        try:
            scheduled = getattr(email, 'scheduled', None)
            prepare_email_message = email.scheduled.prepare_email_message if scheduled else email.prepare_email_message
            prepare_email_message()
        except Exception as e:
            failed_emails.append((email, e))

    number_of_threads = min(get_threads_per_process(), email_count)
    pool = ThreadPool(number_of_threads)

    pool.map(send, emails)
    pool.close()
    pool.join()

    # todo: this is not working as connections are created by providers
    connections.close()

    # Update statuses of sent and failed emails
    email_ids = [email.id for email in sent_emails]
    Email.objects.filter(id__in=email_ids).update(status=STATUS.sent)

    email_ids = [email.id for (email, e) in failed_emails]
    Email.objects.filter(id__in=email_ids).update(status=STATUS.failed)

    # If log level is 0, log nothing, 1 logs only sending failures
    # and 2 means log both successes and failures
    if log_level >= 1:

        logs = []
        for (email, exception) in failed_emails:
            logs.append(
                Log(email=email, status=STATUS.failed,
                    message=str(exception),
                    exception_type=type(exception).__name__)
            )

        if logs:
            Log.objects.bulk_create(logs)

    if log_level == 2:

        logs = []
        for email in sent_emails:
            logs.append(Log(email=email, status=STATUS.sent))

        if logs:
            Log.objects.bulk_create(logs)

    logger.info(
        'Process finished, %s attempted, %s sent, %s failed',
        email_count, len(sent_emails), len(failed_emails)
    )

    return len(sent_emails), len(failed_emails)


def convert_header_to_unicode(header: str) -> str:
    from django_mailbox import utils

    if six.PY2 and isinstance(header, six.text_type):
        return header

    try:
        return utils.convert_header_to_unicode(header)
    except LookupError:
        pass

    import codecs
    import webencodings
    import email

    default_charset = utils.get_settings()['default_charset']

    def factory(decoder):
        def _decode(value, encoding):
            if isinstance(value, six.text_type):
                return value

            if not encoding or encoding == 'unknown-8bit':
                encoding = default_charset

            return decoder(value, encoding)

        return _decode

    for _decode in [
        factory(lambda value, encoding: codecs.decode(value, encoding, 'replace')),
        factory(lambda value, encoding: webencodings.decode(value, encoding, 'replace')[0]),
    ]:
        try:
            return ''.join([(
                _decode(bytestr, encoding)
            ) for bytestr, encoding in email.header.decode_header(header)])
        except LookupError as e:
            last_error = e

    raise last_error
