from django.apps import AppConfig


class RentalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rental'

    def ready(self):
        from . import signals  # noqa
        self._patch_admin_index()
    
    def _patch_admin_index(self):
        """Добавляем Dashboard в app_list на главной странице админки"""
        from django.contrib import admin
        from django.urls import reverse
        
        original_index = admin.site.index
        
        def custom_index(request, extra_context=None):
            # Получаем оригинальный ответ
            response = original_index(request, extra_context)
            
            # Если это TemplateResponse, модифицируем context_data
            if hasattr(response, 'context_data') and 'app_list' in response.context_data:
                app_list = response.context_data['app_list']
                
                # Находим приложение rental
                for app in app_list:
                    if app.get('app_label') == 'rental':
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
            
            return response
        
        # Заменяем метод index
        admin.site.index = custom_index
