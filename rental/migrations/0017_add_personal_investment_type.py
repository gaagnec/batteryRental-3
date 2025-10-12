# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0016_add_new_expense_categories'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expense',
            name='payment_type',
            field=models.CharField(
                choices=[
                    ('purchase', 'Закупка'),
                    ('deposit', 'Внесение денег'),
                    ('personal', 'Личное вложение')
                ],
                default='purchase',
                max_length=16
            ),
        ),
        migrations.AlterField(
            model_name='historicalexpense',
            name='payment_type',
            field=models.CharField(
                choices=[
                    ('purchase', 'Закупка'),
                    ('deposit', 'Внесение денег'),
                    ('personal', 'Личное вложение')
                ],
                default='purchase',
                max_length=16
            ),
        ),
    ]
