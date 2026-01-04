# Generated manually for multi-city system
# Adds city fields to all models and links existing data to Poznan

from django.db import migrations, models
import django.db.models.deletion


def link_existing_data_to_poznan(apps, schema_editor):
    """Привязывает все существующие данные к Познани"""
    City = apps.get_model('rental', 'City')
    Client = apps.get_model('rental', 'Client')
    Battery = apps.get_model('rental', 'Battery')
    Rental = apps.get_model('rental', 'Rental')
    Payment = apps.get_model('rental', 'Payment')
    FinancePartner = apps.get_model('rental', 'FinancePartner')
    
    try:
        poznan = City.objects.get(code='poznan')
    except City.DoesNotExist:
        # Если Познань не найдена, создаем её
        poznan = City.objects.create(name='Познань', code='poznan', active=True)
    
    # Привязываем все существующие данные к Познани
    Client.objects.filter(city__isnull=True).update(city=poznan)
    Battery.objects.filter(city__isnull=True).update(city=poznan)
    Rental.objects.filter(city__isnull=True).update(city=poznan)
    Payment.objects.filter(city__isnull=True).update(city=poznan)
    
    # Для модераторов city обязательное - привязываем к Познани
    FinancePartner.objects.filter(role='moderator', city__isnull=True).update(city=poznan)


def reverse_link_data(apps, schema_editor):
    """Откат - убираем привязку к городам"""
    Client = apps.get_model('rental', 'Client')
    Battery = apps.get_model('rental', 'Battery')
    Rental = apps.get_model('rental', 'Rental')
    Payment = apps.get_model('rental', 'Payment')
    FinancePartner = apps.get_model('rental', 'FinancePartner')
    
    Client.objects.all().update(city=None)
    Battery.objects.all().update(city=None)
    Rental.objects.all().update(city=None)
    Payment.objects.all().update(city=None)
    FinancePartner.objects.all().update(city=None)


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0020_add_city_model'),
    ]

    operations = [
        # Add city field to Client
        migrations.AddField(
            model_name='client',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clients', to='rental.city'),
        ),
        
        # Add city field to Battery
        migrations.AddField(
            model_name='battery',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='batteries', to='rental.city'),
        ),
        
        # Add city field to Rental
        migrations.AddField(
            model_name='rental',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rentals', to='rental.city'),
        ),
        
        # Add city field to Payment
        migrations.AddField(
            model_name='payment',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='rental.city'),
        ),
        
        # Add city field to FinancePartner (nullable for now, will be required for moderators)
        migrations.AddField(
            model_name='financepartner',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='finance_partners', to='rental.city'),
        ),
        
        # Add reward_percent to FinancePartner
        migrations.AddField(
            model_name='financepartner',
            name='reward_percent',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Процент вознаграждения модератора (0-100)', max_digits=5),
        ),
        
        # Link existing data to Poznan
        migrations.RunPython(link_existing_data_to_poznan, reverse_link_data),
    ]

