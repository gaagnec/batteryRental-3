# Generated manually for multi-city system

from django.db import migrations, models
import django.db.models.deletion


def create_cities(apps, schema_editor):
    City = apps.get_model('rental', 'City')
    City.objects.get_or_create(name='Вроцлав', defaults={'code': 'wroclaw', 'active': True})
    City.objects.get_or_create(name='Познань', defaults={'code': 'poznan', 'active': True})
    City.objects.get_or_create(name='Варшава', defaults={'code': 'warsaw', 'active': True})


def reverse_create_cities(apps, schema_editor):
    City = apps.get_model('rental', 'City')
    City.objects.filter(code__in=['wroclaw', 'poznan', 'warsaw']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0019_add_performance_indexes'),
        ('auth', '____latest__'),
    ]

    operations = [
        migrations.CreateModel(
            name='City',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=64, unique=True)),
                ('code', models.CharField(max_length=16, unique=True)),
                ('active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='city_created', to='auth.user')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='city_updated', to='auth.user')),
            ],
            options={
                'verbose_name': 'Город',
                'verbose_name_plural': 'Города',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(create_cities, reverse_create_cities),
    ]

