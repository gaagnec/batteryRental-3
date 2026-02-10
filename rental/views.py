from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Sum, Avg
from datetime import timedelta, datetime, time
from django.db import models
from django.db.models import Prefetch, Q
from django.template.response import TemplateResponse
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.conf import settings
import os

from decimal import Decimal

from .models import Client, Rental, Battery, Payment, Repair, RentalBatteryAssignment, FinancePartner, MoneyTransfer, City
from .admin_utils import get_user_city, get_debug_log_path


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
        """Count billable calendar days for half-open interval [start, end).
        If end is exactly at midnight (00:00:00), it is treated as an exclusive boundary
        (the day of end is NOT counted). Otherwise the day of end IS counted.
        This matches the logic in Rental.charges_until().
        """
        start = timezone.localtime(start, tz)
        end = timezone.localtime(end, tz)
        if end <= start:
            return 0
        s_date = start.date()
        e_date = end.date()
        # Half-open: if end is exactly midnight, exclude that calendar day
        if end.hour == 0 and end.minute == 0 and end.second == 0 and end.microsecond == 0:
            e_date = e_date - timedelta(days=1)
        return max((e_date - s_date).days + 1, 0)

    # Посчитаем charges для каждого root без посуточных циклов
    charges_by_root = {}
    for root_id in root_ids:
        total = Decimal(0)
        for v in versions_by_root.get(root_id, []):
            v_start = timezone.localtime(v.start_at, tz)
            v_end = timezone.localtime(v.end_at, tz) if v.end_at else timezone.localtime(now_dt, tz)
            daily_rate = (v.weekly_rate or Decimal(0)) / Decimal(7)
            # Для каждой привязки считаем календарные дни пересечения интервалов (включительно)
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
    from .logging_utils import log_debug, log_error
    
    # Логируем обращение к дашборду
    log_debug(
        "Загрузка дашборда",
        details={
            'user': request.user.username,
            'is_superuser': request.user.is_superuser,
        }
    )
    
    # Определяем город для фильтрации (для модераторов - их город, для владельцев - все их города, для админов - из параметра)
    from .admin_utils import get_user_cities
    filter_city = None
    filter_cities = None
    if not request.user.is_superuser:
        # Модераторы и владельцы - используем get_user_cities для поддержки мультигорода
        filter_cities = get_user_cities(request.user)
        if filter_cities and len(filter_cities) == 1:
            filter_city = filter_cities[0]
    else:
        # Админы могут фильтровать по городу из параметра
        city_id = request.GET.get('city')
        if city_id:
            try:
                filter_city = City.objects.get(id=city_id)
            except City.DoesNotExist:
                pass
    
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
    if filter_city:
        active_rentals = active_rentals.filter(city=filter_city)
    elif filter_cities:
        active_rentals = active_rentals.filter(city__in=filter_cities)
    active_clients_ids = active_rentals.values_list('client_id', flat=True).distinct()
    active_clients_count = active_rentals.values_list('client_id', flat=True).distinct().count()

    # Батареи у активных клиентов: соберём по предзагруженным назначениям
    batteries_by_client = {r.client_id: [a.battery for a in r.active_assignments] for r in active_rentals}

    # Отдельный запрос для статистики по батареям
    now = timezone.now()
    assignments = RentalBatteryAssignment.objects.filter(
        rental__status=Rental.Status.ACTIVE,
        start_at__lte=now
    ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
    if filter_city:
        assignments = assignments.filter(rental__city=filter_city)
    elif filter_cities:
        assignments = assignments.filter(rental__city__in=filter_cities)

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
    batteries_qs = Battery.objects.all()
    if filter_city:
        batteries_qs = batteries_qs.filter(city=filter_city)
    elif filter_cities:
        batteries_qs = batteries_qs.filter(city__in=filter_cities)
    total_batteries = batteries_qs.count()
    rented_now = assignments.values('battery_id').distinct().count()
    repairs_qs = Repair.objects.filter(end_at__isnull=True)
    if filter_city:
        repairs_qs = repairs_qs.filter(battery__city=filter_city)
    elif filter_cities:
        repairs_qs = repairs_qs.filter(battery__city__in=filter_cities)
    in_service = repairs_qs.count()
    available = max(total_batteries - rented_now - in_service, 0)
    battery_stats = {
        'total': total_batteries,
        'rented': rented_now,
        'in_service': in_service,
        'available': available,
    }

    # Последние 16 платежей
    latest_payments_qs = Payment.objects.select_related('rental__client', 'created_by')
    if filter_city:
        latest_payments_qs = latest_payments_qs.filter(city=filter_city)
    elif filter_cities:
        latest_payments_qs = latest_payments_qs.filter(city__in=filter_cities)
    latest_payments = latest_payments_qs.order_by('-date', '-id')[:16]

    # Месячные итоги
    month_names = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    # Собираем суммы по месяцам за всю историю (тип RENT)
    pay_monthly_qs = Payment.objects.filter(type=Payment.PaymentType.RENT)
    if filter_city:
        pay_monthly_qs = pay_monthly_qs.filter(city=filter_city)
    elif filter_cities:
        pay_monthly_qs = pay_monthly_qs.filter(city__in=filter_cities)
    pay_monthly = (
        pay_monthly_qs
        .values('date__year', 'date__month')
        .annotate(total=Sum('amount'))
        .order_by('date__year', 'date__month')
    )
    # За один проход подготовим и разрез по пользователям
    pay_monthly_by_user_qs = Payment.objects.filter(type=Payment.PaymentType.RENT)
    if filter_city:
        pay_monthly_by_user_qs = pay_monthly_by_user_qs.filter(city=filter_city)
    elif filter_cities:
        pay_monthly_by_user_qs = pay_monthly_by_user_qs.filter(city__in=filter_cities)
    pay_monthly_by_user = (
        pay_monthly_by_user_qs
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
    pay_qs = Payment.objects.filter(date__gte=start_date)
    if filter_city:
        pay_qs = pay_qs.filter(city=filter_city)
    elif filter_cities:
        pay_qs = pay_qs.filter(city__in=filter_cities)
    pay_qs = (
        pay_qs
        .values('date')
        .annotate(total=Sum('amount'))
        .order_by('date')
    )
    labels = []
    paid_values = []
    totals_pay = {row['date']: row['total'] for row in pay_qs}

    # Оптимизация: загрузить все назначения, пересекающие окно по календарным дням
    tz = timezone.get_current_timezone()
    window_start = timezone.make_aware(datetime.combine(start_date, time(0, 0)), tz)
    window_end = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=1), time(0, 0)), tz)
    assigns_window = (
        RentalBatteryAssignment.objects
        .filter(start_at__lt=window_end)
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gt=window_start))
        .select_related('rental')
    )
    if filter_city:
        assigns_window = assigns_window.filter(rental__city=filter_city)
    elif filter_cities:
        assigns_window = assigns_window.filter(rental__city__in=filter_cities)
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
        day_start = timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
        day_end = timezone.make_aware(datetime.combine(d + timedelta(days=1), time(0, 0)), tz)
        day_total = Decimal(0)
        for na in norm_assigns:
            if na['a_start'] < day_end and (na['a_end'] is None or na['a_end'] > day_start):
                if na['r_start'] < day_end and (na['r_end'] is None or na['r_end'] > day_start):
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
    )
    if filter_city:
        recent_closed = recent_closed.filter(city=filter_city)
    elif filter_cities:
        recent_closed = recent_closed.filter(city__in=filter_cities)
    recent_closed = recent_closed.order_by('-end_at')[:5]
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
    # Используем ту же дату cutoff, что и на странице financeoverviewproxy2
    cutoff = timezone.datetime(2025, 9, 1).date()
    
    partners = FinancePartner.objects.filter(active=True).select_related('user')
    if filter_city:
        partners = partners.filter(city=filter_city)
    elif filter_cities:
        partners = partners.filter(Q(city__in=filter_cities) | Q(cities__in=filter_cities)).distinct()
    moderators = [p for p in partners if p.role == FinancePartner.Role.MODERATOR]
    
    # Платежи, собранные модераторами (RENT + SOLD)
    payments_by_user_qs = Payment.objects.filter(date__gte=cutoff, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD])
    if filter_city:
        payments_by_user_qs = payments_by_user_qs.filter(city=filter_city)
    elif filter_cities:
        payments_by_user_qs = payments_by_user_qs.filter(city__in=filter_cities)
    payments_by_user = dict(
        payments_by_user_qs
        .values('created_by_id')
        .annotate(total=Sum('amount'))
        .values_list('created_by_id', 'total')
    )
    
    # Переводы от модераторов к владельцам
    outgoing_from_mods_qs = MoneyTransfer.objects.filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER, use_collected=True)
    if filter_city:
        outgoing_from_mods_qs = outgoing_from_mods_qs.filter(from_partner__city=filter_city)
    elif filter_cities:
        outgoing_from_mods_qs = outgoing_from_mods_qs.filter(from_partner__city__in=filter_cities)
    outgoing_from_mods = dict(
        outgoing_from_mods_qs
        .values('from_partner_id')
        .annotate(total=Sum('amount'))
        .values_list('from_partner_id', 'total')
    )
    
    # Определяем период последней завершенной недели
    # Неделя начинается в понедельник и заканчивается в воскресенье
    today = timezone.localdate()
    # Находим понедельник текущей недели
    days_since_monday = today.weekday()  # 0 = понедельник, 6 = воскресенье
    current_week_monday = today - timedelta(days=days_since_monday)
    # Последняя завершенная неделя: с понедельника по воскресенье
    last_week_end = current_week_monday - timedelta(days=1)  # воскресенье прошлой недели
    last_week_start = last_week_end - timedelta(days=6)  # понедельник прошлой недели
    
    # Платежи за последнюю неделю
    payments_last_week_qs = Payment.objects.filter(
        date__gte=last_week_start, 
        date__lte=last_week_end,
        type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
    )
    if filter_city:
        payments_last_week_qs = payments_last_week_qs.filter(city=filter_city)
    elif filter_cities:
        payments_last_week_qs = payments_last_week_qs.filter(city__in=filter_cities)
    payments_last_week_by_user = dict(
        payments_last_week_qs
        .values('created_by_id')
        .annotate(total=Sum('amount'))
        .values_list('created_by_id', 'total')
    )
    
    moderator_debts = []
    for mod in moderators:
        uid = mod.user_id
        pid = mod.id
        
        collected = Decimal(payments_by_user.get(uid, 0))
        transferred = Decimal(outgoing_from_mods.get(pid, 0))
        debt = collected - transferred
        
        # Сумма поступлений за последнюю неделю (без вычета переводов)
        collected_last_week = Decimal(payments_last_week_by_user.get(uid, 0))
        
        moderator_debts.append({
            'partner': mod,
            'collected': collected,
            'transferred': transferred,
            'debt': debt,
            'collected_last_week': collected_last_week,
        })
    
    # История переводов от модераторов к владельцам (последние 10)
    moderator_transfers_recent = (
        MoneyTransfer.objects
        .filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER)
        .select_related('from_partner__user', 'to_partner__user')
    )
    if filter_city:
        moderator_transfers_recent = moderator_transfers_recent.filter(from_partner__city=filter_city)
    elif filter_cities:
        moderator_transfers_recent = moderator_transfers_recent.filter(from_partner__city__in=filter_cities)
    moderator_transfers_recent = moderator_transfers_recent.order_by('-date', '-id')[:10]
    
    # Разбивка по городам (для админов)
    city_breakdown = None
    city_stats_by_city = {}
    if request.user.is_superuser:
        cities = City.objects.filter(active=True)
        today = timezone.localdate()
        last_30_days = today - timedelta(days=30)
        
        for city in cities:
            # Батареи по городу
            city_batteries = Battery.objects.filter(city=city)
            city_batteries_total = city_batteries.count()
            city_batteries_rented = Battery.objects.filter(
                city=city,
                assignments__rental__status=Rental.Status.ACTIVE,
                assignments__start_at__lte=timezone.now()
            ).filter(
                Q(assignments__end_at__isnull=True) | Q(assignments__end_at__gt=timezone.now())
            ).distinct().count()
            city_batteries_available = city_batteries.filter(status=Battery.Status.AVAILABLE).count()
            
            # Активные клиенты по городу
            city_active_clients = Client.objects.filter(
                city=city,
                rentals__status=Rental.Status.ACTIVE
            ).distinct().count()
            
            # Доходы по городу за 30 дней
            city_income_30 = Payment.objects.filter(
                city=city,
                date__gte=last_30_days,
                type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
            ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
            
            city_stats_by_city[city] = {
                'batteries_total': city_batteries_total,
                'batteries_rented': city_batteries_rented,
                'batteries_available': city_batteries_available,
                'active_clients': city_active_clients,
                'income_30': city_income_30,
            }
        
        city_breakdown = sorted(
            [(city, stats) for city, stats in city_stats_by_city.items()],
            key=lambda x: x[1]['income_30'],
            reverse=True
        )
    
    try:
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
            'filter_city': filter_city,
            'city_breakdown': city_breakdown,
            'cities': City.objects.filter(active=True) if request.user.is_superuser else [],
        }
        
        log_debug(
            "Дашборд загружен успешно",
            details={
                'active_clients': active_clients_count,
                'total_batteries': battery_stats['total'],
                'filter_city': str(filter_city) if filter_city else 'все',
            }
        )
        
        return render(request, 'admin/dashboard.html', context)
        
    except Exception as e:
        # Логируем ошибку при рендеринге дашборда
        log_error(
            "Ошибка при загрузке дашборда",
            exception=e,
            user=request.user,
            context={
                'filter_city': str(filter_city) if filter_city else None,
            },
            request=request
        )
        raise  # Пробрасываем ошибку дальше для стандартной обработки Django


@staff_member_required
def load_more_investments(request):
    """HTMX endpoint для подгрузки следующих 10 вложений"""
    from .models import Expense, FinancePartner
    from .logging_utils import log_error, log_warning
    from django.http import HttpResponse
    
    try:
        offset = int(request.GET.get('offset', 10))
        limit = 10
        cutoff = timezone.now().date() - timedelta(days=365)
        
        # Получаем только владельцев
        owner_ids = list(
            FinancePartner.objects
            .filter(is_owner=True)
            .values_list('id', flat=True)
        )
        
        if not owner_ids:
            log_warning(
                "Попытка загрузить инвестиции, но владельцы не найдены",
                user=request.user,
                request=request
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
        
    except ValueError as e:
        # Ошибка парсинга offset
        log_error(
            "Ошибка парсинга параметра offset",
            exception=e,
            user=request.user,
            context={'offset_param': request.GET.get('offset')},
            request=request
        )
        return HttpResponse("Ошибка: некорректный параметр offset", status=400)
        
    except Exception as e:
        # Любая другая ошибка
        log_error(
            "Ошибка при загрузке инвестиций",
            exception=e,
            user=request.user,
            context={
                'offset': request.GET.get('offset'),
                'limit': limit,
            },
            request=request
        )
        return HttpResponse("Ошибка при загрузке данных", status=500)


@staff_member_required
def city_analytics(request):
    """Аналитика по городам с детальной статистикой"""
    # Получаем фильтр по городу
    city_filter = None
    if not request.user.is_superuser:
        city_filter = get_user_city(request.user)
    else:
        city_id = request.GET.get('city')
        if city_id:
            try:
                city_filter = City.objects.get(id=city_id)
            except City.DoesNotExist:
                pass
    
    # Период для анализа
    today = timezone.localdate()
    last_30_days = today - timedelta(days=30)
    last_90_days = today - timedelta(days=90)
    this_month_start = today.replace(day=1)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    
    cities = City.objects.filter(active=True)
    if city_filter:
        cities = cities.filter(id=city_filter.id)
    
    analytics_data = []
    for city in cities:
        # Доходы по городу
        payments_qs = Payment.objects.filter(city=city)
        
        # За 30 дней
        income_30 = payments_qs.filter(
            date__gte=last_30_days,
            type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
        ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
        
        # За этот месяц
        income_this_month = payments_qs.filter(
            date__gte=this_month_start,
            type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
        ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
        
        # За прошлый месяц
        income_last_month = payments_qs.filter(
            date__gte=last_month_start,
            date__lte=last_month_end,
            type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
        ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
        
        # Статистика по батареям
        batteries_total = Battery.objects.filter(city=city).count()
        batteries_rented = Battery.objects.filter(
            city=city,
            assignments__rental__status=Rental.Status.ACTIVE,
            assignments__start_at__lte=timezone.now()
        ).filter(
            Q(assignments__end_at__isnull=True) | Q(assignments__end_at__gt=timezone.now())
        ).distinct().count()
        
        batteries_available = Battery.objects.filter(
            city=city,
            status=Battery.Status.AVAILABLE
        ).count()
        
        # Активные клиенты
        active_clients = Client.objects.filter(
            city=city,
            rentals__status=Rental.Status.ACTIVE
        ).distinct().count()
        
        # Средний чек (средняя сумма платежа)
        avg_payment = payments_qs.filter(
            date__gte=last_30_days,
            type=Payment.PaymentType.RENT
        ).aggregate(avg=Avg('amount'))['avg'] or Decimal(0)
        
        analytics_data.append({
            'city': city,
            'income_30_days': income_30,
            'income_this_month': income_this_month,
            'income_last_month': income_last_month,
            'income_growth': income_this_month - income_last_month if income_last_month > 0 else Decimal(0),
            'income_growth_percent': ((income_this_month - income_last_month) / income_last_month * 100) if income_last_month > 0 else 0,
            'batteries_total': batteries_total,
            'batteries_rented': batteries_rented,
            'batteries_available': batteries_available,
            'batteries_utilization': (batteries_rented / batteries_total * 100) if batteries_total > 0 else 0,
            'active_clients': active_clients,
            'avg_payment': avg_payment,
        })
    
    # Сравнение городов (только для админов)
    city_comparison = None
    if request.user.is_superuser and not city_filter:
        city_comparison = sorted(analytics_data, key=lambda x: x['income_30_days'], reverse=True)
    
    context = {
        'analytics_data': analytics_data,
        'city_comparison': city_comparison,
        'selected_city': city_filter,
        'cities': City.objects.filter(active=True),
    }
    return TemplateResponse(request, 'admin/city_analytics.html', context)


@staff_member_required
def download_debug_log(request):
    """Временный endpoint для скачивания debug лога. Доступен только для администраторов (не модераторов)"""
    from .admin_utils import is_moderator
    
    # Проверяем, что пользователь не модератор
    if is_moderator(request.user):
        return HttpResponse("Доступ запрещен. Эта функция доступна только для администраторов.", status=403)
    
    # Используем функцию для получения пути к лог-файлу
    log_path = get_debug_log_path()
    
    if not log_path.exists():
        return HttpResponse(f"Log file not found. Path: {log_path}. The file will be created when you access the payment form as a moderator.", status=404)
    
    try:
        response = FileResponse(
            open(str(log_path), 'rb'),
            content_type='application/json',
            as_attachment=True,
            filename='debug.log'
        )
        return response
    except Exception as e:
        return HttpResponse(f"Error reading log: {str(e)}", status=500)
