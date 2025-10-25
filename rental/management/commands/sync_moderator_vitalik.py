from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from rental.models import FinancePartner


class Command(BaseCommand):
    help = 'Добавляет пользователя Vitalik в таблицу FinancePartner с ролью MODERATOR'

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username='Vitalik')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('Пользователь Vitalik не найден'))
            return

        finance_partner, created = FinancePartner.objects.get_or_create(
            user=user,
            defaults={
                'role': FinancePartner.Role.MODERATOR,
                'active': True,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Создана запись FinancePartner для {user.username} с ролью MODERATOR'))
        else:
            if finance_partner.role != FinancePartner.Role.MODERATOR:
                finance_partner.role = FinancePartner.Role.MODERATOR
                finance_partner.save()
                self.stdout.write(self.style.SUCCESS(f'Обновлена роль для {user.username} на MODERATOR'))
            else:
                self.stdout.write(self.style.WARNING(f'Запись для {user.username} уже существует с ролью MODERATOR'))
