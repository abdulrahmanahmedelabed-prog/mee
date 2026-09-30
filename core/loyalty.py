# -*- coding: utf-8 -*-
"""
نقاط الولاء للزبائن الدائمين:
- كل فاتورة لعميل مسجّل تكسبه نقاطاً حسب قيمتها (مثلاً نقطة لكل شيكل).
- يستبدل النقاط بخصم على فاتورة لاحقة (مثلاً 100 نقطة = 5 شيكل).
- المرتجع يلغي النقاط المكتسبة بنفس نسبته.
الاستبدال يُسجَّل كخصم على الفاتورة، فيبقى حساب الربح صحيحاً.

محاسبياً: النقاط غير المستبدلة دَين على المحل للزبائن. كل حركة نقاط تحفظ قيمتها بالعملة وقت حدوثها:
الكسب يُقيَّد مصروفاً (تكلفة نقاط الولاء) والتزاماً للعملاء، والاستبدال أو الإلغاء يعكسهما.
"""

import math

from core import db, settings
from core.utils import money


def enabled():
    return settings.get_bool("loyalty_enabled")


def points_for(amount):
    if not enabled():
        return 0.0
    return float(math.floor(max(amount, 0) * settings.get_float("loyalty_points_per_unit", 1) + 1e-9))


def value_of(points):
    return money(points * settings.get_float("loyalty_point_value", 0.05))


def balance(customer_id):
    return float(db.scalar("SELECT SUM(points) FROM loyalty_transactions WHERE customer_id=?", (customer_id,)) or 0)


def history(customer_id, limit=200):
    return db.query("""SELECT l.*, i.invoice_number FROM loyalty_transactions l LEFT JOIN invoices i ON i.id=l.invoice_id
                       WHERE l.customer_id=? ORDER BY l.id DESC LIMIT ?""", (customer_id, limit))


def _check_redeem(conn, customer_id, points):
    """التحقق من إمكانية الاستبدال داخل معاملة البيع. يرجع قيمة النقاط بالعملة"""
    if not points:
        return 0.0
    if not enabled():
        raise ValueError("نقاط الولاء غير مفعّلة")
    if not customer_id:
        raise ValueError("اختر العميل لاستبدال نقاطه")
    have = conn.execute("SELECT COALESCE(SUM(points),0) FROM loyalty_transactions WHERE customer_id=?",
                        (customer_id,)).fetchone()[0]
    if points > have + 1e-9:
        raise ValueError(f"رصيد النقاط غير كافٍ (المتوفر {have:g})")
    if points < settings.get_float("loyalty_min_redeem", 0):
        raise ValueError(f"أقل عدد نقاط للاستبدال {settings.get_float('loyalty_min_redeem', 0):g}")
    return value_of(points)


def _record(conn, customer_id, points, invoice_id=None, note="", user_id=None, value=None):
    """value: قيمة النقاط بالعملة بنفس إشارتها (افتراضياً حسب قيمة النقطة الحالية)"""
    if customer_id and points:
        if value is None:
            value = value_of(abs(points)) * (1 if points > 0 else -1)
        conn.execute("""INSERT INTO loyalty_transactions(customer_id, points, invoice_id, note, user_id, created_at, value)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""", (customer_id, points, invoice_id, note, user_id, db.now(),
                                                          money(value)))


def value_sql():
    """قيمة الحركة المحفوظة، أو حسب قيمة النقطة الحالية للحركات القديمة (قبل حفظ القيمة)"""
    return f"COALESCE(value, ROUND(points * {settings.get_float('loyalty_point_value', 0.05)!r}, 2))"


def liability():
    """قيمة النقاط غير المستبدلة (دَين على المحل للزبائن)"""
    return money(db.scalar(f"SELECT SUM({value_sql()}) FROM loyalty_transactions"))


def adjust(customer_id, points, note="تعديل يدوي"):
    from core import auth, audit
    with db.tx() as conn:
        _record(conn, customer_id, float(points), note=note, user_id=auth.current_user_id())
        audit.log("تعديل نقاط ولاء", f"عميل #{customer_id}: {points:+g} ({note})", conn)


def top_members(limit=50):
    return db.query("""SELECT c.id, c.name, c.phone, SUM(l.points) AS points FROM loyalty_transactions l
                       JOIN customers c ON c.id=l.customer_id GROUP BY c.id HAVING points > 0
                       ORDER BY points DESC LIMIT ?""", (limit,))
