from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import timedelta
from django.db import models

from decimal import Decimal

from .models import Client, Rental, Battery, Payment, Repair, RentalBatteryAssignment


@staff_member_required
def dashboard(request):
    # Активные клиенты: есть хотя бы один активный рентал
    active_rentals = Rental.objects.filter(status=Rental.Status.ACTIVE)
    active_clients_ids = active_rentals.values_list('client_id', flat=True).distinct()
    active_clients_count = active_clients_ids.count()

    # Батареи у активных клиентов: соберём по assignments сейчас
    now = timezone.now()
    assignments = RentalBatteryAssignment.objects.filter(
        rental__status=Rental.Status.ACTIVE,
        start_at__lte=now
    ).filter(models.Q(end_at__isnull=True) | models.Q(end_at__gt=now))

    batteries_by_client = {}
    for a in assignments.select_related('battery', 'rental__client'):
        cid = a.rental.client_id
        batteries_by_client.setdefault(cid, []).append(a.battery)

    clients_data = []
    # Баланс считаем по root-группе последних активных ренталов клиента
    latest_by_client = (
        active_rentals.order_by('client_id', '-start_at')
        .distinct('client_id')
        .select_related('client')
    )
    for r in latest_by_client:
        balance = r.group_balance()
        # Найти активный договор клиента
        active_rental = Rental.objects.filter(client=r.client, status=Rental.Status.ACTIVE).first()
        weekly_rate = active_rental.weekly_rate if active_rental else None
        clients_data.append({
            'client': r.client,
            'batteries': batteries_by_client.get(r.client_id, []),
            'balance': balance,
            'weekly_rate': weekly_rate,
        })

    # Статистика по батареям
    total_batteries = Battery.objects.count()
    rented_now = assignments.values('battery_id').distinct().count()
    in_service = Repair.objects.filter(end_at__isnull=True).count()
    available = max(total_batteries - rented_now - in_service, 0)
    battery_stats = {
        'total': total_batteries,
        'rented': rented_now,
        'in_service': in_service,
        'available': available,
    }

    # Последние 10 платежей
    latest_payments = Payment.objects.select_related('rental__client', 'created_by').order_by('-date', '-id')[:10]

    # Серия платежей и начислений за 30 дней
    window_days = 30
    start_date = timezone.localdate() - timedelta(days=window_days - 1)
    pay_qs = (
        Payment.objects.filter(date__gte=start_date)
        .values('date')
        .annotate(total=Sum('amount'))
        .order_by('date')
    )
    labels = []
    paid_values = []
    totals_pay = {row['date']: row['total'] for row in pay_qs}

    # Начисления в день считаем как сумму дневной ставки по активным назначениям
    # Перебор по дням и подсчет активных assignments на 14:00 каждого дня
    charges_values = []
    tz = timezone.get_current_timezone()
    for i in range(window_days):
        d = start_date + timedelta(days=i)
        labels.append(d.isoformat())
        paid_values.append(float(totals_pay.get(d, 0) or 0))
        # 14:00 якорь
        anchor = timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time().replace(hour=14)), tz)
        # активные ренты, покрывающие якорь
        day_total = Decimal(0)
        day_assigns = RentalBatteryAssignment.objects.filter(
            start_at__lte=anchor,
        ).filter(models.Q(end_at__isnull=True) | models.Q(end_at__gt=anchor))
        # для каждой привязки берём недельную ставку её рентала
        for a in day_assigns.select_related('rental'):
            r = a.rental
            # учитывать только если статус активен и интервал рентала покрывает якорь
            r_start = timezone.localtime(r.start_at, tz)
            r_end = timezone.localtime(r.end_at, tz) if r.end_at else None
            if r.status == Rental.Status.ACTIVE and r_start <= anchor and (r_end is None or r_end > anchor):
                day_total += (r.weekly_rate or Decimal(0)) / Decimal(7)
        charges_values.append(float(day_total))

    payments_series = {'labels': labels, 'values': paid_values}
    charges_series = {'labels': labels, 'values': charges_values}

    # Топ должников: по текущему балансу, берём 5
    debtors = []
    overall_debt = Decimal(0)
    for r in latest_by_client:
        bal = r.group_balance()
        if bal > 0:
            debtors.append((str(r.client), float(bal)))
            overall_debt += bal
    debtors.sort(key=lambda x: x[1], reverse=True)
    debtors = debtors[:5]
    top_debtors = {
        'names': [name for name, _ in debtors],
        'values': [val for _, val in debtors]
    }

    total_paid_30 = float(sum(paid_values))
    total_charged_30 = float(sum(charges_values))

    context = {
        'active_clients_count': active_clients_count,
        'clients_data': clients_data,
        'battery_stats': battery_stats,
        'latest_payments': latest_payments,
        'payments_series': payments_series,
        'charges_series': charges_series,
        'top_debtors': top_debtors,
        'overall_debt': overall_debt,
        'total_paid_30': total_paid_30,
        'total_charged_30': total_charged_30,
        'window_days': window_days,
    }
    return render(request, 'admin/dashboard.html', context)
