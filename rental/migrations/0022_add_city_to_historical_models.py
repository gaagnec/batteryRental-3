# Migration to add city field to historical models
# Adds city_id to HistoricalRental, HistoricalClient, HistoricalBattery, HistoricalPayment, HistoricalFinancePartner

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0021_seed_cities'),
    ]

    operations = [
        # Add city field to HistoricalRental
        migrations.AddField(
            model_name='historicalrental',
            name='city',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
        ),
        # Add city field to HistoricalClient
        migrations.AddField(
            model_name='historicalclient',
            name='city',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
        ),
        # Add city field to HistoricalBattery
        migrations.AddField(
            model_name='historicalbattery',
            name='city',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
        ),
        # Add city field to HistoricalPayment
        migrations.AddField(
            model_name='historicalpayment',
            name='city',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
        ),
        # Add city field to HistoricalFinancePartner
        migrations.AddField(
            model_name='historicalfinancepartner',
            name='city',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
        ),
    ]

