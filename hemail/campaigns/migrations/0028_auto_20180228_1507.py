# Generated by Django 2.0.2 on 2018-02-28 15:07

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import users.utils


class Migration(migrations.Migration):
    dependencies = [
        ('campaigns', '0027_scheduledemail_inbox_message'),
    ]

    operations = [
        migrations.AlterField(
            model_name='campaign',
            name='owner',
            field=models.ForeignKey(limit_choices_to=users.utils.tenant_users, on_delete=django.db.models.deletion.PROTECT,
                                    to=settings.AUTH_USER_MODEL),
        ),
    ]
