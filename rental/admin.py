from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Client, Battery, Rental, RentalBatteryAssignment,
    Payment, ExpenseCategory, Expense, Repair, BatteryStatusLog, RateChange
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


@admin.register(Rental)
class RentalAdmin(SimpleHistoryAdmin):
    list_display = ("id", "client", "start_at", "end_at", "weekly_rate", "deposit_amount", "status")
    list_filter = ("status",)
    search_fields = ("client__name",)
    inlines = [RentalBatteryAssignmentInline, PaymentInline]


@admin.register(RateChange)
class RateChangeAdmin(SimpleHistoryAdmin):
    list_display = ("id", "rental", "effective_date", "weekly_rate")


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
