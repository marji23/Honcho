import json
from urllib.parse import urlencode, urljoin

from django.test import modify_settings
from rest_framework import reverse, status
from rest_framework.test import ForceAuthClientHandler, force_authenticate
from rest_framework_extensions.utils import compose_parent_pk_kwarg_name
from tenant_schemas.test.client import TenantClient

from tenancy.test.cases import TenantsAPIRequestFactory, TenantsRequestFactory, TenantsTestCase
from ...contacts.models import Contact, ContactList
from ...contacts.views import ContactViewSet, NestedContactListContactViewSet


class ContactViewTestCase(TenantsTestCase):
    auto_create_schema = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = cls.create_superuser('first', 'test@one.com', 'p',
                                        first_name='Pretty', last_name='Smart',
                                        tenant=0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.set_tenant(0)
        cls.user.delete()
        super().tearDownClass()

    def test_contact_view(self) -> None:
        self.set_tenant(0)

        contact = Contact.objects.create(email='test@example.com', first_name='James', last_name='Bond')

        factory = TenantsAPIRequestFactory(force_authenticate=self.user)
        request = factory.get('')
        response = ContactViewSet.as_view({'get': 'list'})(request)
        contact_data = response.data

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(contact_data))
        self.assertEqual(1, len(contact_data))
        self.assertEqual(contact.id, contact_data[0]['id'])
        self.assertEqual(contact.first_name, contact_data[0]['first_name'])
        self.assertEqual(contact.last_name, contact_data[0]['last_name'])

    def test_bulk_add_to_list(self) -> None:
        self.set_tenant(0)

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')
        third_contact = Contact.objects.create(email='third@example.com', first_name='Third', last_name='Smith')

        contact_list = ContactList.objects.create(name='people')
        contact_list.contacts.add(third_contact)

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.patch(
            '',
            json.dumps(
                [dict(id=first_contact.id), dict(id=second_contact.id), ]
            ),
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)

        response = NestedContactListContactViewSet.as_view({'patch': 'partial_bulk_update', })(
            request, **{compose_parent_pk_kwarg_name('lists'): contact_list.id}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        contacts_data = response.data
        self.assertTrue(2, len(contacts_data))
        self.assertSetEqual(
            {first_contact.id, second_contact.id, },
            {c['id'] for c in contacts_data}
        )

        contact_list.refresh_from_db()
        contacts = contact_list.contacts.all()
        self.assertSetEqual({first_contact.id, second_contact.id, third_contact.id, }, {c.id for c in contacts})

    def test_bulk_remove_from_list(self) -> None:
        self.set_tenant(0)

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')
        third_contact = Contact.objects.create(email='third@example.com', first_name='Third', last_name='Smith')

        contact_list = ContactList.objects.create(name='people')
        contact_list.contacts.add(*[first_contact, second_contact, third_contact])

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.delete(
            '',
            content_type='application/json',
            QUERY_STRING=urlencode({'id__in': ','.join([str(first_contact.id), str(second_contact.id), ])}),
        )
        force_authenticate(request, user=self.user)

        response = NestedContactListContactViewSet.as_view({'delete': 'bulk_destroy'})(
            request, **{compose_parent_pk_kwarg_name('lists'): contact_list.id}
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, str(response.data))

        contact_list.refresh_from_db()
        contacts = contact_list.contacts.all()
        self.assertListEqual([third_contact.id, ], [c.id for c in contacts])

    def test_bulk_delete_contact_view(self) -> None:
        self.set_tenant(0)

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.delete(
            '',
            json.dumps([
                dict(id=first_contact.id),
                dict(id=second_contact.id),
            ]),
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)
        response = ContactViewSet.as_view({'delete': 'bulk_destroy'})(request)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, str(response.data))
        self.assertFalse(Contact.objects.filter(id__in=(first_contact.id, second_contact.id,)).exists())

    def test_bulk_delete_with_filtering(self) -> None:
        self.set_tenant(0)

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')
        third_contact = Contact.objects.create(email='third@example.com', first_name='Third', last_name='Smith')

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = self.user
        self.assertTrue(t_client.login(username=self.user.username, password='p'), 'Test user was not logged in')

        ids_for_delete = [first_contact.id, third_contact.id, ]
        url = reverse.reverse('api:contacts-list')
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            response = t_client.delete(urljoin(url, '?id__in=%s' % ','.join(str(pk) for pk in ids_for_delete)))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, str(response.content))
        self.assertFalse(Contact.objects.filter(id__in=ids_for_delete).exists())
        self.assertTrue(Contact.objects.filter(id=second_contact.id).exists())

    def test_phone_number_format(self) -> None:
        self.set_tenant(0)
        profile = self.user.profile  # type: Profile
        profile.country = 'US'
        profile.save()

        factory = TenantsRequestFactory(force_authenticate=self.user)

        requests_data = [
            dict(email='first.contact@phone.com', phone_number='1-310-848-7864'),
            dict(email='second.contact@phone.com', phone_number='310-848-7864'),
            dict(email='third.contact@phone.com', phone_number='13108487864'),
            dict(email='fouth.contact@phone.com', phone_number='3108487864'),
        ]

        responses_data = []
        for request_data in requests_data:
            request = factory.post(
                '',
                json.dumps(request_data),
                content_type='application/json',
            )
            force_authenticate(request, user=self.user)
            response = ContactViewSet.as_view({'post': 'create'})(request)
            contact_data = response.data
            responses_data.append(contact_data)

            self.assertEqual(response.status_code, status.HTTP_201_CREATED, str(contact_data))
            self.assertEqual(request_data['email'], contact_data['email'])

        self.assertTrue(len(requests_data), len(responses_data))
        self.assertSetEqual({'+13108487864'}, {cd['phone_number'] for cd in responses_data})

    def test_contact_by_lists_filtering(self) -> None:
        self.set_tenant(0)
        user = self.user

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')
        Contact.objects.create(email='third@example.com', first_name='Third', last_name='Smith')
        fourth_contact = Contact.objects.create(email='fourth@example.com', first_name='Fourth', last_name='Smith')

        first_list = ContactList.objects.create(name='first list')
        first_list.contacts.add(*[first_contact, fourth_contact])
        second_list = ContactList.objects.create(name='second list')
        second_list.contacts.add(*[second_contact, fourth_contact])

        t_client = TenantClient(self.get_current_tenant())
        t_client.handler = ForceAuthClientHandler(enforce_csrf_checks=False)
        t_client.handler._force_user = user
        self.assertTrue(t_client.login(username=user.username, password='p'), 'Test user was not logged in')

        url = reverse.reverse('api:contacts-list')
        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?lists__in=%s' % ','.join(map(str, [first_list.id, second_list.id]))
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        contacts_data = response.data
        self.assertEqual(3, len(contacts_data))
        self.assertSetEqual({first_contact.id, second_contact.id, fourth_contact.id},
                            {c['id'] for c in contacts_data})

        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?lists=' + ','.join(map(str, [first_list.id, second_list.id]))
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        contacts_data = response.data
        self.assertEqual(1, len(contacts_data))
        self.assertEqual(fourth_contact.id, contacts_data[0]['id'])

        with modify_settings(ALLOWED_HOSTS={'append': self.get_current_tenant().domain_url}):
            query = '?lists=%s' % second_list.id
            response = t_client.get(urljoin(url, query))

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.content))
        contacts_data = response.data
        self.assertEqual(1, len(contacts_data))
        self.assertEqual(second_contact.id, contacts_data[0]['id'])

    def test_partial_bulk_update(self) -> None:
        self.set_tenant(0)

        contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')

        test_data = dict(
            first_name="John",
            last_name="Doe",
            email="john@example.com",  # this is important because `email` field has unique constrain
            company_name="Acme",
            phone_number="",
            title="",
            state="",
            country="",
            city="Podunk",
            street_address="",
            zip_code=""
        )

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.patch(
            '',
            json.dumps([dict(id=contact.id, **test_data), ]),
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)

        response = ContactViewSet.as_view({'patch': 'partial_bulk_update', })(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        contacts_data = response.data
        self.assertEqual(1, len(contacts_data))
        contact_data = contacts_data[0]
        empty = object()
        self.assertDictEqual(test_data, {k: contact_data.get(k, empty) for k in test_data.keys()})

    def test_bulk_blacklisting(self) -> None:
        self.set_tenant(0)

        first_contact = Contact.objects.create(email='first@example.com', first_name='First', last_name='Smith')
        second_contact = Contact.objects.create(email='second@example.com', first_name='Second', last_name='Smith')
        third_contact = Contact.objects.create(email='third@example.com', first_name='Third', last_name='Smith')

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.patch(
            '',
            json.dumps([
                dict(id=first_contact.id, blacklisted=True),
                dict(id=third_contact.id, blacklisted=True),
            ]),
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)

        response = ContactViewSet.as_view({'patch': 'partial_bulk_update', })(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        contacts_data = response.data
        self.assertEqual(2, len(contacts_data))
        self.assertSetEqual(
            {first_contact.id, third_contact.id},
            {c['id'] for c in contacts_data}
        )
        self.assertTrue(all(c['blacklisted'] for c in contacts_data))
        first_contact.refresh_from_db()
        self.assertTrue(first_contact.blacklisted)
        second_contact.refresh_from_db()
        self.assertFalse(second_contact.blacklisted)
        third_contact.refresh_from_db()
        self.assertTrue(third_contact.blacklisted)
