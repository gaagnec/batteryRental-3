# Migration to create BatteryTransfer model and its historical table
# Safe migration with existence checks to prevent errors if tables already exist

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import simple_history.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0022_add_city_to_historical_models'),
    ]

    operations = [
        # Create BatteryTransfer table with IF NOT EXISTS check
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'rental_batterytransfer'
                    ) THEN
                        CREATE TABLE rental_batterytransfer (
                            id BIGSERIAL PRIMARY KEY,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                            status VARCHAR(16) NOT NULL DEFAULT 'pending',
                            note TEXT NOT NULL DEFAULT '',
                            battery_id BIGINT NOT NULL REFERENCES rental_battery(id) ON DELETE CASCADE,
                            from_city_id INTEGER NOT NULL REFERENCES rental_city(id) ON DELETE RESTRICT,
                            to_city_id INTEGER NOT NULL REFERENCES rental_city(id) ON DELETE RESTRICT,
                            requested_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
                            approved_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
                            created_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
                            updated_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL
                        );
                        
                        CREATE INDEX IF NOT EXISTS rental_batte_status_created_idx ON rental_batterytransfer(status, created_at);
                        CREATE INDEX IF NOT EXISTS rental_batte_battery_status_idx ON rental_batterytransfer(battery_id, status);
                        CREATE INDEX IF NOT EXISTS rental_batte_battery_id_idx ON rental_batterytransfer(battery_id);
                        CREATE INDEX IF NOT EXISTS rental_batte_from_city_id_idx ON rental_batterytransfer(from_city_id);
                        CREATE INDEX IF NOT EXISTS rental_batte_to_city_id_idx ON rental_batterytransfer(to_city_id);
                    END IF;
                END $$;
            """,
            reverse_sql="DROP TABLE IF EXISTS rental_batterytransfer CASCADE;",
        ),
        # Create HistoricalBatteryTransfer table with IF NOT EXISTS check
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'rental_historicalbatterytransfer'
                    ) THEN
                        CREATE TABLE rental_historicalbatterytransfer (
                            history_id SERIAL PRIMARY KEY,
                            history_date TIMESTAMP WITH TIME ZONE NOT NULL,
                            history_change_reason VARCHAR(100),
                            history_type VARCHAR(1) NOT NULL,
                            id BIGINT NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE,
                            updated_at TIMESTAMP WITH TIME ZONE,
                            status VARCHAR(16) NOT NULL DEFAULT 'pending',
                            note TEXT NOT NULL DEFAULT '',
                            battery_id BIGINT,
                            from_city_id INTEGER,
                            to_city_id INTEGER,
                            requested_by_id INTEGER,
                            approved_by_id INTEGER,
                            created_by_id INTEGER,
                            updated_by_id INTEGER,
                            history_user_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL
                        );
                        
                        CREATE INDEX IF NOT EXISTS rental_hist_batt_history_date_idx ON rental_historicalbatterytransfer(history_date);
                        CREATE INDEX IF NOT EXISTS rental_hist_batt_id_idx ON rental_historicalbatterytransfer(id);
                    END IF;
                END $$;
            """,
            reverse_sql="DROP TABLE IF EXISTS rental_historicalbatterytransfer CASCADE;",
        ),
        # Update Django state to reflect the changes
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # Already done above with RunSQL
            state_operations=[
                migrations.CreateModel(
                    name='BatteryTransfer',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('status', models.CharField(choices=[('pending', 'Ожидает подтверждения'), ('approved', 'Подтверждён'), ('rejected', 'Отклонён')], default='pending', max_length=16)),
                        ('note', models.TextField(blank=True, verbose_name='Комментарий')),
                        ('battery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transfers', to='rental.battery')),
                        ('from_city', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_from', to='rental.city')),
                        ('to_city', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_to', to='rental.city')),
                        ('requested_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transfer_requests', to=settings.AUTH_USER_MODEL)),
                        ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_transfers', to=settings.AUTH_USER_MODEL)),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                        ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'verbose_name': 'Перенос батареи',
                        'verbose_name_plural': 'Переносы батарей',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.AddIndex(
                    model_name='batterytransfer',
                    index=models.Index(fields=['status', 'created_at'], name='rental_batte_status_created_idx'),
                ),
                migrations.AddIndex(
                    model_name='batterytransfer',
                    index=models.Index(fields=['battery', 'status'], name='rental_batte_battery_status_idx'),
                ),
                migrations.CreateModel(
                    name='HistoricalBatteryTransfer',
                    fields=[
                        ('history_id', models.AutoField(primary_key=True, serialize=False)),
                        ('history_date', models.DateTimeField(db_index=True)),
                        ('history_change_reason', models.CharField(max_length=100, null=True)),
                        ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                        ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                        ('created_at', models.DateTimeField(blank=True, editable=False)),
                        ('updated_at', models.DateTimeField(blank=True, editable=False)),
                        ('status', models.CharField(choices=[('pending', 'Ожидает подтверждения'), ('approved', 'Подтверждён'), ('rejected', 'Отклонён')], default='pending', max_length=16)),
                        ('note', models.TextField(blank=True, verbose_name='Комментарий')),
                        ('battery', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.battery')),
                        ('from_city', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city')),
                        ('to_city', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='rental.city')),
                        ('requested_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('approved_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('created_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('updated_by', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'verbose_name': 'historical перенос батареи',
                        'verbose_name_plural': 'historical переносы батарей',
                        'ordering': ('-history_date', '-history_id'),
                        'get_latest_by': ('history_date', 'history_id'),
                    },
                    bases=(simple_history.models.HistoricalChanges, models.Model),
                ),
            ],
        ),
    ]

