"""
Примеры использования системы логирования в приложении аренды батарей.

Этот файл содержит примеры того, как интегрировать логирование
в различные части вашего приложения.

ВАЖНО: Это только примеры! Не используйте этот файл напрямую.
Копируйте нужные примеры в ваши файлы (views.py, admin.py, models.py и т.д.)
"""

from django.contrib import admin
from django.contrib import messages as django_messages
from django.shortcuts import get_object_or_404
from django.http import HttpRequest, JsonResponse
from decimal import Decimal

# Импортируем наши утилиты логирования
from .logging_utils import (
    log_action, log_error, log_warning, log_info, log_debug, LogOperation
)
from .models import Rental, Payment, Battery, Client


# =============================================================================
# ПРИМЕР 1: Логирование в Django Admin при сохранении объекта
# =============================================================================

class PaymentAdmin(admin.ModelAdmin):
    """Пример логирования при создании/обновлении платежа."""
    
    def save_model(self, request, obj, form, change):
        """Переопределяем save_model для логирования."""
        try:
            # Определяем, это создание или обновление
            action = "Обновлён платеж" if change else "Создан новый платеж"
            
            # Сохраняем объект
            super().save_model(request, obj, form, change)
            
            # Логируем успешное действие
            log_action(
                action,
                user=request.user,
                details={
                    'payment_id': obj.id,
                    'amount': float(obj.amount),
                    'type': obj.get_type_display(),
                    'rental_id': obj.rental_id if obj.rental else None,
                    'date': str(obj.date),
                },
                request=request
            )
            
            # Показываем сообщение пользователю
            django_messages.success(request, f"{action} успешно (ID: {obj.id})")
            
        except Exception as e:
            # Логируем ошибку
            log_error(
                "Ошибка при сохранении платежа",
                exception=e,
                user=request.user,
                context={
                    'payment_id': obj.id if obj.id else 'новый',
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request
            )
            # Показываем ошибку пользователю
            django_messages.error(request, f"Ошибка при сохранении платежа: {str(e)}")
            raise  # Прерываем сохранение


# =============================================================================
# ПРИМЕР 2: Логирование в Django Admin действиях (actions)
# =============================================================================

class RentalAdmin(admin.ModelAdmin):
    """Пример логирования при массовых действиях."""
    
    actions = ['close_selected_rentals']
    
    def close_selected_rentals(self, request, queryset):
        """Массовое закрытие аренд с логированием."""
        count = queryset.count()
        
        # Используем контекстный менеджер для автоматического логирования
        with LogOperation(
            "Массовое закрытие аренд",
            user=request.user,
            details={'count': count},
            request=request
        ) as op:
            try:
                closed_ids = []
                for rental in queryset:
                    rental.status = Rental.Status.CLOSED
                    rental.save()
                    closed_ids.append(rental.id)
                
                # Добавляем результат в лог
                op.add_result({'closed_ids': closed_ids})
                
                # Уведомляем пользователя
                django_messages.success(
                    request,
                    f"Успешно закрыто аренд: {len(closed_ids)}"
                )
                
            except Exception as e:
                # Ошибка будет автоматически залогирована контекстным менеджером
                django_messages.error(request, f"Ошибка: {str(e)}")
                raise
    
    close_selected_rentals.short_description = "Закрыть выбранные аренды"


# =============================================================================
# ПРИМЕР 3: Логирование в обычных views (функциях представления)
# =============================================================================

def create_payment_view(request: HttpRequest):
    """Пример создания платежа с логированием."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST'}, status=405)
    
    try:
        # Получаем данные из запроса
        rental_id = request.POST.get('rental_id')
        amount = Decimal(request.POST.get('amount', '0'))
        
        # Валидация
        if amount <= 0:
            log_warning(
                "Попытка создать платеж с нулевой или отрицательной суммой",
                user=request.user,
                context={'rental_id': rental_id, 'amount': float(amount)},
                request=request
            )
            return JsonResponse({'error': 'Сумма должна быть положительной'}, status=400)
        
        # Получаем аренду
        rental = get_object_or_404(Rental, id=rental_id)
        
        # Создаем платеж
        payment = Payment.objects.create(
            rental=rental,
            amount=amount,
            type=Payment.PaymentType.RENT,
            created_by=request.user,
            date=timezone.now().date()
        )
        
        # Логируем успешное создание
        log_action(
            "Создан платеж через API",
            user=request.user,
            details={
                'payment_id': payment.id,
                'rental_id': rental.id,
                'client': str(rental.client),
                'amount': float(amount),
            },
            request=request
        )
        
        return JsonResponse({
            'success': True,
            'payment_id': payment.id,
            'amount': float(payment.amount)
        })
        
    except Rental.DoesNotExist:
        log_error(
            "Попытка создать платеж для несуществующей аренды",
            user=request.user,
            context={'rental_id': rental_id},
            request=request
        )
        return JsonResponse({'error': 'Аренда не найдена'}, status=404)
        
    except Exception as e:
        log_error(
            "Неожиданная ошибка при создании платежа",
            exception=e,
            user=request.user,
            context={
                'rental_id': rental_id,
                'amount': float(amount) if amount else None,
            },
            request=request
        )
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


# =============================================================================
# ПРИМЕР 4: Логирование в Django signals
# =============================================================================

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

@receiver(post_save, sender=Rental)
def log_rental_changes(sender, instance, created, **kwargs):
    """Автоматическое логирование при создании/обновлении аренды."""
    if created:
        log_action(
            "Создана новая аренда через сигнал",
            details={
                'rental_id': instance.id,
                'client': str(instance.client),
                'status': instance.get_status_display(),
                'weekly_rate': float(instance.weekly_rate or 0),
            }
        )
    else:
        # Логируем только важные изменения статуса
        if instance.status == Rental.Status.CLOSED:
            log_action(
                "Аренда закрыта",
                details={
                    'rental_id': instance.id,
                    'client': str(instance.client),
                }
            )


@receiver(pre_delete, sender=Battery)
def log_battery_deletion(sender, instance, **kwargs):
    """Логирование при удалении батареи."""
    log_warning(
        "Удаление батареи",
        context={
            'battery_id': instance.id,
            'battery_code': instance.battery_code,
            'status': instance.get_status_display(),
        }
    )


# =============================================================================
# ПРИМЕР 5: Логирование в методах модели
# =============================================================================

class RentalWithLogging(Rental):
    """Пример добавления логирования в методы модели."""
    
    class Meta:
        proxy = True  # Прокси-модель, чтобы не создавать новую таблицу
    
    def calculate_balance_with_logging(self, user=None):
        """Расчет баланса с логированием для отладки."""
        log_debug(
            "Начало расчета баланса",
            details={
                'rental_id': self.id,
                'client': str(self.client),
            }
        )
        
        try:
            # Ваша логика расчета баланса
            charges = self.calculate_charges()
            paid = self.calculate_paid()
            balance = charges - paid
            
            log_debug(
                "Расчет баланса завершен",
                details={
                    'rental_id': self.id,
                    'charges': float(charges),
                    'paid': float(paid),
                    'balance': float(balance),
                }
            )
            
            return balance
            
        except Exception as e:
            log_error(
                "Ошибка при расчете баланса",
                exception=e,
                user=user,
                context={'rental_id': self.id}
            )
            raise


# =============================================================================
# ПРИМЕР 6: Логирование длительных операций
# =============================================================================

def bulk_update_battery_status(battery_ids: list, new_status: str, user):
    """Массовое обновление статусов батарей."""
    with LogOperation(
        "Массовое обновление статусов батарей",
        user=user,
        details={
            'count': len(battery_ids),
            'new_status': new_status,
        }
    ) as op:
        updated_count = 0
        errors = []
        
        for battery_id in battery_ids:
            try:
                battery = Battery.objects.get(id=battery_id)
                old_status = battery.status
                battery.status = new_status
                battery.save()
                updated_count += 1
                
                log_debug(
                    f"Обновлен статус батареи",
                    details={
                        'battery_id': battery_id,
                        'old_status': old_status,
                        'new_status': new_status,
                    }
                )
                
            except Battery.DoesNotExist:
                error_msg = f"Батарея {battery_id} не найдена"
                errors.append(error_msg)
                log_warning(error_msg)
            except Exception as e:
                error_msg = f"Ошибка при обновлении батареи {battery_id}: {str(e)}"
                errors.append(error_msg)
                log_error(error_msg, exception=e, user=user)
        
        # Добавляем итоги в лог
        op.add_result({
            'updated': updated_count,
            'errors_count': len(errors),
        })
        
        if errors:
            log_warning(
                "Обновление завершено с ошибками",
                user=user,
                context={
                    'errors': errors[:5],  # Только первые 5 ошибок
                }
            )


# =============================================================================
# ПРИМЕР 7: Логирование в management commands
# =============================================================================

from django.core.management.base import BaseCommand

class Command(BaseCommand):
    """Пример команды с логированием."""
    help = 'Синхронизация данных с внешним источником'
    
    def handle(self, *args, **options):
        log_info("Запуск команды синхронизации данных")
        
        with LogOperation("Синхронизация данных") as op:
            try:
                # Ваша логика синхронизации
                synced_count = 0
                
                # ... код синхронизации ...
                
                op.add_result({'synced': synced_count})
                
                self.stdout.write(
                    self.style.SUCCESS(f'Успешно синхронизировано: {synced_count}')
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Ошибка: {str(e)}')
                )
                raise


# =============================================================================
# ПРИМЕР 8: Использование разных уровней логирования
# =============================================================================

def complex_operation_example(request):
    """Пример использования разных уровней логирования."""
    
    # DEBUG - детальная информация для отладки (только в DEBUG режиме)
    log_debug(
        "Начало сложной операции",
        details={'user_id': request.user.id, 'timestamp': timezone.now()}
    )
    
    # INFO - обычная информация о ходе работы
    log_info(
        "Загрузка данных из базы",
        details={'query_type': 'SELECT', 'table': 'rental'}
    )
    
    # WARNING - предупреждения о потенциальных проблемах
    if some_condition:
        log_warning(
            "Обнаружена потенциальная проблема",
            user=request.user,
            context={'issue': 'duplicate_data'}
        )
    
    # ERROR - ошибки, требующие внимания
    try:
        risky_operation()
    except Exception as e:
        log_error(
            "Критическая ошибка в операции",
            exception=e,
            user=request.user,
            context={'operation': 'risky_operation'}
        )
        # Обрабатываем ошибку...


# =============================================================================
# ЗАКЛЮЧЕНИЕ
# =============================================================================
"""
КОГДА ИСПОЛЬЗОВАТЬ КАЖДЫЙ УРОВЕНЬ ЛОГИРОВАНИЯ:

1. log_debug() - Детальная отладочная информация
   - Промежуточные значения в расчетах
   - Детали алгоритмов
   - Только для разработки (не пишется в production логи)

2. log_info() - Обычная информация о работе системы
   - Запуск/завершение процессов
   - Статистика операций
   - Успешное выполнение задач

3. log_warning() - Предупреждения о потенциальных проблемах
   - Неожиданные, но обработанные ситуации
   - Приближение к лимитам
   - Устаревшие данные

4. log_error() - Ошибки, требующие внимания
   - Исключения и ошибки
   - Неудачные операции
   - Проблемы с данными

5. log_action() - Важные действия пользователей
   - Создание/обновление/удаление данных
   - Изменение статусов
   - Финансовые операции

BEST PRACTICES:

1. Логируйте важные бизнес-операции (платежи, аренда и т.д.)
2. Логируйте все ошибки с контекстом
3. Не логируйте чувствительные данные (пароли, токены и т.д.)
4. Используйте log_debug() для отладки, но помните, что он не работает в production
5. Добавляйте достаточно контекста для понимания проблемы
6. Используйте LogOperation для длительных операций
7. Не забывайте показывать сообщения пользователю через django_messages

ВАЖНО:
- Логи автоматически ротируются (максимум 10 MB, хранится 5-10 копий)
- Логи пишутся в папку logs/ в корне проекта
- Middleware автоматически логирует все запросы
- В production DEBUG логи не пишутся
"""

