# Generated manually

from django.db import migrations


def add_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model('rental', 'ExpenseCategory')
    
    categories = [
        "Аккумуляторы",
        "БМС",
        "Корпуса",
        "Инструменты",
        "Запчасти",
        "Бонус модераторам",
        "Сборка",
        "Рефералы",
        "Разработка ПО",
        "Хостинг",
        "Разное",
    ]
    
    for cat_name in categories:
        ExpenseCategory.objects.get_or_create(name=cat_name)


def remove_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model('rental', 'ExpenseCategory')
    
    categories = [
        "Аккумуляторы",
        "БМС",
        "Корпуса",
        "Инструменты",
        "Запчасти",
        "Бонус модераторам",
        "Сборка",
        "Рефералы",
        "Разработка ПО",
        "Хостинг",
        "Разное",
    ]
    
    ExpenseCategory.objects.filter(name__in=categories).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0015_alter_expense_options_and_more'),
    ]

    operations = [
        migrations.RunPython(add_categories, reverse_code=remove_categories),
    ]
