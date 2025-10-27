# Generated manually

from django.db import migrations, models


def update_status_values(apps, schema_editor):
    """Обновляем старые значения статусов на новые"""
    BatteryStatusLog = apps.get_model('rental', 'BatteryStatusLog')
    
    # Маппинг старых значений на новые
    status_mapping = {
        'rental': 'rented',
        'repair': 'service',
        'idle': 'available',
    }
    
    for old_status, new_status in status_mapping.items():
        BatteryStatusLog.objects.filter(kind=old_status).update(kind=new_status)


def reverse_status_values(apps, schema_editor):
    """Откатываем новые значения на старые"""
    BatteryStatusLog = apps.get_model('rental', 'BatteryStatusLog')
    
    # Обратный маппинг
    status_mapping = {
        'rented': 'rental',
        'service': 'repair',
        'available': 'idle',
    }
    
    for new_status, old_status in status_mapping.items():
        BatteryStatusLog.objects.filter(kind=new_status).update(kind=old_status)
    
    # Если есть 'sold', переводим в 'idle' при откате
    BatteryStatusLog.objects.filter(kind='sold').update(kind='idle')


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0017_add_vitalik_as_moderator'),
    ]

    operations = [
        # Сначала обновляем данные в базе
        migrations.RunPython(update_status_values, reverse_status_values),
        
        # Затем обновляем choices в модели
        migrations.AlterField(
            model_name='batterystatuslog',
            name='kind',
            field=models.CharField(
                choices=[
                    ('rented', 'В аренде'),
                    ('service', 'Сервис'),
                    ('available', 'Доступный'),
                    ('sold', 'Продана')
                ],
                max_length=16
            ),
        ),
    ]
