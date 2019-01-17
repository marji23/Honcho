import email
import os
from unittest.mock import MagicMock

from common.utils import introspect
from tenancy.test.cases import TenantsTestCase
from ..configuration import AuthenticationType, EncryptionType, IncomingConfiguration
from ..models import ConnectionStatus, CoolMailbox
from ..serializers import EmailAccountSerializer, IncomingMailBoxSerializer, OutgoingSmtpConnectionSettingsSerializer


class TestConfigurationGuessing(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@one.com', 'p')

    @classmethod
    def tearDownClass(cls):
        cls.user.delete()
        super().tearDownClass()

    def test_configuration_to_uri_conversion(self):
        self.set_tenant(0)

        conf = IncomingConfiguration(
            'imap.gmail.com', 993,
            EncryptionType.SSL,
            'username@gmail.com',
            AuthenticationType.BASIC,
        )
        uri = CoolMailbox.get_uri_from(conf, 'secret')
        mailbox = CoolMailbox(
            name='testing',
            uri=uri)
        self.assertEqual(conf.host, mailbox.location)
        self.assertEqual(conf.port, mailbox.port)
        self.assertEqual(conf.username_or_template, mailbox.username)
        self.assertTrue(mailbox.use_ssl)
        self.assertFalse(mailbox.use_tls)

        mailbox.save()

        if False:
            def condition(msg):
                has_transfer_encoding = msg.get('content-transfer-encoding') is not None
                if not has_transfer_encoding:
                    pass
                return has_transfer_encoding

            new_mail = mailbox.get_new_mail(condition)
            self.assertTrue(len(new_mail))

    def test_skipping_truncated_messages(self):
        self.set_tenant(0)

        conf = IncomingConfiguration(
            'imap.gmail.com', 993,
            EncryptionType.SSL,
            'abrahas.23@gmail.com',
            AuthenticationType.BASIC,
        )
        uri = CoolMailbox.get_uri_from(conf, 'secret')
        mailbox = CoolMailbox(
            name='testing',
            uri=uri)

        mailbox.save()

        connection_mock = MagicMock()
        mailbox.get_connection = MagicMock(return_value=connection_mock)

        def get_new_messages(*args, **kwargs):
            path = os.path.join(os.path.dirname(__file__), 'data')
            for file_name in os.listdir(path):
                if file_name.endswith('.eml'):
                    with open(os.path.join(path, file_name), 'rb') as f:
                        content = f.read()
                    msg = email.message_from_bytes(content)
                    uid = int(os.path.splitext(file_name)[0])
                    yield uid, msg

        connection_mock.get_new_message = get_new_messages

        mail = mailbox.get_new_mail()
        self.assertEqual(5, len(mail))

    def test_email_account_serialization_and_deserialization(self):
        self.set_tenant(0)

        test_incoming_data = dict(
            host='imap.localhost',
            port=1234,
            encryption=EncryptionType.SSL.name,
            username='user',
            password='secret',
            authentication=AuthenticationType.BASIC.name,
        )
        incoming_serializer = IncomingMailBoxSerializer(data=test_incoming_data)
        self.assertTrue(incoming_serializer.is_valid(raise_exception=True))
        mailbox = incoming_serializer.save()
        self.assertIsNotNone(mailbox)
        self.assertEqual('imap+ssl://user:secret@imap.localhost:1234?authtype=plain', mailbox.uri)

        test_outgoing_data = dict(
            host='smtp.localhost',
            port=9876,
            encryption=EncryptionType.SSL.name,
            username='resu',
            password='terces',
            authentication=AuthenticationType.BASIC.name,
        )
        outgoing_serializer = OutgoingSmtpConnectionSettingsSerializer(data=test_outgoing_data)
        self.assertTrue(outgoing_serializer.is_valid(raise_exception=True))
        smtp_connection_settings = outgoing_serializer.save()
        self.assertIsNotNone(smtp_connection_settings)
        self.assertEqual('smtp+ssl://resu:terces@smtp.localhost:9876?authtype=plain', smtp_connection_settings.uri)

        test_data = dict(
            email='user@localhost.localdomain',
            incoming=test_incoming_data,
            outgoing=test_outgoing_data,
            signature='from honcho with love',
        )

        request_mock = MagicMock()
        request_mock.user = self.user

        serializer = EmailAccountSerializer(data=test_data, context=dict(request=request_mock))
        self.assertTrue(serializer.is_valid(raise_exception=True))
        email_account = serializer.save()
        self.assertIsNotNone(email_account)

        out_serializer = EmailAccountSerializer(instance=email_account)
        out_data = out_serializer.data

        self.assertDictEqual({
            'incoming.password': 'secret',
            'outgoing.password': 'terces',
        }, {k: v for k, v in introspect(test_data).items() if k not in introspect(out_data)})
        self.assertDictEqual({
            'default': True,
            'id': 1,
            'sender_name': 'first',
            'incoming.provider': None,
            'incoming.status': ConnectionStatus.UNKNOWN.name,
            'incoming.status_description': '',
            'outgoing.provider': None,
            'outgoing.status': ConnectionStatus.UNKNOWN.name,
            'outgoing.status_description': '',
        }, {k: v for k, v in introspect(out_data).items() if k not in introspect(test_data)})
