# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-18 20:57
from __future__ import unicode_literals

from django.db import migrations, models

import campaigns.models
import tenancy.storage


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0023_campaignsettings_stop_sending_on_reply'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledemail',
            name='sent',
            field=models.DateTimeField(editable=False, help_text='Time when message was successfully sent', null=True),
        ),
        migrations.AlterField(
            model_name='attachment',
            name='file',
            field=models.FileField(storage=tenancy.storage.TenantFileSystemStorage(base_url='/media/private-attachments', location=(
            '/home/yushkovsky/Dropbox/hcrm/email/bin/media', 'private-attachments')), upload_to=campaigns.models.get_upload_path,
                                   verbose_name='File'),
        ),
    ]