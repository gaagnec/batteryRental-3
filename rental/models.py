from django.db import models
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
    city = models.ForeignKey('City', on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        """Синхронизация города с договорами и платежами клиента при изменении"""
        # Проверяем, изменился ли город (только при редактировании)
        city_changed = False
        if self.pk:
            try:
                old_client = Client.objects.get(pk=self.pk)
                if old_client.city_id != self.city_id:
                    city_changed = True
            except Client.DoesNotExist:
                pass
        
        # Сохраняем клиента
        super().save(*args, **kwargs)
        
        # Если город изменился, обновляем все договоры и платежи клиента
        if city_changed and self.city:
            # Обновляем город во всех договорах клиента
            updated_rentals = Rental.objects.filter(client=self).update(city=self.city)
            # Обновляем город во всех платежах клиента (через договоры)
            if updated_rentals > 0:
                Payment.objects.filter(rental__client=self).update(city=self.city)


class Battery(TimeStampedModel):
    class Status(models.TextChoices):
        RENTED = "rented", "rented"
        SERVICE = "service", "service"
        SOLD = "sold", "sold"
        AVAILABLE = "available", "available"

    short_code = models.CharField(max_length=32, unique=True)
    serial_number = models.CharField(max_length=64, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    city = models.ForeignKey('City', on_delete=models.SET_NULL, null=True, blank=True, related_name='batteries')
    status = models.CharField(max_length=16, choices=Status.choices, blank=True, null=True)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Батарея"
        verbose_name_plural = "Батареи"

    def __str__(self):
        return f"{self.short_code}"


class Rental(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        CLOSED = "closed", "Закрыт"
        MODIFIED = "modified", "Модифицирован"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="rentals")
    city = models.ForeignKey('City', on_delete=models.SET_NULL, null=True, blank=True, related_name='rentals')
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
        verbose_name = "Аренда"
        verbose_name_plural = "Аренды"
        constraints = [
            models.UniqueConstraint(fields=["root", "version"], name="uq_rental_root_version"),
        ]
        indexes = [
            models.Index(fields=["root", "status"], name="idx_rental_root_status"),
            models.Index(fields=["root"], name="idx_rental_root"),
            models.Index(fields=["status"], name="idx_rental_status"),
        ]

    def save(self, *args, **kwargs):
        # Автоматически устанавливаем city из client.city при создании
        if self.pk is None and not self.city and self.client_id:
            if hasattr(self.client, 'city') and self.client.city:
                self.city = self.client.city
        
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
        verbose_name = "Привязка батареи"
        verbose_name_plural = "Привязки батарей"
        ordering = ["start_at", "id"]
        indexes = [
            models.Index(fields=["battery", "start_at"], name="idx_assign_batt_start"),
        ]


class Payment(TimeStampedModel):
    class PaymentType(models.TextChoices):
        RENT = "rent", "Аренда"
        SOLD = "sold", "Продажа"
        DEPOSIT = "deposit", "Депозит"
        RETURN_DEPOSIT = "return_deposit", "Возврат депозита"
        ADJUSTMENT = "adjustment", "Корректировка"

    class Meta:
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"
        indexes = [
            models.Index(fields=["type", "date"], name="idx_pay_type_date"),
            models.Index(fields=["created_by", "date"], name="idx_pay_user_date"),
            models.Index(fields=["date"], name="idx_pay_date"),
            models.Index(fields=["type"], name="idx_pay_type"),
            models.Index(fields=["created_by"], name="idx_pay_user"),
        ]

    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        BLIK = "blik", "BLIK"
        REVOLUT = "revolut", "Revolut"
        OTHER = "other", "Другое"

    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name="payments", verbose_name="Аренда")
    city = models.ForeignKey('City', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    type = models.CharField(max_length=32, choices=PaymentType.choices, default=PaymentType.RENT)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.OTHER)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    def clean(self):
        """Валидация: город платежа должен совпадать с городом договора"""
        super().clean()
        
        if self.rental_id and self.city_id:
            # Загружаем rental с city если нужно
            if not self.rental or not hasattr(self.rental, 'city'):
                try:
                    self.rental = Rental.objects.select_related('city').get(pk=self.rental_id)
                except Rental.DoesNotExist:
                    return
            
            # Проверяем соответствие городов
            if self.rental and self.rental.city and self.rental.city_id != self.city_id:
                raise ValidationError({
                    'city': f'Город платежа должен совпадать с городом договора ({self.rental.city})'
                })

    def save(self, *args, **kwargs):
        # Всегда привязываем платеж к root-договору для консистентности групповых расчетов
        if self.rental and self.rental.root_id and self.rental_id != self.rental.root_id:
            self.rental = self.rental.root
        
        # Автоматически синхронизируем city с rental (ОСНОВНАЯ ЛОГИКА)
        # City платежа всегда должен совпадать с city договора
        if self.rental_id:
            # Загружаем rental с city если еще не загружен
            if not self.rental or not hasattr(self.rental, 'city'):
                try:
                    self.rental = Rental.objects.select_related('city').get(pk=self.rental_id)
                except Rental.DoesNotExist:
                    pass
            
            # Синхронизируем город с договором (приоритет 1)
            if self.rental and self.rental.city:
                self.city = self.rental.city
            # Если у договора нет города, пытаемся использовать город модератора (приоритет 2)
            elif not self.city and self.created_by_id:
                try:
                    FinancePartner = self.__class__._meta.apps.get_model('rental', 'FinancePartner')
                    finance_partner = FinancePartner.objects.filter(
                        user=self.created_by, 
                        role='moderator',
                        active=True
                    ).select_related('city').first()
                    if finance_partner and finance_partner.city:
                        self.city = finance_partner.city
                except Exception:
                    pass
        # Если нет rental, но есть created_by - используем город модератора
        elif not self.city and self.created_by_id:
            try:
                FinancePartner = self.__class__._meta.apps.get_model('rental', 'FinancePartner')
                finance_partner = FinancePartner.objects.filter(
                    user=self.created_by, 
                    role='moderator',
                    active=True
                ).select_related('city').first()
                if finance_partner and finance_partner.city:
                    self.city = finance_partner.city
            except Exception:
                pass
        
        super().save(*args, **kwargs)


class FinanceOverviewProxy(Payment):
    class Meta:
        proxy = True
        verbose_name = "Финансы"
        verbose_name_plural = "Финансы"


class FinanceOverviewProxy2(Payment):
    class Meta:
        proxy = True
        verbose_name = "Бухучёт"
        verbose_name_plural = "Бухучёт"


class ExpenseCategory(TimeStampedModel):
    name = models.CharField(max_length=64, unique=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Категория расходов"
        verbose_name_plural = "Категории расходов"

    def __str__(self):
        return self.name


class Expense(TimeStampedModel):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    class PaymentType(models.TextChoices):
        PURCHASE = "purchase", "Закупка"
        DEPOSIT = "deposit", "Внесение личных средств"
    payment_type = models.CharField(max_length=16, choices=PaymentType.choices, default=PaymentType.PURCHASE)
    paid_by_partner = models.ForeignKey('FinancePartner', null=True, blank=True, on_delete=models.SET_NULL, related_name='expenses_paid')
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Расход"
        verbose_name_plural = "Расходы"
        indexes = [
            models.Index(fields=["date"], name="idx_exp_date"),
            models.Index(fields=["payment_type"], name="idx_exp_type"),
            models.Index(fields=["paid_by_partner"], name="idx_exp_partner"),
        ]


class Repair(TimeStampedModel):
    battery = models.ForeignKey(Battery, on_delete=models.CASCADE, related_name="repairs")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Ремонт"
        verbose_name_plural = "Ремонты"


class BatteryStatusLog(TimeStampedModel):
    class Kind(models.TextChoices):
        RENTED = "rented", "В аренде"
        SERVICE = "service", "Сервис"
        AVAILABLE = "available", "Доступный"
        SOLD = "sold", "Продана"

    battery = models.ForeignKey(Battery, on_delete=models.CASCADE, related_name="status_logs")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    rental = models.ForeignKey(Rental, null=True, blank=True, on_delete=models.SET_NULL)
    repair = models.ForeignKey(Repair, null=True, blank=True, on_delete=models.SET_NULL)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Лог статуса батареи"
        verbose_name_plural = "Логи статусов батарей"


class BatteryTransfer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        APPROVED = "approved", "Подтвержден"
        REJECTED = "rejected", "Отклонен"
    
    battery = models.ForeignKey(Battery, on_delete=models.CASCADE, related_name="transfers")
    from_city = models.ForeignKey('City', on_delete=models.PROTECT, related_name="transfers_from")
    to_city = models.ForeignKey('City', on_delete=models.PROTECT, related_name="transfers_to")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="transfer_requests")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_transfers")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    note = models.TextField(blank=True, verbose_name="Комментарий")
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Перенос батареи"
        verbose_name_plural = "Переносы батарей"
        ordering = ['-created_at']
    
    def approve(self, approved_by_user):
        """Подтверждает перенос и меняет city батареи"""
        if self.status != self.Status.PENDING:
            raise ValidationError("Можно подтвердить только запросы в статусе PENDING")
        
        # Проверка активной аренды перед подтверждением
        from django.utils import timezone
        from django.db.models import Q
        from .models import RentalBatteryAssignment, Rental
        
        now = timezone.now()
        active_assignments = RentalBatteryAssignment.objects.filter(
            battery=self.battery,
            start_at__lte=now
        ).filter(
            Q(end_at__isnull=True) | Q(end_at__gt=now)
        ).filter(
            rental__status=Rental.Status.ACTIVE
        ).exists()
        
        if active_assignments:
            raise ValidationError(f"Батарея {self.battery.short_code} находится в активной аренде. Перенос невозможен.")
        
        self.status = self.Status.APPROVED
        self.approved_by = approved_by_user
        self.battery.city = self.to_city
        self.battery.save()
        self.save()
    
    def reject(self, rejected_by_user):
        """Отклоняет запрос на перенос"""
        if self.status != self.Status.PENDING:
            raise ValidationError("Можно отклонить только запросы в статусе PENDING")
        self.status = self.Status.REJECTED
        self.approved_by = rejected_by_user  # Используем то же поле для логирования
        self.save()
    
    def __str__(self):
        return f"{self.battery} из {self.from_city} в {self.to_city} ({self.get_status_display()})"


# =========================
# Finance models
# =========================

class FinancePartner(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Владелец"
        MODERATOR = "moderator", "Модератор"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="finance_partners")
    role = models.CharField(max_length=16, choices=Role.choices)
    city = models.ForeignKey('City', on_delete=models.PROTECT, null=True, blank=True, related_name='finance_partners')
    share_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("50.00"))
    reward_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), help_text="Процент вознаграждения модератора (0-100)")
    active = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Финансовый партнёр"
        verbose_name_plural = "Финансовые партнёры"

    def clean(self):
        """Валидация: модератор должен иметь город"""
        from django.core.exceptions import ValidationError
        if self.role == self.Role.MODERATOR and not self.city:
            raise ValidationError({'city': 'Модератор должен быть привязан к городу'})
        super().clean()

    def calculate_reward(self, start_date, end_date):
        """Рассчитывает вознаграждение модератора за период"""
        if not self.city or self.role != self.Role.MODERATOR:
            return Decimal('0')
        
        # Используем Payment.city (прямое поле), а не rental__city
        payments = Payment.objects.filter(
            city=self.city,  # Прямое поле city в Payment
            created_by=self.user,
            date__gte=start_date,
            date__lte=end_date,
            type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
        )
        total = payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        # reward_percent в формате 0-100, поэтому делим на 100
        return total * (self.reward_percent / 100)

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"


class OwnerContribution(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Взнос"
        EXPENSE = "expense", "Расход (личные)"

    partner = models.ForeignKey("FinancePartner", on_delete=models.CASCADE, related_name="contributions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    expense = models.ForeignKey("Expense", null=True, blank=True, on_delete=models.SET_NULL, related_name="as_contribution")
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Взнос владельца"
        verbose_name_plural = "Взносы владельцев"

    def clean(self):
        if self.partner and self.partner.role != FinancePartner.Role.OWNER:
            raise ValidationError("Contribution partner must be an owner")

    def __str__(self):
        return f"{self.partner}: +{self.amount} ({self.get_source_display()})"


class OwnerWithdrawal(TimeStampedModel):
    partner = models.ForeignKey("FinancePartner", on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)
    # Reclassification to investment (owner contribution)
    reclassified_to_investment = models.BooleanField(default=False)
    reclassified_contribution = models.ForeignKey(
        "OwnerContribution", null=True, blank=True, on_delete=models.SET_NULL, related_name="from_withdrawal"
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Вывод владельца"
        verbose_name_plural = "Выводы владельцев"

    def clean(self):
        if self.partner and self.partner.role != FinancePartner.Role.OWNER:
            raise ValidationError("Withdrawal partner must be an owner")

    def __str__(self):
        return f"{self.partner}: -{self.amount} (withdrawal)"


class MoneyTransfer(TimeStampedModel):
    class Purpose(models.TextChoices):
        MODERATOR_TO_OWNER = "moderator_to_owner", "От модератора владельцу"
        OWNER_TO_OWNER = "owner_to_owner", "Между владельцами"
        OTHER = "other", "Другое"

    class Meta:
        verbose_name = "Денежный перевод"
        verbose_name_plural = "Денежные переводы"
        indexes = [
            models.Index(fields=["date"], name="idx_mt_date"),
            models.Index(fields=["purpose", "use_collected"], name="idx_mt_purpose_usecol"),
            models.Index(fields=["from_partner"], name="idx_mt_from"),
            models.Index(fields=["to_partner"], name="idx_mt_to"),
            models.Index(fields=["from_partner", "purpose", "use_collected", "date"], name="idx_mt_from_pud"),
            models.Index(fields=["to_partner", "purpose", "use_collected", "date"], name="idx_mt_to_pud"),
        ]


    from_partner = models.ForeignKey("FinancePartner", on_delete=models.CASCADE, related_name="transfers_from")
    to_partner = models.ForeignKey("FinancePartner", on_delete=models.CASCADE, related_name="transfers_to")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    purpose = models.CharField(max_length=32, choices=Purpose.choices, default=Purpose.OTHER)
    use_collected = models.BooleanField(default=False, help_text="Списывать из собранных у отправителя и начислять получателю")
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    def clean(self):
        if self.from_partner_id and self.to_partner_id and self.from_partner_id == self.to_partner_id:
            raise ValidationError("from_partner and to_partner must differ")

    def __str__(self):
        return f"{self.from_partner} → {self.to_partner}: {self.amount}"


class FinanceAdjustment(TimeStampedModel):
    class Target(models.TextChoices):
        COLLECTED = "collected", "Собранные"
        OWNER_SETTLEMENT = "owner_settlement", "Взаиморасчеты владельцев"
        INVESTED = "invested", "Вложено"

    target = models.CharField(max_length=32, choices=Target.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Плюс/минус значение")
    date = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Финансовая корректировка"
        verbose_name_plural = "Финансовые корректировки"

    def __str__(self):
        return f"{self.get_target_display()}: {self.amount}"


# =========================
# City model
# =========================

class City(TimeStampedModel):
    name = models.CharField(max_length=64, unique=True)  # Вроцлав, Познань, Варшава
    code = models.CharField(max_length=16, unique=True)  # wroclaw, poznan, warsaw
    active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Город"
        verbose_name_plural = "Города"
        ordering = ['name']
    
    def __str__(self):
        return self.name
