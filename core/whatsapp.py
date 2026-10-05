# -*- coding: utf-8 -*-
"""
واتساب: تجهيز الرسائل وروابط wa.me.
يفتح البرنامج واتساب (التطبيق أو الويب) والرسالة جاهزة مكتوبة للعميل الصحيح، ويكفي الضغط على إرسال.
(الإرسال الآلي الكامل بدون تدخل يحتاج اشتراك WhatsApp Business API مدفوع.)
"""

from urllib.parse import quote

from core import settings, customers, sales
from core.utils import fmt_money, fmt_qty


def normalize_phone(phone, country_code=None):
    """0599123456 ← 970599123456 . الأرقام التي تبدأ بـ + أو 00 تبقى كما هي"""
    if not phone:
        return None
    raw = phone.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    if raw.startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    cc = "".join(ch for ch in (country_code or settings.get("whatsapp_country_code", "970")) if ch.isdigit())
    if digits.startswith("0"):
        return cc + digits[1:]
    if cc and digits.startswith(cc) and len(digits) > 10:
        return digits
    return cc + digits


def link(phone, text):
    num = normalize_phone(phone)
    if not num:
        return None
    from core import i18n
    text = i18n.tr(text)
    return f"https://wa.me/{num}?text={quote(text)}"


def invoice_text(invoice_id):
    inv = sales.get_invoice(invoice_id)
    items = sales.get_invoice_items(invoice_id)
    lines = [f"🧾 {settings.get('shop_name')}", f"فاتورة رقم {inv['invoice_number']}", inv["created_at"], ""]
    for i in items:
        lines.append(f"• {i['product_name']}  ×{fmt_qty(i['quantity'])}  = {i['total']:.2f}")
    lines.append("")
    if inv["discount"]:
        lines.append(f"الخصم: {inv['discount']:.2f}")
    lines.append(f"الإجمالي: {fmt_money(inv['total'])}")
    if inv["credit_amount"]:
        lines.append(f"منها آجل: {fmt_money(inv['credit_amount'])}")
    if inv["customer_id"]:
        lines.append(f"رصيدكم الحالي: {fmt_money(customers.balance(inv['customer_id']))}")
    footer = settings.get("receipt_footer")
    if footer:
        lines += ["", footer]
    return "\n".join(lines)


def reminder_link(customer_id):
    from core import installments          # من عنده خطة تقسيط يُذكَّر بقسطه
    c = customers.get_customer(customer_id)
    return link(c["phone"], installments.reminder_message(customer_id))
