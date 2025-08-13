from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


@receiver(post_migrate)
def create_groups(sender, **kwargs):
    if sender.name != 'rental':
        return
    # Create groups
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    moderator_group, _ = Group.objects.get_or_create(name='Moderator')

    # Assign permissions
    rental_app_cts = ContentType.objects.filter(app_label='rental')
    perms = Permission.objects.filter(content_type__in=rental_app_cts)

    # Admin gets all perms for rental app
    admin_group.permissions.set(perms)

    # Moderator gets add/change/view but not delete
    mod_perms = perms.exclude(codename__startswith='delete_')
    moderator_group.permissions.set(mod_perms)
