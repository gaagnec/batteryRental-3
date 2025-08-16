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
            balance = charges - paid
            deposit = root.group_deposit_total()
            # Определяем цветовую метку баланса
            if (charges or 0) == 0 and (paid or 0) == 0:
                color = 'gray'
            elif balance <= 0:
                color = 'green'
            elif deposit and balance <= deposit:
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
        js = ["https://unpkg.com/htmx.org@1.9.2"]

    def changelist_view(self, request, extra_context=None):
        if getattr(request, "htmx", False):
            self.list_display = ("id", "name", "phone", "pesel", "created_at", "has_active")
            self.list_filter = (ActiveRentalFilter,)
            response = super().changelist_view(request, extra_context)
            return response
        else:
            self.list_display = ("id", "name", "phone", "pesel", "created_at")
            self.list_filter = (ActiveRentalFilter,)
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

    search_fields = ("name", "phone", "pesel")


@admin.register(Battery)
class BatteryAdmin(SimpleHistoryAdmin):
    list_display = ("id", "short_code", "serial_number", "cost_price", "created_at")
    search_fields = ("short_code", "serial_number")



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
    payment_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма оплаты")
    payment_method = forms.ChoiceField(required=False, choices=[('cash','Наличные'),('blik','BLIK'),('revolut','Revolut'),('other','Другое')], label="Метод оплаты")
    payment_note = forms.CharField(required=False, label="Примечание к оплате")
    deposit_return_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма возврата депозита")
    deposit_return_note = forms.CharField(required=False, label="Примечание к возврату депозита")


@admin.register(Rental)
class RentalAdmin(SimpleHistoryAdmin):
    list_display = (
        "id", "contract_code", "version", "client", "start_at", "end_at",
        "weekly_rate", "status", "assigned_batteries_short", "change_batteries_link", "group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now"
    )
    list_filter = ("status",)
    def change_batteries_link(self, obj):
        url = reverse('admin:rental_rental_change_batteries', args=[obj.pk])
        return format_html('<a class="button" href="{}">Изменить батареи</a>', url)
    change_batteries_link.short_description = "Изменить"

    search_fields = ("client__name", "contract_code")
    inlines = [RentalBatteryAssignmentInline, PaymentInline]

    readonly_fields = ("group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now", "created_by", "updated_by")
    def batteries_count_now(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        count = 0
        for a in obj.assignments.all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                count += 1
        return count


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
        return ", ".join(sorted(set(codes))) or "—"
    assigned_batteries_short.short_description = "Батареи (сейчас)"

    def group_charges_now(self, obj):
        return self.fmt_pln(obj.group_charges_until(until=timezone.now()))
    group_charges_now.short_description = "Начислено (сейчас)"

    def group_paid_total(self, obj):
        return self.fmt_pln(obj.group_paid_total())
    group_paid_total.short_description = "Оплачено (аренда)"

    def group_deposit_total(self, obj):
        return self.fmt_pln(obj.group_deposit_total())
    group_deposit_total.short_description = "Депозит (чистый)"

    def group_balance_now(self, obj):
        now = timezone.now()
        charges = obj.group_charges_until(until=now)
        paid = obj.group_paid_total()
        return self.fmt_pln(paid - charges)

    group_balance_now.short_description = "Баланс (сейчас)"

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
        if rate_str:
            try:
                new_rate = Decimal(rate_str)
            except Exception:
                new_rate = None
        for rental in queryset:
            root = rental.root or rental
            now = timezone.now()
            # Закрываем старую версию
            if not rental.end_at or rental.end_at > now:
                rental.end_at = now
            rental.status = Rental.Status.MODIFIED
            rental.save()
            # Создаем новую версию
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
    make_new_version.short_description = "Создать новую версию (начало сейчас, с переносом батарей)"

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
    list_display = ("id", "rental", "date", "amount", "type", "method")
    list_filter = ("type", "method")
    search_fields = ("rental__id", "note")
    readonly_fields = ("created_by", "updated_by")

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
