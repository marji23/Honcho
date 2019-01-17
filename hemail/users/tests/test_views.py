import base64
import json
from unittest.mock import MagicMock

from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.test import force_authenticate

from files.models import FileUpload
from tenancy.test.cases import TenantsAPIRequestFactory, TenantsRequestFactory, TenantsTestCase
from users.views import AvatarUpdateView


class UsersTestCase(TenantsTestCase):
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

    def test_avatar_upload(self) -> None:
        self.set_tenant(0)

        content = base64.decodebytes(b'R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=')
        file_upload = FileUpload.objects.create(owner=self.user, file=ContentFile(content, 'image.gif'))

        factory = TenantsRequestFactory(force_authenticate=self.user)
        request = factory.post(
            '',
            json.dumps(dict(file=file_upload.id)),
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)

        response = AvatarUpdateView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, str(response.data))
        avatar_data = response.data
        self.assertSetEqual({'url', 'thumbnail', }, set(avatar_data.keys()))

        avatar = self.user.profile.avatar
        avatar_content = avatar.read()
        self.assertEqual(content, avatar_content)

        with self.assertRaises(FileUpload.DoesNotExist):
            file_upload.refresh_from_db()
