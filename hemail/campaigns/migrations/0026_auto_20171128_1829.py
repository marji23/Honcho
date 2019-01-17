# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-28 18:29
from __future__ import unicode_literals

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0025_trackinginfo'),
    ]

    operations = [
        migrations.AddField(
            model_name='participation',
            name='activation',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='participation',
            name='created',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]