# Generated migration for FinancePartner.cities ManyToManyField
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0023_create_batterytransfer_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='financepartner',
            name='cities',
            field=models.ManyToManyField(
                blank=True,
                related_name='finance_partners_multi',
                to='rental.city',
                verbose_name='Города (для владельцев)'
            ),
        ),
    ]

