from django.db import migrations


def add_vitalik_as_moderator(apps, schema_editor):
    """Добавляет пользователя Vitalik в таблицу FinancePartner с ролью MODERATOR"""
    User = apps.get_model('auth', 'User')
    FinancePartner = apps.get_model('rental', 'FinancePartner')
    
    try:
        user = User.objects.get(username='Vitalik')
    except User.DoesNotExist:
        print('Пользователь Vitalik не найден, пропускаем миграцию')
        return
    
    finance_partner, created = FinancePartner.objects.get_or_create(
        user=user,
        defaults={
            'role': 'moderator',
            'active': True,
        }
    )
    
    if created:
        print(f'Создана запись FinancePartner для {user.username} с ролью MODERATOR')
    else:
        if finance_partner.role != 'moderator':
            finance_partner.role = 'moderator'
            finance_partner.save()
            print(f'Обновлена роль для {user.username} на MODERATOR')
        else:
            print(f'Запись для {user.username} уже существует с ролью MODERATOR')


def reverse_add_vitalik(apps, schema_editor):
    """Откатывает изменения"""
    User = apps.get_model('auth', 'User')
    FinancePartner = apps.get_model('rental', 'FinancePartner')
    
    try:
        user = User.objects.get(username='Vitalik')
        FinancePartner.objects.filter(user=user, role='moderator').delete()
        print(f'Удалена запись FinancePartner для {user.username}')
    except User.DoesNotExist:
        print('Пользователь Vitalik не найден')


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0016_add_new_expense_categories'),
    ]

    operations = [
        migrations.RunPython(add_vitalik_as_moderator, reverse_add_vitalik),
    ]
