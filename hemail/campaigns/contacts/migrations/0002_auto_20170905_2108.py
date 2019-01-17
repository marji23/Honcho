# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-09-05 21:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contact',
            name='address',
        ),
        migrations.RemoveField(
            model_name='contact',
            name='name',
        ),
        migrations.AddField(
            model_name='contact',
            name='city',
            field=models.TextField(blank=True, verbose_name='city'),
        ),
        migrations.AddField(
            model_name='contact',
            name='country',
            field=models.TextField(blank=True, verbose_name='country'),
        ),
        migrations.AddField(
            model_name='contact',
            name='first_name',
            field=models.TextField(blank=True, verbose_name='first name'),
        ),
        migrations.AddField(
            model_name='contact',
            name='last_name',
            field=models.TextField(blank=True, verbose_name='last name'),
        ),
        migrations.AddField(
            model_name='contact',
            name='state',
            field=models.TextField(blank=True, verbose_name='state'),
        ),
        migrations.AddField(
            model_name='contact',
            name='street_address',
            field=models.TextField(blank=True, verbose_name='street address'),
        ),
        migrations.AddField(
            model_name='contact',
            name='zip_code',
            field=models.TextField(blank=True, verbose_name='zip code'),
        ),
        migrations.AddField(
            model_name='contactlist',
            name='name',
            field=models.TextField(default='friends', unique=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='contactlist',
            name='contacts',
            field=models.ManyToManyField(related_name='lists', to='contacts.Contact'),
        ),
        migrations.DeleteModel(
            name='Address',
        ),
    ]