# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-13 20:04
from __future__ import unicode_literals

import django.db.models.deletion
import phonenumber_field.modelfields
import timezone_field.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0005_auto_20170724_1841'),
    ]

    operations = [
        migrations.CreateModel(
            name='Address',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('city', models.TextField(blank=True, verbose_name='city')),
                ('state', models.TextField(blank=True, verbose_name='state')),
                ('country', models.TextField(blank=True, verbose_name='country')),
            ],
        ),
        migrations.AddField(
            model_name='contact',
            name='company_name',
            field=models.TextField(blank=True, verbose_name='company name'),
        ),
        migrations.AddField(
            model_name='contact',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True, verbose_name='date of birth'),
        ),
        migrations.AddField(
            model_name='contact',
            name='name',
            field=models.TextField(null=True, verbose_name='Name'),
        ),
        migrations.AddField(
            model_name='contact',
            name='phone_number',
            field=phonenumber_field.modelfields.PhoneNumberField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='contact',
            name='sex',
            field=models.CharField(blank=True, max_length=1, verbose_name='sex'),
        ),
        migrations.AddField(
            model_name='contact',
            name='timezone',
            field=timezone_field.fields.TimeZoneField(default='America/Los_Angeles'),
        ),
        migrations.AddField(
            model_name='contact',
            name='title',
            field=models.TextField(blank=True, verbose_name='title'),
        ),
        migrations.AddField(
            model_name='contact',
            name='address',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    to='campaigns.Address'),
        ),
    ]
