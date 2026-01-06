# Generated migration to update city field in existing payments

from django.db import migrations


def update_payment_cities(apps, schema_editor):
    """Обновляем city в существующих платежах"""
    Payment = apps.get_model('rental', 'Payment')
    Rental = apps.get_model('rental', 'Rental')
    FinancePartner = apps.get_model('rental', 'FinancePartner')
    
    payments_without_city = Payment.objects.filter(city__isnull=True).select_related('rental', 'created_by')
    
    updated_count = 0
    for payment in payments_without_city:
        # Приоритет 1: Город из rental.city
        if payment.rental and payment.rental.city_id:
            payment.city_id = payment.rental.city_id
            payment.save(update_fields=['city'])
            updated_count += 1
        # Приоритет 2: Город модератора из created_by
        elif payment.created_by_id:
            finance_partner = FinancePartner.objects.filter(
                user_id=payment.created_by_id,
                role='moderator',
                active=True
            ).first()
            if finance_partner and finance_partner.city_id:
                payment.city_id = finance_partner.city_id
                payment.save(update_fields=['city'])
                updated_count += 1
    
    print(f"Updated {updated_count} payments with city")


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0022_add_battery_transfer'),
    ]

    operations = [
        migrations.RunPython(update_payment_cities, reverse_code=migrations.RunPython.noop),
    ]
