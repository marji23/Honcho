from unittest.mock import MagicMock

from django.core.files.base import ContentFile

from campaigns.contacts.models import Contact, ContactList
from campaigns.importer.uploader import ContactsCsvImporter
from campaigns.models import Campaign, Participation
from files.models import FileUpload
from tenancy.test.cases import TenantsAPIRequestFactory, TenantsTestCase


class ContactUploaderTestCase(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@one.com', 'p', tenant=0)

        factory = TenantsAPIRequestFactory(force_authenticate=cls.user)
        request = factory.patch('', data=dict())

        view = MagicMock()
        view.request.return_value = request
        cls.serializer_context = dict(view=view, request=request, )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.user.delete()
        super().tearDownClass()

    def test_create_new(self) -> None:
        self.set_tenant(0)

        file_upload = FileUpload.objects.create(owner=self.user, file=ContentFile(
            b'first_name,email,trash\na,a@gmail.com,sdvxz\nb,b@mail.ru,4389\n', 'test.csv'))

        headers = dict(email=1, first_name=0)

        importer = ContactsCsvImporter(
            contact_serializer_context=self.serializer_context,
        )

        result = importer.parse_and_import(
            file_upload,
            headers,
        )

        self.assertEqual(2, result.created)
        self.assertEqual(0, result.updated)
        self.assertEqual(0, result.skipped)
        self.assertEqual(0, len(result.errors), str(result.errors))

    def test_update_existing(self) -> None:
        self.set_tenant(0)

        contact = Contact.objects.create(
            email='existed@local.com',
            first_name='Bill',
            title='Dr.'
        )

        file_upload = FileUpload.objects.create(owner=self.user, file=ContentFile(
            b'First Name,Second Name,Email,Trash\nBob,Robbin,existed@local.com,sdvxz\nAlice,Mol,al@sample.ru,4389\n',
            'test.csv'))

        headers = dict(email=2, first_name=0, last_name=1, )

        importer = ContactsCsvImporter(
            contact_serializer_context=self.serializer_context,
        )

        result = importer.parse_and_import(
            file_upload,
            headers,
            has_headers=True,
            allow_update=True,
        )

        self.assertEqual(1, result.created)
        self.assertEqual(1, result.updated)
        self.assertEqual(0, result.skipped)
        self.assertEqual(0, len(result.errors), str(result.errors))

        contact.refresh_from_db()
        self.assertEqual('Bob', contact.first_name)
        self.assertEqual('Robbin', contact.last_name)
        self.assertEqual('Dr.', contact.title)

    def test_create_failed_rows_file(self) -> None:
        self.set_tenant(0)

        file_upload = FileUpload.objects.create(owner=self.user, file=ContentFile(
            b'First Name,Email,Tel\na,a@gmail.com,+13108487866\nb,b@mail.ru,+12345678901\nbob,existed@local.com,sadf',
            'test.csv'))

        headers = dict(email=1, first_name=0, phone_number=2, )

        importer = ContactsCsvImporter(
            contact_serializer_context=self.serializer_context,
        )

        result = importer.parse_and_import(
            file_upload,
            headers,
            has_headers=True,
            create_failed_rows_file=True,
        )

        self.assertEqual(2, result.created)
        self.assertEqual(0, result.updated)
        self.assertEqual(0, result.skipped)
        self.assertEqual(1, len(result.errors), str(result.errors))
        self.assertDictEqual(
            {'phone_number': ['Enter a valid phone number.']},
            result.errors[2])

        with result.failed_rows_file.open() as f:
            failed_rows = f.readlines()

        self.assertListEqual([
            b'First Name,Email,Tel\r\n',
            b'bob,existed@local.com,sadf\r\n',
        ], failed_rows)

    def test_add_to_campaign_during_import_without_update(self) -> None:
        self.set_tenant(0)

        file_upload = FileUpload.objects.create(owner=self.user, file=ContentFile(
            b'first_name,email,trash\na,a@gmail.com,sdvxz\nb,b@mail.ru,4389\nbob,existed@local.com,sadf', 'test.csv'))

        headers = dict(email=1, first_name=0)

        campaign = Campaign.objects.create(name='testing', owner=self.user)
        contact = Contact.objects.create(email='existed@local.com')

        Participation.objects.create(campaign=campaign, contact=contact)

        importer = ContactsCsvImporter(
            contact_serializer_context=self.serializer_context,
        )

        result = importer.parse_and_import(
            file_upload,
            headers,
            has_headers=True,
            campaign=campaign,
        )

        self.assertEqual(2, result.created)
        self.assertEqual(1, result.updated)
        self.assertEqual(0, result.skipped)
        self.assertEqual(0, len(result.errors), str(result.errors))

        contacts = campaign.contacts.all()
        self.assertSetEqual({
            'a@gmail.com', 'b@mail.ru', contact.email,
        }, {c.email for c in contacts})

    def test_add_to_list_during_import(self) -> None:
        self.set_tenant(0)

        file_upload = FileUpload.objects.create(owner=self.user, file=ContentFile(
            b'first_name,email,trash\na,a@gmail.com,sdvxz\nb,b@mail.ru,4389\n', 'test.csv'))

        headers = dict(email=1, first_name=0)

        contact_list = ContactList.objects.create(name='very important list')

        importer = ContactsCsvImporter(
            contact_serializer_context=self.serializer_context,
        )

        result = importer.parse_and_import(
            file_upload,
            headers,
            has_headers=True,
            contact_list=contact_list,
        )

        self.assertEqual(2, result.created)
        self.assertEqual(0, result.updated)
        self.assertEqual(0, result.skipped)
        self.assertEqual(0, len(result.errors), str(result.errors))

        contacts = contact_list.contacts.all()
        self.assertSetEqual({
            'a@gmail.com', 'b@mail.ru',
        }, {c.email for c in contacts})
