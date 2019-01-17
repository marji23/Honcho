import email
import enum
import logging
import mimetypes
import os
import re
import socket
import uuid
from email.message import Message as RawMessage
from typing import Callable, List, Mapping, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urlparse

import six
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import models, transaction
from django.utils.translation import ugettext_lazy as _
from django_mailbox import utils
from django_mailbox.models import ContentFile, Mailbox, Message, MessageAttachment
from enumfields import EnumField
from post_office import models as post_office_models

from .configuration import AuthenticationType, EncryptionType, IncomingConfiguration, OutgoingConfiguration
from .managers import EmailAccountManager

logger = logging.getLogger(__name__)

mailbox_settings = utils.get_settings()


class ProviderNotSpecified(Exception):
    pass


@enum.unique
class Priority(enum.Enum):
    LOW = post_office_models.PRIORITY.low
    MEDIUM = post_office_models.PRIORITY.medium
    HIGH = post_office_models.PRIORITY.high
    NOW = post_office_models.PRIORITY.now


class ConnectionException(OSError):
    """Base class for all exceptions raised by this module."""


class ResponseException(ConnectionException):
    pass


class AuthenticationException(ResponseException):
    pass


class ProviderEmailMessage(EmailMultiAlternatives):

    def __init__(self, provider: 'EmailAccount',
                 subject: str = '', body: str = '', html_body: str = '',
                 from_email: Optional[str] = None,
                 to: Optional[List[str]] = None,
                 cc: Optional[List[str]] = None,
                 bcc: Optional[List[str]] = None,
                 attachments=None, headers=None,
                 reply_to: Optional[List[str]] = None) -> None:
        alternatives = [(html_body, "text/html"), ] if html_body else None
        super().__init__(subject=subject,
                         body=body, from_email=from_email,
                         to=to, bcc=bcc,
                         attachments=attachments, headers=headers,
                         alternatives=alternatives,
                         cc=cc, reply_to=reply_to)
        self.provider = provider
        self.incoming_message = None

    def get_connection(self, fail_silently: bool = False):
        assert not fail_silently, 'Current implementation do not allow fail_silently to be true'
        return self.provider.outgoing.get_connection()

    def send(self, fail_silently=False) -> int:
        """Send the email message."""
        if not self.recipients():
            # Don't bother creating the network connection if there's nobody to
            # send to.
            return 0

        assert self.incoming_message is None

        count = self.get_connection().send_messages([self])
        if count:
            self.incoming_message = self.provider.incoming.record_outgoing_message(
                email.message_from_string(
                    self.message().as_string()
                )
            )
        return count


@enum.unique
class ConnectionStatus(enum.Enum):
    UNKNOWN = 'UNKNOWN'
    SUCCESS = 'SUCCESS'
    ALERT = 'ALERT'
    AUTHENTICATION_FAILED = 'AUTHENTICATIONFAILED'
    FAILED = 'FAILED'


class SmtpConnectionSettings(models.Model):
    uri = models.TextField(
        _(u'URI'),
        help_text=(_(
            "Example: smtp+ssl://myusername:mypassword@someserver <br />"
            "<br />"
            "Be sure to urlencode your username and password should they "
            "contain illegal characters (like @, :, etc)."
        )),
        blank=True,
        null=True,
        default=None,
    )

    status_description = models.TextField(blank=True, editable=False)
    status = EnumField(ConnectionStatus, max_length=32, default=ConnectionStatus.UNKNOWN, editable=False)

    @staticmethod
    def get_uri_from(conf: OutgoingConfiguration,
                     password: Optional[str] = None,
                     provider: Optional[str] = None) -> str:
        password = (':' + quote_plus(password)) if password is not None else ''
        params = {'authtype': conf.authentication.value}
        if provider is not None:
            params['provider'] = provider
        uri = "smtp{encryption_type}://{username}{password}@{host}:{port}{params}".format(
            encryption_type={
                EncryptionType.SSL: '+ssl',
                EncryptionType.STARTTLS: '+tls',
            }.get(conf.encryption, ''),
            username=quote_plus(conf.username_or_template),
            password=password,  # todo: check auth type in config
            host=conf.host,
            port=conf.port,
            params='?' + urlencode(params, quote_via=quote_plus),
        )

        return uri

    def to_configuration(self) -> OutgoingConfiguration:
        return OutgoingConfiguration(
            self.location,
            self.port,
            self.encryption_type,
            self.username,
            self.authentication,
            self.provider
        )

    def drop_status(self) -> None:
        self.status = ConnectionStatus.UNKNOWN
        self.status_description = ''

    @property
    def _protocol_info(self):
        return urlparse(self.uri)

    @property
    def _query_string(self):
        return parse_qs(self._protocol_info.query)

    @property
    def _domain(self):
        return self._protocol_info.hostname

    @property
    def port(self):
        """Returns the port to use for fetching messages."""
        return self._protocol_info.port

    @property
    def username(self):
        """Returns the username to use for fetching messages."""
        return unquote(self._protocol_info.username)

    @property
    def password(self):
        """Returns the password to use for fetching messages."""
        password = self._protocol_info.password
        return unquote(password) if password is not None else None

    @property
    def location(self):
        """Returns the location (domain and path) of messages."""
        return self._domain if self._domain else '' + self._protocol_info.path

    @property
    def type(self):
        """Returns the 'transport' name for this mailbox."""
        scheme = self._protocol_info.scheme.lower()
        if '+' in scheme:
            return scheme.split('+')[0]
        return scheme

    @property
    def use_ssl(self):
        """Returns whether or not this mailbox's connection uses SSL."""
        return '+ssl' in self._protocol_info.scheme.lower()

    @property
    def use_tls(self):
        """Returns whether or not this mailbox's connection uses STARTTLS."""
        return '+tls' in self._protocol_info.scheme.lower()

    @property
    def encryption_type(self):
        if self.use_ssl:
            return EncryptionType.SSL
        if self.use_tls:
            return EncryptionType.STARTTLS

        return EncryptionType.NONE

    @property
    def authentication(self):
        auth_type = self._query_string.get('authtype', None) or [AuthenticationType.NONE.value]
        return AuthenticationType(auth_type[0])

    @property
    def provider(self) -> Optional[str]:
        provider_ids = self._query_string.get('provider', None)
        if not provider_ids:
            return None
        return provider_ids[0]

    def clean(self):
        super().clean()

        errors = []

        if self.type != 'smtp':
            errors += ["Only smtp protocol is allowed"]

        if self.use_ssl and self.use_tls:
            errors += ["use_tls/use_ssl are mutually exclusive, so only set one of those settings to True."]

        if errors:
            raise ValidationError(errors)

    def get_connection(self) -> 'django.core.mail.backends.smtp.EmailBackend':
        # todo: support connection cache as in post_office.connections.ConnectionHandler

        from .transports.oauth2 import OAuth2SmtpEmailBackend
        conn = OAuth2SmtpEmailBackend(
            # todo: add some type of check or assert to verify this invert
            self.emailaccount.user,
            host=self.location, port=self.port,
            username=self.username, password=self.password,
            use_tls=self.use_tls, fail_silently=False, use_ssl=self.use_ssl,
            authentication=self.authentication,
            provider=self.provider,
        )

        import smtplib
        import socket

        try:
            conn.open()
            self.status = ConnectionStatus.SUCCESS
            self.status_description = 'Success'
            self.save()
        except smtplib.SMTPAuthenticationError as e:
            self.status = ConnectionStatus.AUTHENTICATION_FAILED
            self.status_description = str(e.smtp_error)
            self.save()
            raise AuthenticationException(str(e.smtp_error)) from e
        except smtplib.SMTPResponseException as e:
            self.status = ConnectionStatus.FAILED
            self.status_description = str(e.smtp_error)
            self.save()
            raise ResponseException from e
        except (smtplib.SMTPException, socket.error) as e:
            self.status = ConnectionStatus.FAILED
            self.status_description = str(e)
            self.save()
            raise ConnectionException from e
        return conn


class MessageStripReason(enum.Enum):
    NOT_ALLOWED = 'NOT_ALLOWED'
    TRUNCATED = 'TRUNCATED'


class CoolMailbox(Mailbox):
    status_description = models.TextField(blank=True, editable=False)
    status = EnumField(ConnectionStatus, max_length=32, default=ConnectionStatus.UNKNOWN, editable=False)

    last_uid = models.IntegerField(null=True)

    # todo: add last success date

    @staticmethod
    def get_uri_from(conf: IncomingConfiguration,
                     password: Optional[str] = None,
                     provider: Optional[str] = None) -> str:
        password = (':' + quote_plus(password)) if password is not None else ''
        params = {'authtype': conf.authentication.value}
        if provider is not None:
            params['provider'] = provider
        uri = "imap{encryption_type}://{username}{password}@{host}:{port}{params}".format(
            encryption_type={
                EncryptionType.SSL: '+ssl',
                EncryptionType.STARTTLS: '+tls',
            }.get(conf.encryption, ''),
            username=quote_plus(conf.username_or_template),
            password=password,  # todo: check auth type in config
            host=conf.host,
            port=conf.port,
            params='?' + urlencode(params, quote_via=quote_plus),
        )

        return uri

    def to_configuration(self) -> IncomingConfiguration:
        return IncomingConfiguration(
            self.location,
            self.port,
            self.encryption_type,
            self.username,
            self.authentication,
            self.provider
        )

    def update_uri(self, uri: str) -> None:
        self.uri = uri

    def drop_status(self) -> None:
        self.status = ConnectionStatus.UNKNOWN
        self.status_description = ''

    @property
    def password(self) -> Optional[str]:
        password = self._protocol_info.password
        return unquote(password) if password is not None else None

    @property
    def encryption_type(self) -> EncryptionType:
        if self.use_ssl:
            return EncryptionType.SSL
        if self.use_tls:
            return EncryptionType.STARTTLS

        return EncryptionType.NONE

    @property
    def authentication(self) -> AuthenticationType:
        auth_type = self._query_string.get('authtype', None) or [AuthenticationType.NONE.value]
        return AuthenticationType(auth_type[0])

    @property
    def provider(self) -> Optional[str]:
        provider_ids = self._query_string.get('provider', None)
        if not provider_ids:
            return None
        return provider_ids[0]

    def get_connection(self) -> 'django_mailbox.transports.base.EmailTransport':
        assert self.type == 'imap'
        prog = re.compile(r'\[(?P<type>\w+)\]\s?(?P<msg>.*)')

        from .transports.oauth2 import OAuth2ImapTransport
        conn = OAuth2ImapTransport(
            self.emailaccount.user,
            self.location,
            port=self.port if self.port else None,
            ssl=self.use_ssl,
            tls=self.use_tls,
            archive=self.archive,
            folder=self.folder,
            authentication=self.authentication,
            provider=self.provider,
        )

        try:
            conn.connect(self.username, self.password)
            self.status = ConnectionStatus.SUCCESS
            self.status_description = 'Success'
            self.save()
        except socket.error as e:
            self.status = ConnectionStatus.FAILED
            self.status_description = str(os.strerror(e.errno)) if e.errno is not None else str(e)
            self.save()
            raise ConnectionException from e
        except conn.transport.error as e:
            result = prog.match(str(e))
            if result:
                t, msg = result.group('type', 'msg')
                try:
                    self.status = ConnectionStatus(t)
                    self.status_description = msg
                    self.save()
                    if self.status == ConnectionStatus.AUTHENTICATION_FAILED:
                        raise AuthenticationException(msg) from e
                    raise ConnectionException from e
                except ValueError:
                    pass
            self.status = ConnectionStatus.FAILED
            self.status_description = str(e)
            self.save()

            raise ConnectionException from e

        return conn

    def _get_dehydrated_as_stripped(self, msg: RawMessage, record: Message,
                                    reason: MessageStripReason = MessageStripReason.NOT_ALLOWED) -> RawMessage:
        new = RawMessage()
        for header, value in msg.items():
            new[header] = value
        # Delete header, otherwise when attempting to  deserialize the
        # payload, it will be expecting a body for this.
        del new['Content-Transfer-Encoding']

        if reason == MessageStripReason.NOT_ALLOWED:
            reason_msg = 'Content type %s not allowed' % msg.get_content_type()
        elif reason == MessageStripReason.TRUNCATED:
            reason_msg = 'Message truncated by server'
        else:
            reason_msg = 'Unknown'

        new[mailbox_settings['altered_message_header']] = 'Stripped; %s' % reason_msg
        new.set_payload('')
        return new

    def _get_dehydrated_attachment(self, msg: RawMessage, record: Message) -> RawMessage:
        raw_payload = msg.get_payload()
        if raw_payload and raw_payload.splitlines()[-1] == '----- Message truncated -----':
            return self._get_dehydrated_as_stripped(msg, record, reason=MessageStripReason.TRUNCATED)

        filename = None
        raw_filename = msg.get_filename()
        if raw_filename:
            from campaigns.utils import convert_header_to_unicode

            filename = convert_header_to_unicode(raw_filename)
        if not filename:
            extension = mimetypes.guess_extension(msg.get_content_type())
        else:
            _, extension = os.path.splitext(filename)
        if not extension:
            extension = '.bin'

        attachment = MessageAttachment()

        attachment.document.save(
            uuid.uuid4().hex + extension,
            ContentFile(
                six.BytesIO(
                    msg.get_payload(decode=True)
                ).getvalue()
            )
        )
        attachment.message = record
        for key, value in msg.items():
            attachment[key] = value
        attachment.save()

        placeholder = RawMessage()
        placeholder[
            mailbox_settings['attachment_interpolation_header']
        ] = str(attachment.pk)

        return placeholder

    def _get_dehydrated_message(self, msg: RawMessage, record: Message) -> Message:
        """
        We want to hand truncated messages so we split this method into several and change part with attachments.
        """
        new = RawMessage()
        if msg.is_multipart():
            for header, value in msg.items():
                new[header] = value
            for part in msg.get_payload():
                new.attach(
                    self._get_dehydrated_message(part, record)
                )
            return new

        if (
            mailbox_settings['strip_unallowed_mimetypes'] and
            msg.get_content_type() not in mailbox_settings['allowed_mimetypes']
        ):
            return self._get_dehydrated_as_stripped(msg, record)

        if (
            (
                msg.get_content_type() not in mailbox_settings['text_stored_mimetypes']
            ) or
            ('attachment' in msg.get('Content-Disposition', ''))
        ):
            return self._get_dehydrated_attachment(msg, record)

        content_charset = msg.get_content_charset()
        if not content_charset:
            content_charset = 'ascii'

        raw_payload = msg.get_payload()
        if raw_payload and raw_payload.splitlines()[-1] == '----- Message truncated -----':
            raw_lines = raw_payload.splitlines()[:-1]
            truncated_payload = ''.join(raw_lines)
            truncated_payload = truncated_payload[:-(len(truncated_payload) % 4)]
            msg.set_payload(truncated_payload)

        try:
            # Make sure that the payload can be properly decoded in the
            # defined charset, if it can't, let's mash some things
            # inside the payload :-\

            msg.get_payload(decode=True).decode(content_charset)
        except LookupError:
            import codecs
            try:
                payload = codecs.decode(msg.get_payload(decode=True), content_charset, 'replace')
            except LookupError:
                import webencodings
                try:
                    payload = webencodings.decode(msg.get_payload(decode=True), content_charset, 'replace')[0]
                except LookupError:
                    logger.warning(
                        "Unknown encoding %s; interpreting as ASCII!",
                        content_charset
                    )
                    payload = msg.get_payload(decode=True).decode('ascii', 'ignore')
            msg.set_payload(payload)
        except ValueError:
            logger.warning(
                "Decoding error encountered; interpreting %s as ASCII!",
                content_charset
            )
            msg.set_payload(
                msg.get_payload(decode=True).decode(
                    'ascii',
                    'ignore'
                )
            )
        return msg

    def _process_message(self, message: RawMessage) -> Message:
        """
        We are overriding this method only to change receiving of message
        text form by calling str(message.as_bytes(), charset) instead of
        message.as_string() as original method does.
        """
        from campaigns.utils import convert_header_to_unicode

        msg = Message()

        if mailbox_settings['store_original_message']:
            msg.eml.save(
                '%s.eml' % uuid.uuid4(),
                ContentFile(message.as_string()),
                save=False
            )
        msg.mailbox = self
        if 'subject' in message:
            msg.subject = (
                convert_header_to_unicode(message['subject'])[0:255]
            )
        if 'message-id' in message:
            msg.message_id = message['message-id'][0:255].strip()
        if 'from' in message:
            msg.from_header = convert_header_to_unicode(message['from'])
        if 'to' in message:
            msg.to_header = convert_header_to_unicode(message['to'])
        elif 'Delivered-To' in message:
            msg.to_header = convert_header_to_unicode(
                message['Delivered-To']
            )
        msg.save()
        dehydrated_message = self._get_dehydrated_message(message, msg)

        try:
            message_context = dehydrated_message.as_string()
        except KeyError as e:
            for charset in filter(None, dehydrated_message.get_charsets()):
                try:
                    message_context = str(dehydrated_message.as_bytes(), charset)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise e

        msg.set_body(message_context)
        if dehydrated_message['in-reply-to']:
            msg.in_reply_to = Message.objects.filter(
                message_id=dehydrated_message['in-reply-to'].strip()
            ).first()
        msg.save()
        return msg

    def get_new_mail(self, condition: Optional[Callable[[RawMessage], bool]] = None) -> List[Message]:
        """Connect to this transport and fetch new messages."""
        connection = self.get_connection()
        if not connection:
            return []

        new_mail = []
        with transaction.atomic():
            last_uid = self.last_uid
            for uid, message in connection.get_new_message(last_uid=last_uid, condition=condition):
                msg = self.process_incoming_message(message)
                new_mail.append(msg)
                last_uid = uid
            self.last_uid = last_uid
            self.save()
        return new_mail


class EmailAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_accounts')
    email = models.EmailField(verbose_name=_('e-mail address'))
    sender_name = models.TextField(blank=True)

    incoming = models.OneToOneField(CoolMailbox, on_delete=models.CASCADE)
    outgoing = models.OneToOneField(SmtpConnectionSettings, on_delete=models.CASCADE)

    signature = models.TextField(blank=True)
    default = models.BooleanField(default=False)

    objects = EmailAccountManager()

    class Meta:
        unique_together = [("user", "email",), ]

    @classmethod
    def get_default(cls, user) -> 'EmailAccount':
        provider = user.email_accounts.filter(default=True).first()
        if provider:
            return provider

        raise ProviderNotSpecified('At least default provider should be set')

    @classmethod
    def get_active(cls, user):
        return user.email_accounts.filter(incoming__active=True)

    def from_email(self, sender_name: Optional[str] = None) -> str:
        return "{0} <{1}>".format(sender_name or self.sender_name, self.email)

    def set_as_default(self) -> None:
        self.__class__.objects.filter(user=self.user, default=True).exclude(id=self.id).update(default=False)
        self.default = True
        self.save(update_fields=['default', ])

    def full_clean(self, exclude=None, validate_unique=True):
        return super().full_clean(exclude, validate_unique)

    def verify_connections(self) -> None:
        try:
            self.incoming.get_connection()
        except ConnectionException:
            pass
        try:
            self.outgoing.get_connection()
        except ConnectionException:
            pass

    def get_new_mail(self):
        return self.incoming.get_new_mail()

    def create_email(self,
                     subject: str,
                     body: str,
                     html_body: str,
                     to: Optional[List[str]] = None,
                     cc: Optional[List[str]] = None,
                     bcc: Optional[List[str]] = None,
                     from_email: Optional[str] = None,
                     headers: Optional[Mapping[str, str]] = None) -> ProviderEmailMessage:

        if not from_email:
            from_email = self.from_email()

        msg = ProviderEmailMessage(
            self,
            subject=subject, body=body, html_body=html_body,
            from_email=from_email,
            to=to, cc=cc, bcc=bcc, reply_to=[self.email],
            headers=headers
        )

        return msg
