from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Exists, OuterRef

from rental.models import Battery, RentalBatteryAssignment, Rental


class Command(BaseCommand):
    help = (
        'Исправляет статусы батарей: батареи в аренде (есть активное назначение) — RENTED, '
        'без активного назначения и статусом RENTED — AVAILABLE. Выводит номера (short_code) исправленных батарей.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, какие батареи будут изменены, без записи в БД',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        # Активное назначение: только по активному договору (ACTIVE), start_at <= now, end_at не закрыт
        active_assignment = RentalBatteryAssignment.objects.filter(
            battery_id=OuterRef('pk'),
            rental__status=Rental.Status.ACTIVE,
            start_at__lte=now,
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))

        # 1) В аренде (есть активное назначение), но статус не RENTED
        rented_but_wrong = Battery.objects.filter(
            Exists(active_assignment),
        ).exclude(status=Battery.Status.RENTED)

        fixed_to_rented = []
        for b in rented_but_wrong:
            fixed_to_rented.append(b.short_code)
            if not dry_run:
                Battery.objects.filter(pk=b.pk).update(status=Battery.Status.RENTED)

        # 2) Нет активного назначения, но статус RENTED (не service/sold)
        batteries_with_active = Battery.objects.filter(Exists(active_assignment))
        not_rented_but_wrong = Battery.objects.filter(
            status=Battery.Status.RENTED,
        ).exclude(pk__in=batteries_with_active)

        fixed_to_available = []
        for b in not_rented_but_wrong:
            fixed_to_available.append(b.short_code)
            if not dry_run:
                Battery.objects.filter(pk=b.pk).update(status=Battery.Status.AVAILABLE)

        if dry_run:
            self.stdout.write(self.style.WARNING('Режим dry-run: изменения не применены.'))

        if fixed_to_rented:
            msg = f"Установлен статус RENTED (были в аренде с неверным статусом): {', '.join(sorted(fixed_to_rented))}"
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stdout.write('Батарей с неверным статусом (должны быть RENTED): 0')

        if fixed_to_available:
            msg = f"Установлен статус AVAILABLE (не в аренде, но статус был RENTED): {', '.join(sorted(fixed_to_available))}"
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stdout.write('Батарей с неверным статусом (должны быть AVAILABLE): 0')

        if not fixed_to_rented and not fixed_to_available:
            self.stdout.write(self.style.SUCCESS('Все статусы батарей согласованы с назначениями.'))
