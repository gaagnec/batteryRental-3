# Performance optimization migration
# Adds database indexes for frequently queried fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0018_update_battery_status_choices'),
    ]

    operations = [
        # Rental indexes - optimize dashboard and admin queries
        migrations.AddIndex(
            model_name='rental',
            index=models.Index(fields=['client', 'status'], name='idx_rental_client_status'),
        ),
        migrations.AddIndex(
            model_name='rental',
            index=models.Index(fields=['status', '-start_at'], name='idx_rental_status_start'),
        ),
        
        # Payment indexes - optimize financial queries
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['date', 'type'], name='idx_payment_date_type'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['rental', 'type'], name='idx_payment_rental_type'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['-date'], name='idx_payment_date_desc'),
        ),
        
        # RentalBatteryAssignment indexes - optimize active assignment queries
        migrations.AddIndex(
            model_name='rentalbatteryassignment',
            index=models.Index(fields=['rental', 'start_at'], name='idx_rba_rental_start'),
        ),
        migrations.AddIndex(
            model_name='rentalbatteryassignment',
            index=models.Index(fields=['start_at', 'end_at'], name='idx_rba_dates'),
        ),
        migrations.AddIndex(
            model_name='rentalbatteryassignment',
            index=models.Index(fields=['battery', 'start_at'], name='idx_rba_battery_start'),
        ),
        
        # Client indexes - optimize client lookups
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['name'], name='idx_client_name'),
        ),
        
        # Battery indexes - optimize battery status queries
        migrations.AddIndex(
            model_name='battery',
            index=models.Index(fields=['status'], name='idx_battery_status'),
        ),
        migrations.AddIndex(
            model_name='battery',
            index=models.Index(fields=['serial_number'], name='idx_battery_serial'),
        ),
        
        # Expense indexes - optimize financial reports
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['payment_type', 'date'], name='idx_expense_type_date'),
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['paid_by_partner', 'date'], name='idx_expense_partner_date'),
        ),
        
        # MoneyTransfer indexes - optimize transfer queries
        migrations.AddIndex(
            model_name='moneytransfer',
            index=models.Index(fields=['date'], name='idx_transfer_date'),
        ),
        migrations.AddIndex(
            model_name='moneytransfer',
            index=models.Index(fields=['from_partner'], name='idx_transfer_from'),
        ),
        migrations.AddIndex(
            model_name='moneytransfer',
            index=models.Index(fields=['to_partner'], name='idx_transfer_to'),
        ),
    ]

