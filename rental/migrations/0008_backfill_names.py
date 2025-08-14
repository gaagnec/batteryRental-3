from django.db import migrations


def _name_for(user):
    if not user:
        return ''
    # user in migrations runtime is a model instance; use common attributes
    return (getattr(user, 'get_full_name', lambda: '')() or getattr(user, 'username', '') or getattr(user, 'email', '') or getattr(user, 'first_name', '') or str(getattr(user, 'id', '')))


def forwards(apps, schema_editor):
    Rental = apps.get_model('rental', 'Rental')
    HistoricalRental = apps.get_model('rental', 'HistoricalRental')

    # Backfill current rentals
    for r in Rental.objects.all().iterator():
        changed = False
        if hasattr(r, 'created_by') and hasattr(r, 'created_by_name'):
            name = _name_for(getattr(r, 'created_by', None))
            if name and r.created_by_name != name:
                r.created_by_name = name
                changed = True
        if hasattr(r, 'updated_by') and hasattr(r, 'updated_by_name'):
            name = _name_for(getattr(r, 'updated_by', None))
            if name and r.updated_by_name != name:
                r.updated_by_name = name
                changed = True
        if changed:
            r.save(update_fields=['created_by_name', 'updated_by_name'])

    # Backfill historical rentals (if fields exist)
    # Historical models may not have FKs loaded; guard with getattr
    for hr in HistoricalRental.objects.all().iterator():
        changed = False
        if hasattr(hr, 'created_by') and hasattr(hr, 'created_by_name'):
            name = _name_for(getattr(hr, 'created_by', None))
            if name and hr.created_by_name != name:
                hr.created_by_name = name
                changed = True
        if hasattr(hr, 'updated_by') and hasattr(hr, 'updated_by_name'):
            name = _name_for(getattr(hr, 'updated_by', None))
            if name and hr.updated_by_name != name:
                hr.updated_by_name = name
                changed = True
        if changed:
            hr.save(update_fields=['created_by_name', 'updated_by_name'])


def backwards(apps, schema_editor):
    # No-op; keeping any filled names
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0007_historicalrental_created_by_name_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
