import imaplib
import logging
import smtplib
from email.message import Message
from typing import Callable, Iterator, Optional, Tuple

from django.core.mail.backends.smtp import EmailBackend as SmtpEmailBackend
from django_mailbox.transports.imap import ImapTransport
from oauthlib.oauth2 import OAuth2Error

from users.utils import get_oauth2_token, get_social_token
from ..configuration import AuthenticationType

logger = logging.getLogger(__name__)


def _get_oauth2_object(user, username: str, provider: str) -> Optional[Callable[[bytes], str]]:
    social_token = get_social_token(provider, user)
    if social_token is None:
        return None
    access_token = get_oauth2_token(social_token)
    return lambda ignored=None: 'user=%s\1auth=Bearer %s\1\1' % (
        username,
        access_token
    )


def _get_all_message_ids(self):
    # Fetch all the message uids
    response, message_ids = self.server.uid('search', None, 'ALL')
    message_id_string = message_ids[0].strip()
    # Usually `message_id_string` will be a list of space-separated
    # ids; we must make sure that it isn't an empty string before
    # splitting into individual UIDs.
    if message_id_string:
        return message_id_string.decode().split(' ')
    return []


def fetch_new_mail(server: imaplib.IMAP4, last_uid: Optional[int] = None) -> Iterator[Tuple[int, bytes]]:
    # todo: support UIDVALIDITY

    # issue the search command of the form "SEARCH UID 42:*"
    command = "UID {}:*".format(last_uid) if last_uid else 'ALL'
    result, data = server.uid('search', None, command)
    message_id_string = data[0].strip()
    message_ids = message_id_string.decode().split(' ') if message_id_string else []

    # yield mails
    for message_uid in message_ids:
        # SEARCH command *always* returns at least the most
        # recent message, even if it has already been synced
        uid = int(message_uid)
        if last_uid is None or uid > last_uid:
            result, data = server.uid('fetch', message_uid, '(RFC822)')
            # yield raw mail body
            yield uid, data[0][1]


class OAuth2ImapTransport(ImapTransport):
    def __init__(self, user, hostname: str, port: int = None,
                 ssl: bool = False, tls: bool = False,
                 archive: str = '', folder: str = None,
                 authentication: AuthenticationType = AuthenticationType.OAUTH2,
                 provider: Optional[str] = None,
                 readonly: bool = True):
        self.server = None
        self.user = user
        self.authentication = authentication
        self.provider = provider
        self.readonly = readonly
        super().__init__(hostname, port, ssl, tls, archive, folder)

        if authentication == AuthenticationType.OAUTH2:
            def login(server, username, password):
                try:
                    auth_object = _get_oauth2_object(user, username, provider)
                except ValueError as e:
                    raise server.error("[AUTHENTICATIONFAILED] failed get stored token") from e
                except OAuth2Error as e:
                    raise server.error("[AUTHENTICATIONFAILED] %s" % str(e)) from e

                if auth_object is None:
                    raise server.error("[AUTHENTICATIONFAILED] no token stored")
                typ, msg = server.authenticate('XOAUTH2', auth_object)
                return typ, msg

            self.transport = type(
                'OAuth2Imap4SSL' if ssl else 'OAuth2Imap4',
                (imaplib.IMAP4_SSL if ssl else imaplib.IMAP4,),
                dict(login=login)
            )

    def get_new_message(self, last_uid: Optional[int] = None,
                        condition: Optional[Callable[[Message], bool]] = None) -> Iterator[Tuple[int, Message]]:

        from django_mailbox.transports.base import MessageParseError

        # todo: this is not fully equivalent of get_message, some setting are ignored
        # (max_message_size, archive box creation, etc.)

        for uid, msg_content in fetch_new_mail(self.server, last_uid):
            if not msg_content:
                continue

            try:
                message = self.get_email_from_bytes(msg_content)

                if condition and not condition(message):
                    continue

                if self.archive:
                    self.server.uid('copy', uid, self.archive)

                yield uid, message
            except TypeError:
                # This happens if another thread/process deletes the
                # message between our generating the ID list and our
                # processing it here.
                continue
            except MessageParseError as e:
                logger.warning("Failed to parse message: %s", e, )
                continue

    def get_message(self, condition=None):
        """
        Default implementation delete message from server.
        """
        raise ValueError("This method is forbidden, use 'get_new_message' instead")


class OAuth2SmtpEmailBackend(SmtpEmailBackend):
    def __init__(self, user, host=None, port=None,
                 username=None, password=None,
                 use_tls=None, fail_silently=False, use_ssl=None, timeout=None,
                 ssl_keyfile=None, ssl_certfile=None,
                 authentication: AuthenticationType = AuthenticationType.OAUTH2,
                 provider: Optional[str] = None,
                 **kwargs):
        # The parent implementation of open call 'login' only if both 'user' and 'password' are set.
        # But in case of oauth2 there will be no password, so we doing this trick by setting password
        # to provider (it can be any other value)
        if authentication == AuthenticationType.OAUTH2 and not password:
            password = provider

        self.user = user
        super().__init__(host, port,
                         username, password,
                         use_tls,
                         fail_silently, use_ssl, timeout,
                         ssl_keyfile, ssl_certfile, **kwargs)
        self.authentication = authentication
        self.provider = provider

    @property
    def connection_class(self):
        if self.authentication != AuthenticationType.OAUTH2:
            return super().connection_class

        def login(connection, user, password, *, initial_response_ok=True):
            # self.set_debuglevel(True)
            connection.ehlo_or_helo_if_needed()
            if not connection.has_extn("auth"):
                raise smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")

            connection.user, connection.password = user, password

            # Authentication methods the server claims to support
            advertised_authlist = connection.esmtp_features["auth"].split()

            if connection.auth_method not in advertised_authlist:
                raise smtplib.SMTPException("No suitable authentication method found.")

            try:
                auth_object = _get_oauth2_object(self.user, user, self.provider)
            except ValueError as e:
                raise smtplib.SMTPAuthenticationError(code=-1, msg='failed get stored token') from e
            except OAuth2Error as e:
                raise smtplib.SMTPAuthenticationError(code=-1, msg=str(e)) from e
            try:
                if auth_object is None:
                    raise smtplib.SMTPAuthenticationError(code=-1, msg='no token stored')
                code, resp = connection.auth(connection.auth_method, auth_object,
                                             initial_response_ok=initial_response_ok)
                return code, resp
            except smtplib.SMTPAuthenticationError as e:
                raise e

        return type(
            'OAuth2SmtpSSL' if self.use_ssl else 'OAuth2Smtp',
            (smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP,),
            dict(auth_method='XOAUTH2', login=login)
        )
