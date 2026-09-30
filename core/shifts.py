# -*- coding: utf-8 -*-
"""
الورديات والصندوق (الدرج النقدي):
فتح وردية برصيد افتتاحي ← كل حركة نقدية تُربط بالوردية ← إغلاق بعدّ النقود ومعرفة العجز/الزيادة.
"""

from core import db, auth, audit, context
from core.suppliers import PAY_DRAWER
from core.utils import money


def current_shift():
    """الوردية المفتوحة على هذا الجهاز (لكل نقطة بيع صندوقها ووردياتها)"""
    return db.query_one("""SELECT s.*, u.username, u.full_name FROM shifts s LEFT JOIN users u ON u.id=s.user_id
                           WHERE s.status='open' AND COALESCE(s.terminal,'') = COALESCE(?, '')
                           ORDER BY s.id DESC LIMIT 1""", (context.terminal(),))


def open_shifts():
    """كل الورديات المفتوحة على كل الأجهزة (للمدير)"""
    return db.query("""SELECT s.*, u.username, u.full_name FROM shifts s LEFT JOIN users u ON u.id=s.user_id
                       WHERE s.status='open' ORDER BY s.id""")


def current_shift_id():
    s = current_shift()
    return s["id"] if s else None


def cash_shift(shift_id=None):
    """أي عملية نقدية من الدرج يجب أن تُسجَّل في وردية مفتوحة، وإلا اختل عدّ الصندوق.
    يرجع الوردية المحددة، أو الوردية المفتوحة على هذا الجهاز، أو يرفض العملية إن كانت الورديات إلزامية"""
    if shift_id:
        return shift_id
    sid = current_shift_id()
    if sid:
        return sid
    from core import settings
    if settings.get_bool("require_shift"):
        raise ValueError("العملية نقدية من الدرج ولا توجد وردية مفتوحة على هذا الجهاز. افتح وردية أولاً "
                         "(الصندوق والورديات)، أو اختر طريقة دفع غير نقدية.")
    return None


def open_shift(opening_cash=0.0, note=""):
    if current_shift():
        raise ValueError("توجد وردية مفتوحة بالفعل")
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO shifts(user_id, opened_at, opening_cash, note, status, terminal)
                              VALUES (?, ?, ?, ?, 'open', ?)""",
                           (auth.current_user_id(), db.now(), money(opening_cash), note, context.terminal()))
        audit.log("فتح وردية", f"رصيد افتتاحي {opening_cash}", conn)
        return cur.lastrowid


def cash_movement(amount, reason):
    """إدخال (+) أو سحب (-) نقدي من الصندوق خارج المبيعات، مثل سحب المالك أو إضافة فكّة"""
    s = current_shift()
    if not s:
        raise ValueError("لا توجد وردية مفتوحة")
    if not money(amount):
        raise ValueError("المبلغ مطلوب")
    with db.tx() as conn:
        conn.execute("INSERT INTO cash_movements(shift_id, amount, reason, user_id, created_at) VALUES (?, ?, ?, ?, ?)",
                     (s["id"], money(amount), reason, auth.current_user_id(), db.now()))
        audit.log("حركة صندوق", f"{amount:+} - {reason}", conn)


def summary(shift_id):
    """ملخص الوردية (تقرير Z): كل ما دخل وخرج من الصندوق النقدي"""
    s = db.query_one("SELECT * FROM shifts WHERE id=?", (shift_id,))
    if not s:
        return None
    one = lambda sql: money(db.scalar(sql, (shift_id,)))
    inv = db.query_one("""SELECT COUNT(*) AS cnt, COALESCE(SUM(total),0) AS total, COALESCE(SUM(cash_amount),0) AS cash,
                                 COALESCE(SUM(card_amount),0) AS card, COALESCE(SUM(credit_amount),0) AS credit,
                                 COALESCE(SUM(wallet_amount),0) AS wallet,
                                 COALESCE(SUM(discount),0) AS discount
                          FROM invoices WHERE shift_id=?""", (shift_id,))
    d = {
        "shift": dict(s),
        "invoice_count": inv["cnt"],
        "sales_total": money(inv["total"]),
        "cash_sales": money(inv["cash"]),
        "card_sales": money(inv["card"]),
        "wallet_sales": money(inv["wallet"]),
        "credit_sales": money(inv["credit"]),
        "discounts": money(inv["discount"]),
        "cash_refunds": one("SELECT SUM(total) FROM returns WHERE shift_id=? AND refund_method='نقدي'"),
        "debt_refunds": one("SELECT SUM(total) FROM returns WHERE shift_id=? AND refund_method='خصم من الدين'"),
        "electronic_refunds": one("""SELECT SUM(total) FROM returns WHERE shift_id=?
                                     AND refund_method NOT IN ('نقدي', 'خصم من الدين')"""),
        "customer_payments_cash": -one("SELECT SUM(amount) FROM customer_transactions WHERE shift_id=? AND type='payment' AND method='نقدي'"),
        "customer_payments_other": -one("SELECT SUM(amount) FROM customer_transactions WHERE shift_id=? AND type='payment' AND method!='نقدي'"),
        "expenses_cash": one("SELECT SUM(amount) FROM expenses WHERE shift_id=? AND from_drawer=1"),
        "supplier_payments_cash": money(
            -db.scalar("SELECT SUM(amount) FROM supplier_transactions WHERE shift_id=? AND type='payment' AND method=?",
                       (shift_id, PAY_DRAWER))
            + db.scalar("SELECT SUM(paid) FROM purchases WHERE shift_id=? AND supplier_id IS NULL AND payment_method=?",
                        (shift_id, PAY_DRAWER))),
        "cash_in": one("SELECT SUM(amount) FROM cash_movements WHERE shift_id=? AND amount>0"),
        "cash_out": -one("SELECT SUM(amount) FROM cash_movements WHERE shift_id=? AND amount<0"),
    }
    d["opening_cash"] = money(s["opening_cash"])
    d["expected_cash"] = money(d["opening_cash"] + d["cash_sales"] - d["cash_refunds"] + d["customer_payments_cash"]
                               + d["cash_in"] - d["cash_out"] - d["expenses_cash"] - d["supplier_payments_cash"])
    return d


def close_shift(counted_cash, note=""):
    s = current_shift()
    if not s:
        raise ValueError("لا توجد وردية مفتوحة")
    sm = summary(s["id"])
    diff = money(counted_cash - sm["expected_cash"])
    with db.tx() as conn:
        conn.execute("""UPDATE shifts SET closed_at=?, expected_cash=?, counted_cash=?, difference=?, note=?, status='closed'
                        WHERE id=?""", (db.now(), sm["expected_cash"], money(counted_cash), diff, note, s["id"]))
        audit.log("إغلاق وردية", f"المتوقع {sm['expected_cash']} المعدود {counted_cash} الفرق {diff}", conn)
    return s["id"], diff


def list_shifts(limit=200):
    return db.query("""SELECT s.*, u.username FROM shifts s LEFT JOIN users u ON u.id=s.user_id
                       ORDER BY s.id DESC LIMIT ?""", (limit,))


def movements(shift_id):
    return db.query("""SELECT m.*, u.username FROM cash_movements m LEFT JOIN users u ON u.id=m.user_id
                       WHERE shift_id=? ORDER BY m.id""", (shift_id,))
