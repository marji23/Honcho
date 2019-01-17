import os
from urllib.parse import urlparse

import requests
from celery import shared_task
from celery.exceptions import Reject
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model
from django.core.files import File

logger = get_task_logger(__name__)

UserModel = get_user_model()


@shared_task
def load_avatar(user_id: int, url: str):
    try:
        user = UserModel.objects.get(id=user_id)
    except (UserModel.MultipleObjectsReturned, UserModel.DoesNotExist) as ex:
        raise Reject(ex, requeue=False) from ex

    profile = user.profile
    if profile.avatar:
        raise Reject('Skipping because avatar already set', requeue=False)

    with requests.get(url, stream=True) as resp:
        # todo: it would be better to handle repeats with celery flow control exceptions
        resp.raise_for_status()

        file_name = os.path.basename(urlparse(url).path)
        profile.avatar = File(resp.raw, file_name)
        profile.save()
