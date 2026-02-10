from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse, HttpResponseForbidden

from django.db import transaction
from django.db.models import Sum, Q, F

from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm, ACTION_CHECKBOX_NAME
from django.core.exceptions import ValidationError
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils import timezone
from django.template.response import TemplateResponse
from django.forms import inlineformset_factory, BaseInlineFormSet
from decimal import Decimal
from django.utils.safestring import mark_safe
from datetime import datetime, time, timedelta, date as date_type
from admin_auto_filters.filters import AutocompleteFilter
import json
import traceback

# Register custom template filters
import rental.templatetags.custom_filters

from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Client, Battery, Rental, RentalBatteryAssignment,
    Payment, ExpenseCategory, Expense, Repair, BatteryStatusLog, BatteryTransfer,
    FinancePartner, OwnerContribution, OwnerWithdrawal, MoneyTransfer, FinanceAdjustment,
    City,
)
from .admin_utils import CityFilteredAdminMixin, get_user_city, get_user_cities, is_moderator, get_debug_log_path


class ModeratorRestrictedMixin:
    """
    Mixin для скрытия моделей от модераторов.
    Модераторы имеют доступ только к Dashboard, Payment, Client, Rental.
    """
    def has_module_permission(self, request):
        if is_moderator(request.user):
            return False
        return super().has_module_permission(request) if hasattr(super(), 'has_module_permission') else True


class ModeratorReadOnlyRelatedMixin:
    """
    Mixin для запрета добавления/редактирования связанных объектов модераторами.
    Модераторы могут только выбирать из существующих объектов, но не добавлять/редактировать их.
    """
    def get_form(self, request, obj=None, **kwargs):
        """Переопределяем get_form для работы с autocomplete полями"""
        form = super().get_form(request, obj, **kwargs)
        
        if is_moderator(request.user):
            # Для модераторов запрещаем все действия со связанными объектами
            for field_name, field in form.base_fields.items():
                if hasattr(field, 'widget'):
                    if hasattr(field.widget, 'can_add_related'):
                        field.widget.can_add_related = False
                    if hasattr(field.widget, 'can_change_related'):
                        field.widget.can_change_related = False
                    if hasattr(field.widget, 'can_delete_related'):
                        field.widget.can_delete_related = False
                    if hasattr(field.widget, 'can_view_related'):
                        field.widget.can_view_related = False
        
        return form
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # #region agent log
        import json
        import time as time_module
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A",
                    "location": "admin.py:ModeratorReadOnlyRelatedMixin.formfield_for_foreignkey:entry",
                    "message": "Mixin formfield_for_foreignkey called",
                    "data": {
                        "db_field_name": db_field.name,
                        "user_id": request.user.id if request.user else None,
                        "user_is_moderator": is_moderator(request.user) if request.user else False
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        
        # #region agent log
        try:
            widget_type = type(field.widget).__name__
            has_can_add = hasattr(field.widget, 'can_add_related')
            has_can_change = hasattr(field.widget, 'can_change_related')
            has_can_delete = hasattr(field.widget, 'can_delete_related')
            has_can_view = hasattr(field.widget, 'can_view_related')
            can_add_value = getattr(field.widget, 'can_add_related', None) if has_can_add else None
            can_change_value = getattr(field.widget, 'can_change_related', None) if has_can_change else None
            
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                    "location": "admin.py:ModeratorReadOnlyRelatedMixin.formfield_for_foreignkey:after_super",
                    "message": "After super(), widget info",
                    "data": {
                        "db_field_name": db_field.name,
                        "widget_type": widget_type,
                        "has_can_add_related": has_can_add,
                        "has_can_change_related": has_can_change,
                        "has_can_delete_related": has_can_delete,
                        "has_can_view_related": has_can_view,
                        "can_add_value_before": can_add_value,
                        "can_change_value_before": can_change_value
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        
        if is_moderator(request.user):
            # Запрещаем все действия со связанными объектами для модераторов
            if hasattr(field.widget, 'can_add_related'):
                field.widget.can_add_related = False
            if hasattr(field.widget, 'can_change_related'):
                field.widget.can_change_related = False
            if hasattr(field.widget, 'can_delete_related'):
                field.widget.can_delete_related = False
            if hasattr(field.widget, 'can_view_related'):
                field.widget.can_view_related = False
            
            # #region agent log
            try:
                can_add_after = getattr(field.widget, 'can_add_related', None) if hasattr(field.widget, 'can_add_related') else None
                can_change_after = getattr(field.widget, 'can_change_related', None) if hasattr(field.widget, 'can_change_related') else None
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "C",
                        "location": "admin.py:ModeratorReadOnlyRelatedMixin.formfield_for_foreignkey:after_set_false",
                        "message": "After setting can_*_related to False",
                        "data": {
                            "db_field_name": db_field.name,
                            "can_add_value_after": can_add_after,
                            "can_change_value_after": can_change_after
                        },
                        "timestamp": time_module.time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
        
        return field
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        
        if is_moderator(request.user):
            # Запрещаем все действия со связанными объектами для модераторов
            if hasattr(field.widget, 'can_add_related'):
                field.widget.can_add_related = False
            if hasattr(field.widget, 'can_change_related'):
                field.widget.can_change_related = False
            if hasattr(field.widget, 'can_delete_related'):
                field.widget.can_delete_related = False
            if hasattr(field.widget, 'can_view_related'):
                field.widget.can_view_related = False
        
        return field


@admin.register(City)
class CityAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "name", "code", "active")
    list_filter = ("active",)
    search_fields = ("name", "code")
    ordering = ['name']
    
    def has_module_permission(self, request):
        # Только администраторы видят раздел городов
        if is_moderator(request.user):
            return False
        return request.user.is_superuser


@admin.register(FinancePartner)
class FinancePartnerAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "user", "role", "city", "cities_display", "share_percent", "active")
    list_filter = ("role", "active", "city")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ["city"]
    filter_horizontal = ["cities"]  # Для удобного выбора нескольких городов
    
    def cities_display(self, obj):
        """Отображение списка городов для владельцев"""
        if obj.role == FinancePartner.Role.OWNER:
            cities_list = list(obj.cities.all())
            if cities_list:
                return ", ".join([city.name for city in cities_list])
            return "-"
        return "-"
    cities_display.short_description = "Города (для владельцев)"
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка user, city и cities"""
        qs = super().get_queryset(request)
        qs = qs.select_related('user', 'city').prefetch_related('cities')
        return qs
    
    def get_search_results(self, request, queryset, search_term):
        """Фильтрация результатов autocomplete"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "J",
                    "location": "admin.py:FinancePartnerAdmin.get_search_results:entry",
                    "message": "FinancePartnerAdmin.get_search_results called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "is_superuser": request.user.is_superuser if request.user else False,
                        "search_term": search_term,
                        "path": request.path if hasattr(request, 'path') else None,
                        "has_queryset": queryset is not None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        
        # #region agent log
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "J",
                    "location": "admin.py:FinancePartnerAdmin.get_search_results:exit",
                    "message": "FinancePartnerAdmin.get_search_results completed",
                    "data": {
                        "queryset_filtered": True
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return queryset, use_distinct
    
    def save_model(self, request, obj, form, change):
        """Вызываем clean() для валидации перед сохранением"""
        from django.core.exceptions import ValidationError
        from .logging_utils import log_action, log_error
        
        try:
            obj.full_clean()  # Вызывает clean() и другие валидации
            super().save_model(request, obj, form, change)
            
            # Логируем успешное действие
            action = "Обновлён финансовый партнёр" if change else "Создан финансовый партнёр"
            log_action(
                action,
                user=request.user,
                details={
                    'partner_id': obj.id,
                    'user': str(obj.user),
                    'role': obj.get_role_display(),
                    'city': str(obj.city) if obj.city else None,
                },
                request=request
            )
            
        except ValidationError as e:
            # Если есть ошибки валидации, показываем их пользователю
            from django.contrib import messages
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
            # Логируем ошибку валидации
            log_error(
                "Ошибка валидации финансового партнёра",
                exception=e,
                user=request.user,
                context={
                    'partner_id': obj.id if obj.id else 'новый',
                    'user': str(obj.user) if obj.user else None,
                    'role': obj.role,
                },
                request=request,
                include_traceback=False  # Не нужен полный traceback для валидации
            )
            return  # Не сохраняем объект
    
    def has_module_permission(self, request):
        """Скрываем модуль из списка для не-суперпользователей, но разрешаем autocomplete"""
        if is_moderator(request.user):
            return False
        return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        """Разрешаем просмотр для autocomplete запросов"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "J",
                    "location": "admin.py:FinancePartnerAdmin.has_view_permission:entry",
                    "message": "FinancePartnerAdmin.has_view_permission called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "is_superuser": request.user.is_superuser if request.user else False,
                        "path": request.path if hasattr(request, 'path') else None,
                        "is_autocomplete": request.path and '/autocomplete/' in request.path if hasattr(request, 'path') else False
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        # Проверяем, является ли это autocomplete запросом
        if request.path and '/autocomplete/' in request.path:
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "J",
                        "location": "admin.py:FinancePartnerAdmin.has_view_permission:autocomplete_allowed",
                        "message": "Autocomplete request allowed",
                        "data": {"result": True},
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            return True
        if is_moderator(request.user):
            return False
        result = request.user.is_superuser
        # #region agent log
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "J",
                    "location": "admin.py:FinancePartnerAdmin.has_view_permission:exit",
                    "message": "FinancePartnerAdmin.has_view_permission result",
                    "data": {"result": result},
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return result
    
    def has_change_permission(self, request, obj=None):
        """Разрешаем изменение для autocomplete запросов"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "J",
                    "location": "admin.py:FinancePartnerAdmin.has_change_permission:entry",
                    "message": "FinancePartnerAdmin.has_change_permission called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "is_superuser": request.user.is_superuser if request.user else False,
                        "path": request.path if hasattr(request, 'path') else None,
                        "is_autocomplete": request.path and '/autocomplete/' in request.path if hasattr(request, 'path') else False
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        # Проверяем, является ли это autocomplete запросом
        if request.path and '/autocomplete/' in request.path:
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "J",
                        "location": "admin.py:FinancePartnerAdmin.has_change_permission:autocomplete_allowed",
                        "message": "Autocomplete request allowed",
                        "data": {"result": True},
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            return True
        if is_moderator(request.user):
            return False
        result = request.user.is_superuser
        # #region agent log
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "J",
                    "location": "admin.py:FinancePartnerAdmin.has_change_permission:exit",
                    "message": "FinancePartnerAdmin.has_change_permission result",
                    "data": {"result": result},
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return result


# @admin.register(OwnerContribution)
class OwnerContributionAdmin(SimpleHistoryAdmin):
    list_display = ("id", "partner", "amount", "date", "source")
    list_filter = ("source", "date")
    autocomplete_fields = ("partner", "expense")
    search_fields = ("note", "partner__user__username")
    def has_module_permission(self, request):
        # только владельцы видят раздел; для неаутентифицированных — скрываем
        if not getattr(request.user, 'is_authenticated', False):
            return False
        return False
    def has_view_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OwnerWithdrawal)
class OwnerWithdrawalAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "partner", "amount", "date")
    list_filter = ("date",)
    autocomplete_fields = ("partner",)
    search_fields = ("note", "partner__user__username")
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка partner"""
        qs = super().get_queryset(request)
        qs = qs.select_related('partner__user')
        return qs
    
    def save_model(self, request, obj, form, change):
        """Сохранение с логированием"""
        from .logging_utils import log_action, log_warning
        
        action = "Обновлён вывод владельца" if change else "Создан вывод владельца"
        super().save_model(request, obj, form, change)
        
        # Логируем действие
        log_action(
            action,
            user=request.user,
            details={
                'withdrawal_id': obj.id,
                'partner': str(obj.partner),
                'amount': float(obj.amount),
                'date': str(obj.date),
            },
            request=request
        )
        
        # Предупреждение о крупных суммах
        if obj.amount > 10000:
            log_warning(
                "Вывод крупной суммы",
                user=request.user,
                context={
                    'withdrawal_id': obj.id,
                    'partner': str(obj.partner),
                    'amount': float(obj.amount),
                },
                request=request
            )
    
    def has_module_permission(self, request):
        # Только суперпользователи видят выводы владельцев
        return request.user.is_superuser


@admin.register(MoneyTransfer)
class MoneyTransferAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "from_partner", "to_partner", "amount", "date", "purpose", "use_collected")
    list_filter = ("purpose", "use_collected", "date")
    autocomplete_fields = ("from_partner", "to_partner")
    search_fields = ("note", "from_partner__user__username", "to_partner__user__username")
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка партнеров"""
        qs = super().get_queryset(request)
        qs = qs.select_related('from_partner__user', 'to_partner__user')
        return qs
    
    def has_module_permission(self, request):
        # Только суперпользователи видят денежные переводы
        return request.user.is_superuser
    
    def save_model(self, request, obj, form, change):
        """Сохранение денежного перевода с обработкой ошибок"""
        from .logging_utils import log_action, log_error, log_warning
        from django.core.exceptions import ValidationError
        
        try:
            super().save_model(request, obj, form, change)
            
            # Логируем успешное действие
            action = "Обновлён денежный перевод" if change else "Создан денежный перевод"
            log_action(
                action,
                user=request.user,
                details={
                    'transfer_id': obj.id,
                    'from_partner': str(obj.from_partner),
                    'to_partner': str(obj.to_partner),
                    'amount': float(obj.amount),
                    'purpose': obj.get_purpose_display(),
                    'use_collected': obj.use_collected,
                },
                request=request
            )
            
            # Предупреждение о крупных переводах
            if obj.amount > 10000:
                log_warning(
                    "Создан денежный перевод крупной суммы",
                    user=request.user,
                    context={
                        'transfer_id': obj.id,
                        'amount': float(obj.amount),
                        'from_partner': str(obj.from_partner),
                        'to_partner': str(obj.to_partner),
                    },
                    request=request
                )
            
            # Показываем успешное сообщение
            messages.success(
                request,
                f"{action} успешно (ID: {obj.id}, сумма: {obj.amount} PLN)"
            )
            
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
            log_error(
                "Ошибка валидации денежного перевода",
                exception=e,
                user=request.user,
                context={
                    'transfer_id': obj.id if obj.id else 'новый',
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request,
                include_traceback=False
            )
            raise
            
        except Exception as e:
            messages.error(
                request,
                f"Ошибка при сохранении денежного перевода: {str(e)}"
            )
            
            log_error(
                "Критическая ошибка при сохранении денежного перевода",
                exception=e,
                user=request.user,
                context={
                    'transfer_id': obj.id if obj.id else 'новый',
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request
            )
            raise

    def get_changeform_initial_data(self, request):
        data = super().get_changeform_initial_data(request)
        qp = request.GET
        if "from_partner" in qp:
            data["from_partner"] = qp.get("from_partner")
        if "to_partner" in qp:
            data["to_partner"] = qp.get("to_partner")
        if "amount" in qp:
            try:
                data["amount"] = qp.get("amount")
            except Exception:
                pass
        if "purpose" in qp:
            data["purpose"] = qp.get("purpose")
        if "use_collected" in qp:
            val = qp.get("use_collected")
            data["use_collected"] = val in ("1", "true", "True", "on")
        if "date" in qp:
            data["date"] = qp.get("date")
        return data


@admin.register(FinanceAdjustment)
class FinanceAdjustmentAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "target", "amount", "date")
    
    def has_module_permission(self, request):
        # Только суперпользователи видят финансовые корректировки
        return request.user.is_superuser
    list_filter = ("target", "date")
    search_fields = ("note",)


# Lightweight finance overview entry under Admin Index


class FinanceTransferForm(forms.Form):
    from_partner = forms.IntegerField()
    to_partner = forms.IntegerField()
    amount = forms.DecimalField(max_digits=12, decimal_places=2)
    date = forms.DateField(required=False)
    purpose = forms.ChoiceField(choices=MoneyTransfer.Purpose.choices)
    use_collected = forms.BooleanField(required=False)
    note = forms.CharField(required=False)

class FinanceWithdrawalForm(forms.Form):
    partner = forms.IntegerField()
    amount = forms.DecimalField(max_digits=12, decimal_places=2)
    date = forms.DateField(required=False)
    note = forms.CharField(required=False)


class FinanceOverviewAdmin(admin.ModelAdmin):
    change_list_template = "admin/finance_overview.html"
    CUTOFF_DATE = timezone.datetime(2025, 9, 1).date()

    def _compute_period(self, request):
        today = timezone.localdate()
        preset = request.GET.get("preset") or "month"
        start_param = request.GET.get("start")
        end_param = request.GET.get("end")
        if preset == "prev":
            first_of_this = today.replace(day=1)
            end = first_of_this - timezone.timedelta(days=1)
            start = end.replace(day=1)
        elif preset == "ytd":
            start = today.replace(month=1, day=1)
            end = today
        elif preset == "custom":
            from datetime import datetime as _dt
            def parse_d(s):
                try:
                    return _dt.fromisoformat(s).date()
                except Exception:
                    return None
            start = parse_d(start_param) or today.replace(day=1)
            end = parse_d(end_param) or today
        else:
            start = today.replace(day=1)
            end = today
        if start < self.CUTOFF_DATE:
            start = self.CUTOFF_DATE
        return start, end

    def has_module_permission(self, request):
        # Владельцы и модераторы видят раздел
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        # Проверяем, является ли пользователь владельцем или модератором
        return FinancePartner.objects.filter(
            user=request.user, 
            active=True,
            role__in=[FinancePartner.Role.OWNER, FinancePartner.Role.MODERATOR]
        ).exists()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("create-transfer/", self.admin_site.admin_view(self.create_transfer_view), name="finance_create_transfer"),
            path("create-withdrawal/", self.admin_site.admin_view(self.create_withdrawal_view), name="finance_create_withdrawal"),
            path("reclassify-withdrawal/", self.admin_site.admin_view(self.reclassify_withdrawal_view), name="finance_reclassify_withdrawal"),
        ]
        return custom + urls

    def _redirect_back(self, request):
        ret = request.POST.get("return_url") or request.META.get("HTTP_REFERER")
        if not ret:
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        return HttpResponseRedirect(ret)

    def _ensure_owner(self, request):
        if not request.user.is_authenticated:
            return False
        if not FinancePartner.objects.filter(user=request.user, role=FinancePartner.Role.OWNER, active=True).exists():
            return False
        return True

    def create_transfer_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if not self._ensure_owner(request):
            if is_ajax:
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            return HttpResponseForbidden()
        try:
            from_id = int(request.POST.get("from_partner") or 0)
            to_id = int(request.POST.get("to_partner") or 0)
            amount = Decimal(request.POST.get("amount") or "0")
            purpose = request.POST.get("purpose") or MoneyTransfer.Purpose.OTHER
            use_collected = (request.POST.get("use_collected") in ("1", "true", "True", "on"))
            date_str = request.POST.get("date")
            date_val = timezone.localdate()
            if date_str:
                try:
                    date_val = timezone.datetime.fromisoformat(date_str).date()
                except Exception:
                    pass
            if from_id <= 0 or to_id <= 0 or amount <= 0:
                raise ValidationError("Некорректные данные перевода")
            MoneyTransfer.objects.create(
                from_partner_id=from_id,
                to_partner_id=to_id,
                amount=amount,
                date=date_val,
                purpose=purpose,
                use_collected=use_collected,
            )
            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Перевод создан")
        except Exception as e:
            if is_ajax:
                return JsonResponse({"ok": False, "error": str(e)[:300]})
            messages.error(request, f"Ошибка: {e}")
        return self._redirect_back(request)

    def reclassify_withdrawal_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if not self._ensure_owner(request):
            if is_ajax:
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            return HttpResponseForbidden()
        try:
            wd_id = int(request.POST.get("withdrawal_id") or 0)
            partner_id = int(request.POST.get("partner") or 0)
            amount_override = request.POST.get("amount")
            if wd_id <= 0 or partner_id <= 0:
                raise ValidationError("Некорректные данные конвертации")
            wd = OwnerWithdrawal.objects.select_for_update().get(pk=wd_id)
            if wd.reclassified_to_investment:
                raise ValidationError("Выплата уже конвертирована")
            if amount_override:
                try:
                    amount = Decimal(amount_override)
                except Exception:
                    amount = wd.amount
            else:
                amount = wd.amount
            # Create contribution and mark withdrawal
            contr = OwnerContribution.objects.create(
                partner_id=partner_id,
                amount=amount,
                date=wd.date,
                source=OwnerContribution.Source.MANUAL,
                note=f"Создано из выплаты #{wd.id}: {wd.note}"[:500]
            )
            wd.reclassified_to_investment = True
            wd.reclassified_contribution = contr
            wd.save(update_fields=["reclassified_to_investment", "reclassified_contribution", "updated_at", "updated_by"])
            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Выплата перенесена в 'Вложено'")
        except Exception as e:
            if is_ajax:
                return JsonResponse({"ok": False, "error": str(e)[:300]})
            messages.error(request, f"Ошибка: {e}")
        return self._redirect_back(request)

    def create_withdrawal_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:rental_financeoverviewproxy_changelist"))
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if not self._ensure_owner(request):
            if is_ajax:
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            return HttpResponseForbidden()
        try:
            # Здесь просто создаём выплату; переквалификация выполняется отдельным эндпоинтом
            partner_id = int(request.POST.get("partner") or 0)
            amount = Decimal(request.POST.get("amount") or "0")
            note = request.POST.get("note") or ""
            date_str = request.POST.get("date")
            date_val = timezone.localdate()
            if date_str:
                try:
                    date_val = timezone.datetime.fromisoformat(date_str).date()
                except Exception:
                    pass
            if partner_id <= 0 or amount <= 0:
                raise ValidationError("Некорректные данные выплаты")
            fp = FinancePartner.objects.get(pk=partner_id)
            if fp.role != FinancePartner.Role.OWNER:
                raise ValidationError("Выплаты доступны только владельцам")
            OwnerWithdrawal.objects.create(partner_id=partner_id, amount=amount, date=date_val, note=note)
            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Выплата создана")
        except Exception as e:
            if is_ajax:
                return JsonResponse({"ok": False, "error": str(e)[:300]})
            messages.error(request, f"Ошибка: {e}")
        return self._redirect_back(request)

    def changelist_view(self, request, extra_context=None):
        start_d, end_d = self._compute_period(request)
        
        # Получаем город модератора для фильтрации
        city = None
        if not request.user.is_superuser:
            city = get_user_city(request.user)
        
        # Фильтруем партнёров по городу для модераторов
        partners_qs = FinancePartner.objects.filter(active=True)
        if city:
            partners_qs = partners_qs.filter(city=city)
        partners = partners_qs.values("id", "user_id", "role", "share_percent")
        user_to_partner = {p["user_id"]: p["id"] for p in partners}
        partner_roles = {p["id"]: p["role"] for p in partners}
        partner_shares = {p["id"]: (p["share_percent"] or 0) for p in partners}

        # Income for period (фильтруем по городу для модераторов)
        income_qs = (
            Payment.objects
            .filter(date__gte=start_d, date__lte=end_d, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD], created_by_id__in=list(user_to_partner.keys()))
        )
        if city:
            income_qs = income_qs.filter(city=city)
        income_qs = income_qs.values("created_by_id").annotate(total=Sum("amount"))
        income_by_user = {row["created_by_id"]: row["total"] or 0 for row in income_qs}
        income_total = sum(income_by_user.values())

        # Transfers affecting collected (period) - фильтруем по городу партнёров
        mt_in_qs = MoneyTransfer.objects.filter(date__gte=start_d, date__lte=end_d, use_collected=True)
        mt_out_qs = MoneyTransfer.objects.filter(date__gte=start_d, date__lte=end_d, use_collected=True)
        if city:
            # Фильтруем переводы, где партнёры принадлежат городу
            mt_in_qs = mt_in_qs.filter(to_partner__city=city)
            mt_out_qs = mt_out_qs.filter(from_partner__city=city)
        mt_in = mt_in_qs.values("to_partner_id").annotate(total=Sum("amount"))
        mt_out = mt_out_qs.values("from_partner_id").annotate(total=Sum("amount"))
        incoming_by_partner = {row["to_partner_id"]: row["total"] or 0 for row in mt_in}
        outgoing_by_partner = {row["from_partner_id"]: row["total"] or 0 for row in mt_out}

        # Period delta for collected
        collected_delta_by_partner = {}
        for user_id, partner_id in user_to_partner.items():
            inc = income_by_user.get(user_id, 0)
            inc_in = incoming_by_partner.get(partner_id, 0)
            out = outgoing_by_partner.get(partner_id, 0)
            collected_delta_by_partner[partner_id] = inc + inc_in - out
        collected_delta_total = sum(collected_delta_by_partner.values())

        # Contributions/withdrawals for period (invested delta)
        contr_qs = (
            OwnerContribution.objects
            .filter(date__gte=start_d, date__lte=end_d)
            .values("partner_id")
            .annotate(total=Sum("amount"))
        )
        withdr_qs = (
            OwnerWithdrawal.objects
            .filter(date__gte=start_d, date__lte=end_d)
            .values("partner_id")
            .annotate(total=Sum("amount"))
        )
        contr_by_partner = {row["partner_id"]: row["total"] or 0 for row in contr_qs}
        withdr_by_partner = {row["partner_id"]: row["total"] or 0 for row in withdr_qs}

        from .models import FinanceAdjustment as FA
        adj_rows = (
            FA.objects
            .filter(date__gte=start_d, date__lte=end_d)
            .values("target")
            .annotate(total=Sum("amount"))
        )
        adj_map = {row["target"]: row["total"] or 0 for row in adj_rows}
        adj_invested = adj_map.get(FA.Target.INVESTED, 0)
        adj_collected = adj_map.get(FA.Target.COLLECTED, 0)
        adj_settlement = adj_map.get(FA.Target.OWNER_SETTLEMENT, 0)

        invested_delta_by_owner = {}
        for pid, role in partner_roles.items():
            if role != FinancePartner.Role.OWNER:
                continue
            invested_delta_by_owner[pid] = (contr_by_partner.get(pid, 0) - withdr_by_partner.get(pid, 0))
        invested_delta_total = sum(invested_delta_by_owner.values()) + adj_invested

        # Opening balances (up to day before start)
        from datetime import timedelta
        opening_available = start_d > self.CUTOFF_DATE
        collected_open_by_partner = {}
        invested_open_by_owner = {}
        if opening_available:
            open_end = start_d - timedelta(days=1)
            inc_open_qs = (
                Payment.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD], created_by_id__in=list(user_to_partner.keys()))
            )
            if city:
                inc_open_qs = inc_open_qs.filter(city=city)
            inc_open_qs = inc_open_qs.values("created_by_id").annotate(total=Sum("amount"))
            
            mt_in_open_qs = MoneyTransfer.objects.filter(date__gte=self.CUTOFF_DATE, date__lte=open_end, use_collected=True)
            mt_out_open_qs = MoneyTransfer.objects.filter(date__gte=self.CUTOFF_DATE, date__lte=open_end, use_collected=True)
            if city:
                mt_in_open_qs = mt_in_open_qs.filter(to_partner__city=city)
                mt_out_open_qs = mt_out_open_qs.filter(from_partner__city=city)
            mt_in_open = mt_in_open_qs.values("to_partner_id").annotate(total=Sum("amount"))
            mt_out_open = mt_out_open_qs.values("from_partner_id").annotate(total=Sum("amount"))
            inc_open_by_user = {row["created_by_id"]: row["total"] or 0 for row in inc_open_qs}
            in_open_by_partner = {row["to_partner_id"]: row["total"] or 0 for row in mt_in_open}
            out_open_by_partner = {row["from_partner_id"]: row["total"] or 0 for row in mt_out_open}

            adj_open_rows = (
                FA.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end)
                .values("target")
                .annotate(total=Sum("amount"))
            )
            adj_open_map = {row["target"]: row["total"] or 0 for row in adj_open_rows}
            adj_open_collected = adj_open_map.get(FA.Target.COLLECTED, 0)

            for user_id, partner_id in user_to_partner.items():
                inc = inc_open_by_user.get(user_id, 0)
                inc_in = in_open_by_partner.get(partner_id, 0)
                out = out_open_by_partner.get(partner_id, 0)
                collected_open_by_partner[partner_id] = inc + inc_in - out
            # Apply adjustment (global) to total collected open
            collected_open_total = sum(collected_open_by_partner.values()) + adj_open_collected

            contr_open_qs = (
                OwnerContribution.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end)
                .values("partner_id")
                .annotate(total=Sum("amount"))
            )
            withdr_open_qs = (
                OwnerWithdrawal.objects
                .filter(date__gte=self.CUTOFF_DATE, date__lte=open_end)
                .values("partner_id")
                .annotate(total=Sum("amount"))
            )
            contr_open_by_partner = {row["partner_id"]: row["total"] or 0 for row in contr_open_qs}
            withdr_open_by_partner = {row["partner_id"]: row["total"] or 0 for row in withdr_open_qs}
            adj_open_invested = adj_open_map.get(FA.Target.INVESTED, 0)
            for pid, role in partner_roles.items():
                if role != FinancePartner.Role.OWNER:
                    continue
                invested_open_by_owner[pid] = contr_open_by_partner.get(pid, 0) - withdr_open_by_partner.get(pid, 0)
            invested_open_total = sum(invested_open_by_owner.values()) + adj_open_invested
        else:
            collected_open_total = 0
            invested_open_total = 0

        # Closing balances
        collected_total = collected_open_total + collected_delta_total + adj_collected
        invested_total = invested_open_total + invested_delta_total

        # Per-user display prep
        from django.contrib.auth import get_user_model
        users = get_user_model().objects.filter(id__in=list(user_to_partner.keys())).values("id", "username")
        uid_to_username = {u["id"]: u["username"] for u in users}
        pid_to_username = {pid: uid_to_username.get(uid, str(pid)) for uid, pid in user_to_partner.items()}

        income_rows = [
            {"created_by__username": uid_to_username.get(uid, str(uid)), "total": total}
            for uid, total in sorted(income_by_user.items(), key=lambda kv: uid_to_username.get(kv[0], str(kv[0])))
        ]
        collected_rows = [
            {"partner_id": pid, "username": pid_to_username.get(pid, str(pid)), "delta": collected_delta_by_partner.get(pid, 0), "open": collected_open_by_partner.get(pid, 0) if opening_available else 0}
            for pid in sorted(user_to_partner.values(), key=lambda x: pid_to_username.get(x, str(x)))
        ]
        for row in collected_rows:
            row["close"] = row["open"] + row["delta"]
        invested_rows = [
            {"partner_id": pid, "username": pid_to_username.get(pid, str(pid)), "delta": invested_delta_by_owner.get(pid, 0), "open": invested_open_by_owner.get(pid, 0) if opening_available else 0}
            for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER
        ]
        for row in invested_rows:
            row["close"] = row["open"] + row["delta"]

        # Owner settlements (owner_to_owner, use_collected=False) for the period
        settlements_qs = (
            MoneyTransfer.objects
            .filter(date__gte=start_d, date__lte=end_d, purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER, use_collected=False)
            .values("from_partner_id", "to_partner_id")
            .annotate(total=Sum("amount"))
        )
        settlements_rows = []
        settlements_total = 0
        for r in settlements_qs:
            from_name = pid_to_username.get(r["from_partner_id"], str(r["from_partner_id"]))
            to_name = pid_to_username.get(r["to_partner_id"], str(r["to_partner_id"]))
            total = r["total"] or 0
            settlements_total += total
            settlements_rows.append({"from": from_name, "to": to_name, "total": total})

        if extra_context is None:
            extra_context = {}
        # Partner choice lists for modal selects
        mods_list = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.MODERATOR]
        owners_list = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER]
        partner_choices_all = [{"id": pid, "username": pid_to_username.get(pid, str(pid))} for pid in sorted(partner_roles.keys(), key=lambda x: pid_to_username.get(x, str(x)))]
        partner_choices_mods = [{"id": pid, "username": pid_to_username.get(pid, str(pid))} for pid in sorted(mods_list, key=lambda x: pid_to_username.get(x, str(x)))]
        partner_choices_owners = [{"id": pid, "username": pid_to_username.get(pid, str(pid))} for pid in sorted(owners_list, key=lambda x: pid_to_username.get(x, str(x)))]
        # Admin partners (users in Django group 'Admin' that have FinancePartner)
        from django.contrib.auth import get_user_model as _gum
        admin_user_ids = set(_gum().objects.filter(groups__name='Admin').values_list('id', flat=True))
        admin_partner_ids = [pid for uid, pid in user_to_partner.items() if uid in admin_user_ids]
        partner_choices_admins = [{"id": pid, "username": pid_to_username.get(pid, str(pid))} for pid in sorted(admin_partner_ids, key=lambda x: pid_to_username.get(x, str(x)))]
        default_admin_partner_id = partner_choices_admins[0]["id"] if partner_choices_admins else None

        extra_context.update({
            "start": start_d,
            "end": end_d,
            "income_rows": income_rows,
            "income_total": income_total,
            "collected_rows": collected_rows,
            "collected_open_total": collected_open_total,
            "collected_delta_total": collected_delta_total,
            "collected_total": collected_total,
            "invested_rows": invested_rows,
            "invested_open_total": invested_open_total,
            "invested_delta_total": invested_delta_total,
            "invested_total": invested_total,
            "settlements_rows": settlements_rows,
            "settlements_total": settlements_total,
            "settlements_adj_total": adj_settlement,
            "opening_available": opening_available,
            "partner_choices_all": partner_choices_all,
            "partner_choices_mods": partner_choices_mods,
            "partner_choices_owners": partner_choices_owners,
            "partner_choices_admins": partner_choices_admins,
            "default_admin_partner_id": default_admin_partner_id,
        })

        # Last 5 withdrawals for footer
        last_withdrawals_qs = (
            OwnerWithdrawal.objects
            .order_by('-date', '-id')
            .select_related('partner__user')[:5]
        )
        last_withdrawals = [
            {
                'date': w.date,
                'partner': getattr(w.partner.user, 'username', str(w.partner_id)),
                'amount': w.amount,
            } for w in last_withdrawals_qs
        ]
        extra_context.update({
            'last_withdrawals': last_withdrawals,
        })

        # Suggested owner-to-owner transfers based on collected vs share (period-only)
        owners = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER]
        # Actual collected for owners in period (delta)
        collected_owner_delta = {pid: collected_delta_by_partner.get(pid, 0) for pid in owners}
        # Desired per-share from total income (period)
        total_income_period = income_total
        total_share = sum([float(partner_shares.get(pid, 0)) for pid in owners]) or 100.0
        share_norm = {pid: float(partner_shares.get(pid, 0))/total_share for pid in owners}
        desired_collected = {pid: Decimal(total_income_period) * Decimal(share_norm.get(pid, 0)) for pid in owners}
        diff_collected = {pid: Decimal(collected_owner_delta.get(pid, 0)) - desired_collected.get(pid, Decimal(0)) for pid in owners}
        over_c = [(pid, v) for pid, v in diff_collected.items() if v > 0]
        under_c = [(pid, -v) for pid, v in diff_collected.items() if v < 0]
        over_c.sort(key=lambda x: x[1], reverse=True)
        under_c.sort(key=lambda x: x[1], reverse=True)
        settlements_by_collected = []
        i = j = 0
        while i < len(over_c) and j < len(under_c):
            pid_over, amt_over = over_c[i]
            pid_under, amt_under = under_c[j]
            tr = min(amt_over, amt_under)
            if tr > 0:
                settlements_by_collected.append({
                    "from": pid_over,
                    "to": pid_under,
                    "total": tr
                })
            over_c[i] = (pid_over, amt_over - tr)
            under_c[j] = (pid_under, amt_under - tr)
            if over_c[i][1] == 0:
                i += 1
            if under_c[j][1] == 0:
                j += 1
        # Two-owners highlight
        highlight_reco = None
        if len(owners) == 2:
            a, b = owners[0], owners[1]
            a_name = pid_to_username.get(a, str(a))
            b_name = pid_to_username.get(b, str(b))
            # T = (C_a - C_b)/2
            T = (Decimal(collected_owner_delta.get(a, 0)) - Decimal(collected_owner_delta.get(b, 0))) / Decimal(2)
            if T > 0:
                highlight_reco = {"from": a_name, "to": b_name, "total": T}
            elif T < 0:
                highlight_reco = {"from": b_name, "to": a_name, "total": -T}
        extra_context.update({
            "collected_settlements": [
                {"from": pid_to_username.get(r["from"], str(r["from"])), "to": pid_to_username.get(r["to"], str(r["to"])), "total": r["total"], "from_id": r["from"], "to_id": r["to"]}
                for r in settlements_by_collected
            ],
            "collected_settlements_highlight": highlight_reco,
            "collected_owner_delta": {pid_to_username.get(pid, str(pid)): collected_owner_delta.get(pid, 0) for pid in owners},
            "desired_collected": {pid_to_username.get(pid, str(pid)): desired_collected.get(pid, 0) for pid in owners},
        })

        # Moderators' debts to owners for period: income by moderator minus out transfers use_collected
        moderators = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.MODERATOR]
        income_by_partner = {}
        for uid, pid in user_to_partner.items():
            if pid in moderators:
                income_by_partner[pid] = income_by_user.get(uid, 0)
        # Last 5 transfers for two categories for footer blocks (show after tables)
        last_mod_qs = (
            MoneyTransfer.objects.filter(purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER)
            .order_by('-date', '-id')
            .select_related('from_partner__user', 'to_partner__user')[:5]
        )
        last_owner_qs = (
            MoneyTransfer.objects.filter(purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER)
            .order_by('-date', '-id')
            .select_related('from_partner__user', 'to_partner__user')[:5]
        )
        # Outgoing transfers from moderators within period (for debt calc)
        mt_out_by_mod = (
            MoneyTransfer.objects
            .filter(date__gte=start_d, date__lte=end_d, use_collected=True, from_partner_id__in=moderators)
            .values("from_partner_id")
            .annotate(total=Sum("amount"))
        )
        def tr_row(tr):
            return {
                'date': tr.date,
                'from': getattr(tr.from_partner.user, 'username', str(tr.from_partner_id)),
                'to': getattr(tr.to_partner.user, 'username', str(tr.to_partner_id)),
                'amount': tr.amount,
            }
        def tr_row_with_note(tr):
            return {
                'date': tr.date,
                'from': getattr(tr.from_partner.user, 'username', str(tr.from_partner_id)),
                'to': getattr(tr.to_partner.user, 'username', str(tr.to_partner_id)),
                'amount': tr.amount,
                'note': getattr(tr, 'note', '') or '',
            }
        extra_context.update({
            'last_mod_to_owner': [tr_row_with_note(t) for t in last_mod_qs],
            'last_owner_to_owner': [tr_row_with_note(t) for t in last_owner_qs],
        })
        mt_out_by_mod_map = {row["from_partner_id"]: row["total"] or 0 for row in mt_out_by_mod}
        moderator_debts = []
        for pid in moderators:
            owed = Decimal(income_by_partner.get(pid, 0)) - Decimal(mt_out_by_mod_map.get(pid, 0))
            if owed > 0:
                moderator_debts.append({
                    "partner_id": pid,
                    "username": pid_to_username.get(pid, str(pid)),
                    "amount": owed,
                })
        extra_context.update({"moderator_debts": moderator_debts})

        # Profit share block (split by owner shares)
        # Income I
        I = sum(income_by_user.values())
        
        # Company expenses E: only paid from collected funds
        # Company expenses from collected funds: with new Expense model semantics, treat as 0 here
        E = Decimal(0)
        
        # Adjustments to profit if needed (reuse collected/invested logic as neutral here)
        P = I - E  # base profit without extra adj
        
        # Owners and their shares (normalize to 1.0)
        owners = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER]
        total_share = sum([float(partner_shares.get(pid, 0)) for pid in owners]) or 100.0
        share_norm = {pid: float(partner_shares.get(pid, 0))/total_share for pid in owners}
        
        # Due to each owner from profit
        D_by_owner = {pid: P * Decimal(share_norm.get(pid, 0)) for pid in owners}
        D_total = sum(D_by_owner.values())
        
        # Actually withdrawn by owners in period (exclude reclassified to investment)
        W_by_owner = {row["partner_id"]: row["total"] or 0 for row in (
            OwnerWithdrawal.objects.filter(date__gte=start_d, date__lte=end_d, partner_id__in=owners, reclassified_to_investment=False)
            .values("partner_id").annotate(total=Sum("amount"))
        )}
        W_total = sum(W_by_owner.values())
        
        # How issued funds should be split by shares
        R_by_owner = {pid: Decimal(W_total) * Decimal(share_norm.get(pid, 0)) for pid in owners}
        
        # Suggested owner-to-owner transfer to rebalance already issued funds
        # For two owners it's a single number; for N owners show list of imbalances
        imbalance = {pid: Decimal(W_by_owner.get(pid, 0)) - R_by_owner.get(pid, Decimal(0)) for pid in owners}
        # Positive -> owner received more than proportional, should pay out; Negative -> should receive
        over = [(pid, v) for pid, v in imbalance.items() if v > 0]
        under = [(pid, -v) for pid, v in imbalance.items() if v < 0]
        over.sort(key=lambda x: x[1], reverse=True)
        under.sort(key=lambda x: x[1], reverse=True)
        settlements_suggest = []
        i = j = 0
        while i < len(over) and j < len(under):
            pid_over, amt_over = over[i]
            pid_under, amt_under = under[j]
            tr = min(amt_over, amt_under)
            if tr > 0:
                settlements_suggest.append({
                    "from": pid_over,
                    "to": pid_under,
                    "total": tr
                })
            over[i] = (pid_over, amt_over - tr)
            under[j] = (pid_under, amt_under - tr)
            if over[i][1] == 0:
                i += 1
            if under[j][1] == 0:
                j += 1
        
        # Company owes to owners (not yet issued)
        C_total = Decimal(D_total) - Decimal(W_total)
        C_by_owner = {pid: D_by_owner.get(pid, 0) - Decimal(W_by_owner.get(pid, 0)) for pid in owners}
        
        # Prepare display structures
        profit_rows = []
        for pid in owners:
            profit_rows.append({
                "username": pid_to_username.get(pid, str(pid)),
                "share": round(Decimal(share_norm.get(pid, 0)) * Decimal(100), 2),
                "due": D_by_owner.get(pid, 0),
                "withdrawn": Decimal(W_by_owner.get(pid, 0)),
                "withdrawn_should": R_by_owner.get(pid, 0),
                "company_owes": C_by_owner.get(pid, 0),
            })
        settlements_suggest_rows = [
            {"from": pid_to_username.get(r["from"], str(r["from"])), "to": pid_to_username.get(r["to"], str(r["to"])), "total": r["total"]}
            for r in settlements_suggest
        ]
        # Lifetime Invested (Purchases 50% + Contributions - Equal share)
        owners = [pid for pid, role in partner_roles.items() if role == FinancePartner.Role.OWNER]
        # Purchases by owner (only purchase type) - фильтруем по городу
        purch_qs = Expense.objects.filter(paid_by_partner_id__in=owners, payment_type=Expense.PaymentType.PURCHASE)
        if city:
            purch_qs = purch_qs.filter(paid_by_partner__city=city)
        purch_qs = purch_qs.values('paid_by_partner_id').annotate(total=Sum('amount'))
        purch_by_owner = {row['paid_by_partner_id']: row['total'] or 0 for row in purch_qs}
        # Contributions by owner (from expenses: DEPOSIT) - фильтруем по городу
        contr_qs_all = Expense.objects.filter(paid_by_partner_id__in=owners, payment_type=Expense.PaymentType.DEPOSIT)
        if city:
            contr_qs_all = contr_qs_all.filter(paid_by_partner__city=city)
        contr_qs_all = contr_qs_all.values('paid_by_partner_id').annotate(total=Sum('amount'))
        contr_by_owner = {row['paid_by_partner_id']: row['total'] or 0 for row in contr_qs_all}
        # Equal share of total purchases among owners - фильтруем по городу
        total_purchases_qs = Expense.objects.filter(paid_by_partner_id__in=owners, payment_type=Expense.PaymentType.PURCHASE)
        if city:
            total_purchases_qs = total_purchases_qs.filter(paid_by_partner__city=city)
        total_purchases = total_purchases_qs.aggregate(s=Sum('amount'))['s'] or 0
        n = len(owners) or 1
        B_each = (Decimal(total_purchases) / Decimal(n)) if n else Decimal(0)
        invested_ab_rows = []
        for pid in owners:
            purchases_half = Decimal(purch_by_owner.get(pid, 0)) / Decimal(2)
            contribs = Decimal(contr_by_owner.get(pid, 0))
            b = B_each
            balance = purchases_half + contribs - b
            invested_ab_rows.append({
                'username': pid_to_username.get(pid, str(pid)),
                'purchases': purchases_half,
                'contribs': contribs,
                'b': b,
                'balance': balance,
            })
        # Last 5 invested operations: all expenses by owners (both types), newest first - фильтруем по городу
        exp_ops_qs = Expense.objects.filter(paid_by_partner_id__in=owners)
        if city:
            exp_ops_qs = exp_ops_qs.filter(paid_by_partner__city=city)
        exp_ops = list(
            exp_ops_qs
            .order_by('-date', '-id')
            .select_related('paid_by_partner__user')[:5]
        )
        last_invest_ops = []
        for e in exp_ops:
            kind = 'Закупка' if e.payment_type == Expense.PaymentType.PURCHASE else 'Внесение денег'
            who = getattr(getattr(e, 'paid_by_partner', None), 'user', None)
            who_name = getattr(who, 'username', e.paid_by_partner_id)
            last_invest_ops.append({'date': e.date, 'text': f"{kind} {who_name}: {e.amount}"})
        extra_context.update({
            'invested_ab_rows': invested_ab_rows,
            'last_invest_ops': last_invest_ops,
        })

        extra_context.update({
            "profit_income": I,
            "profit_expenses": E,
            "profit_total": P,
            "profit_rows": profit_rows,
            "profit_company_owes_total": C_total,
            "profit_settlements_suggest": settlements_suggest_rows,
        })

        # Render with admin each_context so sidebar/menus are present, honoring GET params
        base_ctx = self.admin_site.each_context(request)
        context = {**base_ctx, **(extra_context or {}), "request": request, "opts": self.model._meta, "title": self.model._meta.verbose_name_plural}
        return TemplateResponse(request, self.change_list_template, context)

        return super().changelist_view(request, extra_context=extra_context)


# Register FinanceOverview using proxy model
from .models import FinanceOverviewProxy
try:
    @admin.register(FinanceOverviewProxy)
    class FinanceOverviewProxyAdmin(ModeratorRestrictedMixin, FinanceOverviewAdmin):
        pass
except admin.sites.AlreadyRegistered:
    pass


# ===================================
# Finance Overview v2 (Бухучёт)
# ===================================

class FinanceOverviewAdmin2(admin.ModelAdmin):
    change_list_template = "admin/finance_overview_v2.html"
    CUTOFF_DATE = timezone.datetime(2025, 9, 1).date()

    def has_module_permission(self, request):
        # Владельцы и модераторы видят раздел
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        # Проверяем, является ли пользователь владельцем или модератором
        return FinancePartner.objects.filter(
            user=request.user, 
            active=True,
            role__in=[FinancePartner.Role.OWNER, FinancePartner.Role.MODERATOR]
        ).exists()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("create-transfer-v2/", self.admin_site.admin_view(self.create_transfer_view), name="finance_v2_create_transfer"),
        ]
        return custom + urls

    def create_transfer_view(self, request):
        """AJAX endpoint для создания перевода"""
        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "Only POST allowed"}, status=405)
        
        if not request.user.is_authenticated:
            return JsonResponse({"ok": False, "error": "Unauthorized"}, status=403)
        
        # Проверка прав (только владельцы)
        if not FinancePartner.objects.filter(user=request.user, role=FinancePartner.Role.OWNER, active=True).exists():
            return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
        
        try:
            from_id = int(request.POST.get("from_partner") or 0)
            to_id = int(request.POST.get("to_partner") or 0)
            amount = Decimal(request.POST.get("amount") or "0")
            purpose = request.POST.get("purpose") or MoneyTransfer.Purpose.OTHER
            use_collected = (request.POST.get("use_collected") == "true")
            add_to_deposits = (request.POST.get("add_to_deposits") == "true")
            date_str = request.POST.get("date") or ""
            note = request.POST.get("note") or ""
            
            # Парсинг даты
            date_val = timezone.localdate()
            if date_str:
                try:
                    date_val = timezone.datetime.fromisoformat(date_str).date()
                except Exception:
                    pass
            
            # Валидация
            if from_id <= 0 or to_id <= 0:
                return JsonResponse({"ok": False, "error": "Некорректные партнёры"})
            
            if amount <= 0:
                return JsonResponse({"ok": False, "error": "Сумма должна быть больше 0"})
            
            if from_id == to_id:
                return JsonResponse({"ok": False, "error": "Нельзя перевести самому себе"})
            
            # Создание перевода
            MoneyTransfer.objects.create(
                from_partner_id=from_id,
                to_partner_id=to_id,
                amount=amount,
                date=date_val,
                purpose=purpose,
                use_collected=use_collected,
                note=note,
            )
            
            # Если галочка "Добавить в взносы" активна
            if add_to_deposits and purpose == MoneyTransfer.Purpose.OWNER_TO_OWNER:
                from_partner = FinancePartner.objects.get(id=from_id)
                to_partner = FinancePartner.objects.get(id=to_id)
                
                # Создаём расход типа DEPOSIT для отправителя
                Expense.objects.create(
                    paid_by_partner_id=from_id,
                    payment_type=Expense.PaymentType.DEPOSIT,
                    amount=amount,
                    date=date_val,
                    description=f"Взнос через перевод владельцу {to_partner.user.username}",
                )
            
            return JsonResponse({"ok": True, "message": "Перевод создан успешно"})
            
        except ValueError as e:
            return JsonResponse({"ok": False, "error": f"Ошибка данных: {str(e)}"})
        except Exception as e:
            return JsonResponse({"ok": False, "error": f"Ошибка: {str(e)[:200]}"})

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Sum, Q
        from django.db.models.functions import TruncMonth
        
        cutoff = self.CUTOFF_DATE
        
        # Получаем города пользователя для фильтрации (для владельцев - несколько городов)
        cities = None
        if not request.user.is_superuser:
            cities = get_user_cities(request.user)
            # Если это список с одним городом, используем его для обратной совместимости
            city = cities[0] if cities and len(cities) == 1 else None
        else:
            city = None
        
        # Получаем всех партнёров (фильтруем по городам для модераторов/владельцев)
        partners_qs = FinancePartner.objects.filter(active=True).select_related('user')
        if cities:
            if len(cities) == 1:
                partners_qs = partners_qs.filter(city=cities[0])
            else:
                # Несколько городов - используем Q для фильтрации
                from django.db.models import Q
                city_filter = Q(city__in=cities)
                # Также проверяем ManyToMany поле cities
                partners_qs = partners_qs.filter(city_filter | Q(cities__in=cities)).distinct()
        partners = list(partners_qs)
        partners_dict = {p.id: p for p in partners}
        
        # Разделяем на владельцев и модераторов
        owners = [p for p in partners if p.role == FinancePartner.Role.OWNER]
        moderators = [p for p in partners if p.role == FinancePartner.Role.MODERATOR]
        
        owner_ids = [p.id for p in owners]
        moderator_ids = [p.id for p in moderators]
        
        user_to_partner = {p.user_id: p.id for p in partners}
        partner_to_user = {p.id: p.user_id for p in partners}
        
        # ========================================
        # 1. ДОХОДЫ (накопленный итог)
        # ========================================
        
        # Payments (RENT + SOLD) с cutoff даты (фильтруем по городам)
        payments_qs = Payment.objects.filter(date__gte=cutoff, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD])
        if cities:
            payments_qs = payments_qs.filter(city__in=cities)
        payments_by_user = dict(
            payments_qs
            .values('created_by_id')
            .annotate(total=Sum('amount'))
            .values_list('created_by_id', 'total')
        )
        
        # Входящие переводы ОТ модераторов К владельцам (фильтруем по городам)
        incoming_from_mods_qs = MoneyTransfer.objects.filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER, use_collected=True)
        if cities:
            incoming_from_mods_qs = incoming_from_mods_qs.filter(to_partner__city__in=cities)
        incoming_from_mods = dict(
            incoming_from_mods_qs
            .values('to_partner_id')
            .annotate(total=Sum('amount'))
            .values_list('to_partner_id', 'total')
        )
        
        # Входящие переводы между владельцами (TO) - фильтруем по городам
        incoming_from_owners_qs = MoneyTransfer.objects.filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER, use_collected=False)
        if cities:
            incoming_from_owners_qs = incoming_from_owners_qs.filter(to_partner__city__in=cities)
        incoming_from_owners = dict(
            incoming_from_owners_qs
            .values('to_partner_id')
            .annotate(total=Sum('amount'))
            .values_list('to_partner_id', 'total')
        )
        
        # Исходящие переводы между владельцами (FROM) - фильтруем по городам
        outgoing_to_owners_qs = MoneyTransfer.objects.filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER, use_collected=False)
        if cities:
            outgoing_to_owners_qs = outgoing_to_owners_qs.filter(from_partner__city__in=cities)
        outgoing_to_owners = dict(
            outgoing_to_owners_qs
            .values('from_partner_id')
            .annotate(total=Sum('amount'))
            .values_list('from_partner_id', 'total')
        )
        
        # Исходящие переводы модераторов владельцам - фильтруем по городам
        outgoing_from_mods_qs = MoneyTransfer.objects.filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.MODERATOR_TO_OWNER, use_collected=True)
        if cities:
            outgoing_from_mods_qs = outgoing_from_mods_qs.filter(from_partner__city__in=cities)
        outgoing_from_mods = dict(
            outgoing_from_mods_qs
            .values('from_partner_id')
            .annotate(total=Sum('amount'))
            .values_list('from_partner_id', 'total')
        )
        
        # Расчёт балансов владельцев (доходы)
        owner_balances = {}
        for owner in owners:
            pid = owner.id
            uid = owner.user_id
            
            # Вариант B: Получил = Payments + От модераторов + От других владельцев
            received_payments = Decimal(payments_by_user.get(uid, 0))
            received_from_mods = Decimal(incoming_from_mods.get(pid, 0))
            received_from_owners = Decimal(incoming_from_owners.get(pid, 0))
            
            sent_to_owners = Decimal(outgoing_to_owners.get(pid, 0))
            
            # Чистый баланс = Получил всего - Перевёл другим владельцам
            net_balance = received_payments + received_from_mods + received_from_owners - sent_to_owners
            
            owner_balances[pid] = {
                'partner': owner,
                'received_payments': received_payments,
                'received_from_mods': received_from_mods,
                'received_from_owners': received_from_owners,
                'total_received': received_payments + received_from_mods + received_from_owners,
                'sent_to_owners': sent_to_owners,
                'net_balance': net_balance,
            }
        
        # Справедливое распределение доходов (50/50)
        total_income_all_owners = sum(ob['net_balance'] for ob in owner_balances.values())
        fair_share_income = total_income_all_owners / Decimal(len(owners)) if owners else Decimal(0)
        
        # Дисбаланс доходов
        income_imbalance = {}
        for pid, data in owner_balances.items():
            data['fair_share'] = fair_share_income
            data['imbalance'] = data['net_balance'] - fair_share_income
            income_imbalance[pid] = data['imbalance']
        
        # ========================================
        # 2. ДОЛГИ МОДЕРАТОРОВ
        # ========================================
        
        moderator_debts = []
        for mod in moderators:
            uid = mod.user_id
            pid = mod.id
            
            collected = Decimal(payments_by_user.get(uid, 0))
            transferred = Decimal(outgoing_from_mods.get(pid, 0))
            debt = collected - transferred
            
            moderator_debts.append({
                'partner': mod,
                'collected': collected,
                'transferred': transferred,
                'debt': debt,
            })
        
        # ========================================
        # 3. ВЛОЖЕНИЯ В БИЗНЕС
        # ========================================
        
        # Закупки (PURCHASE) - реальные расходы на бизнес (фильтруем по городам)
        purchases_qs = Expense.objects.filter(date__gte=cutoff, payment_type=Expense.PaymentType.PURCHASE, paid_by_partner_id__in=owner_ids)
        if cities:
            purchases_qs = purchases_qs.filter(paid_by_partner__city__in=cities)
        purchases_by_partner = dict(
            purchases_qs
            .values('paid_by_partner_id')
            .annotate(total=Sum('amount'))
            .values_list('paid_by_partner_id', 'total')
        )
        
        # Взносы (DEPOSIT) - внесение личных средств (фильтруем по городам)
        deposits_qs = Expense.objects.filter(date__gte=cutoff, payment_type=Expense.PaymentType.DEPOSIT, paid_by_partner_id__in=owner_ids)
        if cities:
            deposits_qs = deposits_qs.filter(paid_by_partner__city__in=cities)
        deposits_by_partner = dict(
            deposits_qs
            .values('paid_by_partner_id')
            .annotate(total=Sum('amount'))
            .values_list('paid_by_partner_id', 'total')
        )
        
        # Общая сумма взносов
        total_deposits = sum(deposits_by_partner.values())
        
        # Расчёт балансов вложений (ОБНОВЛЁННАЯ ФОРМУЛА v5)
        # Справедливая доля = Все закупки / 2
        total_purchases = sum(purchases_by_partner.values())
        # Итого вложений = только закупки (БЕЗ взносов)
        total_investments = total_purchases
        fair_share_investments = total_purchases / Decimal(2)
        
        # Расходы по категориям для каждого владельца (только PURCHASE)
        category_expenses = {}
        for owner in owners:
            pid = owner.id
            expenses_qs = Expense.objects.filter(date__gte=cutoff, payment_type=Expense.PaymentType.PURCHASE, paid_by_partner_id=pid)
            if cities:
                expenses_qs = expenses_qs.filter(paid_by_partner__city__in=cities)
            expenses_by_category = dict(
                expenses_qs
                .exclude(category__isnull=True)
                .values('category__name')
                .annotate(total=Sum('amount'))
                .values_list('category__name', 'total')
            )
            
            # Батареи = Аккумуляторы + БМС + Корпуса + Сборка
            batteries = sum([
                Decimal(expenses_by_category.get('Аккумуляторы', 0)),
                Decimal(expenses_by_category.get('БМС', 0)),
                Decimal(expenses_by_category.get('Корпуса', 0)),
                Decimal(expenses_by_category.get('Сборка', 0)),
            ])
            
            # Софт = Разработка ПО + Хостинг
            software = sum([
                Decimal(expenses_by_category.get('Разработка ПО', 0)),
                Decimal(expenses_by_category.get('Хостинг', 0)),
            ])
            
            # Остальное = все остальные категории
            battery_software_categories = ['Аккумуляторы', 'БМС', 'Корпуса', 'Сборка', 'Разработка ПО', 'Хостинг']
            other = sum([
                Decimal(expenses_by_category.get(cat, 0))
                for cat in expenses_by_category.keys()
                if cat not in battery_software_categories
            ])
            
            category_expenses[pid] = {
                'batteries': batteries,
                'software': software,
                'other': other,
            }
        
        investment_balances = {}
        for owner in owners:
            pid = owner.id
            
            purchases = Decimal(purchases_by_partner.get(pid, 0))
            
            # Взносы (DEPOSIT): +сумма для автора, -сумма для других владельцев
            deposits_added = Decimal(deposits_by_partner.get(pid, 0))
            deposits_deducted = total_deposits - deposits_added
            effective_deposits = deposits_added - deposits_deducted
            
            # Баланс = Закупки + Взносы - Справедливая доля
            balance = purchases + effective_deposits - fair_share_investments
            
            investment_balances[pid] = {
                'partner': owner,
                'purchases': purchases,
                'deposits': effective_deposits,  # Показываем эффективные взносы (+/-)
                'batteries': category_expenses[pid]['batteries'],
                'software': category_expenses[pid]['software'],
                'other': category_expenses[pid]['other'],
                'fair_share': fair_share_investments,
                'balance': balance,
            }
        
        # ========================================
        # 4. ИТОГОВЫЙ ДОЛГ
        # ========================================
        
        # Для 2 владельцев: простой расчёт
        total_debt_between_owners = None
        if len(owners) == 2:
            owner1, owner2 = owners[0], owners[1]
            pid1, pid2 = owner1.id, owner2.id
            
            # По доходам
            # imbalance показывает отклонение от справедливой доли
            # Если owner1.imbalance > 0, то owner1 получил больше и должен owner2
            income_transfer = income_imbalance.get(pid1, 0)  # + значит owner1 должен owner2
            
            # По вложениям
            # balance показывает отклонение от справедливой доли вложений
            # Если owner1.balance > 0, то owner1 вложил больше и owner2 должен owner1
            # Инвертируем знак для единообразия: + значит owner1 должен owner2
            investment_transfer = -investment_balances[pid1]['balance']  # + значит owner1 должен owner2
            
            # Итого
            total_transfer = income_transfer + investment_transfer
            
            total_debt_between_owners = {
                'owner1': owner1,
                'owner2': owner2,
                'income_transfer': income_transfer,  # + значит owner1 должен owner2
                'investment_transfer': investment_transfer,  # + значит owner1 должен owner2
                'total_transfer': total_transfer,  # + значит owner1 должен owner2
            }
        
        # ========================================
        # 5. ПО МЕСЯЦАМ
        # ========================================
        
        # Payments по месяцам (фильтруем по городам)
        payments_by_month_qs = (
            Payment.objects
            .filter(date__gte=cutoff, type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD])
        )
        if cities:
            payments_by_month_qs = payments_by_month_qs.filter(city__in=cities)
        payments_by_month = (
            payments_by_month_qs
            .annotate(month=TruncMonth('date'))
            .values('month', 'created_by_id')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
        
        # Группируем по месяцам
        from collections import defaultdict
        months_data = defaultdict(lambda: defaultdict(Decimal))
        
        for row in payments_by_month:
            month = row['month']
            user_id = row['created_by_id']
            total = row['total'] or Decimal(0)
            
            partner_id = user_to_partner.get(user_id)
            if partner_id:
                months_data[month][partner_id] = total
        
        # Формируем список месяцев
        months_list = []
        for month in sorted(months_data.keys()):
            month_row = {
                'month': month,
                'by_partner': {},
                'total': Decimal(0),
            }
            
            for pid, total in months_data[month].items():
                month_row['by_partner'][pid] = total
                month_row['total'] += total
            
            months_list.append(month_row)
        
        # ========================================
        # 6. ИСТОРИЯ ПЕРЕВОДОВ
        # ========================================
        
        transfers_history = (
            MoneyTransfer.objects
            .filter(date__gte=cutoff)
            .select_related('from_partner__user', 'to_partner__user')
            .order_by('-date', '-id')[:50]
        )
        
        # Последние 10 переводов между владельцами (для таблицы под балансом доходов)
        owner_transfers_recent = (
            MoneyTransfer.objects
            .filter(date__gte=cutoff, purpose=MoneyTransfer.Purpose.OWNER_TO_OWNER)
            .select_related('from_partner__user', 'to_partner__user')
            .order_by('-date', '-id')[:10]
        )
        
        # Последние 10 вложений (закупки + взносы, для таблицы под вложениями)
        investments_recent_qs = (
            Expense.objects
            .filter(
                date__gte=cutoff,
                payment_type__in=[Expense.PaymentType.PURCHASE, Expense.PaymentType.DEPOSIT],
                paid_by_partner_id__in=owner_ids
            )
            .select_related('paid_by_partner__user', 'category')
        )
        if cities:
            investments_recent_qs = investments_recent_qs.filter(paid_by_partner__city__in=cities)
        investments_recent = list(investments_recent_qs.order_by('-date', '-id')[:10])
        
        # ========================================
        # СРАВНИТЕЛЬНАЯ СТАТИСТИКА ПО ГОРОДАМ (для админов)
        # ========================================
        city_comparison = None
        if request.user.is_superuser:
            from datetime import timedelta
            today = timezone.localdate()
            last_30_days = today - timedelta(days=30)
            
            all_cities = City.objects.filter(active=True)
            city_stats = []
            
            for city_obj in all_cities:
                # Доходы по городу за 30 дней
                city_income = Payment.objects.filter(
                    city=city_obj,
                    date__gte=last_30_days,
                    type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
                ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
                
                # Доходы за период (cutoff)
                city_income_period = Payment.objects.filter(
                    city=city_obj,
                    date__gte=cutoff,
                    type__in=[Payment.PaymentType.RENT, Payment.PaymentType.SOLD]
                ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
                
                # Модераторы города
                city_mods = FinancePartner.objects.filter(city=city_obj, role=FinancePartner.Role.MODERATOR, active=True).count()
                
                # Батареи в городе
                city_batteries = Battery.objects.filter(city=city_obj).count()
                
                # Активные клиенты
                city_clients = Client.objects.filter(
                    city=city_obj,
                    rentals__status=Rental.Status.ACTIVE
                ).distinct().count()
                
                city_stats.append({
                    'city': city_obj,
                    'income_30_days': city_income,
                    'income_period': city_income_period,
                    'moderators_count': city_mods,
                    'batteries_count': city_batteries,
                    'active_clients': city_clients,
                })
            
            # Сортируем по доходу за 30 дней
            city_comparison = sorted(city_stats, key=lambda x: x['income_30_days'], reverse=True)
        
        # ========================================
        # CONTEXT
        # ========================================
        
        context = {
            'title': 'Бухучёт',
            'cutoff_date': cutoff,
            'owners': owners,
            'moderators': moderators,
            'partners_dict': partners_dict,
            
            # Долги модераторов
            'moderator_debts': moderator_debts,
            
            # Балансы владельцев (доходы)
            'owner_balances': owner_balances,
            'fair_share_income': fair_share_income,
            'total_income_all_owners': total_income_all_owners,
            
            # Вложения
            'investment_balances': investment_balances,
            'fair_share_investments': fair_share_investments,
            'total_investments': total_investments,
            
            # Итоговый долг
            'total_debt': total_debt_between_owners,
            
            # По месяцам
            'months_list': months_list,
            
            # История
            'transfers_history': transfers_history,
            'owner_transfers_recent': owner_transfers_recent,
            'investments_recent': investments_recent,
            
            # Сравнительная статистика по городам
            'city_comparison': city_comparison,
            'cities': City.objects.filter(active=True) if request.user.is_superuser else [],
            
            # Для форм
            'partner_choices': [{'id': p.id, 'name': p.user.username, 'role': p.role} for p in partners],
            'today': timezone.localdate(),
        }
        
        base_ctx = self.admin_site.each_context(request)
        context = {**base_ctx, **context}
        
        return TemplateResponse(request, self.change_list_template, context)


from .models import FinanceOverviewProxy2
try:
    @admin.register(FinanceOverviewProxy2)
    class FinanceOverviewProxy2Admin(ModeratorRestrictedMixin, FinanceOverviewAdmin2):
        pass
except admin.sites.AlreadyRegistered:
    pass

class ActiveRentalFilter(admin.SimpleListFilter):
    title = "Активный договор"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return (
            ("1", "С активным"),
            ("0", "Без активного"),
        )

    def queryset(self, request, queryset):
        from django.db.models import Exists, OuterRef, Q
        now = timezone.now()
        active_qs = Rental.objects.filter(client=OuterRef("pk")).filter(
            status=Rental.Status.ACTIVE
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
        queryset = queryset.annotate(has_active=Exists(active_qs))
        if self.value() == "1":
            return queryset.filter(has_active=True)
        if self.value() == "0":
            return queryset.filter(has_active=False)
        return queryset


@admin.register(Client)
class ClientAdmin(ModeratorReadOnlyRelatedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    list_display = ("id", "name", "phone", "pesel", "city", "created_at", "has_active")
    list_filter = (ActiveRentalFilter, "city")
    search_fields = ("name", "phone", "pesel")
    autocomplete_fields = ["city"]

    def has_active(self, obj):
        return getattr(obj, "has_active", False)
    has_active.boolean = True
    has_active.short_description = "Активный договор"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        client = self.get_object(request, object_id)
        if not client:
            return super().change_view(request, object_id, form_url, extra_context)

        # Получаем все root-группы договоров клиента
        root_rentals = client.rentals.filter(parent__isnull=True).order_by("contract_code")

        # Собираем данные для шаблона
        rental_data = []
        now = timezone.now()
        for root in root_rentals:
            versions = root.group_versions()
            start = versions.first().start_at if versions.exists() else None
            end = versions.last().end_at if versions.exists() else None
            days_total = (end or now) - (start or now)
            days_total = days_total.days if days_total else 0
            billable_days = sum(v.billable_days() for v in versions)
            charges = root.group_charges_until(now)
            paid = root.group_paid_total()
            balance = (paid or Decimal(0)) - (charges or Decimal(0))
            deposit = root.group_deposit_total()
            # Определяем цветовую метку баланса (зелёный, если не должен)
            if (charges or 0) == 0 and (paid or 0) == 0:
                color = 'gray'
            elif balance >= 0:
                color = 'green'
            elif deposit and (balance + deposit) >= 0:
                color = 'yellow'
            else:
                color = 'red'
            rental_data.append({
                "contract_code": root.contract_code,
                "version_range": f"v1–v{versions.count()}",
                "start": start,
                "end": end,
                "days_total": days_total,
                "billable_days": billable_days,
                "charges": charges,
                "paid": paid,
                "balance": balance,
                "deposit": deposit,
                "color": color,
                "url": reverse("admin:rental_rental_change", args=[root.pk]),
            })

        # Платежи по всем договорам клиента
        payments = Payment.objects.filter(rental__root__in=root_rentals).order_by("date")

        if extra_context is None:
            extra_context = {}
        extra_context["rental_data"] = rental_data
        extra_context["payments"] = payments

        return super().change_view(request, object_id, form_url, extra_context)

    list_filter = (ActiveRentalFilter,)

    class Media:
        js = [
            "https://unpkg.com/htmx.org@1.9.2",
            "https://unpkg.com/htmx.org@1.9.2/dist/ext/morphdom-swap.umd.js",
        ]

    def balance_badge(self, obj):
        # Суммарный баланс по всем root-догорам клиента: Оплатил - Должен
        roots = obj.rentals.filter(parent__isnull=True)
        from decimal import Decimal
        charges = Decimal(0)
        paid = Decimal(0)
        deposit = Decimal(0)
        now = timezone.now()
        for r in roots:
            charges += r.group_charges_until(now)
            paid += r.group_paid_total()
            deposit += r.group_deposit_total()
        balance = paid - charges
        color = "secondary"
        if charges == 0 and paid == 0:
            color = "secondary"
        elif balance >= 0:
            color = "success"
        elif (balance + deposit) >= 0:
            color = "warning"
        else:
            color = "danger"
        formatted = f"{balance:.2f}"
        return format_html('<span class="badge badge-balance bg-{}">{}</span>', color, formatted)
    balance_badge.short_description = "Баланс"

    def changelist_view(self, request, extra_context=None):
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,E",
                    "location": "admin.py:ClientAdmin.changelist_view:entry",
                    "message": "ClientAdmin.changelist_view started",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "is_htmx": getattr(request, "htmx", False)
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        self.list_filter = (ActiveRentalFilter,)
        if getattr(request, "htmx", False):
            # Для HTMX отдаём только таблицу результатов
            self.list_display = ("id", "name", "phone", "pesel", "created_at", "has_active")
            response = super().changelist_view(request, extra_context)
            # Заменяем шаблон на частичный список результатов, чтобы не дублировать шапку
            try:
                response.template_name = 'admin/change_list_results.html'
            except Exception:
                pass
            # #region agent log
            try:
                elapsed = (time_module.time() - start_time) * 1000
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "E",
                        "location": "admin.py:ClientAdmin.changelist_view:htmx_exit",
                        "message": "ClientAdmin.changelist_view HTMX completed",
                        "data": {"elapsed_ms": elapsed},
                        "timestamp": time_module.time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            return response
        # Не-HTMX: обычная страница
        self.list_display = ("id", "name", "phone", "pesel", "created_at", "has_active")
        response = super().changelist_view(request, extra_context)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "E",
                    "location": "admin.py:ClientAdmin.changelist_view:exit",
                    "message": "ClientAdmin.changelist_view completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return response

    def get_queryset(self, request):
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,F",
                    "location": "admin.py:ClientAdmin.get_queryset:entry",
                    "message": "ClientAdmin.get_queryset started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        qs = super().get_queryset(request)
        qs = qs.select_related('city')
        from django.db.models import Exists, OuterRef, Q
        now = timezone.now()
        active_qs = Rental.objects.filter(client=OuterRef("pk")).filter(
            status=Rental.Status.ACTIVE
        ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now))
        qs = qs.annotate(has_active=Exists(active_qs))
        # #region agent log
        try:
            count = qs.count()
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "F",
                    "location": "admin.py:ClientAdmin.get_queryset:exit",
                    "message": "ClientAdmin.get_queryset completed",
                    "data": {"count": count, "elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return qs
    
    def get_form(self, request, obj=None, **kwargs):
        """Делаем поле city readonly для модераторов"""
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and 'city' in form.base_fields:
            form.base_fields['city'].disabled = True
            form.base_fields['city'].help_text = "Город автоматически устанавливается из города модератора"
        return form
    
    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем city для модераторов"""
        # Для модераторов при создании устанавливаем город
        if not change and not obj.city and not request.user.is_superuser:
            obj.city = get_user_city(request.user)
        super().save_model(request, obj, form, change)


class BatteryTransferActionForm(ActionForm):
    """Форма для action создания запроса на перенос батарей"""
    to_city = forms.ModelChoiceField(
        queryset=City.objects.none(),  # Будет установлен в __init__
        required=True,
        label="Город назначения",
        help_text="Выберите город, в который нужно перенести батареи"
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Комментарий",
        help_text="Дополнительная информация о переносе"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Устанавливаем queryset для выбора активных городов
        self.fields['to_city'].queryset = City.objects.filter(active=True).order_by('name')


@admin.register(Battery)
class BatteryAdmin(ModeratorRestrictedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    # Убираем тяжёлые колонки roi_progress из списка, возвращаем в detail
    list_display = ("id", "short_code", "status_display", "usage_now", "serial_number", "city", "cost_price", "created_at")
    search_fields = ("short_code", "serial_number")
    list_filter = ("status", "city")
    autocomplete_fields = ["city"]
    change_list_template = 'admin/rental/battery/change_list.html'
    list_per_page = 50
    ordering = ['id']  # Сортировка по умолчанию от меньшего к большему
    actions = ["create_transfer_request"]
    action_form = BatteryTransferActionForm

    def has_module_permission(self, request):
        """Скрываем модуль из списка для модераторов, но разрешаем autocomplete"""
        if is_moderator(request.user):
            return False
        return super().has_module_permission(request) if hasattr(super(), 'has_module_permission') else True
    
    def has_view_permission(self, request, obj=None):
        """Разрешаем просмотр для autocomplete запросов"""
        # Проверяем, является ли это autocomplete запросом
        if request.path and '/autocomplete/' in request.path:
            return True
        if is_moderator(request.user):
            return False
        return super().has_view_permission(request, obj) if hasattr(super(), 'has_view_permission') else True

    def get_queryset(self, request):
        """Оптимизация: предзагрузка assignments для избежания N+1"""
        qs = super().get_queryset(request)
        qs = qs.select_related('city')
        qs = qs.prefetch_related(
            'assignments__rental__client',
            'assignments__rental__root'
        )
        return qs
    
    def get_form(self, request, obj=None, **kwargs):
        """Делаем поле city readonly для модераторов"""
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and 'city' in form.base_fields:
            form.base_fields['city'].disabled = True
            form.base_fields['city'].help_text = "Город автоматически устанавливается из города модератора"
        return form
    
    def get_search_results(self, request, queryset, search_term):
        """Фильтрация результатов autocomplete для модераторов"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "I",
                    "location": "admin.py:BatteryAdmin.get_search_results:entry",
                    "message": "BatteryAdmin.get_search_results called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "search_term": search_term,
                        "path": request.path if hasattr(request, 'path') else None,
                        "has_queryset": queryset is not None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        
        # Если пользователь модератор, фильтруем по городу
        if is_moderator(request.user):
            city = get_user_city(request.user)
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "I",
                        "location": "admin.py:BatteryAdmin.get_search_results:filtering",
                        "message": "Filtering batteries by city for moderator",
                        "data": {
                            "city_id": city.id if city else None,
                            "city_name": city.name if city else None
                        },
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            if city:
                queryset = queryset.filter(city=city)
        
        # #region agent log
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "I",
                    "location": "admin.py:BatteryAdmin.get_search_results:exit",
                    "message": "BatteryAdmin.get_search_results completed",
                    "data": {
                        "queryset_filtered": True
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return queryset, use_distinct
    
    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем city для модераторов"""
        # Для модераторов при создании устанавливаем город
        if not change and not obj.city and not request.user.is_superuser:
            obj.city = get_user_city(request.user)
        super().save_model(request, obj, form, change)

    def usage_now(self, obj):
        # Активные договоры сейчас, где батарея назначена
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        assignments = obj.assignments.select_related('rental__client').all()
        active_roots = []
        for a in assignments:
            start = timezone.localtime(a.start_at, tz)
            end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if start <= now and (end is None or end > now):
                root = a.rental.root if hasattr(a.rental, 'root') and a.rental.root_id else a.rental
                active_roots.append(root)
        # Уникальные root договоры
        uniq = []
        seen = set()
        for r in active_roots:
            if r.pk not in seen:
                uniq.append(r)
                seen.add(r.pk)
        parts = []
        for r in uniq:
            client_link = format_html('<a href="{}" style="color:#000; text-decoration:none;">{}</a>', reverse('admin:rental_client_change', args=[r.client_id]), r.client.name)
            rental_link = format_html('<a href="{}" style="color:#000; text-decoration:none;">{}</a>', reverse('admin:rental_rental_change', args=[r.pk]), r.contract_code)
            parts.append(format_html('[{}, {}]', client_link, rental_link))
        count = len(uniq)
        # Цвет + инлайн-стиль как fallback, если Bootstrap не подгрузился
        bg = 'secondary'
        bg_color = '#6c757d'
        if count == 1:
            bg = 'success'
            bg_color = '#198754'
        elif count > 1:
            bg = 'warning'
            bg_color = '#ffc107'
        content = format_html(', '.join(['{}'] * len(parts)), *parts) if parts else '-'
        return format_html('<span class="badge bg-{}" style="background-color:{}; color:#000;">{}</span>', bg, bg_color, content)
    usage_now.short_description = "В аренде"

    @admin.display(ordering='status', description='Статус')
    def status_display(self, obj):
        """Отображение статуса батареи с бэджами"""
        if not obj.status:
            return format_html('<span class="badge bg-secondary">Не указан</span>')
        
        # Цвета для статусов (Bootstrap 5)
        colors = {
            'rented': 'success',      # Зелёный - в аренде
            'service': 'warning',     # Жёлтый - на сервисе
            'available': 'primary',   # Синий - доступен
            'sold': 'info'            # Голубой - продана
        }
        
        # Русские названия статусов из BatteryStatusLog.Kind
        labels = {
            'rented': 'В аренде',
            'service': 'Сервис',
            'available': 'Доступный',
            'sold': 'Продана'
        }
        
        color = colors.get(obj.status, 'secondary')
        label = labels.get(obj.status, obj.status)
        
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            label
        )

    def roi_progress(self, obj):
        # Окупаемость по фактическим оплатам: распределяем оплаты по доле "нагрузки" батареи
        from decimal import Decimal, InvalidOperation
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        # Группируем по root-договорам, где батарея была назначена
        by_root_share = {}
        days_total = 0
        # Сначала соберём версии по root для быстрого доступа
        roots = {}
        for a in obj.assignments.select_related('rental').all():
            root = a.rental.root if getattr(a.rental, 'root_id', None) else a.rental
            roots.setdefault(root.pk, root)
        # Для каждого root считаем долю батареи (battery_share) и дни аренды
        for root in roots.values():
            versions = list(root.group_versions())
            # Precompute version windows with daily_rate
            v_windows = []
            for v in versions:
                v_start = timezone.localtime(v.start_at, tz)
                v_end = timezone.localtime(v.end_at, tz) if v.end_at else now
                v_windows.append((v_start, v_end, (v.weekly_rate or Decimal(0)) / Decimal(7)))
            battery_share = Decimal(0)
            # Соберём интервалы назначений этой батареи внутри данного root
            for a in obj.assignments.filter(rental__root=root).all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else now
                # Идём по календарным дням, считаем только те дни, когда есть активная версия
                d = a_start.date()
                end_date = a_end.date()
                while d <= end_date:
                    day_start = timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
                    day_end = timezone.make_aware(datetime.combine(d + timedelta(days=1), time(0, 0)), tz)
                    rate = None
                    for v_start, v_end, v_rate in v_windows:
                        if v_start < day_end and v_end > day_start:
                            rate = v_rate
                            break
                    if rate is not None:
                        battery_share += rate
                    d += timedelta(days=1)
            # Считаем дни аренды без привязки к активной версии
            days_total = 0
            for a in obj.assignments.all():
                a_start = timezone.localtime(a.start_at, tz)
                a_end = timezone.localtime(a.end_at, tz) if a.end_at else now
                d = a_start.date()
                end_date = a_end.date()
                while d <= end_date:
                    days_total += 1
                    d += timedelta(days=1)
            # Общая сумма начислений по группе
            group_charges = root.group_charges_until(until=now) or Decimal(0)
            group_paid = root.group_paid_total() or Decimal(0)
            if group_charges > 0 and battery_share > 0:
                by_root_share[root.pk] = (battery_share, group_charges, group_paid)
        # Распределяем оплаты пропорционально
        allocated = Decimal(0)
        for battery_share, group_charges, group_paid in by_root_share.values():
            try:
                allocated += (battery_share / group_charges) * group_paid
            except (InvalidOperation, ZeroDivisionError):
                continue
        cost = obj.cost_price or Decimal(0)
        try:
            pct = int(round((allocated / cost) * 100)) if cost else 0
        except Exception:
            pct = 0
        # Цвета прогресса
        bar_class = 'bg-danger'
        bar_style = ''
        if pct >= 100:
            bar_class = 'bg-success'
        elif pct >= 75:
            bar_class = ''
            bar_style = 'background-color: orange;'
        elif pct >= 25:
            bar_class = 'bg-warning'
        width = min(max(pct, 0), 150)
        # Внутри бара показываем значение процента
        return format_html(
            '<div>'
            '<div class="progress" style="width:160px; height: 1rem;">'
            '<div class="progress-bar {}" role="progressbar" style="width: {}%; {};" aria-valuenow="{}" aria-valuemin="0" aria-valuemax="150">{}%</div>'
            '</div>'
            '<div style="font-size: 0.8rem; color: #666;">Дней в аренде: {}</div>'
            '</div>',
            bar_class, width, bar_style, pct, pct, days_total
        )
    roi_progress.short_description = "Окупаемость"
    
    @admin.action(description="Создать запрос на перенос батарей")
    def create_transfer_request(self, request, queryset):
        """Создает запросы на перенос для выбранных батарей"""
        # Django admin автоматически показывает форму через action_form
        # Когда форма подтверждена, данные приходят через request.POST
        form_data = request.POST
        
        # Получаем данные из формы (Django admin передает их через POST)
        to_city_id = form_data.get('to_city')
        note = form_data.get('note', '')
        
        if not to_city_id:
            self.message_user(
                request,
                "Необходимо выбрать город назначения",
                level=messages.ERROR
            )
            return
        
        try:
            to_city = City.objects.get(id=to_city_id, active=True)
        except City.DoesNotExist:
            self.message_user(
                request,
                "Выбранный город не найден",
                level=messages.ERROR
            )
            return
        
        # Получаем город отправителя (модератора или из батареи)
        user_city = get_user_city(request.user) if not request.user.is_superuser else None
        
        created_count = 0
        errors = []
        
        for battery in queryset:
            # Определяем город отправления
            from_city = user_city if user_city else battery.city
            
            if not from_city:
                errors.append(f"У батареи {battery.short_code} не указан город")
                continue
            
            if from_city.id == to_city.id:
                errors.append(f"Батарея {battery.short_code} уже находится в городе {to_city.name}")
                continue
            
            # Проверяем активную аренду
            now = timezone.now()
            active_assignments = battery.assignments.filter(
                start_at__lte=now
            ).filter(
                Q(end_at__isnull=True) | Q(end_at__gt=now)
            ).filter(
                rental__status=Rental.Status.ACTIVE
            ).exists()
            
            if active_assignments:
                errors.append(f"Батарея {battery.short_code} находится в активной аренде")
                continue
            
            # Создаем запрос на перенос
            try:
                BatteryTransfer.objects.create(
                    battery=battery,
                    from_city=from_city,
                    to_city=to_city,
                    requested_by=request.user,
                    note=note,
                    status=BatteryTransfer.Status.PENDING
                )
                created_count += 1
            except Exception as e:
                errors.append(f"Ошибка при создании запроса для {battery.short_code}: {str(e)}")
        
        if created_count > 0:
            self.message_user(
                request,
                f"Создано запросов на перенос: {created_count}",
                level=messages.SUCCESS
            )
        
        if errors:
            for error in errors:
                self.message_user(request, error, level=messages.ERROR)

    def changelist_view(self, request, extra_context=None):
        """Добавляем статистику в контекст списка батарей с кэшированием"""
        from django.core.cache import cache
        
        extra_context = extra_context or {}
        
        # Кэш на 24 часа (86400 секунд)
        cache_key = 'battery_admin_stats'
        cached_stats = cache.get(cache_key)
        
        if cached_stats is None:
            # Статистика по статусам
            from django.db.models import Count, Sum
            status_stats = Battery.objects.values('status').annotate(
                count=Count('id'),
                total_cost=Sum('cost_price')
            ).order_by('status')
            
            # Общая статистика
            total_batteries = Battery.objects.count()
            total_cost = Battery.objects.aggregate(total=Sum('cost_price'))['total'] or 0
            
            # Форматируем статистику по статусам
            formatted_stats = []
            status_labels = {
                'rented': 'В аренде',
                'service': 'Сервис',
                'available': 'Доступны',
                'sold': 'Продано'
            }
            status_colors = {
                'rented': 'success',
                'service': 'warning',
                'available': 'primary',
                'sold': 'info'
            }
            
            for stat in status_stats:
                if stat['status']:
                    formatted_stats.append({
                        'label': status_labels.get(stat['status'], stat['status']),
                        'count': stat['count'],
                        'total_cost': stat['total_cost'] or 0,
                        'color': status_colors.get(stat['status'], 'secondary')
                    })
            
            cached_stats = {
                'total_batteries': total_batteries,
                'total_cost': total_cost,
                'status_breakdown': formatted_stats
            }
            
            # Кэшируем на 24 часа
            cache.set(cache_key, cached_stats, 86400)
        
        extra_context['battery_stats'] = cached_stats
        
        return super().changelist_view(request, extra_context)



class RentalBatteryAssignmentForm(forms.ModelForm):
    class Meta:
        model = RentalBatteryAssignment
        fields = "__all__"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # поле видно, но не обязательно; если оставить пустым при создании — подставим старт договора
        if 'start_at' in self.fields:
            self.fields['start_at'].required = False
    def clean(self):
        cd = super().clean()
        start = cd.get('start_at')
        if not start:
            rental = getattr(self.instance, 'rental', None)
            if rental and getattr(rental, 'start_at', None):
                cd['start_at'] = rental.start_at
                self.cleaned_data['start_at'] = rental.start_at
        return cd

class RentalBatteryAssignmentInline(admin.TabularInline):
    model = RentalBatteryAssignment
    form = RentalBatteryAssignmentForm
    extra = 0
    readonly_fields = ("created_by", "updated_by")
    autocomplete_fields = ("battery",)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Запрещаем добавление/редактирование батарей для модераторов"""
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        
        if db_field.name == "battery" and is_moderator(request.user):
            # Запрещаем все действия со связанными объектами для модераторов
            if hasattr(field.widget, 'can_add_related'):
                field.widget.can_add_related = False
            if hasattr(field.widget, 'can_change_related'):
                field.widget.can_change_related = False
            if hasattr(field.widget, 'can_delete_related'):
                field.widget.can_delete_related = False
            if hasattr(field.widget, 'can_view_related'):
                field.widget.can_view_related = False
        
        return field
    
    def get_formset(self, request, obj=None, **kwargs):
        """Дополнительно запрещаем добавление/редактирование батарей для модераторов через get_formset"""
        formset = super().get_formset(request, obj, **kwargs)
        
        if is_moderator(request.user):
            # Для модераторов запрещаем все действия со связанными объектами
            if hasattr(formset.form, 'base_fields'):
                battery_field = formset.form.base_fields.get('battery')
                if battery_field and hasattr(battery_field, 'widget'):
                    if hasattr(battery_field.widget, 'can_add_related'):
                        battery_field.widget.can_add_related = False
                    if hasattr(battery_field.widget, 'can_change_related'):
                        battery_field.widget.can_change_related = False
                    if hasattr(battery_field.widget, 'can_delete_related'):
                        battery_field.widget.can_delete_related = False
                    if hasattr(battery_field.widget, 'can_view_related'):
                        battery_field.widget.can_view_related = False
        
        return formset


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            field = formset.form.base_fields.get('created_by')
            if field:
                field.queryset = User.objects.filter(is_staff=True).order_by('username')
                field.label = "Кто принял деньги"
                if request.user.is_superuser:
                    field.required = True
                else:
                    field.initial = request.user.pk
                    field.disabled = True
                    field.help_text = "Доступно только суперпользователю"
        except Exception:
            pass
        return formset


class NewVersionActionForm(ActionForm):
    new_weekly_rate = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2, label="Новая недельная ставка (PLN)"
    )
    new_start_at = forms.DateTimeField(required=False, label="Начало новой версии", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    free_days = forms.IntegerField(required=False, min_value=0, label="Бесплатные дни")
    payment_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма оплаты")
    payment_method = forms.ChoiceField(required=False, choices=[('cash','Наличные'),('blik','BLIK'),('revolut','Revolut'),('other','Другое')], label="Метод оплаты")
    payment_note = forms.CharField(required=False, label="Примечание к оплате")
    deposit_return_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Сумма возврата депозита")
    deposit_return_note = forms.CharField(required=False, label="Примечание к возврату депозита")


@admin.register(Rental)
class RentalAdmin(ModeratorReadOnlyRelatedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    autocomplete_fields = ('client', 'city')

    def changelist_view(self, request, extra_context=None):
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,E",
                    "location": "admin.py:RentalAdmin.changelist_view:entry",
                    "message": "RentalAdmin.changelist_view started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        if extra_context is None:
            extra_context = {}
        from .models import Client
        # Используем только необходимые поля, чтобы не тянуть всё
        extra_context['clients'] = Client.objects.only('id', 'name').order_by('name')
        # Добавляем список городов для фильтра (только для администраторов)
        if request.user.is_superuser:
            extra_context['cities'] = City.objects.filter(active=True).order_by('name')
        response = super().changelist_view(request, extra_context=extra_context)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "E",
                    "location": "admin.py:RentalAdmin.changelist_view:exit",
                    "message": "RentalAdmin.changelist_view completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return response

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList

        class CustomChangeList(ChangeList):
            def get_results(self, request):
                super().get_results(request)
                # Приглушить строки с статусом modified или closed
                for result in self.result_list:
                    if hasattr(result, 'status') and result.status in [result.Status.MODIFIED, result.Status.CLOSED]:
                        result.row_class = 'opacity-80'

        return CustomChangeList

    def get_queryset(self, request):
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,F",
                    "location": "admin.py:RentalAdmin.get_queryset:entry",
                    "message": "RentalAdmin.get_queryset started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        qs = super().get_queryset(request)
        # Предзагрузить связанные объекты, чтобы избежать N+1
        from django.db.models import Count
        qs = qs.select_related('client', 'city').prefetch_related('assignments', 'assignments__battery')
        qs = qs.annotate(assignments_count=Count('assignments'))
        # Добавить row_class для приглушения строк
        for obj in qs:
            if obj.status in [obj.Status.MODIFIED, obj.Status.CLOSED]:
                obj.row_class = 'opacity-80'
            else:
                obj.row_class = ''
        # #region agent log
        try:
            count = qs.count()
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "F",
                    "location": "admin.py:RentalAdmin.get_queryset:exit",
                    "message": "RentalAdmin.get_queryset completed",
                    "data": {"count": count, "elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return qs
    
    def get_search_results(self, request, queryset, search_term):
        """Фильтрация результатов autocomplete для модераторов"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "F",
                    "location": "admin.py:RentalAdmin.get_search_results:entry",
                    "message": "RentalAdmin.get_search_results called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "search_term": search_term,
                        "has_queryset": queryset is not None,
                        "model_name": queryset.model.__name__ if queryset else None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        
        # Если пользователь модератор, фильтруем по городу
        user_is_moderator = is_moderator(request.user)
        # #region agent log
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,F",
                    "location": "admin.py:RentalAdmin.get_search_results:after_super",
                    "message": "After super().get_search_results",
                    "data": {
                        "user_is_moderator": user_is_moderator,
                        "has_queryset": queryset is not None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        if user_is_moderator:
            city = get_user_city(request.user)
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "B,F",
                        "location": "admin.py:RentalAdmin.get_search_results:before_filter",
                        "message": "Before filtering by city",
                        "data": {
                            "city_id": city.id if city else None,
                            "city_name": city.name if city else None
                        },
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            if city:
                queryset = queryset.filter(city=city)
                # #region agent log
                try:
                    with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "F",
                            "location": "admin.py:RentalAdmin.get_search_results:after_filter",
                            "message": "After filtering by city",
                            "data": {
                                "queryset_filtered": True
                            },
                            "timestamp": __import__('time').time() * 1000
                        }, ensure_ascii=False) + '\n')
                except: pass
                # #endregion
        
        return queryset, use_distinct

    class Media:
        css = {
            'all': ('admin/css/custom.css',)
        }

    list_display = (
        "id", "contract_code", "version", "client", "city", "start_at", "end_at",
        "weekly_rate", "status", "assigned_batteries_short",
    )
    list_filter = ("status", "city")
    list_per_page = 25  # Ограничение записей на странице для ускорения отображения


    search_fields = ("client__name", "contract_code")
    inlines = [RentalBatteryAssignmentInline, PaymentInline]

    readonly_fields = ("group_charges_now", "group_paid_total", "group_deposit_total", "group_balance_now", "created_by", "updated_by")
    
    def get_inlines(self, request, obj):
        """Скрываем PaymentInline для модераторов"""
        inlines = list(super().get_inlines(request, obj))
        if is_moderator(request.user):
            # Убираем PaymentInline для модераторов
            inlines = [inline for inline in inlines if inline != PaymentInline]
        return inlines
    
    def batteries_count_now(self, obj):
        tz = timezone.get_current_timezone()
        now = timezone.now()
        count = 0
        batteries = []
        for a in obj.assignments.all():
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                count += 1
                batteries.append(a.battery.short_code)
        obj._batteries_list = batteries
        return count

    def assigned_batteries_short(self, obj):
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                    "location": "admin.py:RentalAdmin.assigned_batteries_short:entry",
                    "message": "assigned_batteries_short called",
                    "data": {"rental_id": obj.id if obj else None},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        tz = timezone.get_current_timezone()
        now = timezone.now()
        codes = []
        # #region agent log
        try:
            assignments_before = getattr(obj, '_prefetched_objects_cache', {}).get('assignments', None)
            has_prefetch = assignments_before is not None
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                    "location": "admin.py:RentalAdmin.assigned_batteries_short:before_query",
                    "message": "Before assignments query",
                    "data": {"has_prefetch": has_prefetch, "prefetch_count": len(assignments_before) if assignments_before else None},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        # Используем prefetch_related если доступен (Django автоматически использует его)
        # Просто обращаемся к assignments.all() - Django использует prefetch если он был установлен
        assignments = obj.assignments.all()
        
        for a in assignments:
            a_start = timezone.localtime(a.start_at, tz)
            a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
            if a_start <= now and (a_end is None or a_end > now):
                # Батарея должна быть загружена через prefetch_related('assignments__battery')
                if hasattr(a, 'battery') and a.battery:
                    codes.append(a.battery.short_code)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                    "location": "admin.py:RentalAdmin.assigned_batteries_short:exit",
                    "message": "assigned_batteries_short completed",
                    "data": {"codes_count": len(codes), "elapsed_ms": elapsed, "used_prefetch": has_prefetch},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        if obj.status in [obj.Status.ACTIVE, obj.Status.MODIFIED]:
            if codes:
                return format_html(' '.join(['<span class="badge bg-secondary me-1">{}</span>'] * len(codes)), *codes)
            else:
                return mark_safe('<span class="text-muted">—</span>')
        if obj.status == obj.Status.CLOSED:
            return mark_safe('<span class="text-muted">—</span>')
        return ''

    assigned_batteries_short.short_description = "Батареи"

    # Custom template for change_form
    change_form_template = 'admin/rental/rental/change_form.html'
    
    def get_list_display(self, request):
        base = list(super().get_list_display(request)) if hasattr(super(), 'get_list_display') else list(self.list_display)
        # вставим количество батарей рядом с агрегатами
        if "batteries_count_now" not in base:
            base = list(self.list_display)
        return tuple(base)

    def fmt_pln(self, value):
        try:
            return f"{value:.2f} PLN"
        except Exception:
            return value


    def group_charges_now(self, obj):
        return self.fmt_pln(obj.group_charges_until(until=timezone.now()))
    group_charges_now.short_description = "Начислено"

    def group_paid_total(self, obj):
        return self.fmt_pln(obj.group_paid_total())
    group_paid_total.short_description = "Оплачено"

    def group_deposit_total(self, obj):
        return self.fmt_pln(obj.group_deposit_total())
    group_deposit_total.short_description = "Депозит"

    def group_balance_now(self, obj):
        now = timezone.now()
        charges = obj.group_charges_until(until=now)
        paid = obj.group_paid_total()
        return self.fmt_pln(paid - charges)

    group_balance_now.short_description = "Баланс"

    def add_view(self, request, form_url='', extra_context=None):
        """Логирование для страницы добавления"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:RentalAdmin.add_view:entry",
                    "message": "RentalAdmin.add_view started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        response = super().add_view(request, form_url, extra_context)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:RentalAdmin.add_view:exit",
                    "message": "RentalAdmin.add_view completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return response
    
    def get_form(self, request, obj=None, **kwargs):
        """Делаем поле city readonly для модераторов и фильтруем клиентов"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:RentalAdmin.get_form:entry",
                    "message": "get_form called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "obj_id": obj.id if obj else None,
                        "is_add": obj is None
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        form = super().get_form(request, obj, **kwargs)
        user_is_moderator = is_moderator(request.user)
        if not request.user.is_superuser:
            if 'city' in form.base_fields:
                if user_is_moderator:
                    # Скрываем поле city для модераторов
                    form.base_fields.pop('city', None)
                else:
                    form.base_fields['city'].disabled = True
                    form.base_fields['city'].help_text = "Город автоматически устанавливается из города клиента или модератора"
            if 'client' in form.base_fields:
                # Фильтруем клиентов по городу модератора
                city = get_user_city(request.user)
                if city:
                    form.base_fields['client'].queryset = Client.objects.filter(city=city).only('id', 'name')
        
        # Скрываем поля для модераторов
        if user_is_moderator:
            fields_to_hide = [
                'battery_type',
                'battery_numbers',
                'created_by_name',
                'updated_by_name',
                'parent',
                'root',
                'version',
                'contract_code'
            ]
            for field_name in fields_to_hide:
                if field_name in form.base_fields:
                    form.base_fields.pop(field_name, None)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:RentalAdmin.get_form:exit",
                    "message": "get_form completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return form
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Фильтрация клиентов и батарей по городу для модераторов"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:RentalAdmin.formfield_for_foreignkey:entry",
                    "message": "formfield_for_foreignkey called",
                    "data": {
                        "db_field_name": db_field.name,
                        "user_id": request.user.id if request.user else None
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        if db_field.name == "client" and not request.user.is_superuser:
            city = get_user_city(request.user)
            if city:
                kwargs["queryset"] = Client.objects.filter(city=city).only('id', 'name')
                # #region agent log
                try:
                    elapsed = (time_module.time() - start_time) * 1000
                    with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "H",
                            "location": "admin.py:RentalAdmin.formfield_for_foreignkey:after_client_filter",
                            "message": "After filtering client queryset",
                            "data": {"elapsed_ms": elapsed},
                            "timestamp": time_module.time() * 1000
                        }, ensure_ascii=False) + '\n')
                except: pass
                # #endregion
        elif db_field.name == "battery" and not request.user.is_superuser:
            city = get_user_city(request.user)
            if city:
                kwargs["queryset"] = Battery.objects.filter(city=city)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def save_model(self, request, obj, form, change):
        # Автоматически устанавливаем city из client.city при создании
        if not change and not obj.city:
            if obj.client_id and obj.client.city:
                obj.city = obj.client.city
            elif not request.user.is_superuser:
                obj.city = get_user_city(request.user)
        if not change and not getattr(obj, 'created_by_id', None):
            obj.created_by = request.user
        obj.updated_by = request.user
        # проставляем имена для Supabase
        if hasattr(obj, 'created_by_name') and obj.created_by and not obj.created_by_name:
            obj.created_by_name = request.user.get_full_name() or request.user.username or request.user.email
        if hasattr(obj, 'updated_by_name'):
            obj.updated_by_name = request.user.get_full_name() or request.user.username or request.user.email
        super().save_model(request, obj, form, change)
        
        # Отобразить человеку сразу обновленные агрегаты
        self.message_user(request, f"Баланс: {self.group_balance_now(obj)}; Начислено: {self.group_charges_now(obj)}; Оплачено: {self.group_paid_total(obj)}; Депозит: {self.group_deposit_total(obj)}")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            # Default start_at to rental.start_at if not provided in inline
            if hasattr(inst, "start_at") and not inst.start_at:
                parent_start = getattr(form.instance, "start_at", None)
                if parent_start:
                    inst.start_at = parent_start
            if hasattr(inst, "created_by") and not inst.pk:
                inst.created_by = request.user
            if hasattr(inst, "updated_by"):
                inst.updated_by = request.user
            inst.save()
        formset.save_m2m()

    def make_new_version(self, request, queryset):
        count = 0
        # Получаем ставку из формы действий
        rate_str = request.POST.get("new_weekly_rate")
        new_rate = None
        # Получаем дату и время из формы (новое поле)
        new_start = None
        if request.POST.get("new_start_at"):
            try:
                # получаем datetime-local => 'YYYY-MM-DDTHH:MM'
                new_start = timezone.datetime.fromisoformat(request.POST.get("new_start_at").replace('T', ' '))
                if timezone.is_naive(new_start):
                    new_start = timezone.make_aware(new_start, timezone.get_current_timezone())
            except Exception:
                new_start = None
        # Получаем бесплатные дни
        free_days_str = request.POST.get("free_days")
        free_days = 0
        if free_days_str:
            try:
                free_days = int(free_days_str)
            except Exception:
                free_days = 0
        if rate_str:
            try:
                new_rate = Decimal(rate_str)
            except Exception:
                new_rate = None
        for rental in queryset:
            root = rental.root or rental
            now = new_start or timezone.now()
            # Закрываем старую версию
            if not rental.end_at or rental.end_at > now:
                rental.end_at = now
            rental.status = Rental.Status.MODIFIED
            rental.save()
            if free_days > 0:
                # Создаем версию с бесплатными днями
                free_start = now
                free_end = free_start + timezone.timedelta(days=free_days)
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = rental.version + 1
                free_version = Rental(
                    client=rental.client,
                    start_at=free_start,
                    end_at=free_end,
                    weekly_rate=Decimal(0),
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=rental,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                free_version.created_by = request.user
                free_version.updated_by = request.user
                free_version.save()
                # Создаем следующую версию после бесплатных дней
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = free_version.version + 1
                next_start = free_end
                new_rental = Rental(
                    client=rental.client,
                    start_at=next_start,
                    weekly_rate=new_rate if new_rate is not None else rental.weekly_rate,
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=free_version,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                new_rental.created_by = request.user
                new_rental.updated_by = request.user
                new_rental.save()
                # Переносим активные назначения батарей на новую версию, закрыв их в старой
                tz = timezone.get_current_timezone()
                for a in rental.assignments.all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_end is None or a_end > now:
                        # закрываем в старой версии
                        if a_end is None or a_end > now:
                            a.end_at = now
                            a.updated_by = request.user
                            a.save(update_fields=["end_at", "updated_by"])
                        # создаем продолжение в новой версии, начиная сейчас
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery=a.battery,
                            start_at=now,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                count += 2
            else:
                # Создаем новую версию без бесплатных дней
                try:
                    new_version_num = root.group_versions().count() + 1
                except Exception:
                    new_version_num = rental.version + 1
                new_rental = Rental(
                    client=rental.client,
                    start_at=now,
                    weekly_rate=new_rate if new_rate is not None else rental.weekly_rate,
                    deposit_amount=rental.deposit_amount,
                    status=Rental.Status.ACTIVE,
                    battery_type=rental.battery_type,
                    parent=rental,
                    root=root,
                    version=new_version_num,
                    contract_code=root.contract_code or rental.contract_code,
                )
                new_rental.created_by = request.user
                new_rental.updated_by = request.user
                new_rental.save()
                # Переносим активные назначения батарей на новую версию, закрыв их в старой
                tz = timezone.get_current_timezone()
                for a in rental.assignments.all():
                    a_start = timezone.localtime(a.start_at, tz)
                    a_end = timezone.localtime(a.end_at, tz) if a.end_at else None
                    if a_end is None or a_end > now:
                        # закрываем в старой версии
                        if a_end is None or a_end > now:
                            a.end_at = now
                            a.updated_by = request.user
                            a.save(update_fields=["end_at", "updated_by"])
                        # создаем продолжение в новой версии, начиная сейчас
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery=a.battery,
                            start_at=now,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                count += 1
        self.message_user(request, f"Создано новых версий: {count}; активные батареи перенесены")
    make_new_version.short_description = "Создать новую версию (начало с даты и времени, с переносом батарей)"

    # --- Helper: create next version and carry over batteries ---
    def _create_next_version(self, rental, user, cut_date, weekly_rate=None, end_at=None):
        """
        Close current rental version and create a new one.
        Returns the new Rental object.
        Uses select_for_update on root to prevent race conditions on version number.
        """
        root = rental.root or rental
        # Lock root row to serialize version creation
        Rental.objects.select_for_update().filter(pk=root.pk).first()

        # Close current version
        if not rental.end_at or rental.end_at > cut_date:
            rental.end_at = cut_date
        rental.status = Rental.Status.MODIFIED
        rental.updated_by = user
        rental.save(update_fields=["end_at", "status", "updated_by"])

        # New version
        new_version_num = root.group_versions().count() + 1
        new_rental = Rental(
            client=rental.client,
            city=rental.city,
            start_at=cut_date,
            end_at=end_at,
            weekly_rate=weekly_rate if weekly_rate is not None else rental.weekly_rate,
            deposit_amount=rental.deposit_amount,
            status=Rental.Status.ACTIVE,
            battery_type=rental.battery_type,
            parent=rental,
            root=root,
            version=new_version_num,
            contract_code=root.contract_code or rental.contract_code,
            created_by=user,
            updated_by=user,
        )
        new_rental.save()
        return new_rental

    def _carry_over_batteries(self, rental, new_rental, user, cut_date):
        """Close active assignments in old version and create continuations in new version."""
        for a in rental.assignments.select_related("battery").all():
            if a.end_at is None or a.end_at > cut_date:
                a.end_at = cut_date
                a.updated_by = user
                a.save(update_fields=["end_at", "updated_by"])
                RentalBatteryAssignment.objects.create(
                    rental=new_rental,
                    battery=a.battery,
                    start_at=cut_date,
                    end_at=None,
                    created_by=user,
                    updated_by=user,
                )

    # Пользовательский admin-view для изменения состава батарей
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/change-batteries/',
                self.admin_site.admin_view(self.change_batteries_view),
                name='rental_rental_change_batteries',
            ),
            path(
                '<int:pk>/available-batteries/',
                self.admin_site.admin_view(self.available_batteries_view),
                name='rental_rental_available_batteries',
            ),
            path(
                '<int:pk>/close/',
                self.admin_site.admin_view(self.close_rental_view),
                name='rental_rental_close',
            ),
            path(
                '<int:pk>/pause/',
                self.admin_site.admin_view(self.pause_rental_view),
                name='rental_rental_pause',
            ),
            path(
                '<int:pk>/new-tariff/',
                self.admin_site.admin_view(self.new_tariff_view),
                name='rental_rental_new_tariff',
            ),
            path(
                '<int:pk>/add-payment/',
                self.admin_site.admin_view(self.add_payment_view),
                name='rental_rental_add_payment',
            ),
            path(
                '<int:pk>/financial-data/',
                self.admin_site.admin_view(self.financial_data_view),
                name='rental_rental_financial_data',
            ),
        ]
        return custom + urls

    def available_batteries_view(self, request, pk):
        """GET: список батарей города договора со статусом AVAILABLE, не занятых в других активных договорах."""
        if request.method != 'GET':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        try:
            rental = Rental.objects.select_related('city').get(pk=pk)
            if not self.has_change_permission(request, rental):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            city_id = rental.city_id
            if not city_id:
                return JsonResponse({'batteries': []})
            now = timezone.now()
            # Батареи в активных назначениях других активных договоров — исключаем
            busy_battery_ids = set(
                RentalBatteryAssignment.objects.filter(
                    end_at__isnull=True,
                    rental__status=Rental.Status.ACTIVE,
                ).exclude(rental_id=pk).values_list('battery_id', flat=True)
            )
            busy_battery_ids |= set(
                RentalBatteryAssignment.objects.filter(
                    end_at__gt=now,
                    rental__status=Rental.Status.ACTIVE,
                ).exclude(rental_id=pk).values_list('battery_id', flat=True)
            )
            qs = Battery.objects.filter(
                city_id=city_id,
                status=Battery.Status.AVAILABLE,
            ).exclude(id__in=busy_battery_ids).order_by('short_code')
            batteries = [{'id': b.id, 'short_code': b.short_code} for b in qs.only('id', 'short_code')]
            return JsonResponse({'batteries': batteries})
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)

    def change_batteries_view(self, request, pk):
        """GET: JSON с назначениями батарей договора. POST: JSON с actions (end, add, replace)."""
        try:
            rental = Rental.objects.select_related('city').get(pk=pk)
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)
        if not self.has_change_permission(request, rental):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        if request.method == 'POST' and rental.status != Rental.Status.ACTIVE:
            return JsonResponse({'success': False, 'error': 'Изменение батарей доступно только для активных договоров'}, status=400)

        if request.method == 'GET':
            # #11: If this version is not active, find the latest active version in group
            target_rental = rental
            if rental.status != Rental.Status.ACTIVE:
                root = rental.root or rental
                latest_active = Rental.objects.filter(root=root, status=Rental.Status.ACTIVE).order_by('-version').first()
                if latest_active:
                    target_rental = latest_active

            assignments = target_rental.assignments.select_related('battery').order_by('start_at', 'id')
            tz = timezone.get_current_timezone()
            now = timezone.now()
            out = []
            for a in assignments:
                is_active = a.start_at <= now and (a.end_at is None or a.end_at > now)
                out.append({
                    'id': a.id,
                    'battery_id': a.battery_id,
                    'battery_short_code': a.battery.short_code,
                    'start_at': a.start_at.isoformat(),
                    'end_at': a.end_at.isoformat() if a.end_at else None,
                    'end_reason': (a.end_reason or '')[:255],
                    'is_active': is_active,
                })
            # Find earliest start_at across all versions in the group (for date validation on frontend)
            root_rental = target_rental.root or target_rental
            group_start_at = root_rental.start_at.isoformat()

            return JsonResponse({
                'rental': {
                    'id': target_rental.id,
                    'city_id': target_rental.city_id,
                    'contract_code': target_rental.contract_code,
                    'version': target_rental.version,
                    'is_active': target_rental.status == Rental.Status.ACTIVE,
                    'start_at': target_rental.start_at.isoformat(),
                    'group_start_at': group_start_at,
                },
                'assignments': out,
            })

        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            return JsonResponse({'success': False, 'error': 'Неверный JSON'}, status=400)
        actions = body.get('actions') or []

        def parse_date_to_start_of_day(s):
            """Parse YYYY-MM-DD or datetime string to 00:00:00 in current timezone (для стыковки дат при замене)."""
            if not s:
                return None
            s = (s or "").strip()
            tz = timezone.get_current_timezone()
            if len(s) <= 10 or "T" not in s:
                try:
                    d = date_type.fromisoformat(s[:10])
                except ValueError:
                    dt = timezone.datetime.fromisoformat(s.replace("Z", "+00:00"))
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt, tz)
                    return dt.replace(hour=0, minute=0, second=0, microsecond=0)
                return timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
            dt = timezone.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, tz)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            with transaction.atomic():
                end_actions = {}   # assignment_id -> (end_at_exclusive, reason)
                replace_actions = {}  # assignment_id -> (new_battery_id, replace_date_dt, reason)
                add_actions = []  # (battery_id, start_date_dt)
                all_user_dates = []  # original user dates (before +1 for end) for cut_date

                # Date boundaries for validation
                tz_val = timezone.get_current_timezone()
                now_local = timezone.localtime(timezone.now(), tz_val)
                today_start = timezone.make_aware(datetime.combine(now_local.date(), time(0, 0)), tz_val)
                tomorrow_start = today_start + timedelta(days=1)
                rental_start_date = timezone.localtime(rental.start_at, tz_val).date()  # current version start

                # Preload assignments for validation
                assignments_by_id = {
                    a.id: a for a in rental.assignments.select_related("battery").all()
                }

                for act in actions:
                    if act.get("type") == "end":
                        aid = act.get("assignment_id")
                        if not aid:
                            raise ValidationError("end: assignment_id обязателен")
                        end_at = parse_date_to_start_of_day(act.get("end_at"))
                        if not end_at:
                            end_at = today_start
                        # Validate date range
                        if end_at.date() < rental_start_date:
                            raise ValidationError(f"Дата завершения не может быть раньше начала договора ({rental_start_date.strftime('%d.%m.%Y')})")
                        if end_at > tomorrow_start:
                            raise ValidationError("Дата завершения не может быть позже завтрашнего дня")
                        # Validate end >= assignment start
                        assignment = assignments_by_id.get(aid)
                        if assignment:
                            a_start_date = timezone.localtime(assignment.start_at, tz_val).date()
                            if end_at.date() < a_start_date:
                                raise ValidationError(
                                    f"Дата завершения ({end_at.date().strftime('%d.%m.%Y')}) раньше даты подключения батареи "
                                    f"{assignment.battery.short_code} ({a_start_date.strftime('%d.%m.%Y')})"
                                )
                        # Inclusive end: user date is last billed day → store next day 00:00 (exclusive boundary)
                        end_at_exclusive = end_at + timedelta(days=1)
                        end_actions[aid] = (end_at_exclusive, (act.get("reason") or "")[:255])
                        all_user_dates.append(end_at)
                    elif act.get("type") == "replace":
                        aid = act.get("assignment_id")
                        new_battery_id = act.get("new_battery_id")
                        if not aid or not new_battery_id:
                            raise ValidationError("replace: assignment_id и new_battery_id обязательны")
                        replace_date = parse_date_to_start_of_day(act.get("date"))
                        if not replace_date:
                            replace_date = today_start
                        # Validate date range
                        if replace_date.date() < rental_start_date:
                            raise ValidationError(f"Дата замены не может быть раньше начала договора ({rental_start_date.strftime('%d.%m.%Y')})")
                        if replace_date > tomorrow_start:
                            raise ValidationError("Дата замены не может быть позже завтрашнего дня")
                        # Validate replace >= assignment start
                        assignment = assignments_by_id.get(aid)
                        if assignment:
                            a_start_date = timezone.localtime(assignment.start_at, tz_val).date()
                            if replace_date.date() < a_start_date:
                                raise ValidationError(
                                    f"Дата замены ({replace_date.date().strftime('%d.%m.%Y')}) раньше даты подключения батареи "
                                    f"{assignment.battery.short_code} ({a_start_date.strftime('%d.%m.%Y')})"
                                )
                        reason = (act.get("reason") or "Замена батареи")[:255]
                        new_battery = Battery.objects.filter(pk=new_battery_id).first()
                        if not new_battery:
                            raise ValidationError("Новая батарея не найдена")
                        if new_battery.city_id != rental.city_id:
                            raise ValidationError(f"Батарея {new_battery.short_code} из другого города")
                        if new_battery.status != Battery.Status.AVAILABLE:
                            raise ValidationError(f"Батарея {new_battery.short_code} недоступна (статус не AVAILABLE)")
                        overlap = RentalBatteryAssignment.objects.filter(
                            battery_id=new_battery_id,
                            rental__status=Rental.Status.ACTIVE,
                        ).filter(
                            Q(end_at__isnull=True) | Q(end_at__gt=replace_date),
                        ).filter(start_at__lte=replace_date).exclude(rental=rental).exists()
                        if overlap:
                            raise ValidationError(f"Батарея {new_battery.short_code} уже занята в другом договоре")
                        replace_actions[aid] = (new_battery_id, replace_date, reason)
                        all_user_dates.append(replace_date)
                    elif act.get("type") == "add":
                        battery_id = act.get("battery_id")
                        start_at = parse_date_to_start_of_day(act.get("start_at"))
                        if not battery_id:
                            raise ValidationError("add: battery_id обязателен")
                        if not start_at:
                            start_at = today_start
                        # Validate date range
                        if start_at.date() < rental_start_date:
                            raise ValidationError(f"Дата добавления не может быть раньше начала договора ({rental_start_date.strftime('%d.%m.%Y')})")
                        if start_at > tomorrow_start:
                            raise ValidationError("Дата добавления не может быть позже завтрашнего дня")
                        bat = Battery.objects.filter(pk=battery_id).first()
                        if not bat:
                            raise ValidationError("Батарея не найдена")
                        if bat.city_id != rental.city_id:
                            raise ValidationError(f"Батарея {bat.short_code} из другого города")
                        if bat.status != Battery.Status.AVAILABLE:
                            raise ValidationError(f"Батарея {bat.short_code} недоступна (статус не AVAILABLE)")
                        overlap = RentalBatteryAssignment.objects.filter(
                            battery_id=battery_id,
                            rental__status=Rental.Status.ACTIVE,
                        ).filter(
                            Q(end_at__isnull=True) | Q(end_at__gt=start_at),
                        ).filter(start_at__lte=start_at).exclude(rental=rental).exists()
                        if overlap:
                            raise ValidationError(f"Батарея {bat.short_code} уже занята в другом договоре")
                        add_actions.append((battery_id, start_at))
                        all_user_dates.append(start_at)

                if not all_user_dates:
                    raise ValidationError("Нет действий для применения")

                # #5: Validate no conflict: same assignment_id in both end and replace
                conflict_ids = set(end_actions.keys()) & set(replace_actions.keys())
                if conflict_ids:
                    raise ValidationError("Нельзя одновременно завершить и заменить одну и ту же батарею")

                cut_date_dt = min(all_user_dates)

                # Активные на cut_date назначения до закрытия (для переноса в новую версию)
                active_at_cut = list(
                    rental.assignments.select_related("battery").filter(
                        start_at__lte=cut_date_dt,
                    ).filter(Q(end_at__isnull=True) | Q(end_at__gt=cut_date_dt))
                )

                # Создаём новую версию через хелпер (с select_for_update на root)
                new_rental = self._create_next_version(rental, request.user, cut_date_dt)

                # В старой версии закрываем все назначения на cut_date_dt (00:00)
                for a in rental.assignments.filter(Q(end_at__isnull=True) | Q(end_at__gt=cut_date_dt)):
                    a.end_at = cut_date_dt
                    a.updated_by = request.user
                    if a.id in end_actions:
                        a.end_reason = end_actions[a.id][1]
                    elif a.id in replace_actions:
                        a.end_reason = replace_actions[a.id][2]
                    else:
                        a.end_reason = ""
                    a.save(update_fields=["end_at", "end_reason", "updated_by"])
                    if a.id in end_actions or a.id in replace_actions:
                        a.battery.status = Battery.Status.AVAILABLE
                        a.battery.save(update_fields=["status"])

                # Переносим в новую версию: продолжения (не end, не replace) с cut_date_dt; replace — новая батарея с replace_date (00:00)
                for a in active_at_cut:
                    if a.id in end_actions:
                        end_at_db, reason = end_actions[a.id]
                        if end_at_db > cut_date_dt:
                            # End date extends beyond version boundary (mixed case) — carry remainder to new version
                            RentalBatteryAssignment.objects.create(
                                rental=new_rental,
                                battery=a.battery,
                                start_at=cut_date_dt,
                                end_at=end_at_db,
                                end_reason=reason,
                                created_by=request.user,
                                updated_by=request.user,
                            )
                        continue
                    if a.id in replace_actions:
                        new_bid, rep_dt, _ = replace_actions[a.id]
                        RentalBatteryAssignment.objects.create(
                            rental=new_rental,
                            battery_id=new_bid,
                            start_at=rep_dt,
                            end_at=None,
                            created_by=request.user,
                            updated_by=request.user,
                        )
                        Battery.objects.filter(pk=new_bid).update(status=Battery.Status.RENTED)
                        continue
                    RentalBatteryAssignment.objects.create(
                        rental=new_rental,
                        battery=a.battery,
                        start_at=cut_date_dt,
                        end_at=None,
                        created_by=request.user,
                        updated_by=request.user,
                    )

                for battery_id, start_dt in add_actions:
                    RentalBatteryAssignment.objects.create(
                        rental=new_rental,
                        battery_id=battery_id,
                        start_at=start_dt,
                        end_at=None,
                        created_by=request.user,
                        updated_by=request.user,
                    )
                    Battery.objects.filter(pk=battery_id).update(status=Battery.Status.RENTED)

                now = timezone.now()
                active_count = new_rental.assignments.filter(
                    start_at__lte=now,
                ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now)).count()
                if active_count < 1:
                    raise ValidationError("Должна остаться минимум одна активная батарея на текущий момент")

                redirect_url = reverse("admin:rental_rental_change", args=[new_rental.pk])
                return JsonResponse({
                    "success": True,
                    "message": "Состав батарей обновлён, создана новая версия договора",
                    "redirect_url": redirect_url,
                })
        except ValidationError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

    def close_rental_view(self, request, pk):
        """AJAX endpoint для закрытия договора"""
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
        try:
            rental = Rental.objects.get(pk=pk)
            
            # Проверка прав доступа
            if not self.has_change_permission(request, rental):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
            # Получаем дату закрытия (inclusive: user date = last billed day → store next day 00:00)
            close_date_str = request.POST.get('close_date')
            tz = timezone.get_current_timezone()
            if close_date_str:
                d = date_type.fromisoformat(close_date_str[:10])
                close_date = timezone.make_aware(
                    datetime.combine(d + timedelta(days=1), time(0, 0)), tz
                )
            else:
                now_local = timezone.localtime(timezone.now(), tz)
                close_date = timezone.make_aware(
                    datetime.combine(now_local.date() + timedelta(days=1), time(0, 0)), tz
                )
            
            # Закрываем договор
            root = rental.root or rental
            for v in Rental.objects.filter(root=root, status=Rental.Status.ACTIVE):
                if not v.end_at or v.end_at > close_date:
                    v.end_at = close_date
                v.status = Rental.Status.CLOSED
                v.updated_by = request.user
                v.save()
                
                # Закрываем все активные назначения батарей и освобождаем батареи
                for assignment in v.assignments.select_related("battery").filter(end_at__isnull=True):
                    assignment.end_at = close_date
                    assignment.updated_by = request.user
                    assignment.save()
                    assignment.battery.status = Battery.Status.AVAILABLE
                    assignment.battery.save(update_fields=["status"])
                for assignment in v.assignments.select_related("battery").filter(end_at__gt=close_date):
                    assignment.end_at = close_date
                    assignment.updated_by = request.user
                    assignment.save()
                    assignment.battery.status = Battery.Status.AVAILABLE
                    assignment.battery.save(update_fields=["status"])
            
            return JsonResponse({'success': True, 'message': 'Договор закрыт'})
            
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def pause_rental_view(self, request, pk):
        """AJAX endpoint для создания паузы договора"""
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
        try:
            rental = Rental.objects.get(pk=pk)
            
            # Проверка прав доступа
            if not self.has_change_permission(request, rental):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
            # Получаем параметры
            pause_days = int(request.POST.get('pause_days', 0))
            if pause_days <= 0:
                return JsonResponse({'success': False, 'error': 'Укажите количество дней'}, status=400)
            
            pause_start_str = request.POST.get('pause_start_date')
            tz = timezone.get_current_timezone()
            if pause_start_str:
                d = date_type.fromisoformat(pause_start_str[:10])
                pause_start = timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
            else:
                now_local = timezone.localtime(timezone.now(), tz)
                pause_start = timezone.make_aware(
                    datetime.combine(now_local.date(), time(0, 0)), tz
                )
            
            pause_end = pause_start + timedelta(days=pause_days)
            with transaction.atomic():
                pause_version = self._create_next_version(rental, request.user, pause_start, weekly_rate=Decimal(0), end_at=pause_end)
                next_rental = self._create_next_version(pause_version, request.user, pause_end, weekly_rate=rental.weekly_rate)
                self._carry_over_batteries(rental, next_rental, request.user, pause_start)
            
            return JsonResponse({'success': True, 'message': f'Пауза на {pause_days} дней создана'})
            
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def new_tariff_view(self, request, pk):
        """AJAX endpoint для создания новой версии с новым тарифом"""
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
        try:
            rental = Rental.objects.get(pk=pk)
            
            # Проверка прав доступа
            if not self.has_change_permission(request, rental):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
            # Получаем параметры
            new_weekly_rate = Decimal(request.POST.get('new_weekly_rate', 0))
            if new_weekly_rate < 0:
                return JsonResponse({'success': False, 'error': 'Укажите корректную ставку'}, status=400)
            
            tariff_start_str = request.POST.get('tariff_start_date')
            tz = timezone.get_current_timezone()
            if tariff_start_str:
                d = date_type.fromisoformat(tariff_start_str[:10])
                tariff_start = timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
            else:
                now_local = timezone.localtime(timezone.now(), tz)
                tariff_start = timezone.make_aware(
                    datetime.combine(now_local.date(), time(0, 0)), tz
                )
            
            with transaction.atomic():
                new_rental = self._create_next_version(rental, request.user, tariff_start, weekly_rate=new_weekly_rate)
                self._carry_over_batteries(rental, new_rental, request.user, tariff_start)
            
            # Возвращаем URL новой версии
            redirect_url = reverse('admin:rental_rental_change', args=[new_rental.pk])
            return JsonResponse({
                'success': True,
                'message': f'Создана новая версия с тарифом {new_weekly_rate} PLN/неделя',
                'redirect_url': redirect_url
            })
            
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def add_payment_view(self, request, pk):
        """AJAX endpoint для добавления платежа к договору"""
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
        try:
            rental = Rental.objects.get(pk=pk)
            
            # Проверка прав доступа
            if not self.has_change_permission(request, rental):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
            # Получаем параметры
            amount = Decimal(request.POST.get('payment_amount', 0))
            payment_date_str = request.POST.get('payment_date')
            payment_type = request.POST.get('payment_type', 'rent')
            payment_method = request.POST.get('payment_method', 'cash')
            payment_note = request.POST.get('payment_note', '')
            
            if amount == 0:
                return JsonResponse({'success': False, 'error': 'Укажите сумму платежа'}, status=400)
            
            # Парсим дату
            payment_date = timezone.datetime.strptime(payment_date_str, '%Y-%m-%d').date()
            
            # Создаем платеж
            root = rental.root or rental
            payment = Payment.objects.create(
                rental=root,
                amount=amount,
                date=payment_date,
                type=payment_type,
                method=payment_method,
                note=payment_note,
                city=rental.city,
                created_by=request.user,
                updated_by=request.user,
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Платеж на сумму {amount} PLN добавлен',
                'payment_id': payment.id
            })
            
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def financial_data_view(self, request, pk):
        """AJAX endpoint для получения финансовых данных"""
        try:
            rental = Rental.objects.get(pk=pk)
            
            # Проверка прав доступа
            if not self.has_view_permission(request, rental):
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
            
            # Получаем root для group методов
            root = rental.root or rental
            now = timezone.now()
            
            # Вычисляем данные
            charges = float(root.group_charges_until(until=now))
            paid = float(root.group_paid_total())
            deposit = float(root.group_deposit_total())
            balance = paid - charges
            
            return JsonResponse({
                'success': True,
                'charges': f"{charges:.2f}",
                'paid': f"{paid:.2f}",
                'deposit': f"{deposit:.2f}",
                'balance': f"{balance:.2f}",
            })
            
        except Rental.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Договор не найден'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Добавляем дополнительный контекст для шаблона change_form"""
        extra_context = extra_context or {}
        
        try:
            rental = self.get_object(request, object_id)
            if rental:
                # Получаем root для группы версий
                root = rental.root or rental
                
                # Получаем все версии договора
                all_versions = list(
                    Rental.objects.filter(root=root)
                    .select_related('updated_by')
                    .prefetch_related('assignments__battery')
                    .order_by('version')
                )
                
                # Находим предыдущую и следующую версию
                current_idx = None
                for i, v in enumerate(all_versions):
                    if v.pk == rental.pk:
                        current_idx = i
                        break
                
                if current_idx is not None:
                    extra_context['prev_version'] = all_versions[current_idx - 1] if current_idx > 0 else None
                    extra_context['next_version'] = all_versions[current_idx + 1] if current_idx < len(all_versions) - 1 else None

                # Determine version change type for icons
                for i, v in enumerate(all_versions):
                    if v.weekly_rate == 0 and v.end_at:
                        v.change_type = 'pause'
                    elif i > 0:
                        prev = all_versions[i - 1]
                        prev_batteries = set(
                            a.battery_id for a in prev.assignments.all()
                        )
                        cur_batteries = set(
                            a.battery_id for a in v.assignments.all()
                        )
                        added = cur_batteries - prev_batteries
                        removed = prev_batteries - cur_batteries
                        if added and removed and len(added) == len(removed):
                            v.change_type = 'swap'
                            v.change_detail = str(len(added))
                        elif added and not removed:
                            v.change_type = 'add'
                            v.change_detail = str(len(added))
                        elif removed and not added:
                            v.change_type = 'remove'
                            v.change_detail = str(len(removed))
                        elif added and removed:
                            v.change_type = 'mixed'
                            v.change_detail = f"+{len(added)}/−{len(removed)}"
                        elif v.weekly_rate != prev.weekly_rate:
                            v.change_type = 'tariff'
                        else:
                            v.change_type = ''
                    else:
                        v.change_type = ''
                    # Battery codes for this version (all assignments in this version)
                    v.battery_codes = ', '.join(
                        a.battery.short_code for a in v.assignments.all()
                    ) or '—'
                    # Who made changes (updated_by, updated_at)
                    if getattr(v, 'updated_by', None):
                        v.updated_by_name = (v.updated_by.get_full_name() or v.updated_by.username or str(v.updated_by)) if v.updated_by else '—'
                    else:
                        v.updated_by_name = '—'
                    v.updated_at_dt = getattr(v, 'updated_at', None)

                extra_context['all_versions'] = all_versions
                # Change type for current version (to show icon next to status in main info)
                for v in all_versions:
                    if v.pk == rental.pk:
                        extra_context['original_change_type'] = getattr(v, 'change_type', '')
                        extra_context['original_change_detail'] = getattr(v, 'change_detail', '')
                        break
                else:
                    extra_context['original_change_type'] = ''
                    extra_context['original_change_detail'] = ''

                # Получаем все назначения батарей по всем версиям договора
                all_assignments = RentalBatteryAssignment.objects.filter(
                    rental__root=root
                ).select_related('battery', 'rental').order_by('start_at', 'id')
                extra_context['all_assignments'] = all_assignments
                
                # Получаем все платежи по всем версиям договора
                all_payments = Payment.objects.filter(
                    rental__root=root
                ).select_related('rental').order_by('-date')
                extra_context['all_payments'] = all_payments
                
                # Получаем номера батарей для текущей версии (активные сейчас)
                now = timezone.now()
                current_batteries = []
                for a in rental.assignments.select_related('battery').all():
                    a_start = a.start_at
                    a_end = a.end_at
                    # Батарея активна если начало <= сейчас и (нет окончания или окончание > сейчас)
                    if a_start <= now and (a_end is None or a_end > now):
                        current_batteries.append(a.battery.short_code)
                extra_context['current_battery_codes'] = ', '.join(current_batteries) if current_batteries else '—'
                
                # Вычисляем длительность текущей версии в днях
                start = rental.start_at
                end = rental.end_at or now
                duration_days = (end - start).days
                extra_context['version_duration_days'] = duration_days
        except Exception:
            pass
        
        return super().change_view(request, object_id, form_url, extra_context)

    def close_with_deposit(self, request, queryset):
        closed = 0
        # Опционально: принять оплату (аренда) сразу из формы действия
        amt = request.POST.get("payment_amount")
        mth = request.POST.get("payment_method")
        note = request.POST.get("payment_note")
        for rental in queryset:
            root = rental.root or rental
            now = timezone.now()
            for v in Rental.objects.filter(root=root, status=Rental.Status.ACTIVE):
                if not v.end_at or v.end_at > now:
                    v.end_at = now
                v.status = Rental.Status.CLOSED
                v.save()
            balance = root.group_balance(until=now)
            deposit_left = root.group_deposit_total()
            applied = Decimal(0)
            if balance > 0 and deposit_left > 0:
                applied = min(balance, deposit_left)
                Payment.objects.create(
                    rental=root,
                    amount=-applied,
                    date=timezone.localdate(),
                    type=Payment.PaymentType.ADJUSTMENT,
                    method=Payment.Method.OTHER,
                    note="Зачёт депозита при закрытии",
                    created_by=request.user,
                    updated_by=request.user,
                )
                balance -= applied
                deposit_left -= applied
            if deposit_left > 0:
                Payment.objects.create(
                    rental=root,
                    amount=deposit_left,
                    date=timezone.localdate(),
                    type=Payment.PaymentType.RETURN_DEPOSIT,
                    method=Payment.Method.OTHER,
                    note="Возврат остатка депозита",
                    created_by=request.user,
                    updated_by=request.user,
                )
            if amt:
                try:
                    amt_dec = Decimal(amt)
                    if amt_dec != 0:
                        Payment.objects.create(
                            rental=root,
                            amount=amt_dec,
                            date=timezone.localdate(),
                            type=Payment.PaymentType.RENT,
                            method=mth or Payment.Method.OTHER,
                            note=note or "",
                            created_by=request.user,
                            updated_by=request.user,
                        )
                except Exception:
                    pass
            closed += 1
        self.message_user(request, f"Закрыто договоров: {closed}")
    close_with_deposit.short_description = "Закрыть договор (с зачётом депозита)"


@admin.register(Payment)
class PaymentAdmin(ModeratorReadOnlyRelatedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    class RentalFilter(AutocompleteFilter):
        title = 'Договор'
        field_name = 'rental'

    list_display = ("id", "rental_link", "date", "amount_display", "type_display", "method_display", "city_display", "created_by_name")
    list_filter = (RentalFilter, "type", "method", "city")
    search_fields = ("rental__id", "note", "rental__client__name", "created_by__username")
    readonly_fields = ("updated_by",)
    autocomplete_fields = ["city"]
    date_hierarchy = 'date'
    list_per_page = 50
    change_form_template = 'admin/rental/payment/change_form.html'
    
    def changelist_view(self, request, extra_context=None):
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,E",
                    "location": "admin.py:PaymentAdmin.changelist_view:entry",
                    "message": "PaymentAdmin.changelist_view started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        response = super().changelist_view(request, extra_context)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "E",
                    "location": "admin.py:PaymentAdmin.changelist_view:exit",
                    "message": "PaymentAdmin.changelist_view completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return response
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка связанных rental и client для избежания N+1"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,F",
                    "location": "admin.py:PaymentAdmin.get_queryset:entry",
                    "message": "PaymentAdmin.get_queryset started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        qs = super().get_queryset(request)
        qs = qs.select_related('rental__client', 'rental__root', 'created_by', 'city')
        # #region agent log
        try:
            count = qs.count()
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "F",
                    "location": "admin.py:PaymentAdmin.get_queryset:exit",
                    "message": "PaymentAdmin.get_queryset completed",
                    "data": {"count": count, "elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return qs
    
    def add_view(self, request, form_url='', extra_context=None):
        """Логирование для страницы добавления"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:PaymentAdmin.add_view:entry",
                    "message": "PaymentAdmin.add_view started",
                    "data": {},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        response = super().add_view(request, form_url, extra_context)
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:PaymentAdmin.add_view:exit",
                    "message": "PaymentAdmin.add_view completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return response
    
    def get_form(self, request, obj=None, **kwargs):
        """Делаем поле city readonly для модераторов и фильтруем договоры"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "C,H",
                    "location": "admin.py:PaymentAdmin.get_form:entry",
                    "message": "get_form called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "obj_id": obj.id if obj else None,
                        "is_add": obj is None
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        form = super().get_form(request, obj, **kwargs)
        user_is_moderator = is_moderator(request.user)
        # #region agent log
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A,C",
                    "location": "admin.py:PaymentAdmin.get_form:after_is_moderator",
                    "message": "is_moderator check result",
                    "data": {
                        "user_is_moderator": user_is_moderator,
                        "has_rental_field": 'rental' in form.base_fields,
                        "has_city_field": 'city' in form.base_fields
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        if user_is_moderator:
            if 'city' in form.base_fields:
                form.base_fields['city'].disabled = True
                form.base_fields['city'].help_text = "Город автоматически устанавливается из города договора или модератора"
            # НЕ переопределяем queryset для rental здесь, так как это уже делается правильно
            # в formfield_for_foreignkey с учетом параметра show_all_rentals и фильтрации активных договоров
        # #region agent log
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H",
                    "location": "admin.py:PaymentAdmin.get_form:exit",
                    "message": "get_form completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return form
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Фильтрация договоров по городу для модераторов"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "D",
                    "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:entry",
                    "message": "formfield_for_foreignkey called",
                    "data": {
                        "db_field_name": db_field.name,
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        if db_field.name == "rental":
            user_is_moderator = is_moderator(request.user)
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A,D",
                        "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:rental_check",
                        "message": "rental field check",
                        "data": {
                            "user_is_moderator": user_is_moderator,
                            "has_queryset_in_kwargs": "queryset" in kwargs
                        },
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            if user_is_moderator:
                city = get_user_city(request.user)
                # #region agent log
                try:
                    with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "B,D",
                            "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:before_filter",
                            "message": "Before filtering queryset",
                            "data": {
                                "city_id": city.id if city else None,
                                "city_name": city.name if city else None
                            },
                            "timestamp": __import__('time').time() * 1000
                        }, ensure_ascii=False) + '\n')
                except: pass
                # #endregion
                if city:
                    filtered_qs = Rental.objects.filter(city=city).select_related('client', 'root').only('id', 'contract_code', 'client_id', 'root_id', 'client__name')
                    kwargs["queryset"] = filtered_qs
                    # #region agent log
                    try:
                        with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                            f.write(json.dumps({
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "D,E,H",
                                "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:after_filter",
                                "message": "After filtering queryset",
                                "data": {
                                    "queryset_set": True
                                },
                                "timestamp": __import__('time').time() * 1000
                            }, ensure_ascii=False) + '\n')
                    except: pass
                    # #endregion
        result = super().formfield_for_foreignkey(db_field, request, **kwargs)
        # #region agent log
        try:
            final_qs = result.queryset if hasattr(result, 'queryset') else None
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "D,E",
                    "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:exit",
                    "message": "formfield_for_foreignkey result",
                    "data": {
                        "has_queryset": final_qs is not None,
                        "field_type": type(result).__name__
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return result
    
    def get_field_queryset(self, db, db_field, request):
        """Фильтрация queryset для ForeignKey полей для модераторов"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "G",
                    "location": "admin.py:PaymentAdmin.get_field_queryset:entry",
                    "message": "get_field_queryset called",
                    "data": {
                        "db_field_name": db_field.name if db_field else None,
                        "db_field_model": db_field.related_model.__name__ if db_field and hasattr(db_field, 'related_model') else None,
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        
        queryset = super().get_field_queryset(db, db_field, request)
        
        # Фильтруем поле rental для модераторов
        if db_field and db_field.name == "rental" and is_moderator(request.user):
            city = get_user_city(request.user)
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "B,G",
                        "location": "admin.py:PaymentAdmin.get_field_queryset:before_filter",
                        "message": "Before filtering rental queryset",
                        "data": {
                            "city_id": city.id if city else None,
                            "city_name": city.name if city else None,
                            "has_queryset": queryset is not None
                        },
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            if city:
                filtered_qs = queryset.filter(city=city).select_related('client', 'root')
                # #region agent log
                try:
                    with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "G",
                            "location": "admin.py:PaymentAdmin.get_field_queryset:after_filter",
                            "message": "After filtering rental queryset",
                            "data": {
                                "queryset_set": True
                            },
                            "timestamp": __import__('time').time() * 1000
                        }, ensure_ascii=False) + '\n')
                except: pass
                # #endregion
                return filtered_qs
        
        return queryset
    
    def get_field_queryset(self, db, db_field, request):
        """Фильтрация queryset для ForeignKey полей для модераторов (Django 5.0+)"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "G",
                    "location": "admin.py:PaymentAdmin.get_field_queryset:entry",
                    "message": "get_field_queryset called",
                    "data": {
                        "db_field_name": db_field.name if db_field else None,
                        "db_field_model": db_field.related_model.__name__ if db_field and hasattr(db_field, 'related_model') else None,
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        
        queryset = super().get_field_queryset(db, db_field, request)
        
        # Фильтруем поле rental для модераторов
        if db_field and db_field.name == "rental" and is_moderator(request.user):
            city = get_user_city(request.user)
            # #region agent log
            try:
                with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "B,G",
                        "location": "admin.py:PaymentAdmin.get_field_queryset:before_filter",
                        "message": "Before filtering rental queryset",
                        "data": {
                            "city_id": city.id if city else None,
                            "city_name": city.name if city else None,
                            "has_queryset": queryset is not None
                        },
                        "timestamp": __import__('time').time() * 1000
                    }, ensure_ascii=False) + '\n')
            except: pass
            # #endregion
            if city:
                filtered_qs = queryset.filter(city=city).select_related('client', 'root')
                # #region agent log
                try:
                    with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "G",
                            "location": "admin.py:PaymentAdmin.get_field_queryset:after_filter",
                            "message": "After filtering rental queryset",
                            "data": {
                                "queryset_set": True
                            },
                            "timestamp": __import__('time').time() * 1000
                        }, ensure_ascii=False) + '\n')
                except: pass
                # #endregion
                return filtered_qs
        
        return queryset
    
    def get_search_results(self, request, queryset, search_term):
        """Фильтрация результатов autocomplete для модераторов"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        
        # Если это autocomplete запрос для поля rental и пользователь модератор
        if is_moderator(request.user):
            city = get_user_city(request.user)
            if city:
                # Фильтруем queryset по городу, если это Rental queryset
                if hasattr(queryset.model, 'city'):
                    queryset = queryset.filter(city=city)
        
        return queryset, use_distinct
    
    def add_view(self, request, form_url='', extra_context=None):
        """Переопределяем add_view для фильтрации поля rental"""
        # #region agent log
        import json
        import time as time_module
        start_time = time_module.time()
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "C",
                    "location": "admin.py:PaymentAdmin.add_view:entry",
                    "message": "add_view called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None
                    },
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        
        # Вызываем родительский метод для получения формы
        response = super().add_view(request, form_url, extra_context)
        
        # Если это TemplateResponse, можем получить форму из контекста
        # НЕ переопределяем queryset здесь, так как это уже сделано в formfield_for_foreignkey
        # с учетом параметра show_all_rentals и фильтрации активных договоров
        # #region agent log
        import time as time_module
        try:
            elapsed = (time_module.time() - start_time) * 1000
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "C",
                    "location": "admin.py:PaymentAdmin.add_view:exit",
                    "message": "PaymentAdmin.add_view completed",
                    "data": {"elapsed_ms": elapsed},
                    "timestamp": time_module.time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        return response
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Переопределяем change_view для фильтрации поля rental"""
        # #region agent log
        import json
        try:
            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "C",
                    "location": "admin.py:PaymentAdmin.change_view:entry",
                    "message": "change_view called",
                    "data": {
                        "user_id": request.user.id if request.user else None,
                        "username": request.user.username if request.user else None,
                        "object_id": object_id
                    },
                    "timestamp": __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
        except: pass
        # #endregion
        
        # Вызываем родительский метод для получения формы
        response = super().change_view(request, object_id, form_url, extra_context)
        
        # Если это TemplateResponse, можем получить форму из контекста
        if hasattr(response, 'context_data'):
            form = response.context_data.get('adminform') or response.context_data.get('form')
            if form and hasattr(form, 'fields') and 'rental' in form.fields:
                if is_moderator(request.user):
                    city = get_user_city(request.user)
                    if city:
                        form.fields['rental'].queryset = Rental.objects.filter(city=city).select_related('client', 'root')
        
        return response
    
    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем city для модераторов с обработкой ошибок"""
        from .logging_utils import log_action, log_error, log_warning
        from django.core.exceptions import ValidationError
        
        try:
            # Автоматически устанавливаем city из rental или модератора
            if not change and not obj.city:
                if obj.rental_id and obj.rental.city:
                    obj.city = obj.rental.city
                elif not request.user.is_superuser:
                    obj.city = get_user_city(request.user)
            
            # Сохраняем объект
            super().save_model(request, obj, form, change)
            
            # Логируем успешное действие
            action = "Обновлён платёж" if change else "Создан новый платёж"
            log_action(
                action,
                user=request.user,
                details={
                    'payment_id': obj.id,
                    'rental_id': obj.rental_id if obj.rental else None,
                    'amount': float(obj.amount),
                    'type': obj.get_type_display(),
                    'date': str(obj.date),
                },
                request=request
            )
            
            # Предупреждение о крупных суммах
            if obj.amount > 5000 and obj.type == Payment.PaymentType.RENT:
                log_warning(
                    "Создан платёж с крупной суммой",
                    user=request.user,
                    context={
                        'payment_id': obj.id,
                        'amount': float(obj.amount),
                        'rental_id': obj.rental_id if obj.rental else None,
                    },
                    request=request
                )
            
            # Показываем успешное сообщение пользователю
            messages.success(request, f"{action} успешно (ID: {obj.id}, сумма: {obj.amount} PLN)")
            
        except ValidationError as e:
            # Ошибки валидации
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
            log_error(
                "Ошибка валидации платежа",
                exception=e,
                user=request.user,
                context={
                    'payment_id': obj.id if obj.id else 'новый',
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request,
                include_traceback=False
            )
            raise
            
        except Exception as e:
            # Любые другие ошибки
            messages.error(
                request,
                f"Ошибка при сохранении платежа: {str(e)}"
            )
            
            log_error(
                "Критическая ошибка при сохранении платежа",
                exception=e,
                user=request.user,
                context={
                    'payment_id': obj.id if obj.id else 'новый',
                    'rental_id': obj.rental_id if obj.rental else None,
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request
            )
            raise
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('rental', 'amount', 'date', 'type')
        }),
        ('Детали платежа', {
            'fields': ('method', 'note', 'created_by')
        }),
        ('Служебная информация', {
            'fields': ('updated_by',),
            'classes': ('collapse',)
        }),
    )

    def changelist_view(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        from .models import Rental
        from django.db.models import Avg, Count
        
        # Получаем filtered queryset для статистики
        response = super().changelist_view(request, extra_context=extra_context)
        
        try:
            qs = response.context_data['cl'].queryset
            
            # Агрегированная статистика
            stats = qs.aggregate(
                total_amount=Sum('amount'),
                avg_amount=Avg('amount'),
                count=Count('id')
            )
            extra_context['stats'] = {
                'total_amount': stats['total_amount'] or Decimal('0'),
                'avg_amount': stats['avg_amount'] or Decimal('0'),
                'count': stats['count'] or 0
            }
            
            # Статистика по типам
            type_stats = qs.values('type').annotate(
                total=Sum('amount'),
                count=Count('id')
            ).order_by('-total')
            extra_context['type_stats'] = type_stats
            
        except (AttributeError, KeyError):
            pass
        
        # Информация о выбранном договоре
        rid = request.GET.get('rental__id__exact')
        if rid:
            try:
                rental = Rental.objects.select_related('client').only('id','contract_code','client__name','status').get(pk=rid)
                extra_context['selected_rental'] = rental
                
                # Расчет баланса для выбранного договора
                from .views import calculate_balances_for_rentals
                from django.utils import timezone
                tz = timezone.get_current_timezone()
                now_dt = timezone.now()
                
                charges_dict, paid_dict, _ = calculate_balances_for_rentals([rental], tz, now_dt)
                root_id = rental.root_id or rental.id
                
                charges = charges_dict.get(root_id, Decimal('0'))
                paid = paid_dict.get(root_id, Decimal('0'))
                balance = charges - paid
                
                extra_context['rental_balance'] = {
                    'charges': charges,
                    'paid': paid,
                    'balance': balance,
                    'color': 'success' if balance <= 0 else ('warning' if balance <= 100 else 'danger')
                }
            except Rental.DoesNotExist:
                extra_context['selected_rental'] = None
        
        return response

    def get_search_results(self, request, queryset, search_term):
        # Ограничение базового поиска по платежам — оставляем стандартное поведение
        return super().get_search_results(request, queryset, search_term)


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('rental__client', 'created_by')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        from django.contrib.auth import get_user_model
        from .models import FinancePartner
        
        User = get_user_model()
        field = form.base_fields.get('created_by')
        if field:
            field.queryset = User.objects.filter(is_staff=True).order_by('username')
            field.label = "Кто принял деньги"
            
            # Проверяем права доступа: суперпользователь, владелец, или пользователь 'admin'
            is_owner = FinancePartner.objects.filter(
                user=request.user, 
                role=FinancePartner.Role.OWNER,
                active=True
            ).exists()
            
            can_choose = (
                request.user.is_superuser or 
                is_owner or 
                request.user.username == 'admin'
            )
            
            # Для суперпользователей, владельцев и admin - можно выбирать
            if can_choose:
                field.required = False
                field.disabled = False
                field.initial = request.user.pk
                field.help_text = "Выберите сотрудника, который принял деньги (по умолчанию - вы)"
            else:
                # Для остальных (модераторов и т.д.) - автоматически
                field.initial = request.user.pk
                field.disabled = True
                field.required = False
                field.help_text = "Автоматически заполняется текущим пользователем"
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "rental":
            from .models import Rental
            
            # Если пользователь модератор, фильтруем по городу
            if is_moderator(request.user):
                city = get_user_city(request.user)
                # #region agent log
                import json
                try:
                    with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A,B,C",
                            "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:moderator_entry",
                            "message": "formfield_for_foreignkey called for moderator",
                            "data": {
                                "city_id": city.id if city else None,
                                "city_name": city.name if city else None,
                                "user_id": request.user.id if request.user else None,
                                "username": request.user.username if request.user else None,
                                "show_all_param": request.GET.get('show_all_rentals'),
                                "show_all_post": request.POST.get('show_all_rentals')
                            },
                            "timestamp": __import__('time').time() * 1000
                        }, ensure_ascii=False) + '\n')
                except: pass
                # #endregion
                if city:
                    # Проверяем параметр show_all_rentals для модераторов
                    show_all = request.GET.get('show_all_rentals') == '1' or request.POST.get('show_all_rentals') == '1'
                    # #region agent log
                    try:
                        with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                            f.write(json.dumps({
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "B",
                                "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:before_queryset",
                                "message": "Before creating queryset for moderator",
                                "data": {
                                    "show_all": show_all,
                                    "city_id": city.id,
                                    "city_name": city.name
                                },
                                "timestamp": __import__('time').time() * 1000
                            }, ensure_ascii=False) + '\n')
                    except: pass
                    # #endregion
                    if show_all:
                        # Показываем все договора города модератора
                        all_rentals_qs = Rental.objects.filter(city=city).select_related('client', 'root').order_by('-id')
                        kwargs["queryset"] = all_rentals_qs
                        # #region agent log
                        try:
                            count = all_rentals_qs.count()
                            statuses = list(all_rentals_qs.values_list('status', flat=True).distinct())
                            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                                f.write(json.dumps({
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "B",
                                    "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:all_rentals",
                                    "message": "All rentals queryset for moderator",
                                    "data": {
                                        "queryset_count": count,
                                        "statuses": statuses
                                    },
                                    "timestamp": __import__('time').time() * 1000
                                }, ensure_ascii=False) + '\n')
                        except: pass
                        # #endregion
                    else:
                        # По умолчанию показываем только активные договора последней версии города модератора
                        from django.db.models import Count, Q
                        active_rentals_qs = Rental.objects.filter(city=city).select_related('client', 'root').annotate(
                            children_count=Count('children')
                        ).filter(
                            Q(status=Rental.Status.ACTIVE) & Q(children_count=0)
                        ).order_by('-id')
                        kwargs["queryset"] = active_rentals_qs
                        # #region agent log
                        try:
                            count = active_rentals_qs.count()
                            with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                                f.write(json.dumps({
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "A",
                                    "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:active_rentals",
                                    "message": "Active rentals queryset for moderator",
                                    "data": {
                                        "queryset_count": count,
                                        "city_id": city.id,
                                        "city_name": city.name,
                                        "filter_applied": "status=ACTIVE AND children_count=0"
                                    },
                                    "timestamp": __import__('time').time() * 1000
                                }, ensure_ascii=False) + '\n')
                        except: pass
                        # #endregion
                else:
                    # Если у модератора нет города, показываем пустой queryset
                    kwargs["queryset"] = Rental.objects.none()
                    # #region agent log
                    try:
                        with open(str(get_debug_log_path()), 'a', encoding='utf-8') as f:
                            f.write(json.dumps({
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "C",
                                "location": "admin.py:PaymentAdmin.formfield_for_foreignkey:no_city",
                                "message": "Moderator has no city, returning empty queryset",
                                "data": {
                                    "user_id": request.user.id,
                                    "username": request.user.username
                                },
                                "timestamp": __import__('time').time() * 1000
                            }, ensure_ascii=False) + '\n')
                    except: pass
                    # #endregion
            else:
                # Для не-модераторов используем существующую логику
                # Проверяем параметр show_all_rentals в GET или POST
                show_all = request.GET.get('show_all_rentals') == '1' or request.POST.get('show_all_rentals') == '1'
                
                if show_all:
                    # Показываем все договора, отсортированные от большего к меньшему
                    kwargs["queryset"] = Rental.objects.select_related('client').order_by('-id')
                else:
                    # По умолчанию показываем только активные договора последней версии
                    # Последняя версия = договор не имеет детей (children)
                    from django.db.models import Count, Q
                    queryset = Rental.objects.select_related('client').annotate(
                        children_count=Count('children')
                    ).filter(
                        Q(status=Rental.Status.ACTIVE) & Q(children_count=0)
                    ).order_by('-id')
                    kwargs["queryset"] = queryset
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        # Добавляем информацию о состоянии галочки "показать все договора"
        show_all = request.GET.get('show_all_rentals') == '1'
        context['show_all_rentals'] = show_all
        return super().render_change_form(request, context, add, change, form_url, obj)

    @admin.display(ordering='rental', description='Договор')
    def rental_link(self, obj):
        if not obj.rental:
            return '-'
        url = reverse('admin:rental_rental_change', args=[obj.rental.id])
        client_name = obj.rental.client.name if obj.rental.client else 'N/A'
        contract = obj.rental.contract_code or f'#{obj.rental.id}'
        return format_html(
            '<a href="{}">{}<br><small class="text-muted">{}</small></a>',
            url,
            client_name,
            contract
        )
    
    @admin.display(ordering='amount', description='Сумма')
    def amount_display(self, obj):
        return format_html(
            '<span style="font-size: 1.05em;">{}</span> <small class="text-muted">PLN</small>',
            obj.amount
        )
    
    @admin.display(ordering='type', description='Тип')
    def type_display(self, obj):
        colors = {
            'rent': 'success',
            'deposit': 'primary',
            'return_deposit': 'warning',
            'sold': 'info',
            'adjustment': 'secondary'
        }
        color = colors.get(obj.type, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            obj.get_type_display()
        )
    
    @admin.display(ordering='method', description='Метод')
    def method_display(self, obj):
        icons = {
            'cash': '💵',
            'blik': '📱',
            'revolut': '💳',
            'other': '❓'
        }
        icon = icons.get(obj.method, '❓')
        return format_html(
            '<span class="method-icon">{}</span> {}',
            icon,
            obj.get_method_display()
        )

    @admin.display(ordering='created_by__username', description='Кто ввёл запись')
    def created_by_name(self, obj):
        user = obj.created_by
        if not user:
            return ''
        return user.username
    
    @admin.display(ordering='city__name', description='Город')
    def city_display(self, obj):
        """Отображение города с возможностью сортировки по имени"""
        if obj.city:
            return str(obj.city)
        return "-"

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            # Для несуперпользователя всегда фиксируем автора как текущего
            obj.created_by = request.user
        elif not getattr(obj, 'created_by_id', None):
            # Для суперпользователя, если поле не выбрано, используем текущего
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('get-rental-info/', self.admin_site.admin_view(self.get_rental_info_view), name='payment_get_rental_info'),
        ]
        return custom_urls + urls
    
    def get_rental_info_view(self, request):
        """AJAX endpoint для получения информации о договоре"""
        import traceback
        import sys
        
        rental_id = request.GET.get('rental_id')
        
        if not rental_id:
            return JsonResponse({
                'success': False, 
                'error': 'Rental ID не указан',
                'error_type': 'ValidationError'
            })
        
        try:
            from .models import Rental
            from .views import calculate_balances_for_rentals
            
            rental = Rental.objects.select_related('client').get(pk=rental_id)
            
            # Расчет баланса
            tz = timezone.get_current_timezone()
            now_dt = timezone.now()
            charges_dict, paid_dict, _ = calculate_balances_for_rentals([rental], tz, now_dt)
            root_id = rental.root_id or rental.id
            
            charges = charges_dict.get(root_id, Decimal('0'))
            paid = paid_dict.get(root_id, Decimal('0'))
            balance = charges - paid
            
            # Последние 5 платежей
            recent_payments = rental.payments.order_by('-date', '-id')[:5]
            recent_payments_data = [
                {
                    'date': p.date.strftime('%d.%m.%Y'),
                    'amount': str(p.amount),
                    'type_display': p.get_type_display(),
                    'method_display': p.get_method_display(),
                }
                for p in recent_payments
            ]
            
            # Получаем номера батарей через assignments (активные на данный момент)
            battery_numbers = []
            if rental.status == Rental.Status.ACTIVE:
                # Получаем активные батареи (где end_at is NULL или в будущем)
                active_assignments = rental.assignments.filter(
                    Q(end_at__isnull=True) | Q(end_at__gt=now_dt)
                ).select_related('battery')
                battery_numbers = [a.battery.short_code for a in active_assignments]
                battery_numbers.sort()
            
            # Получаем дату старта от первой версии (root)
            if rental.root_id:
                try:
                    root_rental = Rental.objects.get(pk=rental.root_id)
                    start_at = root_rental.start_at
                except Rental.DoesNotExist:
                    start_at = rental.start_at
            else:
                start_at = rental.start_at
            
            return JsonResponse({
                'success': True,
                'client_name': rental.client.name if rental.client else '-',
                'contract_code': rental.contract_code or f'#{rental.id}',
                'status': rental.status,
                'status_display': rental.get_status_display(),
                'balance': str(balance),
                'charges': str(charges),
                'paid': str(paid),
                'recent_payments': recent_payments_data,
                'battery_numbers': battery_numbers,
                'start_date': timezone.localtime(start_at).strftime('%d.%m.%Y %H:%M') if start_at else '-',
            })
            
        except Rental.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': f'Договор с ID {rental_id} не найден',
                'error_type': 'DoesNotExist'
            })
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            tb_text = ''.join(tb_lines)
            
            # Логируем ошибку на сервере
            print(f"ERROR in get_rental_info_view: {e}")
            print(tb_text)
            
            return JsonResponse({
                'success': False, 
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': tb_text if request.user.is_superuser else None  # Только для суперпользователей
            })


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "name")
    
    def has_module_permission(self, request):
        # Только суперпользователи видят категории расходов
        return request.user.is_superuser


@admin.register(Expense)
class ExpenseAdmin(ModeratorRestrictedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    city_filter_field = 'paid_by_partner__city'  # Фильтруем через связанное поле
    
    list_display = ("id", "date", "amount", "category", "payment_type", "paid_by_partner")
    list_filter = ("category", "payment_type")
    search_fields = ("note", "description")
    autocomplete_fields = ("paid_by_partner",)
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка связанных данных"""
        qs = super().get_queryset(request)
        qs = qs.select_related('category', 'paid_by_partner__user', 'paid_by_partner__city')
        return qs
    
    def get_form(self, request, obj=None, **kwargs):
        """Фильтруем партнёров по городу для модераторов"""
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and 'paid_by_partner' in form.base_fields:
            city = get_user_city(request.user)
            if city:
                form.base_fields['paid_by_partner'].queryset = FinancePartner.objects.filter(city=city)
        return form
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Фильтрация партнёров по городу для модераторов"""
        if db_field.name == "paid_by_partner" and not request.user.is_superuser:
            city = get_user_city(request.user)
            if city:
                kwargs["queryset"] = FinancePartner.objects.filter(city=city)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def save_model(self, request, obj, form, change):
        """Сохранение расхода с обработкой ошибок"""
        from .logging_utils import log_action, log_error, log_warning
        from django.core.exceptions import ValidationError
        
        try:
            super().save_model(request, obj, form, change)
            
            # Логируем успешное действие
            action = "Обновлён расход" if change else "Создан новый расход"
            log_action(
                action,
                user=request.user,
                details={
                    'expense_id': obj.id,
                    'amount': float(obj.amount),
                    'category': str(obj.category) if obj.category else None,
                    'payment_type': obj.get_payment_type_display(),
                    'paid_by': str(obj.paid_by_partner) if obj.paid_by_partner else None,
                },
                request=request
            )
            
            # Предупреждение о крупных расходах
            if obj.amount > 5000:
                log_warning(
                    "Создан расход с крупной суммой",
                    user=request.user,
                    context={
                        'expense_id': obj.id,
                        'amount': float(obj.amount),
                        'category': str(obj.category) if obj.category else None,
                    },
                    request=request
                )
            
            # Показываем успешное сообщение
            messages.success(
                request,
                f"{action} успешно (ID: {obj.id}, сумма: {obj.amount} PLN)"
            )
            
        except ValidationError as e:
            for field, errors in e.error_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
            log_error(
                "Ошибка валидации расхода",
                exception=e,
                user=request.user,
                context={
                    'expense_id': obj.id if obj.id else 'новый',
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request,
                include_traceback=False
            )
            raise
            
        except Exception as e:
            messages.error(
                request,
                f"Ошибка при сохранении расхода: {str(e)}"
            )
            
            log_error(
                "Критическая ошибка при сохранении расхода",
                exception=e,
                user=request.user,
                context={
                    'expense_id': obj.id if obj.id else 'новый',
                    'amount': float(obj.amount) if obj.amount else None,
                },
                request=request
            )
            raise
    
    def has_module_permission(self, request):
        # Только суперпользователи видят расходы
        return request.user.is_superuser


@admin.register(Repair)
class RepairAdmin(ModeratorRestrictedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    city_filter_field = 'battery__city'  # Фильтруем через связанное поле
    
    list_display = ("id", "battery", "start_at", "end_at", "cost")
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка battery и city"""
        qs = super().get_queryset(request)
        qs = qs.select_related('battery__city')
        return qs
    
    def has_module_permission(self, request):
        # Разрешаем доступ модераторам и суперпользователям
        if request.user.is_superuser:
            return True
        return get_user_city(request.user) is not None


@admin.register(BatteryStatusLog)
class BatteryStatusLogAdmin(ModeratorRestrictedMixin, SimpleHistoryAdmin):
    list_display = ("id", "battery", "kind", "start_at", "end_at")
    
    def get_queryset(self, request):
        """Оптимизация: предзагрузка battery"""
        qs = super().get_queryset(request)
        qs = qs.select_related('battery')
        return qs
    
    def has_module_permission(self, request):
        # Только суперпользователи видят логи статусов батарей
        return request.user.is_superuser


@admin.register(BatteryTransfer)
class BatteryTransferAdmin(ModeratorRestrictedMixin, CityFilteredAdminMixin, SimpleHistoryAdmin):
    city_filter_field = 'from_city'  # Модераторы видят только запросы из своего города
    
    list_display = ("id", "battery", "from_city", "to_city", "status_display", "requested_by", "approved_by", "created_at")
    list_filter = ("status", "from_city", "to_city", "created_at")
    search_fields = ("battery__short_code", "note")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ["battery", "from_city", "to_city"]
    actions = ["approve_transfers", "reject_transfers"]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('battery', 'from_city', 'to_city', 'requested_by', 'approved_by')
        return qs
    
    def status_display(self, obj):
        """Цветовая индикация статусов"""
        colors = {
            BatteryTransfer.Status.PENDING: ('#ffd28a', 'rgba(255, 210, 138, 0.15)'),
            BatteryTransfer.Status.APPROVED: ('#00d27a', 'rgba(0, 210, 122, 0.15)'),
            BatteryTransfer.Status.REJECTED: ('#ff6b6b', 'rgba(255, 107, 107, 0.15)'),
        }
        color, bg_color = colors.get(obj.status, ('#9fa6bc', 'rgba(159, 166, 188, 0.15)'))
        return format_html(
            '<span class="badge" style="background-color: {}; color: {};">{}</span>',
            bg_color, color, obj.get_status_display()
        )
    status_display.short_description = "Статус"
    
    @admin.action(description="Подтвердить выбранные переносы")
    def approve_transfers(self, request, queryset):
        from .logging_utils import log_error, log_action
        import logging
        import traceback
        import os
        
        logger = logging.getLogger('rental')
        
        try:
            pending = queryset.filter(status=BatteryTransfer.Status.PENDING)
            count = 0
            errors = []
            
            logger.info(f"Начало подтверждения переносов. Выбрано: {pending.count()}")
            
            for transfer in pending:
                try:
                    logger.debug(f"Попытка подтверждения переноса ID={transfer.id}, батарея={transfer.battery.short_code if transfer.battery else 'None'}, from_city={transfer.from_city.name if transfer.from_city else 'None'}, to_city={transfer.to_city.name if transfer.to_city else 'None'}")
                    
                    # Проверяем, что все необходимые объекты существуют
                    if not transfer.battery:
                        raise ValueError(f"У переноса {transfer.id} отсутствует батарея")
                    if not transfer.from_city:
                        raise ValueError(f"У переноса {transfer.id} отсутствует город отправления")
                    if not transfer.to_city:
                        raise ValueError(f"У переноса {transfer.id} отсутствует город назначения")
                    
                    transfer.approve(request.user)
                    count += 1
                    
                    logger.info(f"Перенос {transfer.id} успешно подтверждён")
                    
                    log_action(
                        "Подтверждён перенос батареи",
                        user=request.user,
                        details={
                            'transfer_id': transfer.id,
                            'battery': transfer.battery.short_code,
                            'from_city': str(transfer.from_city),
                            'to_city': str(transfer.to_city),
                        },
                        request=request
                    )
                except ValidationError as e:
                    error_msg = str(e)
                    logger.error(f"ValidationError при подтверждении переноса {transfer.id}: {error_msg}\n{traceback.format_exc()}")
                    errors.append(f"{transfer}: {error_msg}")
                    log_error(
                        "Ошибка при подтверждении переноса батареи",
                        exception=e,
                        user=request.user,
                        context={
                            'transfer_id': transfer.id,
                            'battery': transfer.battery.short_code if transfer.battery else None,
                            'from_city': str(transfer.from_city) if transfer.from_city else None,
                            'to_city': str(transfer.to_city) if transfer.to_city else None,
                        },
                        request=request
                    )
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Неожиданная ошибка при подтверждении переноса {transfer.id}: {error_msg}\n{traceback.format_exc()}")
                    errors.append(f"{transfer}: {error_msg}")
                    log_error(
                        "Неожиданная ошибка при подтверждении переноса батареи",
                        exception=e,
                        user=request.user,
                        context={
                            'transfer_id': transfer.id,
                            'battery': transfer.battery.short_code if transfer.battery else None,
                        },
                        request=request
                    )
            
            if count:
                self.message_user(request, f"Подтверждено переносов: {count}", level=messages.SUCCESS)
            if errors:
                for error in errors:
                    self.message_user(request, error, level=messages.ERROR)
                    
        except Exception as e:
            error_msg = f"Критическая ошибка в approve_transfers: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            log_error(
                "Критическая ошибка в approve_transfers",
                exception=e,
                user=request.user,
                context={},
                request=request
            )
            self.message_user(request, f"Произошла ошибка при подтверждении переносов: {str(e)}", level=messages.ERROR)
    
    @admin.action(description="Отклонить выбранные переносы")
    def reject_transfers(self, request, queryset):
        # Можно добавить форму для указания причины отклонения
        pending = queryset.filter(status=BatteryTransfer.Status.PENDING)
        for transfer in pending:
            transfer.reject(request.user)
        self.message_user(request, f"Отклонено переносов: {pending.count()}", level=messages.SUCCESS)
