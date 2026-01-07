"""
Утилиты для логирования действий и ошибок в системе аренды батарей.

Этот модуль предоставляет удобные функции для логирования различных типов событий:
- Успешные действия пользователей
- Ошибки и исключения
- Важные системные события
- Изменения данных

Примеры использования см. в документации функций.
"""

import logging
import traceback
from typing import Optional, Dict, Any
from django.contrib.auth.models import User
from django.http import HttpRequest


# Создаем логгеры для разных типов событий
general_logger = logging.getLogger('rental')
actions_logger = logging.getLogger('rental.actions')


def log_action(
    action: str,
    user: Optional[User] = None,
    details: Optional[Dict[str, Any]] = None,
    level: str = 'info',
    request: Optional[HttpRequest] = None
):
    """
    Логирует действие пользователя в системе.
    
    Args:
        action: Описание действия (например, "Создан новый платеж")
        user: Пользователь, выполнивший действие
        details: Дополнительные детали (словарь с данными)
        level: Уровень логирования ('debug', 'info', 'warning', 'error')
        request: HTTP запрос (для получения IP и других данных)
    
    Примеры:
        >>> log_action("Создан платеж", user=request.user, details={
        ...     'rental_id': 123,
        ...     'amount': 500.00,
        ...     'type': 'RENT'
        ... })
        
        >>> log_action("Завершена аренда", user=request.user, details={
        ...     'rental_id': 123,
        ...     'client': 'Иван Иванов',
        ...     'duration_days': 30
        ... })
    """
    # Формируем сообщение
    message_parts = [action]
    
    if user:
        username = user.get_full_name() or user.username
        message_parts.append(f"| Пользователь: {username} (ID: {user.id})")
    
    if request:
        ip = get_client_ip(request)
        if ip:
            message_parts.append(f"| IP: {ip}")
    
    if details:
        details_str = " | ".join([f"{k}: {v}" for k, v in details.items()])
        message_parts.append(f"| {details_str}")
    
    message = " ".join(message_parts)
    
    # Логируем на нужном уровне
    log_func = getattr(actions_logger, level.lower(), actions_logger.info)
    log_func(message)


def log_error(
    error_message: str,
    exception: Optional[Exception] = None,
    user: Optional[User] = None,
    context: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
    include_traceback: bool = True
):
    """
    Логирует ошибку с подробной информацией.
    
    Args:
        error_message: Описание ошибки
        exception: Объект исключения (если есть)
        user: Пользователь, при действиях которого произошла ошибка
        context: Контекст ошибки (дополнительные данные)
        request: HTTP запрос
        include_traceback: Включать ли трейсбек в лог
    
    Примеры:
        >>> try:
        ...     rental.calculate_balance()
        ... except Exception as e:
        ...     log_error(
        ...         "Ошибка при расчете баланса",
        ...         exception=e,
        ...         user=request.user,
        ...         context={'rental_id': rental.id}
        ...     )
        
        >>> log_error(
        ...     "Недостаточно батарей на складе",
        ...     context={'requested': 5, 'available': 3},
        ...     user=request.user
        ... )
    """
    message_parts = [f"ОШИБКА: {error_message}"]
    
    if user:
        username = user.get_full_name() or user.username
        message_parts.append(f"Пользователь: {username} (ID: {user.id})")
    
    if request:
        ip = get_client_ip(request)
        path = request.path
        method = request.method
        message_parts.append(f"Запрос: {method} {path} | IP: {ip}")
    
    if context:
        context_str = " | ".join([f"{k}: {v}" for k, v in context.items()])
        message_parts.append(f"Контекст: {context_str}")
    
    if exception:
        message_parts.append(f"Исключение: {type(exception).__name__}: {str(exception)}")
    
    message = "\n".join(message_parts)
    
    if include_traceback and exception:
        tb = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        message += f"\n\nТрейсбек:\n{tb}"
    
    general_logger.error(message)


def log_warning(
    warning_message: str,
    user: Optional[User] = None,
    context: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None
):
    """
    Логирует предупреждение.
    
    Args:
        warning_message: Текст предупреждения
        user: Пользователь
        context: Контекст
        request: HTTP запрос
    
    Примеры:
        >>> log_warning(
        ...     "Батарея в аренде уже 90 дней",
        ...     context={'battery_id': 123, 'client': 'Иван Иванов'}
        ... )
        
        >>> log_warning(
        ...     "Попытка создать дубликат платежа",
        ...     user=request.user,
        ...     context={'rental_id': 456, 'amount': 500}
        ... )
    """
    message_parts = [f"ПРЕДУПРЕЖДЕНИЕ: {warning_message}"]
    
    if user:
        username = user.get_full_name() or user.username
        message_parts.append(f"Пользователь: {username} (ID: {user.id})")
    
    if request:
        ip = get_client_ip(request)
        message_parts.append(f"IP: {ip}")
    
    if context:
        context_str = " | ".join([f"{k}: {v}" for k, v in context.items()])
        message_parts.append(f"Контекст: {context_str}")
    
    message = " | ".join(message_parts)
    general_logger.warning(message)


def log_info(
    info_message: str,
    details: Optional[Dict[str, Any]] = None
):
    """
    Логирует информационное сообщение.
    
    Args:
        info_message: Информационное сообщение
        details: Дополнительные детали
    
    Примеры:
        >>> log_info("Запущена синхронизация данных", details={'count': 150})
        
        >>> log_info("Очистка старых логов завершена", details={
        ...     'deleted': 1000,
        ...     'kept': 5000
        ... })
    """
    message_parts = [info_message]
    
    if details:
        details_str = " | ".join([f"{k}: {v}" for k, v in details.items()])
        message_parts.append(details_str)
    
    message = " | ".join(message_parts)
    general_logger.info(message)


def log_debug(
    debug_message: str,
    details: Optional[Dict[str, Any]] = None
):
    """
    Логирует отладочное сообщение (только в DEBUG режиме).
    
    Args:
        debug_message: Отладочное сообщение
        details: Дополнительные детали
    
    Примеры:
        >>> log_debug("Расчет баланса", details={
        ...     'charges': 1500.00,
        ...     'paid': 1000.00,
        ...     'balance': -500.00
        ... })
    """
    message_parts = [debug_message]
    
    if details:
        details_str = " | ".join([f"{k}: {v}" for k, v in details.items()])
        message_parts.append(details_str)
    
    message = " | ".join(message_parts)
    general_logger.debug(message)


def get_client_ip(request: HttpRequest) -> str:
    """
    Получает IP адрес клиента из запроса.
    
    Args:
        request: HTTP запрос
        
    Returns:
        IP адрес клиента
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return ip


# Контекстный менеджер для логирования операций
class LogOperation:
    """
    Контекстный менеджер для логирования начала и конца операции.
    Автоматически логирует ошибки если они возникают.
    
    Примеры:
        >>> with LogOperation("Обновление статусов батарей", user=request.user):
        ...     for battery in batteries:
        ...         battery.status = 'AVAILABLE'
        ...         battery.save()
        
        >>> with LogOperation(
        ...     "Массовое создание платежей",
        ...     user=request.user,
        ...     details={'count': len(payments)}
        ... ) as log_op:
        ...     for payment in payments:
        ...         payment.save()
        ...     log_op.add_result({'created': len(payments)})
    """
    
    def __init__(
        self,
        operation_name: str,
        user: Optional[User] = None,
        details: Optional[Dict[str, Any]] = None,
        request: Optional[HttpRequest] = None
    ):
        self.operation_name = operation_name
        self.user = user
        self.details = details or {}
        self.request = request
        self.result = {}
    
    def add_result(self, result: Dict[str, Any]):
        """Добавить результат операции для логирования при завершении."""
        self.result.update(result)
    
    def __enter__(self):
        log_action(
            f"НАЧАЛО: {self.operation_name}",
            user=self.user,
            details=self.details,
            request=self.request
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Операция завершилась успешно
            combined_details = {**self.details, **self.result}
            log_action(
                f"ЗАВЕРШЕНО: {self.operation_name}",
                user=self.user,
                details=combined_details if combined_details else None,
                request=self.request
            )
        else:
            # Произошла ошибка
            log_error(
                f"ОШИБКА в операции: {self.operation_name}",
                exception=exc_val,
                user=self.user,
                context=self.details,
                request=self.request
            )
        return False  # Не подавляем исключение

