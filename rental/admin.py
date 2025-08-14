from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.utils import timezone
from decimal import Decimal
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Client, Battery, Rental, RentalBatteryAssignment,
    Payment, ExpenseCategory, Expense, Repair, BatteryStatusLog
)


@admin.register(Client)
class ClientAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "phone", "pesel", "created_at")
    search_fields = ("name", "phone", "pesel")


@admin.register(Battery)
class BatteryAdmin(SimpleHistoryAdmin):
    list_display = ("id", "short_code", "serial_number", "cost_price", "created_at")
    search_fields = ("short_code", "serial_number")


class RentalBatteryAssignmentInline(admin.TabularInline):
    model = RentalBatteryAssignment
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class NewVersionActionForm(ActionForm):
    new_weekly_rate = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2, label="Новая недельная ставка (PLN)"
    )


@admin.register(Rental)
class RentalAdmin(SimpleHistoryAdmin):
    list_display = (
        "id", "contract_code", "version", "client", "start_at", "end_at",
        "weekly_rate", "status", "group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now"
    )
    list_filter = ("status",)
    search_fields = ("client__name", "contract_code")
    inlines = [RentalBatteryAssignmentInline, PaymentInline]

    readonly_fields = ("group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now")

    action_form = NewVersionActionForm
    actions = ["make_new_version", "close_with_deposit"]

    def group_charges_now(self, obj):
        return obj.group_charges_until(until=timezone.now())
    group_charges_now.short_description = "Начислено (сейчас)"

    def group_paid_total(self, obj):
        return obj.group_paid_total()
    group_paid_total.short_description = "Оплачено (аренда)"

    def group_deposit_total(self, obj):
        return obj.group_deposit_total()
    group_deposit_total.short_description = "Депозит (чистый)"

    def group_balance_now(self, obj):
        return obj.group_balance(until=timezone.now())
    group_balance_now.short_description = "Баланс (сейчас)"

    def save_model(self, request, obj, form, change):
        if not change and not obj.root_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
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
            if not rental.end_at or rental.end_at > now:
                rental.end_at = now
            rental.status = Rental.Status.MODIFIED
            rental.save()
            # Номер новой версии = количество версий в группе + 1
            try:
                new_version_num = root.group.all().count() + 1
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
            count += 1
        self.message_user(request, f"Создано новых версий: {count}")
    make_new_version.short_description = "Создать новую версию (начало сейчас)"

    def close_with_deposit(self, request, queryset):
        closed = 0
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
            closed += 1
        self.message_user(request, f"Закрыто договоров: {closed}")
    close_with_deposit.short_description = "Закрыть договор (с зачётом депозита)"


@admin.register(Payment)
class PaymentAdmin(SimpleHistoryAdmin):
    list_display = ("id", "rental", "date", "amount", "type", "method")
    list_filter = ("type", "method")
    search_fields = ("rental__id", "note")


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
