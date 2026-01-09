from django import template
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


@register.simple_tag
def check_moderator(user):
    """Check if user is moderator"""
    return is_moderator(user)
