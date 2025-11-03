from django.apps import AppConfig


class RentalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rental'

    def ready(self):
        from . import signals  # noqa
        self._patch_admin_index()
    
    def _patch_admin_index(self):
        """Добавляем Dashboard в app_list на всех страницах админки"""
        from django.contrib import admin
        from django.urls import reverse
        
        def add_dashboard_to_app_list(app_list):
            """Вспомогательная функция для добавления Dashboard в app_list"""
            for app in app_list:
                if app.get('app_label') == 'rental':
                    # Проверяем, не добавлен ли уже Dashboard
                    dashboard_exists = any(
                        model.get('object_name') == 'Dashboard' 
                        for model in app.get('models', [])
                    )
                    if not dashboard_exists:
                        # Добавляем Dashboard первым в списке моделей
                        dashboard_model = {
                            'name': 'Dashboard',
                            'object_name': 'Dashboard',
                            'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                            'admin_url': reverse('admin-dashboard'),
                            'view_only': True,
                        }
                        app['models'].insert(0, dashboard_model)
                    break
            return app_list
        
        # Патчим метод _build_app_dict для всех страниц админки
        original_build_app_dict = admin.site._build_app_dict
        
        def custom_build_app_dict(request, label=None):
            app_dict = original_build_app_dict(request, label)
            
            # Добавляем Dashboard в rental app
            if 'rental' in app_dict:
                dashboard_model = {
                    'name': 'Dashboard',
                    'object_name': 'Dashboard',
                    'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
                    'admin_url': reverse('admin-dashboard'),
                    'view_only': True,
                }
                # Проверяем, не добавлен ли уже
                dashboard_exists = any(
                    model.get('object_name') == 'Dashboard' 
                    for model in app_dict['rental'].get('models', [])
                )
                if not dashboard_exists:
                    app_dict['rental']['models'].insert(0, dashboard_model)
            
            return app_dict
        
        admin.site._build_app_dict = custom_build_app_dict
        
        # Также патчим index для главной страницы
        original_index = admin.site.index
        
        def custom_index(request, extra_context=None):
            response = original_index(request, extra_context)
            
            if hasattr(response, 'context_data') and 'app_list' in response.context_data:
                add_dashboard_to_app_list(response.context_data['app_list'])
            
            return response
        
        admin.site.index = custom_index
