from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import timedelta, datetime, time
from django.db import models
from django.db.models import Prefetch, Q

from decimal import Decimal

from .models import Client, Rental, Battery, Payment, Repair, RentalBatteryAssignment, FinancePartner, MoneyTransfer


def calculate_balances_for_rentals(rentals, tz, now_dt):
    """
    Оптимизированный расчёт балансов для списка договоров.
    Возвращает словари: charges_by_root, paid_by_root, versions_by_root
    """
    root_ids = []
    for r in rentals:
        root_ids.append(r.root_id or r.id)
    root_ids = list(set(root_ids))
    
    if not root_ids:
        return {}, {}, {}
    
    # Версии по этим root + назначенные батареи одним заходом
    versions_qs = (
        Rental.objects
        .filter(root_id__in=root_ids)
        .only('id','root_id','start_at','end_at','weekly_rate','status')
        .prefetch_related('assignments')
    )
    versions_by_root = {}
    for v in versions_qs:
        versions_by_root.setdefault(v.root_id, []).append(v)
    
    # Платежи по root за всё время (тип RENT)
    paid_rows = (
        Payment.objects
        .filter(rental__root_id__in=root_ids, type=Payment.PaymentType.RENT)
        .values('rental__root_id')
        .annotate(total=Sum('amount'))
    )
    paid_by_root = {row['rental__root_id']: (row['total'] or Decimal(0)) for row in paid_rows}
    
    def billable_days_interval(start, end):
        start = timezone.localtime(start, tz)
        end = timezone.localtime(end, tz)
        if end <= start:
            return 0
        days = (end.date() - start.date()).days
        if start.hour < 14 or (start.hour == 14 and start.minute == 0 and start.second == 0):
            days += 1
        if end.hour < 14 or (end.hour == 14 and end.minute == 0 and end.second == 0):
            days -= 1
        return max(days, 0)
    
    # Посчитаем charges для каждого root без посуточных циклов
    charges_by_root = {}
    for root_id in root_ids:
        total = Decimal(0)
        for v in versions_by_root.get(root_id, []):
            v_start = timezone.localtime(v.start_at, tz)
            v_end = timezone.localtime(v.end_at, tz) if v.end_at else timezone.localtime(now_dt, tz)
            daily_rate = (v.weekly_rate or Decimal(0)) / Decimal(7)
            # Для каждой привязки этой версии считаем дни пересечения интервалов (с 14:00 cut-off)
            for a in getattr(v, 'assignments', []).all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else timezone.localtime(now_dt, tz)
                # Пересечение [max(start), min(end)]
                s = max(v_start, a_start)
                e = min(v_end, a_end)
                d = billable_days_interval(s, e)
                if d:
                    total += daily_rate * Decimal(d)
        charges_by_root[root_id] = total
    
    return charges_by_root, paid_by_root, versions_by_root


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
    # Предрассчёт балансов без N+1 и без посуточных циклов
    tz = timezone.get_current_timezone()
    now_dt = timezone.now()
    latest_by_client_list = list(latest_by_client)
    
    # Используем общую функцию для расчёта балансов
    charges_by_root, paid_by_root, versions_by_root = calculate_balances_for_rentals(
        latest_by_client_list, tz, now_dt
    )

    for r in latest_by_client_list:
        root_id = r.root_id or r.id
        charges = charges_by_root.get(root_id, Decimal(0))
        paid = paid_by_root.get(root_id, Decimal(0))
        balance_raw = charges - paid
        balance_ui = -balance_raw  # для UI: кредит положительный, долг отрицательный
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
    # За один проход подготовим и разрез по пользователям
    pay_monthly_by_user = (
        Payment.objects
        .filter(type=Payment.PaymentType.RENT)
        .values('date__year', 'date__month', 'created_by__username', 'created_by__first_name', 'created_by__last_name')
        .annotate(total=Sum('amount'))
        .order_by('date__year', 'date__month', '-total')
    )
    users_map = {}
    for pu in pay_monthly_by_user:
        key = (pu['date__year'], pu['date__month'])
        first = pu.get('created_by__first_name') or ''
        last = pu.get('created_by__last_name') or ''
        name = f"{first} {last}".strip() or pu.get('created_by__username')
        users_map.setdefault(key, []).append({'user': name, 'total': float(pu.get('total') or 0)})

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
        user_totals = users_map.get((y, m), [])
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

    # Оптимизация: загрузить все назначения, пересекающие окно, одним запросом
    tz = timezone.get_current_timezone()
    window_start_anchor = timezone.make_aware(datetime.combine(start_date, time(14, 0)), tz)
    window_end_anchor = timezone.make_aware(datetime.combine(timezone.localdate(), time(14, 0)), tz)
    assigns_window = (
        RentalBatteryAssignment.objects
        .filter(start_at__lte=window_end_anchor)
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=window_start_anchor))
        .select_related('rental')
    )
    # Подготовим список назначений с нормализованными датами
    norm_assigns = []
    now_tz = timezone.localtime(timezone.now(), tz)
    for a in assigns_window:
        r = a.rental
        # Берём только активные ренты, чтобы не фильтровать по каждому дню
        if r.status != Rental.Status.ACTIVE:
            continue
        a_start = timezone.localtime(a.start_at, tz)
        a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
        r_start = timezone.localtime(r.start_at, tz)
        r_end = timezone.localtime(r.end_at, tz) if r.end_at else None
        norm_assigns.append({
            'a_start': a_start,
            'a_end': a_end,
            'r_start': r_start,
            'r_end': r_end,
            'daily_rate': (r.weekly_rate or Decimal(0)) / Decimal(7),
        })

    charges_values = []
    for i in range(window_days):
        d = start_date + timedelta(days=i)
        labels.append(d.isoformat())
        paid_values.append(float(totals_pay.get(d, 0) or 0))
        anchor = timezone.make_aware(datetime.combine(d, time(14, 0)), tz)
        day_total = Decimal(0)
        for na in norm_assigns:
            if na['a_start'] <= anchor and (na['a_end'] is None or na['a_end'] > anchor):
                if na['r_start'] <= anchor and (na['r_end'] is None or na['r_end'] > anchor):
                    day_total += na['daily_rate']
        charges_values.append(float(day_total))

    payments_series = {'labels': labels, 'values': paid_values}
    charges_series = {'labels': labels, 'values': charges_values}

    # Топ должников: по текущему балансу, берём 5
    # Используем уже рассчитанные балансы из clients_data вместо N+1 запросов
    debtors = []
    overall_debt = Decimal(0)
    for cd in clients_data:
        # balance_ui отображает кредит клиента как положительное, долг как отрицательное
        # balance_raw = charges - paid, поэтому нужно инвертировать
        balance_raw = -cd['balance_ui']
        if balance_raw > 0:  # Клиент должен нам
            debtors.append((str(cd['client']), float(balance_raw)))
            overall_debt += balance_raw
    debtors.sort(key=lambda x: x[1], reverse=True)
    debtors = debtors[:5]
    top_debtors = {
        'names': [name for name, _ in debtors],
        'values': [val for _, val in debtors]
    }

    total_paid_30 = float(sum(paid_values))
    total_charged_30 = float(sum(charges_values))

    # Недавно закрытые клиенты (по последним закрытым договорам)
    recent_closed = (
        Rental.objects
        .filter(status=Rental.Status.CLOSED, end_at__isnull=False)
        .select_related('client')
        .order_by('-end_at')[:5]
    )
    recent_closed_list = list(recent_closed)
    
    # Используем общую функцию для расчёта балансов закрытых клиентов
    closed_charges_by_root, closed_paid_by_root, closed_versions_by_root = calculate_balances_for_rentals(
        recent_closed_list, tz, now_dt
    )
    
    closed_clients_data = []
    for r in recent_closed_list:
        root_id = r.root_id or r.id
        charges = closed_charges_by_root.get(root_id, Decimal(0))
        paid = closed_paid_by_root.get(root_id, Decimal(0))
        balance_raw = charges - paid
        balance_ui = -balance_raw
        closed_clients_data.append({
            'client': r.client,
            'batteries': [],
            'balance_ui': balance_ui,
            'weekly_rate': r.weekly_rate,
        })

    # Расчет долгов модераторов для блока "Взаиморасчеты"
    cutoff = timezone.localdate() - timedelta(days=365)
    
    partners = FinancePartner.objects.filter(active=True).select_related('user')
    moderators = [p for p in partners if p.role == FinancePartner.Role.MODERATOR]
    
    # Платежи, собранные модераторами (RENT + SOLD)
    payments_by_user = dict(
        Payment.objects
        .filter(date__gte=cutoff, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD])
        .values('created_by_id')
        .annotate(total=Sum('amount'))
        .values_list('created_by_id', 'total')
    )
    
    # Переводы от модераторов к владельцам
    outgoing_from_mods = dict(
        MoneyTransfer.objects
        .filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER, use_collected=True)
        .values('from_partner_id')
        .annotate(total=Sum('amount'))
        .values_list('from_partner_id', 'total')
    )
    
    moderator_debts = []
    for mod in moderators:
        uid = mod.user_id
        pid = mod.id
        
        collected = Decimal(payments_by_user.get(uid, 0))
        transferred = Decimal(outgoing_from_mods.get(pid, 0))
        debt = collected - transferred
        
        moderator_debts.append({
            'partner': mod,
            'collected': collected,
            'transferred': transferred,
            'debt': debt,
        })
    
    # История переводов от модераторов к владельцам (последние 10)
    moderator_transfers_recent = (
        MoneyTransfer.objects
        .filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER)
        .select_related('from_partner__user', 'to_partner__user')
        .order_by('-date', '-id')[:10]
    )
    
    context = {
        'active_clients_count': active_clients_count,
        'clients_data': clients_data,
        'closed_clients_data': closed_clients_data,
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
        'moderator_debts': moderator_debts,
        'moderator_transfers_recent': moderator_transfers_recent,
    }
    return render(request, 'admin/dashboard.html', context)


@staff_member_required
def load_more_investments(request):
    """HTMX endpoint для подгрузки следующих 10 вложений"""
    from .models import Expense, FinancePartner
    
    offset = int(request.GET.get('offset', 10))
    limit = 10
    cutoff = timezone.now().date() - timedelta(days=365)
    
    # Получаем только владельцев
    owner_ids = list(
        FinancePartner.objects
        .filter(is_owner=True)
        .values_list('id', flat=True)
    )
    
    investments = (
        Expense.objects
        .filter(
            date__gte=cutoff,
            payment_type__in=[Expense.PaymentType.PURCHASE, Expense.PaymentType.DEPOSIT],
            paid_by_partner_id__in=owner_ids
        )
        .select_related('paid_by_partner__user', 'category')
        .order_by('-date', '-id')[offset:offset + limit]
    )
    
    investments_list = list(investments)
    has_more = len(investments_list) == limit
    
    return render(request, 'admin/partials/investments_rows.html', {
        'investments_recent': investments_list,
        'offset': offset + limit,
        'has_more': has_more,
    })
