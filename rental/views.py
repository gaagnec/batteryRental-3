from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import timedelta, datetime, time
from django.db import models
from django.db.models import Prefetch, Q

from decimal import Decimal

from .models import Client, Rental, Battery, Payment, Repair, RentalBatteryAssignment


@staff_member_required
def dashboard(request):
    # Активные клиенты: есть хотя бы один активный рентал
    # Активные клиенты с предзагрузкой назначений батарей
    now = timezone.now()
    active_assignments_qs = RentalBatteryAssignment.objects.filter(
        start_at__lte=now
    ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now)).select_related('battery')
    active_rentals = (
        Rental.objects
        .filter(status=Rental.Status.ACTIVE)
        .select_related('client')
        .prefetch_related(Prefetch('assignments', queryset=active_assignments_qs, to_attr='active_assignments'))
    )
    active_clients_ids = active_rentals.values_list('client_id', flat=True).distinct()
    active_clients_count = active_clients_ids.count()

    # Батареи у активных клиентов: соберём по предзагруженным назначениям
    batteries_by_client = {r.client_id: [a.battery for a in r.active_assignments] for r in active_rentals}

    # Отдельный запрос для статистики по батареям
    now = timezone.now()
    assignments = RentalBatteryAssignment.objects.filter(
        rental__status=Rental.Status.ACTIVE,
        start_at__lte=now
    ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))

    clients_data = []
    # Баланс считаем по root-группе последних активных ренталов клиента
    latest_by_client = (
        active_rentals.order_by('client_id', '-start_at')
        .distinct('client_id')
        .select_related('client')
    )
    for r in latest_by_client:
        balance_raw = r.group_balance()
        balance_ui = -balance_raw  # для UI: кредит положительный, долг отрицательный
        # Ставка из последней версии активного договора (r уже последний по дате)
        weekly_rate = r.weekly_rate
        clients_data.append({
            'client': r.client,
            'batteries': batteries_by_client.get(r.client_id, []),
            'balance_ui': balance_ui,
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

    # Последние 15 платежей
    latest_payments = Payment.objects.select_related('rental__client', 'created_by').order_by('-date', '-id')[:15]

    # Месячные итоги
    month_names = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    # Собираем суммы по месяцам за всю историю (тип RENT)
    pay_monthly = (
        Payment.objects
        .filter(type=Payment.PaymentType.RENT)
        .values('date__year', 'date__month')
        .annotate(total=Sum('amount'))
        .order_by('date__year', 'date__month')
    )
    monthly3_rows = []
    chart_labels = []
    chart_income = []
    chart_expense = []
    chart_profit = []
    for row in pay_monthly:
        y = row['date__year']
        m = row['date__month']
        label = f"{month_names[m]} {y}"
        income = float(row['total'] or 0)
        expense = 500.0
        profit = round(income - expense, 2)
        # aggregate payments by user for this month
        payments_by_user = (
            Payment.objects
            .filter(date__year=y, date__month=m, type=Payment.PaymentType.RENT)
            .values('created_by__username', 'created_by__first_name', 'created_by__last_name')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        user_totals = []
        for pu in payments_by_user:
            first = pu.get('created_by__first_name') or ''
            last = pu.get('created_by__last_name') or ''
            name = f"{first} {last}".strip() or pu.get('created_by__username')
            user_totals.append({'user': name, 'total': float(pu.get('total') or 0)})
        monthly3_rows.append({
            'label': label,
            'income': income,
            'expense': expense,
            'profit': profit,
            'user_totals': user_totals,
        })
        chart_labels.append(label)
        chart_income.append(income)
        chart_expense.append(expense)
        chart_profit.append(profit)
    monthly3_chart = {
        'labels': chart_labels,
        'income': chart_income,
        'expense': chart_expense,
        'profit': chart_profit,
    }

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
        'monthly3_rows': monthly3_rows,
        'monthly3_chart': monthly3_chart,
    }
    return render(request, 'admin/dashboard.html', context)
