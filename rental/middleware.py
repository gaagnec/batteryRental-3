"""
Middleware для логирования HTTP запросов и ответов.

Автоматически логирует:
- Медленные запросы (> 3 секунд)
- Ошибки (5xx)
- Предупреждения (4xx)
- Важные действия (POST, PUT, DELETE, PATCH)
"""

import logging
import time
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpRequest, HttpResponse


logger = logging.getLogger('rental')
actions_logger = logging.getLogger('rental.actions')


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware для логирования HTTP запросов и ответов.
    
    Логирует:
    - Все POST/PUT/DELETE/PATCH запросы как действия
    - Медленные запросы (> 3 сек) как предупреждения
    - Ошибки 5xx как errors
    - Ошибки 4xx как warnings (только в DEBUG режиме)
    """
    
    # Время в секундах, после которого запрос считается медленным
    SLOW_REQUEST_THRESHOLD = 3.0
    
    def process_request(self, request: HttpRequest):
        """Сохраняем время начала обработки запроса."""
        request._start_time = time.time()
        return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse):
        """Логируем информацию о запросе после его обработки."""
        if not hasattr(request, '_start_time'):
            return response
        
        # Вычисляем время обработки
        duration = time.time() - request._start_time
        
        # Получаем информацию о запросе
        method = request.method
        path = request.path
        status_code = response.status_code
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        ip = self._get_client_ip(request)
        
        # Формируем базовое сообщение
        user_info = f"{user.get_full_name() or user.username} (ID: {user.id})" if user else "Анонимный"
        message = f"{method} {path} | Статус: {status_code} | Время: {duration:.2f}с | IP: {ip} | Пользователь: {user_info}"
        
        # Логируем в зависимости от типа запроса и статуса
        if status_code >= 500:
            # Серверные ошибки
            logger.error(f"ОШИБКА СЕРВЕРА: {message}")
        elif status_code >= 400:
            # Клиентские ошибки (только важные или в DEBUG)
            if status_code in [401, 403, 404] or request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                logger.warning(f"ОШИБКА КЛИЕНТА: {message}")
        elif method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Важные действия (изменение данных)
            actions_logger.info(f"ДЕЙСТВИЕ: {message}")
            # Дополнительно логируем данные POST (если не слишком большие и не содержат паролей)
            if method == 'POST' and request.POST:
                # Фильтруем чувствительные данные
                safe_data = {k: v for k, v in request.POST.items() 
                            if not any(sensitive in k.lower() 
                                     for sensitive in ['password', 'token', 'secret', 'csrf'])}
                if safe_data and len(str(safe_data)) < 500:
                    actions_logger.debug(f"POST данные: {safe_data}")
        
        # Логируем медленные запросы
        if duration > self.SLOW_REQUEST_THRESHOLD:
            logger.warning(f"МЕДЛЕННЫЙ ЗАПРОС: {message}")
        
        return response
    
    def process_exception(self, request: HttpRequest, exception: Exception):
        """Логируем необработанные исключения."""
        method = request.method
        path = request.path
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        ip = self._get_client_ip(request)
        
        user_info = f"{user.get_full_name() or user.username} (ID: {user.id})" if user else "Анонимный"
        
        logger.error(
            f"НЕОБРАБОТАННОЕ ИСКЛЮЧЕНИЕ:\n"
            f"Запрос: {method} {path}\n"
            f"Пользователь: {user_info}\n"
            f"IP: {ip}\n"
            f"Исключение: {type(exception).__name__}: {str(exception)}",
            exc_info=True  # Добавляет полный traceback
        )
        
        return None  # Позволяем Django обработать исключение стандартным образом
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получает IP адрес клиента."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        return ip

