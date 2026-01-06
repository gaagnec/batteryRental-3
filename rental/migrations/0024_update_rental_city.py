# Generated migration to update city field in existing rentals

from django.db import migrations


def update_rental_cities(apps, schema_editor):
    """Обновляем city в существующих договорах"""
    Rental = apps.get_model('rental', 'Rental')
    Client = apps.get_model('rental', 'Client')
    
    rentals_without_city = Rental.objects.filter(city__isnull=True).select_related('client')
    
    updated_count = 0
    for rental in rentals_without_city:
        # Устанавливаем city из client.city
        if rental.client and rental.client.city_id:
            rental.city_id = rental.client.city_id
            rental.save(update_fields=['city'])
            updated_count += 1
    
    print(f"Updated {updated_count} rentals with city")


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0023_update_payment_city'),
    ]

    operations = [
        migrations.RunPython(update_rental_cities, reverse_code=migrations.RunPython.noop),
    ]

