# Migration to seed initial cities
# Creates Wrocław, Poznań, Warszawa

from django.db import migrations


def create_cities(apps, schema_editor):
    City = apps.get_model('rental', 'City')
    
    cities_data = [
        {'name': 'Вроцлав', 'code': 'wroclaw', 'active': True},
        {'name': 'Познань', 'code': 'poznan', 'active': True},
        {'name': 'Варшава', 'code': 'warsaw', 'active': True},
    ]
    
    for city_data in cities_data:
        City.objects.get_or_create(
            code=city_data['code'],
            defaults={
                'name': city_data['name'],
                'active': city_data['active'],
            }
        )


def reverse_cities(apps, schema_editor):
    City = apps.get_model('rental', 'City')
    City.objects.filter(code__in=['wroclaw', 'poznan', 'warsaw']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0020_add_city_model_and_fields'),
    ]

    operations = [
        migrations.RunPython(create_cities, reverse_cities),
    ]

