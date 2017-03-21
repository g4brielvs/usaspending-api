# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2017-03-18 20:52
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    # note: a hacky data migration because this is a new table
    # and a one-time thing (note that create/update dates are
    # hard-coded here b/c they don't really matter right now)
    forward_sql = [
        '''TRUNCATE TABLE object_class''',
        '''
            INSERT INTO object_class (
                major_object_class,
                major_object_class_name,
                object_class,
                object_class_name,
                direct_reimbursable,
                direct_reimbursable_name,
                create_date,
                update_date
            )
            SELECT
                CASE WHEN LEFT(RIGHT(object_class, 3),1) = '1' THEN '10' WHEN LEFT(RIGHT(object_class, 3),1) = '2' THEN '20' WHEN LEFT(RIGHT(object_class, 3),1) = '3' THEN '30' WHEN LEFT(RIGHT(object_class, 3),1) = '4' THEN '40' ELSE '90' END,
                CASE WHEN LEFT(RIGHT(object_class, 3),1) = '1' THEN 'Personnel compensation and benefits' WHEN LEFT(RIGHT(object_class, 3),1) = '2' THEN 'Contractual services and supplies' WHEN LEFT(RIGHT(object_class, 3),1) = '3' THEN 'Acquisition of assets' WHEN LEFT(RIGHT(object_class, 3),1) = '4' THEN 'Grants and fixed charges' ELSE 'Other' END,
                RIGHT(object_class, 3),
                max_object_class_name,
                CASE WHEN length(object_class) = 4 THEN LEFT(object_class, 1) ELSE NULL END,
                CASE WHEN length(object_class) = 4 AND LEFT(object_class, 1) = '1' THEN 'Direct' WHEN length(object_class) = 4 THEN 'Reimbursable' ELSE NULL END,
                '2017-03-20', '2017-03-20'
            FROM ref_object_class_code
        '''
    ]

    dependencies = [
        ('references', '0055_auto_20170319_1841'),
    ]

    operations = [
        migrations.RunSQL(sql, migrations.RunSQL.noop) for sql in forward_sql
    ]
