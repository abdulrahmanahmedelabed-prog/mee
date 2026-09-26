# -*- coding: utf-8 -*-
"""أدوات مساعدة: تقريب المبالغ وتنسيقها"""

from decimal import Decimal, ROUND_HALF_UP


def money(value):
    """تقريب مالي صحيح لخانتين (ROUND_HALF_UP) لتجنب أخطاء الأعداد العشرية"""
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) + 0.0  # يمنع ظهور -0.00


def qty(value):
    """تقريب الكميات لثلاث خانات (للموزونات بالكيلو)"""
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def fmt_money(value, symbol=None):
    from core import settings
    if symbol is None:
        symbol = settings.get("currency_symbol", "₪")
    text = f"{money(value):,.2f}"
    return f"{text} {symbol}" if symbol else text


def fmt_qty(value):
    """عرض الكمية بدون أصفار زائدة: 5 بدل 5.0 و 1.25 كما هي"""
    v = qty(value)
    if v == int(v):
        return str(int(v))
    return f"{v:.3f}".rstrip("0").rstrip(".")


def to_float(text, default=0.0):
    try:
        return float(str(text).replace(",", "").replace("٫", ".").strip())
    except (ValueError, TypeError):
        return default
