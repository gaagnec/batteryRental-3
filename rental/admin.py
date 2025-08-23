from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.core.exceptions import ValidationError
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils import timezone
from django.template.response import TemplateResponse
from django.forms import inlineformset_factory, BaseInlineFormSet
from decimal import Decimal
from django.utils.safestring import mark_safe
from datetime import datetime, time, timedelta

# Register custom template filters
import rental.templatetags.custom_filters

from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Client, Battery, Rental, RentalBatteryAssignment,
    Payment, ExpenseCategory, Expense, Repair, BatteryStatusLog
)


class ActiveRentalFilter(admin.SimpleListFilter):
    title = "Активный договор"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return (
            ("1", "С активным"),
            ("0", "Без активного"),
        )

    def queryset(self, request, queryset):
        from django.db.models import Exists, OuterRef, Q
        now = timezone.now()
        active_qs = Rental.objects.filter(client=OuterRef("pk")).filter(
            status=Rental.Status.ACTIVE
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
        queryset = queryset.annotate(has_active=Exists(active_qs))
        if self.value() == "1":
            return queryset.filter(has_active=True)
        if self.value() == "0":
            return queryset.filter(has_active=False)
        return queryset


@admin.register(Client)
class ClientAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "phone", "pesel", "created_at", "has_active")
    list_filter = (ActiveRentalFilter,)
    search_fields = ("name", "phone", "pesel")

    def has_active(self, obj):
        return getattr(obj, "has_active", False)
    has_active.boolean = True
    has_active.short_description = "Активный договор"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        client = self.get_object(request, object_id)
        if not client:
            return super().change_view(request, object_id, form_url, extra_context)

        # Получаем все root-группы договоров клиента
        root_rentals = client.rentals.filter(parent__isnull=True).order_by("contract_code")

        # Собираем данные для шаблона
        rental_data = []
        now = timezone.now()
        for root in root_rentals:
            versions = root.group_versions()
            start = versions.first().start_at if versions.exists() else None
            end = versions.last().end_at if versions.exists() else None
            days_total = (end or now) - (start or now)
            days_total = days_total.days if days_total else 0
            billable_days = sum(v.billable_days() for v in versions)
            charges = root.group_charges_until(now)
            paid = root.group_paid_total()
            balance = (paid or Decimal(0)) - (charges or Decimal(0))
            deposit = root.group_deposit_total()
            # Определяем цветовую метку баланса (зелёный, если не должен)
            if (charges or 0) == 0 and (paid or 0) == 0:
                color = 'gray'
            elif balance >= 0:
                color = 'green'
            elif deposit and (balance + deposit) >= 0:
                color = 'yellow'
            else:
                color = 'red'
            rental_data.append({
                "contract_code": root.contract_code,
                "version_range": f"v1–v{versions.count()}",
                "start": start,
                "end": end,
                "days_total": days_total,
                "billable_days": billable_days,
                "charges": charges,
                "paid": paid,
                "balance": balance,
                "deposit": deposit,
                "color": color,
                "url": reverse("admin:rental_rental_change", args=[root.pk]),
            })

        # Платежи по всем договорам клиента
        payments = Payment.objects.filter(rental__root__in=root_rentals).order_by("date")

        if extra_context is None:
            extra_context = {}
        extra_context["rental_data"] = rental_data
        extra_context["payments"] = payments

        return super().change_view(request, object_id, form_url, extra_context)

    list_filter = (ActiveRentalFilter,)

    class Media:
        js = [
            "https://unpkg.com/htmx.org@1.9.2",
            "https://unpkg.com/htmx.org@1.9.2/dist/ext/morphdom-swap.umd.js",
        ]

    def balance_badge(self, obj):
        # Суммарный баланс по всем root-догорам клиента: Оплатил - Должен
        roots = obj.rentals.filter(parent__isnull=True)
        from decimal import Decimal
        charges = Decimal(0)
        paid = Decimal(0)
        deposit = Decimal(0)
        now = timezone.now()
        for r in roots:
            charges += r.group_charges_until(now)
            paid += r.group_paid_total()
            deposit += r.group_deposit_total()
        balance = paid - charges
        color = "secondary"
        if charges == 0 and paid == 0:
            color = "secondary"
        elif balance >= 0:
            color = "success"
        elif (balance + deposit) >= 0:
            color = "warning"
        else:
            color = "danger"
        formatted = f"{balance:.2f}"
        return format_html('<span class="badge badge-balance bg-{}">{}</span>', color, formatted)
    balance_badge.short_description = "Баланс"

    def changelist_view(self, request, extra_context=None):
        self.list_filter = (ActiveRentalFilter,)
        if getattr(request, "htmx", False):
            # Для HTMX отдаём только таблицу результатов
            self.list_display = ("id", "name", "phone", "pesel", "created_at", "has_active", "balance_badge")
            response = super().changelist_view(request, extra_context)
            # Заменяем шаблон на частичный список результатов, чтобы не дублировать шапку
            try:
                response.template_name = 'admin/change_list_results.html'
            except Exception:
                pass
            return response
        # Не-HTMX: обычная страница
        self.list_display = ("id", "name", "phone", "pesel", "created_at", "balance_badge")
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        from django.db.models import Exists, OuterRef, Q
        now = timezone.now()
        active_qs = Rental.objects.filter(client=OuterRef("pk")).filter(
            status=Rental.Status.ACTIVE
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
        qs = qs.annotate(has_active=Exists(active_qs))
        return qs


@admin.register(Battery)
class BatteryAdmin(SimpleHistoryAdmin):
    # Убираем тяжёлые колонки roi_progress из списка, возвращаем в detail
    list_display = ("id", "short_code", "usage_now", "serial_number", "cost_price", "created_at")
    search_fields = ("short_code", "serial_number")

    def usage_now(self, obj):
        # Активные договоры сейчас, где батарея назначена
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        assignments = obj.assignments.select_related('rental__client').all()
        active_roots = []
        for a in assignments:
            start = timezone.localtime(a.start_at, tz)
            end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if start <= now and (end is None or end > now):
                root = a.rental.root if hasattr(a.rental, 'root') and a.rental.root_id else a.rental
                active_roots.append(root)
        # Уникальные root договоры
        uniq = []
        seen = set()
        for r in active_roots:
            if r.pk not in seen:
                uniq.append(r)
                seen.add(r.pk)
        parts = []
        for r in uniq:
            client_link = format_html('<a href="{}" style="color:#000; text-decoration:none;">{}</a>', reverse('admin:rental_client_change', args=[r.client_id]), r.client.name)
            rental_link = format_html('<a href="{}" style="color:#000; text-decoration:none;">{}</a>', reverse('admin:rental_rental_change', args=[r.pk]), r.contract_code)
            parts.append(format_html('[{}, {}]', client_link, rental_link))
        count = len(uniq)
        # Цвет + инлайн-стиль как fallback, если Bootstrap не подгрузился
        bg = 'secondary'
        bg_color = '#6c757d'
        if count == 1:
            bg = 'success'
            bg_color = '#198754'
        elif count > 1:
            bg = 'warning'
            bg_color = '#ffc107'
        content = format_html(', '.join(['{}'] * len(parts)), *parts) if parts else '-'
        return format_html('<span class="badge bg-{}" style="background-color:{}; color:#000;">{}</span>', bg, bg_color, content)
    usage_now.short_description = "В аренде"

    def roi_progress(self, obj):
        # Окупаемость по фактическим оплатам: распределяем оплаты по доле "нагрузки" батареи
        from decimal import Decimal, InvalidOperation
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        # Группируем по root-договорам, где батарея была назначена
        by_root_share = {}
        days_total = 0
        # Сначала соберём версии по root для быстрого доступа
        roots = {}
        for a in obj.assignments.select_related('rental').all():
            root = a.rental.root if getattr(a.rental, 'root_id', None) else a.rental
            roots.setdefault(root.pk, root)
        # Для каждого root считаем долю батареи (battery_share) и дни аренды
        for root in roots.values():
            versions = list(root.group_versions())
            # Precompute version windows with daily_rate
            v_windows = []
            for v in versions:
                v_start = timezone.localtime(v.start_at, tz)
                v_end = timezone.localtime(v.end_at, tz) if v.end_at else now
                v_windows.append((v_start, v_end, (v.weekly_rate or Decimal(0)) / Decimal(7)))
            battery_share = Decimal(0)
            # Соберём интервалы назначений этой батареи внутри данного root
            for a in obj.assignments.filter(rental__root=root).all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else now
                # Идём по дням, считаем только те дни, когда есть активная версия
                d = a_start.date()
                end_date = a_end.date()
                while d <= end_date:
                    anchor = timezone.make_aware(datetime.combine(d, time(14, 0)), tz)
                    # Найти активную версию на этот anchor
                    rate = None
                    for v_start, v_end, v_rate in v_windows:
                        if v_start <= anchor and anchor < v_end and anchor <= now:
                            rate = v_rate
                            break
                    if rate is not None:
                        battery_share += rate
                    d += timedelta(days=1)
            # Считаем дни аренды без привязки к активной версии
            days_total = 0
            for a in obj.assignments.all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else now
                d = a_start.date()
                end_date = a_end.date()
                while d <= end_date:
                    days_total += 1
                    d += timedelta(days=1)
            # Общая сумма начислений по группе
            group_charges = root.group_charges_until(until=now) or Decimal(0)
            group_paid = root.group_paid_total() or Decimal(0)
            if group_charges > 0 and battery_share > 0:
                by_root_share[root.pk] = (battery_share, group_charges, group_paid)
        # Распределяем оплаты пропорционально
        allocated = Decimal(0)
        for battery_share, group_charges, group_paid in by_root_share.values():
            try:
                allocated += (battery_share / group_charges) * group_paid
            except (InvalidOperation, ZeroDivisionError):
                continue
        cost = obj.cost_price or Decimal(0)
        try:
            pct = int(round((allocated / cost) * 100)) if cost else 0
        except Exception:
            pct = 0
        # Цвета прогресса
        bar_class = 'bg-danger'
        bar_style = ''
        if pct >= 100:
            bar_class = 'bg-success'
        elif pct >= 75:
            bar_class = ''
            bar_style = 'background-color: orange;'
        elif pct >= 25:
            bar_class = 'bg-warning'
        width = min(max(pct, 0), 150)
        # Внутри бара показываем значение процента
        return format_html(
            '<div>'
            '<div class="progress" style="width:160px; height: 1rem;">'
            '<div class="progress-bar {}" role="progressbar" style="width: {}%; {};" aria-valuenow="{}" aria-valuemin="0" aria-valuemax="150">{}%</div>'
            '</div>'
            '<div style="font-size: 0.8rem; color: #666;">Дней в аренде: {}</div>'
            '</div>',
            bar_class, width, bar_style, pct, pct, days_total
        )
    roi_progress.short_description = "Окупаемость"



class RentalBatteryAssignmentForm(forms.ModelForm):
    class Meta:
        model = RentalBatteryAssignment
        fields = "__all__"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # поле видно, но не обязательно; если оставить пустым при создании — подставим старт договора
        if 'start_at' in self.fields:
            self.fields['start_at'].required = False
    def clean(self):
        cd = super().clean()
        start = cd.get('start_at')
        if not start:
            rental = getattr(self.instance, 'rental', None)
            if rental and getattr(rental, 'start_at', None):
                cd['start_at'] = rental.start_at
                self.cleaned_data['start_at'] = rental.start_at
        return cd

class RentalBatteryAssignmentInline(admin.TabularInline):
    model = RentalBatteryAssignment
    form = RentalBatteryAssignmentForm
    extra = 0
    readonly_fields = ("created_by", "updated_by")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class NewVersionActionForm(ActionForm):
    new_weekly_rate = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2, label="Новая недельная ставка (PLN)"
    )
    new_start_at = forms.DateTimeField(required=False, label="Начало новой версии", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    free_days = forms.IntegerField(required=False, min_value=0, label="Бесплатные дни")
    payment_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма оплаты")
    payment_method = forms.ChoiceField(required=False, choices=[('cash','Наличные'),('blik','BLIK'),('revolut','Revolut'),('other','Другое')], label="Метод оплаты")
    payment_note = forms.CharField(required=False, label="Примечание к оплате")
    deposit_return_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма возврата депозита")
    deposit_return_note = forms.CharField(required=False, label="Примечание к возврату депозита")


@admin.register(Rental)
class RentalAdmin(SimpleHistoryAdmin):
    def changelist_view(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        from .models import Client
        extra_context['clients'] = Client.objects.all().order_by('name')
        return super().changelist_view(request, extra_context=extra_context)

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList

        class CustomChangeList(ChangeList):
            def get_results(self, request):
                super().get_results(request)
                # Приглушить строки с статусом modified или closed
                for result in self.result_list:
                    if hasattr(result, 'status') and result.status in [result.Status.MODIFIED, result.Status.CLOSED]:
                        result.row_class = 'opacity-80'

        return CustomChangeList

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Предзагрузить связанные assignments, чтобы избежать N+1
        from django.db.models import Count
        qs = qs.prefetch_related('assignments', 'assignments__battery')
        qs = qs.annotate(assignments_count=Count('assignments'))
        # Добавить row_class для приглушения строк
        for obj in qs:
            if obj.status in [obj.Status.MODIFIED, obj.Status.CLOSED]:
                obj.row_class = 'opacity-80'
            else:
                obj.row_class = ''
        return qs

    class Media:
        css = {
            'all': ('admin/css/custom.css',)
        }

    list_display = (
        "id", "contract_code", "version", "client", "start_at", "end_at",
        "weekly_rate", "status", "assigned_batteries_short",
    )
    list_filter = ("status",)
    list_per_page = 25  # Ограничение записей на странице для ускорения отображения


    search_fields = ("client__name", "contract_code")
    inlines = [RentalBatteryAssignmentInline, PaymentInline]

    readonly_fields = ("group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now", "created_by", "updated_by")
    def batteries_count_now(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        count = 0
        batteries = []
        for a in obj.assignments.all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                count += 1
                batteries.append(a.battery.short_code)
        obj._batteries_list = batteries
        return count

    def assigned_batteries_short(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        codes = []
        for a in obj.assignments.select_related('battery').all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                codes.append(a.battery.short_code)
        if obj.status in [obj.Status.ACTIVE, obj.Status.MODIFIED]:
            if codes:
                return format_html(' '.join(['<span class="badge bg-secondary me-1">{}</span>'] * len(codes)), *codes)
            else:
                return mark_safe('<span class="text-muted">—</span>')
        if obj.status == obj.Status.CLOSED:
            return mark_safe('<span class="text-muted">—</span>')
        return ''

    assigned_batteries_short.short_description = "Батареи"


    action_form = NewVersionActionForm
    actions = ["make_new_version", "close_with_deposit"]
    
    def get_list_display(self, request):
        base = list(super().get_list_display(request)) if hasattr(super(), 'get_list_display') else list(self.list_display)
        # вставим количество батарей рядом с агрегатами
        if "batteries_count_now" not in base:
            base = list(self.list_display)
        return tuple(base)

    def fmt_pln(self, value):
        try:
            return f"{value:.2f} PLN"
        except Exception:
            return value

    def assigned_batteries_short(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        codes = []
        for a in obj.assignments.select_related('battery').all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                codes.append(a.battery.short_code)
        if obj.status in [obj.Status.ACTIVE, obj.Status.MODIFIED]:
            if codes:
                # badges for active or modified
                return format_html(' '.join(['<span class="badge bg-secondary me-1">{}</span>'] * len(codes)), *codes)
            else:
                return mark_safe('<span class="text-muted">—</span>')
        if obj.status == obj.Status.CLOSED:
            return mark_safe('<span class="text-muted">—</span>')
        return ''
    assigned_batteries_short.short_description = "Батареи"

    def group_charges_now(self, obj):
        return self.fmt_pln(obj.group_charges_until(until=timezone.now()))
    group_charges_now.short_description = "Начислено"

    def group_paid_total(self, obj):
        return self.fmt_pln(obj.group_paid_total())
    group_paid_total.short_description = "Оплачено"

    def group_deposit_total(self, obj):
        return self.fmt_pln(obj.group_deposit_total())
    group_deposit_total.short_description = "Депозит"

    def group_balance_now(self, obj):
        now = timezone.now()
        charges = obj.group_charges_until(until=now)
        paid = obj.group_paid_total()
        return self.fmt_pln(paid - charges)

    group_balance_now.short_description = "Баланс"

    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, 'created_by_id', None):
            obj.created_by = request.user
        obj.updated_by = request.user
        # проставляем имена для Supabase
        if hasattr(obj, 'created_by_name') and obj.created_by and not obj.created_by_name:
            obj.created_by_name = request.user.get_full_name() or request.user.username or request.user.email
        if hasattr(obj, 'updated_by_name'):
            obj.updated_by_name = request.user.get_full_name() or request.user.username or request.user.email
        super().save_model(request, obj, form, change)
        
        # Отобразить человеку сразу обновленные агрегаты
        self.message_user(request, f"Баланс: {self.group_balance_now(obj)}; Начислено: {self.group_charges_now(obj)}; Оплачено: {self.group_paid_total(obj)}; Депозит: {self.group_deposit_total(obj)}")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            # Default start_at to rental.start_at if not provided in inline
            if hasattr(inst, "start_at") and not inst.start_at:
                parent_start = getattr(form.instance, "start_at", None)
                if parent_start:
                    inst.start_at = parent_start
            if hasattr(inst, "created_by") and not inst.pk:
                inst.created_by = request.user
            if hasattr(inst, "updated_by"):
                inst.updated_by = request.user
            inst.save()
        formset.save_m2m()

    def make_new_version(self, request, queryset):
        count = 0
        # Получаем ставку из формы действий
        rate_str = request.POST.get("new_weekly_rate")
        new_rate = None
        # Получаем дату и время из формы (новое поле)
        new_start = None
        if request.POST.get("new_start_at"):
            try:
                # получаем datetime-local => 'YYYY-MM-DDTHH:MM'
                new_start = timezone.datetime.fromisoformat(request.POST.get("new_start_at").replace('T', ' '))
                if timezone.is_naive(new_start):
                    new_start = timezone.make_aware(new_start, timezone.get_current_timezone())
            except Exception:
                new_start = None
        # Получаем бесплатные дни
        free_days_str = request.POST.get("free_days")
        free_days = 0
        if free_days_str:
            try:
                free_days = int(free_days_str)
            except Exception:
                free_days = 0
        if rate_str:
            try:
                new_rate = Decimal(rate_str)
            except Exception:
                new_rate = None
        for rental in queryset:
            root = rental.root or rental
            now = new_start or timezone.now()
            # Закрываем старую версию
            if not rental.end_at or rental.end_at > now:
                rental.end_at = now
            rental.status = Rental.Status.MODIFIED
            rental.save()
            if free_days > 0:
                # Создаем версию с бесплатными днями
                free_start = now
                free_end = free_start + timezone.timedelta(days=free_days)
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = rental.version + 1
                free_version = Rental(
                    client=rental.client,
                    start_at=free_start,
                    end_at=free_end,
                    weekly_rate=Decimal(0),
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=rental,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                free_version.created_by = request.user
                free_version.updated_by = request.user
                free_version.save()
                # Создаем следующую версию после бесплатных дней
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = free_version.version + 1
                next_start = free_end
                new_rental = Rental(
                    client=rental.client,
                    start_at=next_start,
                    weekly_rate=new_rate if new_rate is not None else rental.weekly_rate,
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=free_version,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                new_rental.created_by = request.user
                new_rental.updated_by = request.user
                new_rental.save()
                # Переносим активные назначения батарей на новую версию, закрыв их в старой
                tz = timezone.get_current_timezone()
                for a in rental.assignments.all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_end is None or a_end > now:
                        # закрываем в старой версии
                        if a_end is None or a_end > now:
                            a.end_at = now
                            a.updated_by = request.user
                            a.save(update_fields=["end_at", "updated_by"])
                        # создаем продолжение в новой версии, начиная сейчас
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery=a.battery,
                            start_at=now,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                count += 2
            else:
                # Создаем новую версию без бесплатных дней
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = rental.version + 1
                new_rental = Rental(
                    client=rental.client,
                    start_at=now,
                    weekly_rate=new_rate if new_rate is not None else rental.weekly_rate,
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=rental,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                new_rental.created_by = request.user
                new_rental.updated_by = request.user
                new_rental.save()
                # Переносим активные назначения батарей на новую версию, закрыв их в старой
                tz = timezone.get_current_timezone()
                for a in rental.assignments.all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_end is None or a_end > now:
                        # закрываем в старой версии
                        if a_end is None or a_end > now:
                            a.end_at = now
                            a.updated_by = request.user
                            a.save(update_fields=["end_at", "updated_by"])
                        # создаем продолжение в новой версии, начиная сейчас
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery=a.battery,
                            start_at=now,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                count += 1
        self.message_user(request, f"Создано новых версий: {count}; активные батареи перенесены")
    make_new_version.short_description = "Создать новую версию (начало с даты и времени, с переносом батарей)"

    # Пользовательский admin-view для изменения состава батарей
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/change-batteries/',
                self.admin_site.admin_view(self.change_batteries_view),
                name='rental_rental_change_batteries',
            )
        ]
        return custom + urls

    def change_batteries_view(self, request, pk):
        rental = Rental.objects.get(pk=pk)
        AssignmentFormSet = inlineformset_factory(
            Rental,
            RentalBatteryAssignment,
            form=RentalBatteryAssignmentForm,
            extra=0,
            can_delete=True,
            fields=('battery', 'start_at', 'end_at'),
        )
        if request.method == 'POST':
            formset = AssignmentFormSet(request.POST, instance=rental)
            if formset.is_valid():
                instances = formset.save(commit=False)
                # Валидация: после сохранения должно остаться >=1 активное назначение сейчас или в будущем
                for inst in instances:
                    if not getattr(inst, 'created_by_id', None):
                        inst.created_by = request.user
                    inst.updated_by = request.user
                    inst.save()
                for obj in formset.deleted_objects:
                    obj.delete()
                # Проверка минимума одной батареи ("на сейчас")
                tz = timezone.get_current_timezone()
                now = timezone.now()
                active = 0
                for a in rental.assignments.select_related('battery').all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_start <= now and (a_end is None or a_end > now):
                        active += 1
                if active <= 0:
                    messages.error(request, "Должна быть назначена минимум одна батарея на текущий момент")
                else:
                    messages.success(request, "Состав батарей обновлён")
                    return TemplateResponse(request, 'admin/rental/change_batteries_done.html', {'rental': rental})
            else:
                messages.error(request, "Исправьте ошибки в форме")
        else:
            formset = AssignmentFormSet(instance=rental)
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            rental=rental,
            title=f"Изменение батарей: договор {rental.contract_code} v{rental.version}",
            formset=formset,
        )
        return TemplateResponse(request, 'admin/rental/change_batteries.html', context)

    def close_with_deposit(self, request, queryset):
        closed = 0
        # Опционально: принять оплату (аренда) сразу из формы действия
        amt = request.POST.get("payment_amount")
        mth = request.POST.get("payment_method")
        note = request.POST.get("payment_note")
        for rental in queryset:
            root = rental.root or rental
            now = timezone.now()
            for v in Rental.objects.filter(root=root, status=Rental.Status.ACTIVE):
                if not v.end_at or v.end_at > now:
                    v.end_at = now
                v.status = Rental.Status.CLOSED
                v.save()
            balance = root.group_balance(until=now)
            deposit_left = root.group_deposit_total()
            applied = Decimal(0)
            if balance > 0 and deposit_left > 0:
                applied = min(balance, deposit_left)
                Payment.objects.create(
                    rental=root,
                    amount=-applied,
                    date=timezone.localdate(),
                    type=Payment.PaymentType.ADJUSTMENT,
                    method=Payment.Method.OTHER,
                    note="Зачёт депозита при закрытии",
                    created_by=request.user,
                    updated_by=request.user,
                )
                balance -= applied
                deposit_left -= applied
            if deposit_left > 0:
                Payment.objects.create(
                    rental=root,
                    amount=deposit_left,
                    date=timezone.localdate(),
                    type=Payment.PaymentType.RETURN_DEPOSIT,
                    method=Payment.Method.OTHER,
                    note="Возврат остатка депозита",
                    created_by=request.user,
                    updated_by=request.user,
                )
            if amt:
                try:
                    amt_dec = Decimal(amt)
                    if amt_dec != 0:
                        Payment.objects.create(
                            rental=root,
                            amount=amt_dec,
                            date=timezone.localdate(),
                            type=Payment.PaymentType.RENT,
                            method=mth or Payment.Method.OTHER,
                            note=note or "",
                            created_by=request.user,
                            updated_by=request.user,
                        )
                except Exception:
                    pass
            closed += 1
        self.message_user(request, f"Закрыто договоров: {closed}")
    close_with_deposit.short_description = "Закрыть договор (с зачётом депозита)"


@admin.register(Payment)
class PaymentAdmin(SimpleHistoryAdmin):
    list_display = ("id", "rental", "date", "amount", "type", "method", "created_by_name")
    list_filter = ("type", "method")
    search_fields = ("rental__id", "note")
    readonly_fields = ("created_by", "updated_by")
    @admin.display(ordering='created_by__username', description='Кто ввёл запись')
    def created_by_name(self, obj):
        user = obj.created_by
        if not user:
            return ''
        name = f"{user.first_name} {user.last_name}".strip()
        return name or user.username


    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, 'created_by_id', None):
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name")


@admin.register(Expense)
class ExpenseAdmin(SimpleHistoryAdmin):
    list_display = ("id", "date", "amount", "category")
    list_filter = ("category",)


@admin.register(Repair)
class RepairAdmin(SimpleHistoryAdmin):
    list_display = ("id", "battery", "start_at", "end_at", "cost")


@admin.register(BatteryStatusLog)
class BatteryStatusLogAdmin(SimpleHistoryAdmin):
    list_display = ("id", "battery", "kind", "start_at", "end_at")
