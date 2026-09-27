# -*- coding: utf-8 -*-
"""توليد مستندات الطباعة كـ HTML (الفاتورة الحرارية، تقرير الوردية، كشف الحساب)"""

from html import escape

from core import settings, sales, customers, shifts
from core.utils import money, fmt_qty


def _m(v):
    return f"{money(v):,.2f}"


def _header():
    s = settings.get
    parts = [f"<div class='c big'><b>{escape(s('shop_name'))}</b></div>"]
    if s("shop_address"):
        parts.append(f"<div class='c'>{escape(s('shop_address'))}</div>")
    if s("shop_phone"):
        parts.append(f"<div class='c'>هاتف: {escape(s('shop_phone'))}</div>")
    if s("tax_number"):
        parts.append(f"<div class='c'>الرقم الضريبي: {escape(s('tax_number'))}</div>")
    return "".join(parts)


def _wrap(body, width_mm=None):
    width_mm = width_mm or int(settings.get_float("receipt_width_mm", 80))
    font = 9 if width_mm <= 58 else 10
    return f"""<html><head><meta charset='utf-8'><style>
    body {{ font-family: 'Tahoma','Arial'; font-size: {font}pt; direction: rtl; }}
    .c {{ text-align: center; }} .big {{ font-size: {font + 4}pt; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ padding: 1px 2px; }} th {{ border-bottom: 1px dashed #000; text-align: right; }}
    .l {{ text-align: left; }} .tot td {{ font-weight: bold; font-size: {font + 2}pt; border-top: 1px dashed #000; }}
    hr {{ border: 0; border-top: 1px dashed #000; }}
    </style></head><body dir='rtl'>{body}</body></html>"""


def invoice_html(invoice_id, copy=False):
    inv = sales.get_invoice(invoice_id)
    items = sales.get_invoice_items(invoice_id)
    sym = settings.get("currency_symbol")
    rows = "".join(
        f"<tr><td colspan='3'>{escape(i['product_name'])}</td></tr>"
        f"<tr><td>{fmt_qty(i['quantity'])} × {_m(i['unit_price'])}</td><td></td><td class='l'>{_m(i['total'])}</td></tr>"
        for i in items)
    lines = [f"<tr><td>المجموع</td><td class='l'>{_m(inv['subtotal'])}</td></tr>"]
    manual = money(inv["discount"] - inv["promo_discount"] - inv["points_value"])
    if manual > 0:
        lines.append(f"<tr><td>الخصم</td><td class='l'>-{_m(manual)}</td></tr>")
    if inv["promo_discount"]:
        lines.append(f"<tr><td>خصم العروض 🎁</td><td class='l'>-{_m(inv['promo_discount'])}</td></tr>")
    if inv["points_value"]:
        lines.append(f"<tr><td>استبدال {inv['points_redeemed']:g} نقطة</td><td class='l'>-{_m(inv['points_value'])}</td></tr>")
    if inv["tax"]:
        label = "منها ضريبة" if settings.get_bool("prices_include_vat") else "الضريبة"
        lines.append(f"<tr><td>{label} ({settings.get('vat_rate')}%)</td><td class='l'>{_m(inv['tax'])}</td></tr>")
    lines.append(f"<tr class='tot'><td>الإجمالي</td><td class='l'>{_m(inv['total'])} {sym}</td></tr>")
    if inv["cash_amount"]:
        lines.append(f"<tr><td>نقداً</td><td class='l'>{_m(inv['cash_amount'])}</td></tr>")
        if inv["cash_received"] and inv["cash_received"] > inv["cash_amount"]:
            lines.append(f"<tr><td>المستلم</td><td class='l'>{_m(inv['cash_received'])}</td></tr>")
            lines.append(f"<tr><td>الباقي للزبون</td><td class='l'>{_m(inv['change_given'])}</td></tr>")
    if inv["card_amount"]:
        lines.append(f"<tr><td>بطاقة</td><td class='l'>{_m(inv['card_amount'])}</td></tr>")
    if inv["credit_amount"]:
        lines.append(f"<tr><td>آجل (دين)</td><td class='l'>{_m(inv['credit_amount'])}</td></tr>")
    if inv["customer_id"]:
        lines.append(f"<tr><td>رصيد العميل الحالي</td><td class='l'>{_m(customers.balance(inv['customer_id']))}</td></tr>")
    if inv["customer_id"] and (inv["points_earned"] or inv["points_redeemed"]):
        from core import loyalty
        lines.append(f"<tr><td>نقاط هذه الفاتورة</td><td class='l'>+{inv['points_earned']:g}</td></tr>")
        lines.append(f"<tr><td>رصيد نقاطك</td><td class='l'>{loyalty.balance(inv['customer_id']):g}</td></tr>")
    if inv["returned_total"]:
        lines.append(f"<tr><td>مرتجع</td><td class='l'>-{_m(inv['returned_total'])}</td></tr>")

    body = _header() + "<hr>"
    if copy:
        body += "<div class='c'><b>*** نسخة ***</b></div>"
    if settings.get_bool("einvoice_qr") and inv["tax"]:
        body += "<div class='c'><b>فاتورة ضريبية مبسطة</b></div>"
    body += (f"<div>فاتورة: <b>{inv['invoice_number']}</b></div><div>التاريخ: {inv['created_at']}</div>"
             f"<div>الكاشير: {escape(inv['cashier_name'] or inv['cashier'] or '-')}</div>")
    if inv["customer_name"]:
        body += f"<div>العميل: {escape(inv['customer_name'])}</div>"
    body += f"<hr><table><tr><th>الصنف</th><th></th><th class='l'>المبلغ</th></tr>{rows}</table><hr>"
    body += f"<table>{''.join(lines)}</table><hr>"
    if inv["note"] and "عروض:" in inv["note"]:
        body += f"<div class='c'>{escape(inv['note'].split('عروض:', 1)[1].strip())}</div><hr>"
    body += f"<div class='c'>{escape(settings.get('receipt_footer') or '')}</div>"
    body += f"<div class='c'>عدد الأصناف: {len(items)}</div>"
    if settings.get_bool("einvoice_qr"):
        from core import einvoice
        uri = einvoice.invoice_qr(inv)
        if uri:
            body += f"<div class='c'><img src='{uri}' width='130' height='130'></div>"
    return _wrap(body)


def offline_receipt_html(p):
    """إيصال فاتورة بيعت أثناء انقطاع الشبكة (رقمها الرسمي يُعطى عند الترحيل)"""
    sym = settings.get("currency_symbol")
    rows = "".join(
        f"<tr><td colspan='3'>{escape(i['product_name'])}</td></tr>"
        f"<tr><td>{fmt_qty(i['quantity'])} × {_m(i['unit_price'])}</td><td></td>"
        f"<td class='l'>{_m(i['quantity'] * i['unit_price'])}</td></tr>" for i in p["cart"])
    lines = [f"<tr><td>المجموع</td><td class='l'>{_m(p['subtotal'])}</td></tr>"]
    if p["discount"]:
        lines.append(f"<tr><td>الخصم</td><td class='l'>-{_m(p['discount'])}</td></tr>")
    if p["promo_discount"]:
        lines.append(f"<tr><td>خصم العروض 🎁</td><td class='l'>-{_m(p['promo_discount'])}</td></tr>")
    lines.append(f"<tr class='tot'><td>الإجمالي</td><td class='l'>{_m(p['total'])} {sym}</td></tr>")
    if p["cash_amount"]:
        lines.append(f"<tr><td>نقداً</td><td class='l'>{_m(p['cash_amount'])}</td></tr>")
        if p["change"]:
            lines.append(f"<tr><td>الباقي للزبون</td><td class='l'>{_m(p['change'])}</td></tr>")
    if p["card_amount"]:
        lines.append(f"<tr><td>بطاقة</td><td class='l'>{_m(p['card_amount'])}</td></tr>")
    body = (_header() + f"<hr><div>مرجع: {escape(p['ref'][-10:].upper())}</div><div>التاريخ: {p['created_at']}</div>"
            f"<hr><table>{rows}</table><hr><table>{''.join(lines)}</table><hr>"
            f"<div class='c'>{escape(settings.get('receipt_footer') or '')}</div>")
    return _wrap(body)


def return_html(return_id):
    r = sales.get_return(return_id)
    items = sales.get_return_items(return_id)
    rows = "".join(f"<tr><td>{escape(i['product_name'])}</td><td>{fmt_qty(i['quantity'])}</td>"
                   f"<td class='l'>{_m(i['total'])}</td></tr>" for i in items)
    body = (_header() + "<hr><div class='c'><b>إيصال مرتجع</b></div>"
            f"<div>رقم المرتجع: {r['return_number']}</div><div>من الفاتورة: {r['invoice_number']}</div>"
            f"<div>التاريخ: {r['created_at']}</div><hr><table>{rows}</table><hr>"
            f"<table><tr class='tot'><td>المبلغ المُرجع</td><td class='l'>{_m(r['total'])} {settings.get('currency_symbol')}</td></tr>"
            f"<tr><td>طريقة الإرجاع</td><td class='l'>{r['refund_method']}</td></tr></table>")
    return _wrap(body)


def shift_html(shift_id):
    d = shifts.summary(shift_id)
    s = d["shift"]
    rows = [
        ("الرصيد الافتتاحي", d["opening_cash"]),
        ("عدد الفواتير", None, d["invoice_count"]),
        ("إجمالي المبيعات", d["sales_total"]),
        ("مبيعات نقدية", d["cash_sales"]),
        ("مبيعات بطاقة", d["card_sales"]),
        ("مبيعات آجلة", d["credit_sales"]),
        ("الخصومات", d["discounts"]),
        ("مرتجعات نقدية", d["cash_refunds"]),
        ("تسديدات عملاء نقداً", d["customer_payments_cash"]),
        ("إدخال للصندوق", d["cash_in"]),
        ("سحب من الصندوق", d["cash_out"]),
        ("مصاريف من الصندوق", d["expenses_cash"]),
        ("دفعات موردين من الصندوق", d["supplier_payments_cash"]),
    ]
    html_rows = ""
    for r in rows:
        val = r[2] if len(r) == 3 else _m(r[1])
        html_rows += f"<tr><td>{r[0]}</td><td class='l'>{val}</td></tr>"
    html_rows += f"<tr class='tot'><td>النقد المتوقع</td><td class='l'>{_m(d['expected_cash'])}</td></tr>"
    if s["status"] == "closed":
        html_rows += f"<tr><td>النقد المعدود</td><td class='l'>{_m(s['counted_cash'])}</td></tr>"
        label = "زيادة" if s["difference"] > 0 else ("عجز" if s["difference"] < 0 else "مطابق")
        html_rows += f"<tr class='tot'><td>الفرق ({label})</td><td class='l'>{_m(s['difference'])}</td></tr>"
    body = (_header() + f"<hr><div class='c'><b>تقرير وردية رقم {s['id']}</b></div>"
            f"<div>الفتح: {s['opened_at']}</div><div>الإغلاق: {s['closed_at'] or 'مفتوحة'}</div><hr>"
            f"<table>{html_rows}</table>")
    return _wrap(body)


def statement_html(customer_id, date_from=None, date_to=None):
    c = customers.get_customer(customer_id)
    opening, rows = customers.statement(customer_id, date_from, date_to)
    body_rows = f"<tr><td colspan='4'>رصيد سابق</td><td class='l'>{_m(opening)}</td></tr>" if date_from else ""
    for r in rows:
        body_rows += (f"<tr><td>{r['created_at'][:16]}</td><td>{escape(r['type_label'])} {escape(r['note'] or '')}</td>"
                      f"<td class='l'>{_m(r['debit']) if r['debit'] else ''}</td>"
                      f"<td class='l'>{_m(r['credit']) if r['credit'] else ''}</td><td class='l'>{_m(r['running'])}</td></tr>")
    final = rows[-1]["running"] if rows else opening
    body = (_header() + f"<hr><div class='c'><b>كشف حساب عميل</b></div><div>العميل: <b>{escape(c['name'])}</b> "
            f"{escape(c['phone'] or '')}</div>"
            + (f"<div>الفترة: {date_from} إلى {date_to}</div>" if date_from else "")
            + "<hr><table><tr><th>التاريخ</th><th>البيان</th><th class='l'>عليه</th><th class='l'>له</th><th class='l'>الرصيد</th></tr>"
            + body_rows + f"<tr class='tot'><td colspan='4'>الرصيد المستحق</td><td class='l'>{_m(final)} "
            f"{settings.get('currency_symbol')}</td></tr></table>")
    return _wrap(body, width_mm=210)
