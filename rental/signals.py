from django.db.models.signals import post_migrate, post_save, post_delete
from django.conf import settings
from django.utils import timezone

from django.dispatch import receiver
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from .models import RentalBatteryAssignment, Repair, BatteryStatusLog, Expense, OwnerContribution, FinancePartner


@receiver(post_migrate)
def create_groups(sender, **kwargs):
    if sender.name != 'rental':
        return
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    moderator_group, _ = Group.objects.get_or_create(name='Moderator')

    rental_app_cts = ContentType.objects.filter(app_label='rental')
    perms = Permission.objects.filter(content_type__in=rental_app_cts)

    admin_group.permissions.set(perms)
    mod_perms = perms.exclude(codename__startswith='delete_')
    moderator_group.permissions.set(mod_perms)


# --- BatteryStatusLog automation ---
@receiver(post_save, sender=RentalBatteryAssignment)
def assignment_to_statuslog(sender, instance: RentalBatteryAssignment, created, **kwargs):
    # Upsert RENTAL status for this assignment
    log, _ = BatteryStatusLog.objects.get_or_create(
        battery=instance.battery,
        kind=BatteryStatusLog.Kind.RENTAL,
        rental=instance.rental,
        start_at=instance.start_at,
        defaults={
            'end_at': instance.end_at,
            'created_by': getattr(instance, 'created_by', None),
            'updated_by': getattr(instance, 'updated_by', None),
        }
    )
    changed = False
    if log.end_at != instance.end_at:
        log.end_at = instance.end_at
        changed = True
    if changed:
        log.save(update_fields=['end_at'])


@receiver(post_delete, sender=RentalBatteryAssignment)
def assignment_delete_statuslog(sender, instance: RentalBatteryAssignment, **kwargs):
    BatteryStatusLog.objects.filter(
        battery=instance.battery,
        kind=BatteryStatusLog.Kind.RENTAL,
        rental=instance.rental,
        start_at=instance.start_at,
    ).delete()

# --- Auto create OwnerContribution for "внесение денег" ---
@receiver(post_save, sender=Expense)
def expense_to_contribution(sender, instance: Expense, created, **kwargs):
    # Only for deposit type and when a partner (owner) is provided
    if getattr(instance, 'payment_type', None) != Expense.PaymentType.DEPOSIT:
        return
    if not instance.paid_by_partner_id:
        return
    try:
        partner = FinancePartner.objects.get(pk=instance.paid_by_partner_id)
    except FinancePartner.DoesNotExist:
        return
    if partner.role != FinancePartner.Role.OWNER:
        return
    # Idempotency: link via expense FK
    exists = OwnerContribution.objects.filter(expense=instance).exists()
    if exists:
        return
    OwnerContribution.objects.create(
        partner=partner,
        amount=instance.amount,
        date=instance.date or timezone.localdate(),
        source=OwnerContribution.Source.EXPENSE,
        expense=instance,
        note=(instance.note or "")[:500],
        created_by=getattr(instance, 'created_by', None),
        updated_by=getattr(instance, 'updated_by', None),
    )


@receiver(post_save, sender=Repair)
def repair_to_statuslog(sender, instance: Repair, created, **kwargs):
    log, _ = BatteryStatusLog.objects.get_or_create(
        battery=instance.battery,
        kind=BatteryStatusLog.Kind.REPAIR,
        repair=instance,
        start_at=instance.start_at,
        defaults={
            'end_at': instance.end_at,
            'created_by': getattr(instance, 'created_by', None),
            'updated_by': getattr(instance, 'updated_by', None),
        }
    )
    if log.end_at != instance.end_at:
        log.end_at = instance.end_at
        log.save(update_fields=['end_at'])


@receiver(post_delete, sender=Repair)
def repair_delete_statuslog(sender, instance: Repair, **kwargs):
    BatteryStatusLog.objects.filter(
        battery=instance.battery,
        kind=BatteryStatusLog.Kind.REPAIR,
        repair=instance,
        start_at=instance.start_at,
    ).delete()
