# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-10-20 13:11
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0016_auto_20171004_0017'),
    ]

    operations = [
        migrations.AddField(
            model_name='step',
            name='offset',
            field=models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)]),
        ),
    ]
