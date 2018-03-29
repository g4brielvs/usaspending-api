# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2018-03-29 17:16
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('awards', '0027_add_loan_value_to_awards_and_transactions'),
    ]

    operations = [
        migrations.AddField(
            model_name='award',
            name='total_funding_amount',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='transactionnormalized',
            name='total_funding_amount',
            field=models.TextField(blank=True, null=True),
        ),
    ]
