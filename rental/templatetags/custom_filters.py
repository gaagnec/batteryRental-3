from django import template
from django.utils import timezone
from datetime import timedelta
from rental.admin_utils import is_moderator

register = template.Library()

@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.filter
def get_item_by_partner(list_of_dicts, partner_id):
    """Get dict from list by partner.id"""
    if not list_of_dicts:
        return {}
    for item in list_of_dicts:
        if item.get('partner') and item['partner'].id == partner_id:
            return item
    return {}


@register.filter
def abs_value(value):
    """Return absolute value of number"""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value


@register.filter
def display_end_date(value):
    """Display end_at as previous day 23:59 for UI clarity.
    If end_at is exactly at midnight (00:00:00), show day-1 23:59.
    Otherwise show as-is. Returns formatted string or '—'.
    """
    if not value:
        return '—'
    try:
        tz = timezone.get_current_timezone()
        dt = timezone.localtime(value, tz)
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
            display_dt = dt - timedelta(minutes=1)  # previous day 23:59
        else:
            display_dt = dt
        return display_dt.strftime('%d.%m.%Y %H:%M')
    except (ValueError, TypeError, AttributeError):
        return '—'


@register.simple_tag
def check_moderator(user):
    """Check if user is moderator"""
    return is_moderator(user)
