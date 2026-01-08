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


def get_user_cities(user):
    """
    Получить города пользователя (для владельцев - все их города).
    
    Args:
        user: Пользователь Django
        
    Returns:
        List[City] или None (для суперпользователей - все города)
    """
    if not user or not user.is_authenticated:
        return None
    
    if user.is_superuser:
        return None  # все города
    
    # Модератор - один город
    moderator_fp = FinancePartner.objects.filter(
        user=user, role=FinancePartner.Role.MODERATOR, active=True
    ).select_related('city').first()
    
    if moderator_fp and moderator_fp.city:
        return [moderator_fp.city]
    
    # Владелец - может иметь несколько городов
    owner_fps = FinancePartner.objects.filter(
        user=user, role=FinancePartner.Role.OWNER, active=True
    ).prefetch_related('cities')
    
    cities = []
    for fp in owner_fps:
        if fp.city:
            cities.append(fp.city)
        cities.extend(fp.cities.all())
    
    return list(set(cities)) if cities else None


class CityFilteredAdminMixin:
    """
    Mixin для фильтрации админ-панелей по городу.
    
    Модераторы видят только данные своего города.
    Владельцы видят данные всех своих городов (из поля cities).
    Суперпользователи видят все данные.
    
    Использование:
        class ClientAdmin(CityFilteredAdminMixin, SimpleHistoryAdmin):
            city_filter_field = 'city'  # по умолчанию
    """
    city_filter_field = 'city'  # Переопределить для связанных полей (например, 'battery__city')
    
    def get_queryset(self, request):
        """
        Фильтрует queryset по городу(ам) пользователя.
        """
        qs = super().get_queryset(request)
        
        # Суперпользователи видят всё
        if request.user.is_superuser:
            return qs
        
        # Получаем города пользователя (может быть список для владельцев)
        cities = get_user_cities(request.user)
        
        if cities:
            # Фильтруем по городам (может быть один или несколько)
            if len(cities) == 1:
                filter_kwargs = {self.city_filter_field: cities[0]}
                return qs.filter(**filter_kwargs)
            else:
                # Несколько городов - используем __in
                filter_kwargs = {f"{self.city_filter_field}__in": cities}
                return qs.filter(**filter_kwargs)
        else:
            # Если у пользователя нет городов, не показываем ничего
            return qs.none()
    
    def has_module_permission(self, request):
        """
        Разрешаем доступ модераторам, владельцам и суперпользователям.
        """
        if request.user.is_superuser:
            return True
        
        # Модераторы и владельцы с городами имеют доступ
        cities = get_user_cities(request.user)
        return cities is not None and len(cities) > 0
    
    def has_view_permission(self, request, obj=None):
        """
        Проверка прав на просмотр объекта.
        """
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return self.has_module_permission(request)
        
        # Проверяем, что объект принадлежит одному из городов пользователя
        cities = get_user_cities(request.user)
        if not cities:
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
        
        return obj_city in cities if obj_city else False
    
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

