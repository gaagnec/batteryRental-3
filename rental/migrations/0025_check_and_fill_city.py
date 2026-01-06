# Generated manually to check and fill city fields

from django.db import migrations


def check_and_fill_city(apps, schema_editor):
    Client = apps.get_model('rental', 'Client')
    Rental = apps.get_model('rental', 'Rental')
    Payment = apps.get_model('rental', 'Payment')
    City = apps.get_model('rental', 'City')
    
    # Получаем город по умолчанию (Poznań)
    try:
        default_city = City.objects.get(code='POZ')
    except City.DoesNotExist:
        print("WARNING: Default city (Poznań) not found!")
        return
    
    # Проверяем и заполняем клиентов
    clients_without_city = Client.objects.filter(city__isnull=True)
    clients_count = clients_without_city.count()
    if clients_count > 0:
        print(f"Найдено {clients_count} клиентов без города. Устанавливаем Poznań...")
        clients_without_city.update(city=default_city)
    else:
        print("Все клиенты имеют город ✓")
    
    # Проверяем и заполняем договоры (если остались после 0024)
    rentals_without_city = Rental.objects.filter(city__isnull=True)
    rentals_count = rentals_without_city.count()
    if rentals_count > 0:
        print(f"Найдено {rentals_count} договоров без города. Устанавливаем Poznań...")
        rentals_without_city.update(city=default_city)
    else:
        print("Все договоры имеют город ✓")
    
    # Проверяем и заполняем платежи (если остались после 0023)
    payments_without_city = Payment.objects.filter(city__isnull=True)
    payments_count = payments_without_city.count()
    if payments_count > 0:
        print(f"Найдено {payments_count} платежей без города. Устанавливаем Poznań...")
        payments_without_city.update(city=default_city)
    else:
        print("Все платежи имеют город ✓")
    
    print("\n" + "=" * 60)
    print("ИТОГОВАЯ СТАТИСТИКА:")
    print(f"Клиентов: {Client.objects.count()} (без города: {Client.objects.filter(city__isnull=True).count()})")
    print(f"Договоров: {Rental.objects.count()} (без города: {Rental.objects.filter(city__isnull=True).count()})")
    print(f"Платежей: {Payment.objects.count()} (без города: {Payment.objects.filter(city__isnull=True).count()})")
    print("=" * 60)


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0024_update_rental_city'),
    ]

    operations = [
        migrations.RunPython(check_and_fill_city, reverse_code=migrations.RunPython.noop),
    ]
