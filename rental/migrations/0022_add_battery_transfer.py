# Generated manually for multi-city system
# Adds BatteryTransfer model for tracking battery transfers between cities

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0021_add_city_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='BatteryTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Ожидает подтверждения'), ('approved', 'Подтвержден'), ('rejected', 'Отклонен')], default='pending', max_length=16)),
                ('note', models.TextField(blank=True, verbose_name='Комментарий')),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_transfers', to='auth.user')),
                ('battery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transfers', to='rental.battery')),
                ('from_city', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_from', to='rental.city')),
                ('requested_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transfer_requests', to='auth.user')),
                ('to_city', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_to', to='rental.city')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='batterytransfer_created', to='auth.user')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='batterytransfer_updated', to='auth.user')),
            ],
            options={
                'verbose_name': 'Перенос батареи',
                'verbose_name_plural': 'Переносы батарей',
                'ordering': ['-created_at'],
            },
        ),
    ]

