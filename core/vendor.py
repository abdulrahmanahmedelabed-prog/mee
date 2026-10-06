# -*- coding: utf-8 -*-
"""
بيانات مزوّد البرنامج (أنت كمطوّر/موزّع). عدّلها قبل بناء نسخة البيع:
تظهر في شاشة التفعيل وفي "حول البرنامج"، ويُفتح واتساب على رقمك عند ضغط الزبون «طلب التفعيل».
"""

PRODUCT_NAME = "برنامج المحاسبة ونقاط البيع"
VERSION = "10.4"
VENDOR_NAME = "شركة الحسن للبرمجة والدعاية"
VENDOR_OWNER = "عبد الرحمن العابد"         # المدير
VENDOR_PHONE = "970592458157"          # رقم واتساب الدعم بالصيغة الدولية (بدون +)
VENDOR_PHONE_DISPLAY = "+970 59 245 8157"
VENDOR_EMAIL = ""
VENDOR_WEBSITE = ""
SUPPORT_HOURS = "يومياً 9 صباحاً - 9 مساءً"
# آخر نسخة: صفحة الإصدارات في GitHub (أو رابط JSON بالشكل {"version": "...", "url": "https://...", "notes": "..."})
UPDATE_URL = "https://api.github.com/repos/abdulrahmanahmedelabed-prog/mee/releases/latest"


def display_name():
    """«شركة الحسن للبرمجة والدعاية — عبد الرحمن العابد» بلغة الواجهة"""
    from core.i18n import tr
    return tr(VENDOR_NAME) + (f" — {tr(VENDOR_OWNER)}" if VENDOR_OWNER else "")
