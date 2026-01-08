# Migration to add city field to historical models
# Adds city_id to HistoricalRental, HistoricalClient, HistoricalBattery, HistoricalPayment, HistoricalFinancePartner
# Safe migration with existence checks

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0021_seed_cities'),
    ]

    operations = [
        # Add city field to HistoricalRental
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_historicalrental' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_historicalrental 
                        ADD COLUMN city_id INTEGER;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_historicalrental DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to HistoricalClient
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_historicalclient' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_historicalclient 
                        ADD COLUMN city_id INTEGER;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_historicalclient DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to HistoricalBattery
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_historicalbattery' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_historicalbattery 
                        ADD COLUMN city_id INTEGER;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_historicalbattery DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to HistoricalPayment
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_historicalpayment' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_historicalpayment 
                        ADD COLUMN city_id INTEGER;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_historicalpayment DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to HistoricalFinancePartner
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_historicalfinancepartner' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_historicalfinancepartner 
                        ADD COLUMN city_id INTEGER;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_historicalfinancepartner DROP COLUMN IF EXISTS city_id;",
        ),
        # Update Django state to reflect the changes
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # Already done above with RunSQL
            state_operations=[
                migrations.AddField(
                    model_name='historicalrental',
                    name='city',
                    field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='historicalclient',
                    name='city',
                    field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='historicalbattery',
                    name='city',
                    field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='historicalpayment',
                    name='city',
                    field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='historicalfinancepartner',
                    name='city',
                    field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city'),
                ),
            ],
        ),
    ]

