import json
from urllib.parse import urlencode

from rest_framework import status
from rest_framework.test import force_authenticate
from rest_framework_extensions.utils import compose_parent_pk_kwarg_name

from tenancy.test.cases import TenantsRequestFactory, TenantsTestCase
from ...templates.models import EmailTemplate, Folder
from ...templates.views import NestedFolderEmailTemplateViewSet


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

    def test_bulk_add_to_folder(self) -> None:
        self.set_tenant(0)

        first_template = EmailTemplate.objects.create(owner=self.user,
                                                      subject='First Subject {{ name }}',
                                                      content='First Content {{ name }}')
        second_template = EmailTemplate.objects.create(owner=self.user,
                                                       subject='Second Subject {{ name }}',
                                                       content='SecondContent {{ name }}')
        third_template = EmailTemplate.objects.create(owner=self.user,
                                                      subject='Third Subject {{ name }}',
                                                      content='Third Content {{ name }}')

        folder = Folder.objects.create(name='best templates')
        folder.templates.add(third_template)

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.patch(
            '',
            json.dumps(
                [dict(id=first_template.id), dict(id=second_template.id), ]
            ),
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)

        response = NestedFolderEmailTemplateViewSet.as_view({'patch': 'partial_bulk_update', })(
            request, **{compose_parent_pk_kwarg_name('folder'): folder.id}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        templates_data = response.data
        self.assertEqual(2, len(templates_data))
        self.assertSetEqual(
            {first_template.id, second_template.id, },
            {t['id'] for t in templates_data}
        )

        folder.refresh_from_db()
        templates = folder.templates.all()
        self.assertSetEqual({first_template.id, second_template.id, third_template.id, }, {c.id for c in templates})

    def test_bulk_remove_from_folder(self) -> None:
        self.set_tenant(0)

        first_template = EmailTemplate.objects.create(owner=self.user,
                                                      subject='First Subject {{ name }}',
                                                      content='First Content {{ name }}')
        second_template = EmailTemplate.objects.create(owner=self.user,
                                                       subject='Second Subject {{ name }}',
                                                       content='SecondContent {{ name }}')
        third_template = EmailTemplate.objects.create(owner=self.user,
                                                      subject='Third Subject {{ name }}',
                                                      content='Third Content {{ name }}')

        folder = Folder.objects.create(name='other templates')
        folder.templates.add(*[first_template, second_template, third_template])

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.delete(
            '',
            content_type='application/json',
            QUERY_STRING=urlencode({'id__in': ','.join([str(first_template.id), str(second_template.id), ])}),
        )
        force_authenticate(request, user=self.user)

        response = NestedFolderEmailTemplateViewSet.as_view({'delete': 'bulk_destroy'})(
            request, **{compose_parent_pk_kwarg_name('folder'): folder.id}
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, str(response.data))

        folder.refresh_from_db()
        templates = folder.templates.all()
        self.assertListEqual([third_template.id, ], [c.id for c in templates])
