# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-15 22:40
from __future__ import unicode_literals

import django.db.models.deletion
import timezone_field.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0011_auto_20170815_1846'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contact',
            name='address',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='campaigns.Address'),
        ),
        migrations.AlterField(
            model_name='contact',
            name='name',
            field=models.TextField(blank=True, default=None, verbose_name='Name'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='contact',
            name='timezone',
            field=timezone_field.fields.TimeZoneField(default='America/Los_Angeles'),
        ),
    ]
