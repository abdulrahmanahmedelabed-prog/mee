# -*- coding: utf-8 -*-
"""
الشيكات المؤجلة (واردة من العملاء وصادرة للموردين):

- استلام شيك من عميل: ينقص دينه فوراً، ويبقى الشيك "برسم التحصيل" حتى تاريخ استحقاقه.
- إعطاء شيك لمورد: ينقص ما علينا له، ويبقى الشيك التزاماً علينا حتى يُصرف من البنك.
- عند الاستحقاق: "صُرف" (دخل/خرج من البنك) أو "رجع" (يعود الدين على العميل أو علينا للمورد).
- تنبيه في لوحة التحكم بالشيكات المستحقة خلال أسبوع حتى لا تُفاجأ برصيد البنك.
"""

from core import db, auth, audit
from core.utils import money

STATUS_LABELS = {"pending": "برسم التحصيل", "cleared": "صُرف", "bounced": "راجع (مرتجع)"}
DIRECTION_LABELS = {"in": "وارد من عميل", "out": "صادر لمورد"}
METHOD_IN = "شيك"
METHOD_OUT = "شيك مؤجل"


def _validate(amount, due_date):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("مبلغ الشيك يجب أن يكون أكبر من صفر")
    if not due_date or len(due_date) != 10:
        raise ValueError("تاريخ استحقاق الشيك مطلوب")
    return amount


def receive_cheque(customer_id, amount, due_date, cheque_number="", bank="", note=""):
    """شيك من عميل كتسديد لدينه"""
    amount = _validate(amount, due_date)
    user_id, created = auth.current_user_id(), db.now()
    with db.tx() as conn:
        c = conn.execute("SELECT name FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not c:
            raise ValueError("العميل غير موجود")
        cur = conn.execute("""INSERT INTO cheques(direction, cheque_number, bank, amount, due_date, customer_id, status,
                                                  note, user_id, created_at)
                              VALUES ('in', ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                           (cheque_number.strip(), bank.strip(), amount, due_date, customer_id, note, user_id, created))
        cid = cur.lastrowid
        conn.execute("""INSERT INTO customer_transactions(customer_id, type, amount, method, note, user_id, created_at)
                        VALUES (?, 'payment', ?, ?, ?, ?, ?)""",
                     (customer_id, -amount, METHOD_IN, f"شيك رقم {cheque_number} {bank} يستحق {due_date}".strip(),
                      user_id, created))
        audit.log("استلام شيك", f"من {c['name']}: {amount} يستحق {due_date}", conn)
    return cid


def issue_cheque(supplier_id, amount, due_date, cheque_number="", bank="", note=""):
    """شيك مؤجل لمورد كدفعة من حسابه"""
    amount = _validate(amount, due_date)
    user_id, created = auth.current_user_id(), db.now()
    with db.tx() as conn:
        s = conn.execute("SELECT name FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if not s:
            raise ValueError("المورد غير موجود")
        cur = conn.execute("""INSERT INTO cheques(direction, cheque_number, bank, amount, due_date, supplier_id, status,
                                                  note, user_id, created_at)
                              VALUES ('out', ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                           (cheque_number.strip(), bank.strip(), amount, due_date, supplier_id, note, user_id, created))
        cid = cur.lastrowid
        conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, method, note, user_id, created_at)
                        VALUES (?, 'payment', ?, ?, ?, ?, ?)""",
                     (supplier_id, -amount, METHOD_OUT, f"شيك رقم {cheque_number} {bank} يستحق {due_date}".strip(),
                      user_id, created))
        audit.log("إصدار شيك", f"للمورد {s['name']}: {amount} يستحق {due_date}", conn)
    return cid


def clear_cheque(cheque_id, date=None):
    """الشيك صُرف في البنك"""
    with db.tx() as conn:
        ch = _pending(conn, cheque_id)
        conn.execute("UPDATE cheques SET status='cleared', status_date=? WHERE id=?", (date or db.today(), cheque_id))
        audit.log("صرف شيك", f"#{ch['cheque_number'] or cheque_id} بقيمة {ch['amount']}", conn)


def bounce_cheque(cheque_id, note=""):
    """الشيك رجع: يعود المبلغ ديناً على العميل، أو مستحقاً للمورد"""
    user_id, created = auth.current_user_id(), db.now()
    with db.tx() as conn:
        ch = _pending(conn, cheque_id)
        conn.execute("UPDATE cheques SET status='bounced', status_date=?, note=TRIM(COALESCE(note,'') || ' ' || ?) WHERE id=?",
                     (db.today(), note, cheque_id))
        label = f"شيك راجع رقم {ch['cheque_number'] or cheque_id} {note}".strip()
        if ch["direction"] == "in":
            conn.execute("""INSERT INTO customer_transactions(customer_id, type, amount, note, user_id, created_at)
                            VALUES (?, 'bounced', ?, ?, ?, ?)""", (ch["customer_id"], ch["amount"], label, user_id, created))
        else:
            conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, note, user_id, created_at)
                            VALUES (?, 'bounced', ?, ?, ?, ?)""", (ch["supplier_id"], ch["amount"], label, user_id, created))
        audit.log("شيك راجع", f"#{ch['cheque_number'] or cheque_id} بقيمة {ch['amount']}", conn)


def _pending(conn, cheque_id):
    ch = conn.execute("SELECT * FROM cheques WHERE id=?", (cheque_id,)).fetchone()
    if not ch:
        raise ValueError("الشيك غير موجود")
    if ch["status"] != "pending":
        raise ValueError(f"حالة الشيك الحالية: {STATUS_LABELS.get(ch['status'])}")
    return ch


def list_cheques(direction=None, status=None, search=None):
    sql = """SELECT ch.*, COALESCE(c.name, s.name) AS party,
                    CAST(julianday(ch.due_date) - julianday(date('now','localtime')) AS INTEGER) AS days_left
             FROM cheques ch LEFT JOIN customers c ON c.id=ch.customer_id LEFT JOIN suppliers s ON s.id=ch.supplier_id"""
    cond, params = [], []
    if direction:
        cond.append("ch.direction=?")
        params.append(direction)
    if status:
        cond.append("ch.status=?")
        params.append(status)
    if search:
        cond.append("(ch.cheque_number LIKE ? OR ch.bank LIKE ? OR c.name LIKE ? OR s.name LIKE ?)")
        params += [f"%{search}%"] * 4
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return db.query(sql + " ORDER BY ch.status='pending' DESC, ch.due_date, ch.id", params)


def due_soon(days=7):
    """شيكات معلقة تستحق خلال عدد الأيام (أو فات موعدها)"""
    return db.query("""SELECT ch.*, COALESCE(c.name, s.name) AS party,
                              CAST(julianday(ch.due_date) - julianday(date('now','localtime')) AS INTEGER) AS days_left
                       FROM cheques ch LEFT JOIN customers c ON c.id=ch.customer_id
                       LEFT JOIN suppliers s ON s.id=ch.supplier_id
                       WHERE ch.status='pending' AND date(ch.due_date) <= date('now','localtime', ?)
                       ORDER BY ch.due_date""", (f"+{int(days)} days",))


def totals():
    row = db.query_one("""SELECT COALESCE(SUM(CASE WHEN direction='in' THEN amount END),0) AS incoming,
                                 COALESCE(SUM(CASE WHEN direction='out' THEN amount END),0) AS outgoing
                          FROM cheques WHERE status='pending'""")
    return {"incoming": money(row["incoming"]), "outgoing": money(row["outgoing"])}
