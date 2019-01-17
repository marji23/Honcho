# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-02-20 12:31
from __future__ import unicode_literals

from django.db import migrations

import common.fields
import tenancy.storage
import users.models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0006_auto_20180117_2215'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='avatar',
            field=common.fields.ImageField(blank=True, null=True,
                                           storage=tenancy.storage.TenantFileSystemStorage(base_url='/media/campaign-materials', location=(
                                           '/home/yushkovsky/Dropbox/hcrm/email/bin/media', 'campaign-materials')),
                                           upload_to=users.models.get_upload_path, verbose_name='Avatar'),
        ),
    ]