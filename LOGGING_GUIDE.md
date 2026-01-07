# Руководство по системе логирования

## Обзор

Система логирования настроена для отслеживания всех важных событий, ошибок и действий пользователей в приложении аренды батарей.

## Структура логов

Все логи сохраняются в папку `logs/` в корне проекта:

### Файлы логов

1. **`general.log`** - Общие логи приложения
   - Уровень: INFO и выше
   - Размер: до 10 MB, хранится 5 копий
   - Содержит: обычную работу системы, информационные сообщения

2. **`errors.log`** - Логи ошибок
   - Уровень: ERROR и выше
   - Размер: до 10 MB, хранится 10 копий
   - Содержит: все ошибки и исключения с детальным трейсбеком

3. **`actions.log`** - Логи действий пользователей
   - Уровень: INFO и выше
   - Размер: до 10 MB, хранится 5 копий
   - Содержит: важные действия (создание платежей, изменение статусов и т.д.)

4. **`sql.log`** - SQL запросы (только в DEBUG режиме)
   - Уровень: DEBUG
   - Размер: до 50 MB, хранится 3 копии
   - Содержит: все SQL запросы для оптимизации производительности

## Автоматическое логирование

### Middleware

Система автоматически логирует все HTTP запросы через `RequestLoggingMiddleware`:

- ✅ Все POST/PUT/DELETE/PATCH запросы (действия изменения данных)
- ✅ Медленные запросы (> 3 секунд)
- ✅ Ошибки сервера (5xx)
- ✅ Ошибки клиента (4xx) - важные или в DEBUG режиме
- ✅ IP адреса и информация о пользователях
- ✅ Время обработки каждого запроса

### Что логируется автоматически

```
2026-01-06 15:30:25 [INFO] rental.actions - ДЕЙСТВИЕ: POST /admin/rental/payment/add/ | Статус: 302 | Время: 0.15с | IP: 192.168.1.1 | Пользователь: Иван Иванов (ID: 1)
```

## Ручное логирование

### Импорт утилит

```python
from rental.logging_utils import (
    log_action,      # Логирование действий пользователей
    log_error,       # Логирование ошибок
    log_warning,     # Логирование предупреждений
    log_info,        # Логирование информации
    log_debug,       # Логирование отладочной информации
    LogOperation,    # Контекстный менеджер для операций
)
```

### Базовое использование

#### 1. Логирование действий пользователя

```python
log_action(
    "Создан новый платеж",
    user=request.user,
    details={
        'payment_id': payment.id,
        'amount': 500.00,
        'type': 'RENT'
    },
    request=request
)
```

Результат в `actions.log`:
```
2026-01-06 15:30:25 [INFO] rental.actions - Создан новый платеж | Пользователь: Иван Иванов (ID: 1) | IP: 192.168.1.1 | payment_id: 123 | amount: 500.0 | type: RENT
```

#### 2. Логирование ошибок

```python
try:
    rental.calculate_balance()
except Exception as e:
    log_error(
        "Ошибка при расчете баланса",
        exception=e,
        user=request.user,
        context={'rental_id': rental.id},
        request=request
    )
```

Результат в `errors.log`:
```
2026-01-06 15:30:25 [ERROR] rental - ОШИБКА: Ошибка при расчете баланса
Пользователь: Иван Иванов (ID: 1)
Запрос: POST /admin/rental/rental/123/change/ | IP: 192.168.1.1
Контекст: rental_id: 123
Исключение: ValueError: Invalid rental status

Трейсбек:
Traceback (most recent call last):
  File "rental/views.py", line 45, in dashboard
    rental.calculate_balance()
ValueError: Invalid rental status
```

#### 3. Логирование предупреждений

```python
if battery_rental_days > 90:
    log_warning(
        "Батарея в аренде слишком долго",
        user=request.user,
        context={
            'battery_id': battery.id,
            'days': battery_rental_days,
            'client': str(client)
        },
        request=request
    )
```

#### 4. Информационные логи

```python
log_info(
    "Запущена синхронизация данных",
    details={'count': 150, 'source': 'external_api'}
)
```

#### 5. Отладочные логи (только в DEBUG режиме)

```python
log_debug(
    "Расчет баланса",
    details={
        'charges': 1500.00,
        'paid': 1000.00,
        'balance': -500.00
    }
)
```

### Контекстный менеджер для операций

Для длительных операций используйте `LogOperation`:

```python
with LogOperation(
    "Массовое обновление статусов батарей",
    user=request.user,
    details={'count': 50}
) as op:
    updated_count = 0
    for battery in batteries:
        battery.status = 'AVAILABLE'
        battery.save()
        updated_count += 1
    
    # Добавляем результат
    op.add_result({'updated': updated_count})
```

Это автоматически залогирует:
1. Начало операции
2. Завершение операции с результатами
3. Ошибку, если она произойдет (с трейсбеком)

## Интеграция в существующий код

### В Django Admin

```python
class PaymentAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        try:
            action = "Обновлён платеж" if change else "Создан новый платеж"
            super().save_model(request, obj, form, change)
            
            log_action(
                action,
                user=request.user,
                details={
                    'payment_id': obj.id,
                    'amount': float(obj.amount),
                },
                request=request
            )
            messages.success(request, f"{action} успешно")
            
        except Exception as e:
            log_error(
                "Ошибка при сохранении платежа",
                exception=e,
                user=request.user,
                request=request
            )
            messages.error(request, f"Ошибка: {str(e)}")
            raise
```

### В Views

```python
def create_payment(request):
    try:
        payment = Payment.objects.create(
            rental=rental,
            amount=amount,
            created_by=request.user
        )
        
        log_action(
            "Создан платеж",
            user=request.user,
            details={'payment_id': payment.id, 'amount': float(amount)},
            request=request
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        log_error(
            "Ошибка при создании платежа",
            exception=e,
            user=request.user,
            context={'amount': float(amount)},
            request=request
        )
        return JsonResponse({'error': str(e)}, status=500)
```

### В Signals

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Rental)
def log_rental_changes(sender, instance, created, **kwargs):
    if created:
        log_action(
            "Создана новая аренда",
            details={
                'rental_id': instance.id,
                'client': str(instance.client),
            }
        )
```

### В Management Commands

```python
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, *args, **options):
        log_info("Запуск команды синхронизации")
        
        with LogOperation("Синхронизация данных") as op:
            # Ваша логика
            synced = do_sync()
            op.add_result({'synced': synced})
```

## Уровни логирования

### Когда использовать каждый уровень

| Уровень | Когда использовать | Пример |
|---------|-------------------|--------|
| **DEBUG** | Детальная отладочная информация (не логируется в production) | Промежуточные значения в расчетах |
| **INFO** | Обычная информация о работе системы | Запуск процессов, успешные операции |
| **WARNING** | Предупреждения о потенциальных проблемах | Неожиданные ситуации, приближение к лимитам |
| **ERROR** | Ошибки, требующие внимания | Исключения, неудачные операции |
| **ACTION** | Важные действия пользователей | Создание/обновление данных, изменение статусов |

## Best Practices

### ✅ Хорошие практики

1. **Всегда логируйте важные бизнес-операции**
   ```python
   log_action("Создан платеж", user=request.user, details={'amount': 500})
   ```

2. **Логируйте ошибки с контекстом**
   ```python
   log_error("Ошибка расчета", exception=e, context={'rental_id': 123})
   ```

3. **Используйте LogOperation для сложных операций**
   ```python
   with LogOperation("Импорт данных", user=request.user) as op:
       # код
       op.add_result({'imported': count})
   ```

4. **Добавляйте достаточно информации для диагностики**
   ```python
   log_error("Платеж не создан", context={
       'rental_id': rental.id,
       'amount': amount,
       'user_balance': balance
   })
   ```

5. **Используйте соответствующие уровни**
   ```python
   log_debug("Промежуточный результат: X")  # Только для разработки
   log_info("Процесс завершен успешно")     # Обычная информация
   log_warning("Батарея в аренде 90+ дней") # Предупреждение
   log_error("Ошибка соединения с БД")       # Ошибка
   ```

### ❌ Плохие практики

1. **НЕ логируйте чувствительные данные**
   ```python
   # ПЛОХО:
   log_action("Вход", details={'password': password})
   
   # ХОРОШО:
   log_action("Вход", user=user)
   ```

2. **НЕ логируйте слишком много в циклах**
   ```python
   # ПЛОХО:
   for item in items:  # 10000 items
       log_info(f"Обработка {item}")
   
   # ХОРОШО:
   log_info(f"Начало обработки {len(items)} элементов")
   # ... обработка ...
   log_info(f"Обработано {processed} элементов")
   ```

3. **НЕ игнорируйте ошибки без логирования**
   ```python
   # ПЛОХО:
   try:
       risky_operation()
   except:
       pass  # Молча игнорируем
   
   # ХОРОШО:
   try:
       risky_operation()
   except Exception as e:
       log_error("Ошибка в операции", exception=e)
       # Обработка ошибки
   ```

## Мониторинг логов

### Просмотр логов в реальном времени

```bash
# Linux/Mac
tail -f logs/general.log
tail -f logs/errors.log
tail -f logs/actions.log

# Windows PowerShell
Get-Content logs\general.log -Wait
Get-Content logs\errors.log -Wait
```

### Поиск в логах

```bash
# Найти все ошибки за сегодня
grep "2026-01-06" logs/errors.log

# Найти действия конкретного пользователя
grep "Иван Иванов" logs/actions.log

# Найти медленные запросы
grep "МЕДЛЕННЫЙ ЗАПРОС" logs/general.log

# Подсчет ошибок
grep -c "ERROR" logs/errors.log
```

### Анализ производительности

```bash
# SQL запросы (в DEBUG режиме)
tail -f logs/sql.log

# Медленные запросы
grep "МЕДЛЕННЫЙ" logs/general.log
```

## Production настройки

### Переменные окружения

```bash
# Установите DEBUG=False для production
export DEBUG=False
```

В production:
- DEBUG логи не пишутся
- SQL запросы не логируются
- Только WARNING и ERROR попадают в логи Django
- Все настройки из settings.py применяются автоматически

### Ротация логов

Логи автоматически ротируются:
- При достижении максимального размера создается новый файл
- Старые файлы переименовываются (`.log.1`, `.log.2` и т.д.)
- Хранится ограниченное количество старых версий

### Мониторинг в production

Рекомендуется настроить мониторинг логов ошибок:

1. **Установите оповещения** при появлении ERROR в логах
2. **Регулярно проверяйте** `errors.log`
3. **Анализируйте** медленные запросы
4. **Архивируйте** старые логи

## Примеры реальных сценариев

См. файл `rental/logging_examples.py` для детальных примеров интеграции в:
- Django Admin
- Views
- Signals
- Management Commands
- Models
- И многое другое

## Поддержка

При возникновении проблем с логированием:
1. Проверьте права доступа к папке `logs/`
2. Убедитесь, что папка `logs/` существует
3. Проверьте настройки в `core/settings.py`
4. Посмотрите примеры в `rental/logging_examples.py`

## Заключение

Система логирования настроена и готова к использованию. Просто импортируйте нужные функции из `rental.logging_utils` и начните логировать важные события в вашем приложении!

**Главное правило**: Логируйте все, что поможет вам понять, что происходит в системе и быстро найти проблему.

