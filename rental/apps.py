from django.apps import AppConfig


class RentalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rental'

    def ready(self):
        from . import signals  # noqa
        self._patch_admin_index()
        self._restrict_django_models_for_moderators()
    
    def _patch_admin_index(self):
        """Добавляем Dashboard и CityAnalytics в app_list на всех страницах админки"""
        from django.contrib import admin
        from django.urls import reverse
        from .admin_utils import is_moderator
        
        def add_custom_pages_to_app_list(app_list):
            """Вспомогательная функция для добавления кастомных страниц в app_list"""
            # Проверяем, является ли пользователь модератором
            # Получаем request из контекста, если возможно
            user_is_moderator = False
            try:
                from django.contrib import admin
                # Пытаемся получить request из текущего контекста
                # Это может не работать в некоторых случаях, но для index должно работать
                pass
            except:
                pass
            
            for app in app_list:
                if app.get('app_label') == 'rental':
                    models = app.get('models', [])
                    
                    # Проверяем и добавляем Dashboard
                    dashboard_exists = any(
                        model.get('object_name') == 'Dashboard' 
                        for model in models
                    )
                    if not dashboard_exists:
                        dashboard_model = {
                            'name': 'Dashboard',
                            'object_name': 'Dashboard',
                            'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                            'admin_url': reverse('admin-dashboard'),
                            'view_only': True,
                        }
                        models.insert(0, dashboard_model)
                    
                    # CityAnalytics добавляем только для не-модераторов
                    # Проверка будет в custom_index через request
                    city_analytics_exists = any(
                        model.get('object_name') == 'CityAnalytics' 
                        for model in models
                    )
                    # Не добавляем CityAnalytics здесь, так как фильтрация происходит в custom_build_app_dict
                    break
            return app_list
        
        # Патчим метод _build_app_dict для всех страниц админки
        original_build_app_dict = admin.site._build_app_dict
        
        # Разрешенные модели для модераторов
        ALLOWED_MODERATOR_MODELS = {'Dashboard', 'Payment', 'Client', 'Rental'}
        
        def custom_build_app_dict(request, label=None):
            app_dict = original_build_app_dict(request, label)
            
            # Проверяем, является ли пользователь модератором
            user_is_moderator = is_moderator(request.user) if hasattr(request, 'user') else False
            
            if user_is_moderator:
                # Для модераторов фильтруем все приложения
                filtered_app_dict = {}
                
                # Оставляем только rental app
                if 'rental' in app_dict:
                    models = app_dict['rental'].get('models', [])
                    
                    # Фильтруем модели - оставляем только разрешенные
                    filtered_models = [
                        model for model in models
                        if model.get('object_name') in ALLOWED_MODERATOR_MODELS
                    ]
                    
                    # Добавляем Dashboard если его нет
                    dashboard_exists = any(
                        model.get('object_name') == 'Dashboard' 
                        for model in filtered_models
                    )
                    if not dashboard_exists:
                        dashboard_model = {
                            'name': 'Dashboard',
                            'object_name': 'Dashboard',
                            'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                            'admin_url': reverse('admin-dashboard'),
                            'view_only': True,
                        }
                        filtered_models.insert(0, dashboard_model)
                    
                    # Создаем отфильтрованный app_dict
                    filtered_app_dict['rental'] = {
                        'name': app_dict['rental'].get('name', 'Rental'),
                        'app_label': 'rental',
                        'app_url': app_dict['rental'].get('app_url', ''),
                        'has_module_perms': app_dict['rental'].get('has_module_perms', True),
                        'models': filtered_models,
                    }
                
                return filtered_app_dict
            else:
                # Для не-модераторов добавляем кастомные страницы как обычно
                if 'rental' in app_dict:
                    models = app_dict['rental'].get('models', [])
                    
                    # Dashboard
                    dashboard_exists = any(
                        model.get('object_name') == 'Dashboard' 
                        for model in models
                    )
                    if not dashboard_exists:
                        dashboard_model = {
                            'name': 'Dashboard',
                            'object_name': 'Dashboard',
                            'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                            'admin_url': reverse('admin-dashboard'),
                            'view_only': True,
                        }
                        models.insert(0, dashboard_model)
                    
                    # CityAnalytics
                    city_analytics_exists = any(
                        model.get('object_name') == 'CityAnalytics' 
                        for model in models
                    )
                    if not city_analytics_exists:
                        city_analytics_model = {
                            'name': 'Аналитика по городам',
                            'object_name': 'CityAnalytics',
                            'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                            'admin_url': reverse('city-analytics'),
                            'view_only': True,
                        }
                        # Добавляем после Dashboard
                        dashboard_index = next(
                            (i for i, m in enumerate(models) if m.get('object_name') == 'Dashboard'),
                            -1
                        )
                        if dashboard_index >= 0:
                            models.insert(dashboard_index + 1, city_analytics_model)
                        else:
                            models.insert(0, city_analytics_model)
            
            return app_dict
        
        admin.site._build_app_dict = custom_build_app_dict
        
        # Также патчим index для главной страницы
        original_index = admin.site.index
        
        def custom_index(request, extra_context=None):
            response = original_index(request, extra_context)
            
            if hasattr(response, 'context_data') and 'app_list' in response.context_data:
                # Фильтруем app_list для модераторов
                user_is_moderator = is_moderator(request.user) if hasattr(request, 'user') else False
                
                if user_is_moderator:
                    # Для модераторов оставляем только rental app с разрешенными моделями
                    filtered_app_list = []
                    for app in response.context_data['app_list']:
                        if app.get('app_label') == 'rental':
                            models = app.get('models', [])
                            filtered_models = [
                                model for model in models
                                if model.get('object_name') in ALLOWED_MODERATOR_MODELS
                            ]
                            # Добавляем Dashboard если его нет
                            dashboard_exists = any(
                                model.get('object_name') == 'Dashboard' 
                                for model in filtered_models
                            )
                            if not dashboard_exists:
                                dashboard_model = {
                                    'name': 'Dashboard',
                                    'object_name': 'Dashboard',
                                    'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                                    'admin_url': reverse('admin-dashboard'),
                                    'view_only': True,
                                }
                                filtered_models.insert(0, dashboard_model)
                            
                            filtered_app = {
                                'name': app.get('name', 'Rental'),
                                'app_label': 'rental',
                                'app_url': app.get('app_url', ''),
                                'has_module_perms': app.get('has_module_perms', True),
                                'models': filtered_models,
                            }
                            filtered_app_list.append(filtered_app)
                    response.context_data['app_list'] = filtered_app_list
                else:
                    add_custom_pages_to_app_list(response.context_data['app_list'])
            
            return response
        
        admin.site.index = custom_index
    
    def _restrict_django_models_for_moderators(self):
        """Скрываем стандартные Django модели (User, Group) от модераторов"""
        from django.contrib import admin
        from django.contrib.auth.models import User, Group
        from django.contrib.auth.admin import UserAdmin, GroupAdmin
        from .admin_utils import is_moderator
        
        # Переопределяем UserAdmin
        if admin.site.is_registered(User):
            admin.site.unregister(User)
        
        class RestrictedUserAdmin(UserAdmin):
            def has_module_permission(self, request):
                if is_moderator(request.user):
                    return False
                return super().has_module_permission(request)
        
        admin.site.register(User, RestrictedUserAdmin)
        
        # Переопределяем GroupAdmin
        if admin.site.is_registered(Group):
            admin.site.unregister(Group)
        
        class RestrictedGroupAdmin(GroupAdmin):
            def has_module_permission(self, request):
                if is_moderator(request.user):
                    return False
                return super().has_module_permission(request)
        
        admin.site.register(Group, RestrictedGroupAdmin)
