from __future__ import annotations
from django.db import models
from django.db import connection

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum
from django.core.exceptions import ValidationError
from decimal import Decimal
from simple_history.models import HistoricalRecords


User = get_user_model()


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="%(class)s_created")
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="%(class)s_updated")

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    name = models.CharField(max_length=255)
    pesel = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class Battery(TimeStampedModel):
    short_code = models.CharField(max_length=32, unique=True)
    serial_number = models.CharField(max_length=64, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.short_code}"


class Rental(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        CLOSED = "closed", "Закрыт"
        MODIFIED = "modified", "Модифицирован"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="rentals")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    weekly_rate = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    battery_type = models.CharField(max_length=64, blank=True)
    battery_count = models.PositiveIntegerField(default=0, help_text="Количество арендованных батарей")
    battery_numbers = models.TextField(blank=True, help_text="Номера арендованных батарей")
    # denormalized author names for Supabase UI
    created_by_name = models.CharField(max_length=150, blank=True)
    updated_by_name = models.CharField(max_length=150, blank=True)

    # Versioning fields (Variant B)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    root = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="group")
    version = models.PositiveIntegerField(default=1)
    contract_code = models.CharField(max_length=64, blank=True, help_text="Общий номер договора для всей группы (root)")

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["root", "version"], name="uq_rental_root_version"),
        ]
        indexes = [
            models.Index(fields=["root", "status"], name="idx_rental_root_status"),
            models.Index(fields=["root"], name="idx_rental_root"),
            models.Index(fields=["status"], name="idx_rental_status"),
        ]

    def save(self, *args, **kwargs):
        # Ensure root is set to self for the first version
        if self.pk is None and not self.root:
            # Temporarily save to get pk
            super().save(*args, **kwargs)
            if not self.root:
                self.root = self
                if not self.contract_code:
                    self.contract_code = f"BR-{self.pk}"
            return super().save(update_fields=["root", "contract_code"])  # type: ignore
        # denormalize user names for Supabase: store names alongside FKs
        if self.created_by_id and not self.created_by_name and getattr(self, 'created_by', None):
            self.created_by_name = getattr(self.created_by, 'get_full_name', lambda: '')() or getattr(self.created_by, 'username', '') or getattr(self.created_by, 'email', '')
        if getattr(self, 'updated_by', None):
            self.updated_by_name = getattr(self.updated_by, 'get_full_name', lambda: '')() or getattr(self.updated_by, 'username', '') or getattr(self.updated_by, 'email', '')
        return super().save(*args, **kwargs)

    @property
    def is_root(self) -> bool:
        return self.root_id == self.pk

    def __str__(self):
        base = self.contract_code or (self.root.contract_code if self.root else f"Rental-{self.pk}")
        return f"{base} v{self.version} - {self.client}"

    @property
    def daily_rate(self) -> Decimal:
        return (self.weekly_rate or Decimal(0)) / Decimal(7)

    def billable_days(self, until: timezone.datetime | None = None) -> int:
        """Calculate billable days with 14:00 cutoff for this version interval only."""
        tz = timezone.get_current_timezone()
        start = timezone.localtime(self.start_at, tz)
        end = timezone.localtime(until or self.end_at or timezone.now(), tz)
        if end <= start:
            return 0
        start_date = start.date()
        end_date = end.date()
        days = (end_date - start_date).days
        if start.hour < 14 or (start.hour == 14 and start.minute == 0 and start.second == 0):
            days += 1
        if end.hour < 14 or (end.hour == 14 and end.minute == 0 and end.second == 0):
            days -= 1
        return max(days, 0)

    def charges_until(self, until: timezone.datetime | None = None) -> Decimal:
        """Charges for this version only, multiplied by number of assigned batteries per day.
        Day is billable if 14:00 anchor of that day lies within [start, end).
        """
        from datetime import datetime, time, timedelta
        tz = timezone.get_current_timezone()
        start = timezone.localtime(self.start_at, tz)
        end = timezone.localtime(until or self.end_at or timezone.now(), tz)
        if end <= start:
            return Decimal(0)
        # Preload assignments for this version
        assignments = list(self.assignments.all())
        total = Decimal(0)
        d = start.date()
        end_date = end.date()
        while d <= end_date:
            anchor = timezone.make_aware(datetime.combine(d, time(14, 0)), tz)
            # Count day only if rental covers the 14:00 anchor
            if start <= anchor and (self.end_at is None or timezone.localtime(self.end_at, tz) > anchor) and anchor <= end:
                # number of batteries assigned at this anchor
                cnt = 0
                for a in assignments:
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_start <= anchor and (a_end is None or a_end > anchor):
                        cnt += 1
                if cnt:
                    total += ((self.weekly_rate or Decimal(0)) / Decimal(7)) * Decimal(cnt)
            d += timedelta(days=1)
        return total

    def group_versions(self):
        root = self.root or self
        return Rental.objects.filter(root=root).order_by("start_at", "id")

    def group_charges_until(self, until: timezone.datetime | None = None) -> Decimal:
        """Sum of charges across all versions in the group (root)."""
        total = Decimal(0)
        for v in self.group_versions():
            # Limit 'until' within each version interval
            v_until = until
            if v_until and v.end_at and v.end_at < v_until:
                v_until = v.end_at
            total += v.charges_until(until=v_until)
        return total
    def group_payments(self):
        root = self.root or self
        return Payment.objects.filter(rental__root=root)

    def group_paid_total(self) -> Decimal:
        total = self.group_payments().filter(type=Payment.PaymentType.RENT).aggregate(s=Sum("amount"))['s'] or Decimal(0)
        return total

    def group_deposit_total(self) -> Decimal:
        paid = self.group_payments().filter(type=Payment.PaymentType.DEPOSIT).aggregate(s=Sum("amount"))['s'] or Decimal(0)
        returned = self.group_payments().filter(type=Payment.PaymentType.RETURN_DEPOSIT).aggregate(s=Sum("amount"))['s'] or Decimal(0)
        return paid - returned

    def group_balance(self, until: timezone.datetime | None = None) -> Decimal:
        charges = self.group_charges_until(until=until)
        paid = self.group_paid_total()
        return charges - paid





class RentalBatteryAssignment(TimeStampedModel):
    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name="assignments")
    battery = models.ForeignKey(Battery, on_delete=models.PROTECT, related_name="assignments")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["start_at", "id"]
        indexes = [
            models.Index(fields=["battery", "start_at"], name="idx_assign_batt_start"),
        ]


class Payment(TimeStampedModel):
    class PaymentType(models.TextChoices):
        RENT = "rent", "Аренда"
        DEPOSIT = "deposit", "Депозит"
        RETURN_DEPOSIT = "return_deposit", "Возврат депозита"
        ADJUSTMENT = "adjustment", "Корректировка"

    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        BLIK = "blik", "BLIK"
        REVOLUT = "revolut", "Revolut"
        OTHER = "other", "Другое"

    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    type = models.CharField(max_length=32, choices=PaymentType.choices, default=PaymentType.RENT)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.OTHER)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Всегда привязываем платеж к root-договору для консистентности групповых расчетов
        if self.rental and self.rental.root_id and self.rental_id != self.rental.root_id:
            self.rental = self.rental.root
        super().save(*args, **kwargs)
        # Автопостинг в журнал — делаем за пределами текущей транзакции админки
        try:
            from django.db import transaction
            transaction.on_commit(lambda: post_payment_to_ledger(self))
        except Exception:
            pass


# ---------------------- Мини-бухгалтерия (Журнал проводок) ----------------------
class Account(TimeStampedModel):
    class Type(models.TextChoices):
        ASSET = "asset", "Актив"
        LIABILITY = "liability", "Обязательство"
        INCOME = "income", "Доход"
        EXPENSE = "expense", "Расход"
        EQUITY = "equity", "Капитал"

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=16, choices=Type.choices)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.code} — {self.name}"


class JournalEntry(TimeStampedModel):
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255, blank=True)
    payment = models.OneToOneField('Payment', null=True, blank=True, on_delete=models.CASCADE, related_name='journal_entry')
    expense = models.OneToOneField('Expense', null=True, blank=True, on_delete=models.CASCADE, related_name='journal_entry')
    history = HistoricalRecords()

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        base = self.description or f"Запись #{self.pk}"
        return f"{self.date} — {base}"

    def is_balanced(self) -> bool:
        agg = self.lines.aggregate(deb=Sum('debit'), cred=Sum('credit'))
        return (agg.get('deb') or Decimal(0)) == (agg.get('cred') or Decimal(0))


class JournalLine(TimeStampedModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='lines')
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Атрибуция по клиенту и сотруднику для аналитики
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)
    staff_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    rental = models.ForeignKey(Rental, null=True, blank=True, on_delete=models.SET_NULL)
    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=["account", "created_at"], name="idx_jline_acc_created"),
            models.Index(fields=["client", "created_at"], name="idx_jline_client_created"),
        ]

    def __str__(self):
        amt = self.debit or self.credit
        side = 'D' if self.debit else 'C'
        return f"{self.account.code} {side} {amt}"


# Утилиты для автопроводок
SYSTEM_ACCOUNTS = {
    'cash': ("CASH", "Касса", Account.Type.ASSET),
    'blik': ("BLIK", "BLIK", Account.Type.ASSET),
    'revolut': ("REVOLUT", "Revolut", Account.Type.ASSET),
    'rent_income': ("RENT_INC", "Доход от аренды", Account.Type.INCOME),
    'deposit_liab': ("DEPOSIT", "Залог (обязательство)", Account.Type.LIABILITY),
    'adjust_income': ("ADJ_INC", "Корректировки (доход)", Account.Type.INCOME),
    'adjust_expense': ("ADJ_EXP", "Корректировки (расход)", Account.Type.EXPENSE),
}


def get_or_create_account(code: str, name: str, atype: str) -> Account:
    acc, _ = Account.objects.get_or_create(code=code, defaults={"name": name, "type": atype})
    return acc


def account_for_method(method: str) -> Account:
    key = 'cash'
    if method == Payment.Method.REVOLUT:
        key = 'revolut'
    elif method == Payment.Method.BLIK:
        key = 'blik'
    code, name, atype = SYSTEM_ACCOUNTS[key]
    return get_or_create_account(code, name, atype)


def rent_income_account() -> Account:
    code, name, atype = SYSTEM_ACCOUNTS['rent_income']
    return get_or_create_account(code, name, atype)


def deposit_account() -> Account:
    code, name, atype = SYSTEM_ACCOUNTS['deposit_liab']
    return get_or_create_account(code, name, atype)


def adjust_income_account() -> Account:
    code, name, atype = SYSTEM_ACCOUNTS['adjust_income']
    return get_or_create_account(code, name, atype)


def adjust_expense_account() -> Account:
    code, name, atype = SYSTEM_ACCOUNTS['adjust_expense']
    return get_or_create_account(code, name, atype)


# Постинг платежей и расходов в журнал
def post_payment_to_ledger(payment: Payment):
    # Если таблицы бухгалтерии ещё не созданы (миграции не применены) — выходим молча
    existing = connection.introspection.table_names()
    if (
        Account._meta.db_table not in existing or
        JournalEntry._meta.db_table not in existing or
        JournalLine._meta.db_table not in existing
    ):
        return None
    # Идемпотентность: если уже есть запись — переиспользуем и перезаписываем строки
    from django.db import transaction
    entry, created = JournalEntry.objects.get_or_create(payment=payment, defaults={
        'date': payment.date,
        'description': f"Платеж {payment.get_type_display()} по {payment.rental}",
        'created_by': payment.created_by,
        'updated_by': payment.updated_by,
    })
    if not created:
        entry.lines.all().delete()
        entry.date = payment.date
        entry.description = f"Платеж {payment.get_type_display()} по {payment.rental}"
        entry.updated_by = payment.updated_by
        entry.save(update_fields=["date", "description", "updated_by", "updated_at"])

    amt = payment.amount or Decimal(0)
    asset = account_for_method(payment.method)
    client = payment.rental.client if payment.rental_id else None
    staff = payment.created_by

    if payment.type == Payment.PaymentType.RENT:
        income = rent_income_account()
        # Дт Денежные средства, Кт Доход
        JournalLine.objects.create(entry=entry, account=asset, debit=amt, credit=0, client=client, staff_user=staff, rental=payment.rental)
        JournalLine.objects.create(entry=entry, account=income, debit=0, credit=amt, client=client, staff_user=staff, rental=payment.rental)
    elif payment.type == Payment.PaymentType.DEPOSIT:
        dep = deposit_account()
        JournalLine.objects.create(entry=entry, account=asset, debit=amt, credit=0, client=client, staff_user=staff, rental=payment.rental)
        JournalLine.objects.create(entry=entry, account=dep, debit=0, credit=amt, client=client, staff_user=staff, rental=payment.rental)
    elif payment.type == Payment.PaymentType.RETURN_DEPOSIT:
        dep = deposit_account()
        JournalLine.objects.create(entry=entry, account=dep, debit=amt, credit=0, client=client, staff_user=staff, rental=payment.rental)
        JournalLine.objects.create(entry=entry, account=asset, debit=0, credit=amt, client=client, staff_user=staff, rental=payment.rental)
    else:  # ADJUSTMENT
        # По умолчанию трактуем как поступление (если нужно, можно расширить типы)
        adj_inc = adjust_income_account()
        JournalLine.objects.create(entry=entry, account=asset, debit=amt, credit=0, client=client, staff_user=staff, rental=payment.rental)
        JournalLine.objects.create(entry=entry, account=adj_inc, debit=0, credit=amt, client=client, staff_user=staff, rental=payment.rental)

    return entry


def post_expense_to_ledger(expense: Expense):
    entry, created = JournalEntry.objects.get_or_create(expense=expense, defaults={
        'date': expense.date,
        'description': f"Расход: {expense.category or ''}",
        'created_by': expense.created_by,
        'updated_by': expense.updated_by,
    })
    if not created:
        entry.lines.all().delete()
        entry.date = expense.date
        entry.description = f"Расход: {expense.category or ''}"
        entry.updated_by = expense.updated_by
        entry.save(update_fields=["date", "description", "updated_by", "updated_at"])

    amt = expense.amount or Decimal(0)
    # Счёт расходов по категории (создаём при необходимости)
    cat_name = str(expense.category or 'Прочее')
    expense_acc = get_or_create_account(code=f"EXP_{expense.category_id or 0}", name=f"Расходы: {cat_name}", atype=Account.Type.EXPENSE)
    # По умолчанию кредитуем кассу
    asset = get_or_create_account(*SYSTEM_ACCOUNTS['cash'])
    # Дт Расходы, Кт Денежные средства
    JournalLine.objects.create(entry=entry, account=expense_acc, debit=amt, credit=0)
    JournalLine.objects.create(entry=entry, account=asset, debit=0, credit=amt)
    return entry
# Хуки сохранения: отключено в пользу явного постинга в save() моделей Payment/Expense


class ExpenseCategory(TimeStampedModel):
    name = models.CharField(max_length=64, unique=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class Expense(TimeStampedModel):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            post_expense_to_ledger(self)
        except Exception:
            pass


class Repair(TimeStampedModel):
    battery = models.ForeignKey(Battery, on_delete=models.CASCADE, related_name="repairs")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    history = HistoricalRecords()


class BatteryStatusLog(TimeStampedModel):
    class Kind(models.TextChoices):
        RENTAL = "rental", "Аренда"
        REPAIR = "repair", "Ремонт"
        IDLE = "idle", "Простой"

    battery = models.ForeignKey(Battery, on_delete=models.CASCADE, related_name="status_logs")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    rental = models.ForeignKey(Rental, null=True, blank=True, on_delete=models.SET_NULL)
    repair = models.ForeignKey(Repair, null=True, blank=True, on_delete=models.SET_NULL)
    history = HistoricalRecords()

