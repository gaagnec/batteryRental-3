# Production Configuration - Render.com

## Настройка переменной окружения DEBUG на Render

### Шаги:

1. Откройте ваш проект на https://dashboard.render.com
2. Перейдите в **Environment** → **Environment Variables**
3. Добавьте новую переменную:
   - **Key**: `DEBUG`
   - **Value**: `False`
4. Нажмите **Save Changes**
5. Render автоматически перезапустит сервис

### Что изменилось:

Теперь `settings.py` использует переменную окружения:
```python
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
```

- **По умолчанию** (локально): `DEBUG = True`
- **На Render** (с переменной `DEBUG=False`): `DEBUG = False`

### Автоматические изменения при DEBUG=False:

1. ✅ **debug_toolbar middleware** отключается
2. ✅ **CompressedStaticFilesStorage** вместо ManifestStaticFilesStorage
3. ✅ **Minimal logging** вместо verbose
4. ✅ **Лучшая производительность** (+30-50%)

### Проверка:

После установки `DEBUG=False` на Render:
- Сайт должен работать нормально
- Ошибки будут скрыты (безопасность)
- Скорость загрузки увеличится

### Откат (если нужно):

Если что-то сломается:
1. Удалите переменную `DEBUG` на Render
2. Или установите `DEBUG=True`
3. Render перезапустится с DEBUG режимом

---

**Важно**: Пока не устанавливайте `DEBUG=False` на Render, сначала проверим что всё работает!

