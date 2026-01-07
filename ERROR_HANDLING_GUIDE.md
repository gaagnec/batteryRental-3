# Руководство по обработке ошибок

## Обзор системы

Система обработки ошибок полностью интегрирована с системой логирования и автоматически показывает дружелюбные сообщения пользователям.

## Что работает автоматически

### 1. Автоматическая обработка через Middleware

Middleware (`rental/middleware.py`) автоматически:
- ✅ Логирует все необработанные исключения
- ✅ Показывает дружелюбные сообщения пользователям
- ✅ Разделяет сообщения для админов и обычных пользователей

**Для администраторов:**
```
Ошибка: ValueError: Invalid rental status
```

**Для обычных пользователей:**
```
Произошла ошибка при обработке запроса. Мы уже работаем над её устранением.
```

### 2. Кастомные страницы ошибок

Созданы красивые страницы для:
- **500.html** - внутренние ошибки сервера
- **404.html** - страница не найдена
- **403.html** - доступ запрещён

Эти страницы автоматически показываются Django при соответствующих ошибках.

### 3. Обработка в критичных местах

Добавлена полная обработка ошибок в:
- **PaymentAdmin** - платежи
- **MoneyTransferAdmin** - денежные переводы  
- **ExpenseAdmin** - расходы
- **FinancePartnerAdmin** - финансовые партнёры
- **OwnerWithdrawalAdmin** - выводы владельцев
- **dashboard()** - главный дашборд
- **load_more_investments()** - загрузка инвестиций

## Как это работает на практике

### Пример 1: Создание платежа

#### Успешное создание:
```
Пользователь создаёт платёж → 
Сохраняется в БД → 
Показывается зелёное сообщение: "Создан новый платёж успешно (ID: 123, сумма: 500 PLN)" →
Логируется в actions.log
```

#### Ошибка валидации:
```
Пользователь создаёт платёж с некорректными данными →
Возникает ValidationError →
Показывается красное сообщение: "amount: Сумма должна быть положительной" →
Логируется в errors.log →
Платёж НЕ сохраняется
```

#### Критическая ошибка:
```
Пользователь создаёт платёж →
Возникает неожиданная ошибка (например, проблема с БД) →
Показывается красное сообщение: "Ошибка при сохранении платежа: ..." →
Логируется в errors.log с полным traceback →
Платёж НЕ сохраняется
```

### Пример 2: Крупные суммы

При создании платежа > 5000 PLN:
```
Платёж сохраняется успешно →
Показывается зелёное сообщение об успехе →
Дополнительно логируется WARNING в logs/general.log для отслеживания
```

### Пример 3: Необработанная ошибка на сайте

```
Пользователь открывает страницу →
Возникает неожиданная ошибка →
Middleware перехватывает её →
Логирует в errors.log →
Показывает дружелюбное сообщение пользователю (через messages) →
Django показывает страницу 500.html или перенаправляет обратно
```

## Уровни обработки ошибок

### Уровень 1: Валидация (самый ранний)

Перехватывается: `ValidationError`

```python
try:
    obj.full_clean()
    super().save_model(request, obj, form, change)
except ValidationError as e:
    # Показываем конкретные ошибки валидации
    for field, errors in e.error_dict.items():
        for error in errors:
            messages.error(request, f"{field}: {error}")
    
    log_error(..., include_traceback=False)
    raise  # Прерываем сохранение
```

**Результат для пользователя:**
- Красное сообщение с описанием проблемы
- Форма не сохраняется
- Можно исправить и попробовать снова

### Уровень 2: Ожидаемые ошибки

Перехватывается: конкретные типы ошибок (ValueError, DoesNotExist и т.д.)

```python
try:
    offset = int(request.GET.get('offset', 10))
except ValueError as e:
    log_error("Ошибка парсинга параметра offset", ...)
    return HttpResponse("Ошибка: некорректный параметр", status=400)
```

**Результат для пользователя:**
- Понятное сообщение об ошибке
- Подсказка, что делать дальше

### Уровень 3: Неожиданные ошибки

Перехватывается: `Exception` (все остальные ошибки)

```python
try:
    # Основная логика
    super().save_model(request, obj, form, change)
except Exception as e:
    messages.error(request, f"Ошибка: {str(e)}")
    log_error("Критическая ошибка", exception=e, ...)
    raise  # Пробрасываем дальше
```

**Результат для пользователя:**
- Сообщение об ошибке (для админов - детали, для пользователей - общее)
- Ошибка залогирована с полным traceback
- Можно связаться с поддержкой

### Уровень 4: Middleware (последний рубеж)

Перехватывает: все необработанные исключения

```python
def process_exception(self, request, exception):
    logger.error("НЕОБРАБОТАННОЕ ИСКЛЮЧЕНИЕ", exc_info=True)
    
    if user.is_staff:
        messages.error(request, f"Ошибка: {exception}")
    else:
        messages.error(request, "Произошла ошибка...")
    
    return None  # Django покажет страницу 500.html
```

**Результат для пользователя:**
- Дружелюбное сообщение
- Кастомная страница 500.html
- Ошибка залогирована

## Типы сообщений пользователям

### ✅ Успешные действия (зелёные)

```python
messages.success(request, "Создан новый платёж успешно (ID: 123)")
```

**Когда использовать:**
- Успешное создание/обновление/удаление
- Завершение длительных операций
- Подтверждение важных действий

### ⚠️ Предупреждения (жёлтые)

```python
messages.warning(request, "Обнаружена крупная сумма платежа")
```

**Когда использовать:**
- Необычные, но корректные ситуации
- Предупреждения о потенциальных проблемах
- Рекомендации пользователю

### ❌ Ошибки (красные)

```python
messages.error(request, "Ошибка при сохранении: сумма должна быть положительной")
```

**Когда использовать:**
- Ошибки валидации
- Некорректные данные
- Любые ошибки, требующие действий пользователя

### ℹ️ Информационные (синие)

```python
messages.info(request, "Платёж находится на рассмотрении")
```

**Когда использовать:**
- Информация о статусе
- Нейтральные уведомления
- Подсказки пользователю

## Примеры использования в своём коде

### Пример 1: Добавить обработку в новый Admin класс

```python
class MyModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        from .logging_utils import log_action, log_error
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        
        try:
            # Сохраняем объект
            super().save_model(request, obj, form, change)
            
            # Логируем успех
            log_action(
                "Создан/обновлён объект",
                user=request.user,
                details={'id': obj.id, 'name': str(obj)},
                request=request
            )
            
            # Показываем сообщение пользователю
            messages.success(request, f"Объект успешно сохранён (ID: {obj.id})")
            
        except ValidationError as e:
            # Ошибки валидации
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
            log_error(
                "Ошибка валидации",
                exception=e,
                user=request.user,
                request=request,
                include_traceback=False
            )
            raise
            
        except Exception as e:
            # Любые другие ошибки
            messages.error(request, f"Ошибка при сохранении: {str(e)}")
            
            log_error(
                "Критическая ошибка",
                exception=e,
                user=request.user,
                request=request
            )
            raise
```

### Пример 2: Добавить обработку в View

```python
def my_view(request):
    from .logging_utils import log_action, log_error
    from django.contrib import messages
    
    try:
        # Ваша логика
        result = process_something()
        
        log_action(
            "Выполнено действие",
            user=request.user,
            details={'result': result},
            request=request
        )
        
        messages.success(request, "Операция выполнена успешно!")
        return redirect('success_page')
        
    except ValueError as e:
        # Ожидаемая ошибка
        messages.error(request, f"Некорректные данные: {str(e)}")
        log_error("Ошибка валидации данных", exception=e, user=request.user, request=request)
        return redirect('form_page')
        
    except Exception as e:
        # Неожиданная ошибка
        messages.error(request, "Произошла ошибка. Попробуйте позже.")
        log_error("Критическая ошибка в представлении", exception=e, user=request.user, request=request)
        return redirect('error_page')
```

### Пример 3: Добавить обработку в Action

```python
def my_action(self, request, queryset):
    from .logging_utils import LogOperation, log_warning
    from django.contrib import messages
    
    count = queryset.count()
    
    with LogOperation(
        "Массовое действие",
        user=request.user,
        details={'count': count},
        request=request
    ) as op:
        try:
            success = 0
            errors = []
            
            for obj in queryset:
                try:
                    obj.process()
                    success += 1
                except Exception as e:
                    errors.append(f"{obj}: {str(e)}")
            
            op.add_result({'success': success, 'errors': len(errors)})
            
            # Показываем результат
            if success > 0:
                messages.success(request, f"Обработано объектов: {success}")
            
            if errors:
                for error in errors[:5]:  # Первые 5 ошибок
                    messages.error(request, error)
                
                if len(errors) > 5:
                    messages.warning(request, f"И ещё {len(errors) - 5} ошибок...")
            
        except Exception as e:
            # Критическая ошибка, которая остановила весь процесс
            messages.error(request, f"Критическая ошибка: {str(e)}")
            raise

my_action.short_description = "Выполнить действие"
```

## Best Practices

### ✅ Хорошие практики

1. **Всегда показывайте результат действия**
   ```python
   messages.success(request, "Готово!")  # ✅
   ```

2. **Логируйте ошибки даже если показали сообщение**
   ```python
   messages.error(request, "Ошибка")
   log_error(..., exception=e)  # ✅ Важно для отладки
   ```

3. **Разные сообщения для разных типов ошибок**
   ```python
   except ValidationError as e:
       messages.error(request, f"Проверьте данные: {e}")  # ✅ Конкретно
   except Exception as e:
       messages.error(request, "Ошибка сервера")  # ✅ Общее
   ```

4. **Используйте include_traceback=False для валидации**
   ```python
   log_error(..., include_traceback=False)  # ✅ Не нужен traceback
   ```

5. **Добавляйте контекст в логи**
   ```python
   log_error(..., context={'payment_id': 123, 'amount': 500})  # ✅
   ```

### ❌ Плохие практики

1. **Молча игнорировать ошибки**
   ```python
   try:
       risky_operation()
   except:
       pass  # ❌ Никто не узнает об ошибке!
   ```

2. **Не показывать результат действия**
   ```python
   obj.save()
   return redirect('list')  # ❌ Пользователь не знает, успешно ли
   ```

3. **Показывать технические детали обычным пользователям**
   ```python
   messages.error(request, f"Traceback: {traceback.format_exc()}")  # ❌
   ```

4. **Не логировать ошибки**
   ```python
   except Exception as e:
       messages.error(request, str(e))
       # ❌ Не залогировано - не найдём в логах
   ```

## Мониторинг ошибок

### Проверка логов ошибок

```powershell
# Windows PowerShell
Get-Content logs\errors.log -Tail 50

# В реальном времени
Get-Content logs\errors.log -Wait

# Поиск критических ошибок
Select-String -Pattern "Критическая ошибка" -Path logs\errors.log
```

### Анализ частых ошибок

```powershell
# Подсчёт ошибок по типу
Select-String -Pattern "Ошибка" -Path logs\errors.log | 
    Group-Object Line | 
    Sort-Object Count -Descending | 
    Select-Object Count, Name -First 10
```

### Алерты (рекомендуется для production)

Настройте мониторинг для:
- Появления ERROR в `errors.log`
- Частых ошибок одного типа (> 10 за час)
- Критических ошибок в финансовых операциях
- Ошибок 500 на сайте

## Тестирование обработки ошибок

### 1. Тест валидации

В админке попробуйте создать объект с некорректными данными:
- Отрицательная сумма платежа
- Модератор без города
- Дата в будущем (если есть валидация)

**Ожидаемый результат:**
- Красное сообщение с описанием проблемы
- Объект не сохранён
- Ошибка в `errors.log` без traceback

### 2. Тест критической ошибки

Временно добавьте в код:
```python
def save_model(self, request, obj, form, change):
    raise ValueError("Тестовая ошибка")
```

**Ожидаемый результат:**
- Красное сообщение об ошибке
- Объект не сохранён
- Ошибка в `errors.log` С traceback

### 3. Тест страницы 404

Откройте несуществующую страницу: `/admin/nonexistent/`

**Ожидаемый результат:**
- Красивая страница 404.html
- Предложения что делать
- Ошибка залогирована

## Связь с системой логирования

Обработка ошибок полностью интегрирована с системой логирования:

| Действие | Сообщение пользователю | Лог | Файл |
|----------|----------------------|-----|------|
| Успешное сохранение | ✅ Зелёное сообщение | INFO | actions.log, general.log |
| Ошибка валидации | ❌ Красное сообщение | ERROR | errors.log, general.log |
| Критическая ошибка | ❌ Красное сообщение | ERROR | errors.log, general.log |
| Предупреждение | ⚠️ Жёлтое сообщение | WARNING | general.log |
| Необработанная ошибка | ❌ Сообщение через messages или 500.html | ERROR | errors.log |

## Заключение

Система обработки ошибок обеспечивает:
- ✅ Дружелюбные сообщения для пользователей
- ✅ Детальные логи для разработчиков
- ✅ Автоматическую обработку большинства ошибок
- ✅ Красивые страницы ошибок
- ✅ Легкую интеграцию в новый код

Для дополнительной информации см.:
- `LOGGING_GUIDE.md` - система логирования
- `rental/logging_examples.py` - примеры кода
- `rental/middleware.py` - автоматическая обработка

