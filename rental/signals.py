from django.db.models.signals import post_migrate, post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from .models import RentalBatteryAssignment, Repair, BatteryStatusLog


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
