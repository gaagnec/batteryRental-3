# Migration: add end_reason to RentalBatteryAssignment for battery swap logging
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0024_add_financepartner_cities_m2m'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalbatteryassignment',
            name='end_reason',
            field=models.CharField(
                blank=True,
                help_text='Причина завершения назначения (замена, неисправность, по просьбе клиента и т.д.)',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='historicalrentalbatteryassignment',
            name='end_reason',
            field=models.CharField(
                blank=True,
                help_text='Причина завершения назначения (замена, неисправность, по просьбе клиента и т.д.)',
                max_length=255,
            ),
        ),
    ]
