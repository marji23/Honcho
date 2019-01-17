from urllib import parse
from urllib.parse import urljoin

from django.conf import settings
from libthumbor import CryptoURL
from rest_framework import serializers
from rest_framework.fields import CurrentUserDefault

from common.serializers import EnumField
from .models import FileUpload, FileUploader

_crypto = CryptoURL(key=settings.THUMBOR_SECURITY_KEY)
_THUMBNAILING_URL = settings.THUMBOR_THUMBNAILING_URL.rstrip('/')


class FileUploadSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=CurrentUserDefault())
    uploader = EnumField(FileUploader, read_only=True, default=FileUploader.USER)

    thumbnail = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = FileUpload
        fields = (
            'id',
            'created',
            'updated',
            'file',
            'name',
            'mimetype',
            'owner',
            'uploader',
            'ttl',
            'thumbnail',
            'url',
        )
        read_only_fields = ('id', 'created', 'updated', 'name', 'owner', 'uploader', 'ttl',)
        extra_kwargs = {
            'file': {'write_only': True}
        }

    def get_thumbnail(self, obj: FileUpload):
        options = dict(width=200, height=200)

        options.update(smart=True,
                       image_url=parse.quote(self.context['request'].build_absolute_uri(obj.url)))

        return urljoin(_THUMBNAILING_URL, _crypto.generate(**options))

    def get_url(self, obj: FileUpload):
        return self.context['request'].build_absolute_uri(obj.url)
