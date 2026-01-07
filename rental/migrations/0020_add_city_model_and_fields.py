# Generated migration for city model and fields
# Adds City model and city fields to FinancePartner, Client, Battery, Rental, Payment

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0019_add_performance_indexes'),
    ]

    operations = [
        # Create City model
        migrations.CreateModel(
            name='City',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=64, unique=True)),
                ('code', models.CharField(max_length=16, unique=True)),
                ('active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to='auth.user')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to='auth.user')),
            ],
            options={
                'verbose_name': 'Город',
                'verbose_name_plural': 'Города',
                'ordering': ['name'],
            },
        ),
        # Add city field to FinancePartner
        migrations.AddField(
            model_name='financepartner',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='finance_partners', to='rental.city'),
        ),
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
        # Add index for city field in Payment for better performance
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['city'], name='idx_payment_city'),
        ),
        # Add index for city field in Rental for better performance
        migrations.AddIndex(
            model_name='rental',
            index=models.Index(fields=['city'], name='idx_rental_city'),
        ),
        # Add index for city field in Battery for better performance
        migrations.AddIndex(
            model_name='battery',
            index=models.Index(fields=['city'], name='idx_battery_city'),
        ),
        # Add index for city field in Client for better performance
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['city'], name='idx_client_city'),
        ),
    ]

