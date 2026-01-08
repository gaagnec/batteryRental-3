# Migration to create BatteryTransfer model and its historical table
# This migration creates both rental_batterytransfer and rental_historicalbatterytransfer tables

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
        # Create BatteryTransfer model
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
        # Create indexes for BatteryTransfer
        migrations.AddIndex(
            model_name='batterytransfer',
            index=models.Index(fields=['status', 'created_at'], name='rental_batte_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='batterytransfer',
            index=models.Index(fields=['battery', 'status'], name='rental_batte_battery_status_idx'),
        ),
        # Create HistoricalBatteryTransfer model
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
    ]

