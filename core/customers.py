# -*- coding: utf-8 -*-
"""العملاء والديون (دفتر الدين / الحساب الآجل)"""

from core import db, auth, audit
from core.utils import money, fmt_money

PAYMENT_METHODS = ["نقدي", "بطاقة", "تحويل"]
TYPE_LABELS = {"sale": "فاتورة آجلة", "payment": "تسديد", "return": "مرتجع", "opening": "رصيد سابق", "adjust": "تسوية",
               "bounced": "شيك راجع"}


PRICE_LEVELS = {"retail": "مفرق (سعر البيع العادي)", "wholesale": "جملة (سعر الجملة)"}


def add_customer(name, phone="", address="", credit_limit=0, notes="", opening_balance=0, price_level="retail"):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم العميل مطلوب")
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO customers(name, phone, address, credit_limit, notes, is_active, created_at,
                                                    price_level) VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                           (name, phone.strip(), address.strip(), money(credit_limit), notes, db.now(),
                            price_level if price_level in PRICE_LEVELS else "retail"))
        cid = cur.lastrowid
        if opening_balance:
            conn.execute("""INSERT INTO customer_transactions(customer_id, type, amount, note, user_id, created_at)
                            VALUES (?, 'opening', ?, 'رصيد سابق (دين قديم)', ?, ?)""",
                         (cid, money(opening_balance), auth.current_user_id(), db.now()))
    return cid


def update_customer(customer_id, name, phone, address, credit_limit, notes, price_level=None):
    if not (name or "").strip():
        raise ValueError("اسم العميل مطلوب")
    with db.tx() as conn:
        conn.execute("UPDATE customers SET name=?, phone=?, address=?, credit_limit=?, notes=? WHERE id=?",
                     (name.strip(), phone.strip(), address.strip(), money(credit_limit), notes, customer_id))
        if price_level in PRICE_LEVELS:
            conn.execute("UPDATE customers SET price_level=? WHERE id=?", (price_level, customer_id))


def deactivate_customer(customer_id):
    if abs(balance(customer_id)) > 0.009:
        raise ValueError("لا يمكن حذف عميل عليه رصيد. قم بتسوية حسابه أولاً.")
    with db.tx() as conn:
        conn.execute("UPDATE customers SET is_active=0 WHERE id=?", (customer_id,))
        audit.log("حذف عميل", str(customer_id), conn)


def balance(customer_id):
    return money(db.scalar("SELECT SUM(amount) FROM customer_transactions WHERE customer_id=?", (customer_id,)))


def get_customer(customer_id):
    return db.query_one("SELECT * FROM customers WHERE id=?", (customer_id,))


def list_customers(search=None, debtors_only=False):
    sql = """SELECT c.*, COALESCE((SELECT SUM(amount) FROM customer_transactions t WHERE t.customer_id=c.id),0) AS balance_due,
                    (SELECT MAX(created_at) FROM customer_transactions t WHERE t.customer_id=c.id AND t.type='payment') AS last_payment
             FROM customers c WHERE c.is_active=1"""
    params = []
    if search:
        sql += " AND (c.name LIKE ? OR c.phone LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if debtors_only:
        sql += " AND balance_due > 0.009"
    sql += " ORDER BY balance_due DESC, c.name"
    return db.query(sql, params)


def receive_payment(customer_id, amount, method="نقدي", note="", shift_id=None):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO customer_transactions(customer_id, type, amount, method, note, user_id, shift_id, created_at)
                              VALUES (?, 'payment', ?, ?, ?, ?, ?, ?)""",
                           (customer_id, -amount, method, note or "تسديد دفعة", auth.current_user_id(), shift_id, db.now()))
        audit.log("تسديد عميل", f"عميل #{customer_id}: {amount} ({method})", conn)
        return cur.lastrowid


def adjust_balance(customer_id, amount, note):
    """تسوية يدوية (مثلاً مسامحة بمبلغ بسيط) - موجب يزيد الدين"""
    with db.tx() as conn:
        conn.execute("""INSERT INTO customer_transactions(customer_id, type, amount, note, user_id, created_at)
                        VALUES (?, 'adjust', ?, ?, ?, ?)""", (customer_id, money(amount), note, auth.current_user_id(), db.now()))
        audit.log("تسوية حساب عميل", f"عميل #{customer_id}: {amount} - {note}", conn)


def statement(customer_id, date_from=None, date_to=None):
    """كشف حساب مع رصيد تراكمي. يرجع (رصيد ما قبل الفترة، الحركات)"""
    opening = 0.0
    params = [customer_id]
    sql = """SELECT t.*, i.invoice_number FROM customer_transactions t LEFT JOIN invoices i ON i.id=t.invoice_id
             WHERE t.customer_id=?"""
    if date_from and date_to:
        opening = money(db.scalar("SELECT SUM(amount) FROM customer_transactions WHERE customer_id=? AND date(created_at) < date(?)",
                                  (customer_id, date_from)))
        sql += " AND date(t.created_at) BETWEEN date(?) AND date(?)"
        params += [date_from, date_to]
    sql += " ORDER BY t.created_at, t.id"
    rows, running = [], opening
    for r in db.query(sql, params):
        running = money(running + r["amount"])
        d = dict(r)
        d["type_label"] = TYPE_LABELS.get(r["type"], r["type"])
        d["debit"] = r["amount"] if r["amount"] > 0 else 0
        d["credit"] = -r["amount"] if r["amount"] < 0 else 0
        d["running"] = running
        rows.append(d)
    return opening, rows


def total_debts():
    return money(db.scalar("""SELECT SUM(b) FROM (SELECT SUM(amount) b FROM customer_transactions GROUP BY customer_id HAVING b > 0)"""))


def reminder_message(customer_id):
    from core import settings
    c = get_customer(customer_id)
    bal = balance(customer_id)
    shop = settings.get("shop_name")
    return (f"مرحباً {c['name']}،\nنود تذكيركم بأن الرصيد المستحق لدى {shop} هو {fmt_money(bal)}.\n"
            f"شاكرين لكم حسن التعامل 🌷")
