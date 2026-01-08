from django.apps import AppConfig


class RentalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rental'

    def ready(self):
        from . import signals  # noqa
        self._patch_admin_index()
    
    def _patch_admin_index(self):
        """Добавляем Dashboard и CityAnalytics в app_list на всех страницах админки"""
        from django.contrib import admin
        from django.urls import reverse
        
        def add_custom_pages_to_app_list(app_list):
            """Вспомогательная функция для добавления кастомных страниц в app_list"""
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
                    
                    # Проверяем и добавляем CityAnalytics
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
                    break
            return app_list
        
        # Патчим метод _build_app_dict для всех страниц админки
        original_build_app_dict = admin.site._build_app_dict
        
        def custom_build_app_dict(request, label=None):
            app_dict = original_build_app_dict(request, label)
            
            # Добавляем кастомные страницы в rental app
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
                add_custom_pages_to_app_list(response.context_data['app_list'])
            
            return response
        
        admin.site.index = custom_index
