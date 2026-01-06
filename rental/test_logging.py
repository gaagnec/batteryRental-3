"""
Тестовый скрипт для проверки работы системы логирования.

Запуск:
    python manage.py shell < rental/test_logging.py
    
Или в Django shell:
    from rental.test_logging import test_logging
    test_logging()
"""

def test_logging():
    """Тестирует все функции логирования."""
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ СИСТЕМЫ ЛОГИРОВАНИЯ")
    print("="*60 + "\n")
    
    from rental.logging_utils import (
        log_action, log_error, log_warning, log_info, log_debug, LogOperation
    )
    from django.contrib.auth.models import User
    import os
    from pathlib import Path
    
    # 1. Проверка существования папки логов
    print("1. Проверка папки логов...")
    logs_dir = Path(__file__).resolve().parent.parent / 'logs'
    if logs_dir.exists():
        print(f"   ✅ Папка логов существует: {logs_dir}")
    else:
        print(f"   ❌ Папка логов НЕ существует: {logs_dir}")
        return
    
    # 2. Тест log_info
    print("\n2. Тестирование log_info()...")
    try:
        log_info("Тестовое информационное сообщение", details={'test': 'value'})
        print("   ✅ log_info() работает")
    except Exception as e:
        print(f"   ❌ Ошибка в log_info(): {e}")
    
    # 3. Тест log_debug
    print("\n3. Тестирование log_debug()...")
    try:
        log_debug("Тестовое отладочное сообщение", details={'debug': 'data'})
        print("   ✅ log_debug() работает")
    except Exception as e:
        print(f"   ❌ Ошибка в log_debug(): {e}")
    
    # 4. Тест log_warning
    print("\n4. Тестирование log_warning()...")
    try:
        log_warning("Тестовое предупреждение", context={'warning': 'test'})
        print("   ✅ log_warning() работает")
    except Exception as e:
        print(f"   ❌ Ошибка в log_warning(): {e}")
    
    # 5. Тест log_error
    print("\n5. Тестирование log_error()...")
    try:
        test_exception = ValueError("Тестовая ошибка для логирования")
        log_error(
            "Тестовая ошибка",
            exception=test_exception,
            context={'error': 'test'},
            include_traceback=False
        )
        print("   ✅ log_error() работает")
    except Exception as e:
        print(f"   ❌ Ошибка в log_error(): {e}")
    
    # 6. Тест log_action
    print("\n6. Тестирование log_action()...")
    try:
        # Пытаемся получить первого пользователя
        try:
            user = User.objects.first()
        except:
            user = None
        
        log_action(
            "Тестовое действие",
            user=user,
            details={'action': 'test', 'test_id': 123}
        )
        print("   ✅ log_action() работает")
    except Exception as e:
        print(f"   ❌ Ошибка в log_action(): {e}")
    
    # 7. Тест LogOperation
    print("\n7. Тестирование LogOperation контекстного менеджера...")
    try:
        with LogOperation("Тестовая операция", details={'op': 'test'}) as op:
            # Имитация работы
            result_data = {'processed': 10, 'success': True}
            op.add_result(result_data)
        print("   ✅ LogOperation работает")
    except Exception as e:
        print(f"   ❌ Ошибка в LogOperation: {e}")
    
    # 8. Тест LogOperation с ошибкой
    print("\n8. Тестирование LogOperation с исключением...")
    try:
        with LogOperation("Операция с ошибкой", details={'op': 'error_test'}):
            raise ValueError("Тестовая ошибка внутри операции")
    except ValueError:
        print("   ✅ LogOperation корректно обрабатывает исключения")
    except Exception as e:
        print(f"   ❌ Неожиданная ошибка: {e}")
    
    # 9. Проверка файлов логов
    print("\n9. Проверка созданных файлов логов...")
    log_files = {
        'general.log': logs_dir / 'general.log',
        'errors.log': logs_dir / 'errors.log',
        'actions.log': logs_dir / 'actions.log',
    }
    
    for name, path in log_files.items():
        if path.exists():
            size = path.stat().st_size
            print(f"   ✅ {name} существует ({size} байт)")
        else:
            print(f"   ⚠️  {name} не найден (возможно, еще не создан)")
    
    # 10. Показываем последние записи из логов
    print("\n10. Последние записи из логов:")
    print("-" * 60)
    
    for name, path in log_files.items():
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    last_lines = lines[-3:] if len(lines) >= 3 else lines
                    if last_lines:
                        print(f"\n{name}:")
                        for line in last_lines:
                            print(f"  {line.rstrip()}")
            except Exception as e:
                print(f"  ❌ Ошибка чтения {name}: {e}")
    
    # Итоги
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("="*60)
    print("\nПроверьте файлы в папке logs/ для подтверждения:")
    print(f"  - {logs_dir / 'general.log'}")
    print(f"  - {logs_dir / 'errors.log'}")
    print(f"  - {logs_dir / 'actions.log'}")
    print("\nИспользуйте команды для просмотра:")
    print("  Windows: Get-Content logs\\general.log -Tail 20")
    print("  Linux/Mac: tail -20 logs/general.log")
    print("\n")


if __name__ == '__main__':
    test_logging()

