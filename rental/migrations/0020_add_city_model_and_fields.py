# Generated migration for city model and fields
# Adds City model and city fields to FinancePartner, Client, Battery, Rental, Payment
# Safe migration with existence checks to prevent errors if tables/fields already exist

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0019_add_performance_indexes'),
    ]

    operations = [
        # Create City model - using RunSQL with IF NOT EXISTS check
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS rental_city (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    name VARCHAR(64) NOT NULL UNIQUE,
                    code VARCHAR(16) NOT NULL UNIQUE,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
                    updated_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS rental_city_created_by_id_idx ON rental_city(created_by_id);
                CREATE INDEX IF NOT EXISTS rental_city_updated_by_id_idx ON rental_city(updated_by_id);
            """,
            reverse_sql="DROP TABLE IF EXISTS rental_city CASCADE;",
        ),
        # Add city field to FinancePartner
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_financepartner' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_financepartner 
                        ADD COLUMN city_id INTEGER REFERENCES rental_city(id) ON DELETE RESTRICT;
                        CREATE INDEX IF NOT EXISTS rental_financepartner_city_id_idx ON rental_financepartner(city_id);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_financepartner DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to Client
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_client' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_client 
                        ADD COLUMN city_id INTEGER REFERENCES rental_city(id) ON DELETE SET NULL;
                        CREATE INDEX IF NOT EXISTS rental_client_city_id_idx ON rental_client(city_id);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_client DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to Battery
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_battery' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_battery 
                        ADD COLUMN city_id INTEGER REFERENCES rental_city(id) ON DELETE SET NULL;
                        CREATE INDEX IF NOT EXISTS rental_battery_city_id_idx ON rental_battery(city_id);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_battery DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to Rental
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_rental' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_rental 
                        ADD COLUMN city_id INTEGER REFERENCES rental_city(id) ON DELETE SET NULL;
                        CREATE INDEX IF NOT EXISTS rental_rental_city_id_idx ON rental_rental(city_id);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_rental DROP COLUMN IF EXISTS city_id;",
        ),
        # Add city field to Payment
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'rental_payment' 
                        AND column_name = 'city_id'
                    ) THEN
                        ALTER TABLE rental_payment 
                        ADD COLUMN city_id INTEGER REFERENCES rental_city(id) ON DELETE SET NULL;
                        CREATE INDEX IF NOT EXISTS rental_payment_city_id_idx ON rental_payment(city_id);
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE rental_payment DROP COLUMN IF EXISTS city_id;",
        ),
        # Add custom indexes with IF NOT EXISTS
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS idx_payment_city ON rental_payment(city_id);
                CREATE INDEX IF NOT EXISTS idx_rental_city ON rental_rental(city_id);
                CREATE INDEX IF NOT EXISTS idx_battery_city ON rental_battery(city_id);
                CREATE INDEX IF NOT EXISTS idx_client_city ON rental_client(city_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_payment_city;
                DROP INDEX IF EXISTS idx_rental_city;
                DROP INDEX IF EXISTS idx_battery_city;
                DROP INDEX IF EXISTS idx_client_city;
            """,
        ),
        # Update Django state to reflect the changes (for Django's migration tracking)
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # Already done above with RunSQL
            state_operations=[
                migrations.CreateModel(
                    name='City',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('name', models.CharField(max_length=64, unique=True)),
                        ('code', models.CharField(max_length=16, unique=True)),
                        ('active', models.BooleanField(default=True)),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to='auth.user')),
                        ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to='auth.user')),
                    ],
                    options={
                        'verbose_name': 'Город',
                        'verbose_name_plural': 'Города',
                        'ordering': ['name'],
                    },
                ),
                migrations.AddField(
                    model_name='financepartner',
                    name='city',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='finance_partners', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='client',
                    name='city',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clients', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='battery',
                    name='city',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='batteries', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='rental',
                    name='city',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rentals', to='rental.city'),
                ),
                migrations.AddField(
                    model_name='payment',
                    name='city',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='rental.city'),
                ),
                migrations.AddIndex(
                    model_name='payment',
                    index=models.Index(fields=['city'], name='idx_payment_city'),
                ),
                migrations.AddIndex(
                    model_name='rental',
                    index=models.Index(fields=['city'], name='idx_rental_city'),
                ),
                migrations.AddIndex(
                    model_name='battery',
                    index=models.Index(fields=['city'], name='idx_battery_city'),
                ),
                migrations.AddIndex(
                    model_name='client',
                    index=models.Index(fields=['city'], name='idx_client_city'),
                ),
            ],
        ),
    ]
