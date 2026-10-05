# -*- coding: utf-8 -*-
"""
هوية المحل في كل مكان: الشعار والاسم والعنوان في الطباعة (فاتورة حرارية، A4، كشوف، تقارير، قسائم)
وفي العرض (القائمة الجانبية، شاشة الدخول، شاشة الزبون، لوحة المالك، المتجر الأونلاين).

- shop_logo: نسخة رمادية خفيفة للطابعات الحرارية (أبيض وأسود).
- shop_logo_color: النسخة الملونة للشاشات وتقارير A4 (إن لم توجد تُستخدم الرمادية).
"""

from html import escape

from core import settings


def logo_b64(color=True):
    s = settings.get
    return (s("shop_logo_color") if color else "") or s("shop_logo") or ""


def has_logo():
    return bool(logo_b64())


def logo_img(width=120, color=True, style=""):
    """وسم <img> للشعار، أو نص فارغ إن لم يوجد"""
    b = logo_b64(color)
    if not b:
        return ""
    return f"<img src='data:image/png;base64,{b}' width='{int(width)}' style='{style}'>"


def print_header(title="", subtitle="", logo_width=90):
    """رأس موحّد لمستندات A4: الشعار والاسم وبيانات المحل، ثم عنوان المستند"""
    from core.i18n import is_rtl
    s = settings.get
    info = []
    if s("branch_name"):
        info.append(escape(s("branch_name")))
    if s("shop_address"):
        info.append(escape(s("shop_address")))
    if s("shop_phone"):
        info.append("هاتف: " + escape(s("shop_phone")))
    if s("tax_number"):
        info.append("الرقم الضريبي: " + escape(s("tax_number")))
    logo = logo_img(logo_width)
    side = "left" if is_rtl() else "right"
    head = (f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-bottom:6px'><tr>"
            f"<td valign='middle'><span style='font-size:16pt; font-weight:bold'>{escape(s('shop_name') or '')}</span>"
            f"<br><span style='color:#475467; font-size:9pt'>{' • '.join(info)}</span></td>"
            + (f"<td width='{logo_width + 10}' align='{side}' valign='middle'>{logo}</td>" if logo else "")
            + "</tr></table><hr style='border:0; border-top:2px solid #2563EB'>")
    if title:
        head += f"<h3 style='text-align:center; margin:8px 0 2px 0'>{escape(title)}</h3>"
    if subtitle:
        head += f"<p style='text-align:center; color:#475467; margin:0 0 8px 0'>{escape(subtitle)}</p>"
    return head


def document(body, title="", subtitle="", size_pt=10):
    """مستند A4 كامل برأس المحل"""
    from core.i18n import is_rtl
    d = "rtl" if is_rtl() else "ltr"
    return (f"<html><head><meta charset='utf-8'></head><body dir='{d}' style='font-family:Tahoma;font-size:{size_pt}pt'>"
            f"{print_header(title, subtitle)}{body}</body></html>")


def logo_pixmap(size):
    """الشعار كصورة للواجهة (مربّع بحجم size)، أو None"""
    import base64
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt
    b = logo_b64()
    if not b:
        return None
    pm = QPixmap()
    if not pm.loadFromData(base64.b64decode(b)):
        return None
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
