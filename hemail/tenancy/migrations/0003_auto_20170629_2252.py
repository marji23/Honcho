# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-06-29 22:52
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0002_tenantdata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenantdata',
            name='description',
            field=models.TextField(blank=True, max_length=200),
        ),
    ]