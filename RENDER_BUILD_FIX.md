# Настройка Build Command на Render.com

## Проблема: 
При `DEBUG=False` статические файлы (CSS/JS) не загружаются → "верстка поплыла"

## Решение:

### Шаг 1: Настроить Build Command на Render

1. Откройте https://dashboard.render.com → ваш проект
2. Перейдите в **Settings**
3. Найдите секцию **Build & Deploy**
4. В поле **Build Command** введите:

```bash
./build.sh
```

5. Нажмите **Save Changes**

### Шаг 2: Проверить Start Command

В поле **Start Command** должно быть:

```bash
gunicorn core.wsgi:application
```

### Что делает build.sh:

```bash
#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt    # Установка зависимостей
python manage.py collectstatic --no-input  # ← ВАЖНО! Сбор статики
python manage.py migrate           # Применение миграций
```

### Альтернатива (если build.sh не работает):

Можно прямо в **Build Command** вставить:

```bash
pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate
```

---

## После настройки:

1. Render запустит новый деплой
2. Выполнится `collectstatic` - соберёт все CSS/JS в `/staticfiles`
3. Whitenoise будет отдавать статику при `DEBUG=False`
4. Верстка восстановится ✅

---

## Проверка:

После деплоя откройте:
- `/admin/` - должна быть нормальная верстка
- В DevTools → Network → проверьте что CSS загружается (200 OK)
- URL статики должен быть вида: `/static/css/admin-phoenix.css`

---

## Важно:

- Файл `build.sh` уже создан в корне проекта
- Закоммичен и запушен в ветку `optimization`
- После настройки Build Command на Render всё заработает

