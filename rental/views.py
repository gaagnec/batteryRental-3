from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import timedelta

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
        clients_data.append({
            'client': r.client,
            'batteries': batteries_by_client.get(r.client_id, []),
            'balance': balance,
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

    # Последние 5 платежей
    latest_payments = Payment.objects.select_related('rental__client', 'created_by').order_by('-date', '-id')[:5]

    # Серия платежей за 14 дней
    start_date = timezone.localdate() - timedelta(days=13)
    qs = (
        Payment.objects.filter(date__gte=start_date)
        .values('date')
        .annotate(total=Sum('amount'))
        .order_by('date')
    )
    labels = []
    values = []
    totals = {row['date']: row['total'] for row in qs}
    for i in range(14):
        d = start_date + timedelta(days=i)
        labels.append(d.isoformat())
        values.append(float(totals.get(d, 0) or 0))
    payments_series = {'labels': labels, 'values': values}

    context = {
        'active_clients_count': active_clients_count,
        'clients_data': clients_data,
        'battery_stats': battery_stats,
        'latest_payments': latest_payments,
        'payments_series': payments_series,
    }
    return render(request, 'admin/dashboard.html', context)
