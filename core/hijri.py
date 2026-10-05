# -*- coding: utf-8 -*-
"""
التقويم الهجري (الحسابي الجدولي) بدون مكتبات: للتخطيط للمواسم وحَوْل الزكاة.
قد يختلف عن رؤية الهلال/أم القرى بيوم واحد؛ يكفي للتخطيط، ويمكن تصحيحه من الإعدادات (hijri_adjust).
"""

import math
from datetime import date, timedelta

MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان",
          "شوال", "ذو القعدة", "ذو الحجة"]
_EPOCH = date(622, 7, 19).toordinal()     # 1 محرم 1هـ (تقويم جريجوري ممتد)


def _adjust():
    try:
        from core import settings
        return int(settings.get_float("hijri_adjust", 0))
    except Exception:
        return 0


def _h2ord(y, m, d):
    return _EPOCH + d + math.ceil(29.5 * (m - 1)) + (y - 1) * 354 + (3 + 11 * y) // 30 - 1


def to_gregorian(y, m, d):
    return date.fromordinal(_h2ord(y, m, d) + _adjust())


def from_gregorian(g):
    """(سنة، شهر، يوم) هجري"""
    o = g.toordinal() - _adjust()
    y = (30 * (o - _EPOCH) + 10646) // 10631
    m = min(12, math.ceil((o - (29 + _h2ord(y, 1, 1))) / 29.5) + 1)
    m = max(1, m)
    d = o - _h2ord(y, m, 1) + 1
    return y, m, d


def fmt(g):
    y, m, d = from_gregorian(g)
    return f"{d} {MONTHS[m - 1]} {y}هـ"


def next_occurrence(month, day, today=None, span_days=0):
    """أقرب تاريخ ميلادي لـ (شهر، يوم) هجري: الحالي إن كنا داخله (span_days) أو القادم"""
    today = today or date.today()
    y, _, _ = from_gregorian(today)
    for yy in (y - 1, y, y + 1):
        g = to_gregorian(yy, month, day)
        if g + timedelta(days=span_days) > today:
            return g, yy
    return to_gregorian(y + 1, month, day), y + 1


def hijri_year_later(g):
    """نفس اليوم الهجري بعد سنة (لحَوْل الزكاة)"""
    y, m, d = from_gregorian(g)
    return to_gregorian(y + 1, m, min(d, 29))
