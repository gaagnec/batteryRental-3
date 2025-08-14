from django.db import migrations


def forwards(apps, schema_editor):
    Rental = apps.get_model('rental', 'Rental')
    for r in Rental.objects.filter(root__isnull=True):
        r.root_id = r.id
        if not r.version:
            r.version = 1
        if not r.contract_code:
            r.contract_code = f"BR-{r.id}"
        r.save(update_fields=["root", "version", "contract_code"])


def backwards(apps, schema_editor):
    # No-op
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('rental', '0004_rentalbatteryassignment_idx_assign_batt_start'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
