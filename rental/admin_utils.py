"""
Утилиты для работы с разграничением доступа по городам в админ-панели.
"""
from django.contrib import admin
from .models import FinancePartner, City


def get_user_city(user):
    """
    Получить город модератора через FinancePartner.
    
    Args:
        user: Пользователь Django
        
    Returns:
        City или None, если пользователь не модератор или у него нет города
    """
    if not user or not user.is_authenticated:
        return None
    
    finance_partner = FinancePartner.objects.filter(
        user=user,
        role=FinancePartner.Role.MODERATOR,
        active=True
    ).select_related('city').first()
    
    return finance_partner.city if finance_partner else None


class CityFilteredAdminMixin:
    """
    Mixin для фильтрации админ-панелей по городу.
    
    Модераторы видят только данные своего города.
    Суперпользователи видят все данные.
    
    Использование:
        class ClientAdmin(CityFilteredAdminMixin, SimpleHistoryAdmin):
            city_filter_field = 'city'  # по умолчанию
    """
    city_filter_field = 'city'  # Переопределить для связанных полей (например, 'battery__city')
    
    def get_queryset(self, request):
        """
        Фильтрует queryset по городу модератора.
        """
        qs = super().get_queryset(request)
        
        # Суперпользователи видят всё
        if request.user.is_superuser:
            return qs
        
        # Получаем город модератора
        city = get_user_city(request.user)
        
        if city:
            # Фильтруем по городу
            filter_kwargs = {self.city_filter_field: city}
            return qs.filter(**filter_kwargs)
        else:
            # Если у модератора нет города, не показываем ничего
            return qs.none()
    
    def has_module_permission(self, request):
        """
        Разрешаем доступ модераторам и суперпользователям.
        """
        if request.user.is_superuser:
            return True
        
        # Модераторы с городом имеют доступ
        city = get_user_city(request.user)
        return city is not None
    
    def has_view_permission(self, request, obj=None):
        """
        Проверка прав на просмотр объекта.
        """
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return self.has_module_permission(request)
        
        # Проверяем, что объект принадлежит городу модератора
        city = get_user_city(request.user)
        if not city:
            return False
        
        # Получаем город объекта
        obj_city = None
        if hasattr(obj, self.city_filter_field):
            obj_city = getattr(obj, self.city_filter_field)
        elif '__' in self.city_filter_field:
            # Для связанных полей типа 'battery__city'
            parts = self.city_filter_field.split('__')
            obj_city = obj
            for part in parts:
                if obj_city is None:
                    break
                obj_city = getattr(obj_city, part, None)
        
        return obj_city == city
    
    def has_change_permission(self, request, obj=None):
        """
        Проверка прав на изменение объекта.
        """
        return self.has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """
        Проверка прав на удаление объекта.
        """
        return self.has_view_permission(request, obj)

