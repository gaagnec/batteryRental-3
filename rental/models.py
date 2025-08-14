from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum
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

    # Versioning fields (Variant B)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    root = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="group")
    version = models.PositiveIntegerField(default=1)
    contract_code = models.CharField(max_length=64, blank=True, help_text="Общий номер договора для всей группы (root)")

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Ensure root is set to self for the first version
        if self.pk is None and not self.root:
            # Temporarily save to get pk
            super().save(*args, **kwargs)
            if not self.root:
                self.root = self
                if not self.contract_code:
                    self.contract_code = f"R-{self.pk}"
            return super().save(update_fields=["root", "contract_code"])  # type: ignore
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
        """Charges for this version only, without rate changes inside version."""
        from datetime import timedelta
        tz = timezone.get_current_timezone()
        start = timezone.localtime(self.start_at, tz)
        end = timezone.localtime(until or self.end_at or timezone.now(), tz)
        if end <= start:
            return Decimal(0)
        total = Decimal(0)
        current_date = start.date()
        while current_date < end.date() or (
            current_date == end.date() and not (end.hour < 14 or (end.hour == 14 and end.minute == 0 and end.second == 0))
        ):
            is_first_day = current_date == start.date()
            is_last_day = current_date == end.date()
            count_day = True
            if is_first_day and not (start.hour < 14 or (start.hour == 14 and start.minute == 0 and start.second == 0)):
                count_day = False
            if is_last_day and (end.hour < 14 or (end.hour == 14 and end.minute == 0 and end.second == 0)):
                count_day = False
            if count_day:
                total += (self.weekly_rate or Decimal(0)) / Decimal(7)
            current_date += timedelta(days=1)
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

