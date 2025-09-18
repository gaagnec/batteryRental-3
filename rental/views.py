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
    active_rentals_qs = (
        Rental.objects
        .filter(status=Rental.Status.ACTIVE)
        .select_related('client')
        .prefetch_related(Prefetch('assignments', queryset=active_assignments_qs, to_attr='active_assignments'))
    )
    active_clients_ids = active_rentals_qs.values_list('client_id', flat=True).distinct()
    active_clients_count = active_clients_ids.count()

    # Материализуем один раз
    active_rentals = list(active_rentals_qs)

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
    # Счёт по месяцам и по сотруднику за один проход
    pay_monthly = (
        Payment.objects
        .filter(type=Payment.PaymentType.RENT)
        .values('date__year', 'date__month')
        .annotate(total=Sum('amount'))
        .order_by('date__year', 'date__month')
    )
    pay_by_user_month = (
        Payment.objects
        .filter(type=Payment.PaymentType.RENT)
        .values('date__year', 'date__month', 'created_by__username', 'created_by__first_name', 'created_by__last_name')
        .annotate(total=Sum('amount'))
    )
    # Группируем pay_by_user_month в память
    from collections import defaultdict
    by_month_users = defaultdict(list)
    for pu in pay_by_user_month:
        key = (pu['date__year'], pu['date__month'])
        first = pu.get('created_by__first_name') or ''
        last = pu.get('created_by__last_name') or ''
        name = f"{first} {last}".strip() or pu.get('created_by__username')
        by_month_users[key].append({'user': name, 'total': float(pu.get('total') or 0)})
    # сортируем пользователей по сумме по убыванию для каждого месяца
    for key in by_month_users:
        by_month_users[key].sort(key=lambda x: x['total'], reverse=True)

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
        user_totals = by_month_users.get((y, m), [])
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

    # Начисления в день считаем за один проход: вытащим все назначения за окно и разложим по дням в памяти
    charges_values = []
    tz = timezone.get_current_timezone()
    # Загрузим все назначения, которые пересекают окно
    window_start_dt = timezone.make_aware(datetime.combine(start_date, time(0, 0)), tz)
    window_end_dt = timezone.make_aware(datetime.combine(start_date + timedelta(days=window_days), time(23, 59, 59)), tz)
    assigns = (
        RentalBatteryAssignment.objects
        .filter(start_at__lte=window_end_dt)
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=window_start_dt))
        .select_related('rental')
    )
    # Предподсчёт дневной ставки по ренталу
    daily_rate_by_rental = {}
    for a in assigns:
        r = a.rental
        if r_id := getattr(r, 'id', None):
            if r_id not in daily_rate_by_rental:
                daily_rate_by_rental[r_id] = (r.status == Rental.Status.ACTIVE, (r.weekly_rate or Decimal(0)) / Decimal(7), r.start_at, r.end_at)
    # Для каждого дня считаем сумму
    for i in range(window_days):
        d = start_date + timedelta(days=i)
        labels.append(d.isoformat())
        paid_values.append(float(totals_pay.get(d, 0) or 0))
        anchor = timezone.make_aware(datetime.combine(d, time(14, 0)), tz)
        day_total = Decimal(0)
        for a in assigns:
            r = a.rental
            active, drate, r_start, r_end = daily_rate_by_rental.get(r.id, (False, Decimal(0), None, None))
            if not active:
                continue
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            r_start_l = timezone.localtime(r_start, tz)
            r_end_l = timezone.localtime(r_end, tz) if r_end else None
            if a_start <= anchor and (a_end is None or a_end > anchor) and r_start_l <= anchor and (r_end_l is None or r_end_l > anchor):
                day_total += drate
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
