# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-09-26 01:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('awards', '0014_merge_20170921_1544'),
    ]

    operations = [
        migrations.AddField(
            model_name='transactionfpds',
            name='base_and_all_options_value',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='transactionfpds',
            name='base_exercised_options_val',
            field=models.TextField(blank=True, null=True),
        ),
    ]
