# -*- coding: utf-8 -*-
"""
ختم البيانات ضد العبث (سلسلة بصمات SHA-256، بنفس فكرة ختم الفواتير في أنظمة الفوترة الإلكترونية):
- كل فاتورة بيع تُختم ببصمة تشمل بياناتها المالية وبصمة الفاتورة التي قبلها.
- كل سطر في سجل العمليات يُختم بنفس الطريقة.
أي تعديل أو حذف مباشر في ملف قاعدة البيانات (خارج البرنامج) يكسر السلسلة، ويكشفه المدقق المالي فوراً
مع رقم أول فاتورة/سطر تغيّر. البيانات المسجلة قبل تفعيل الختم لا تُختم (تبدأ السلسلة من أول سجل مختوم).
"""

import hashlib

_INVOICE_FIELDS = ("invoice_number", "customer_id", "subtotal", "discount", "tax", "total", "cash_amount",
                   "card_amount", "credit_amount", "wallet_amount", "user_id", "created_at")


def _num(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def invoice_seal(prev_seal, row):
    data = "|".join([prev_seal or ""] + [_num(row[k]) for k in _INVOICE_FIELDS])
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def audit_chain(prev_chain, user_id, action, details, created_at):
    data = "|".join([prev_chain or "", _num(user_id), action or "", details or "", created_at or ""])
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def seal_invoice(conn, invoice_id):
    """يُستدعى داخل معاملة البيع نفسها بعد إدخال الفاتورة"""
    prev = conn.execute("SELECT seal FROM invoices WHERE id < ? AND seal IS NOT NULL ORDER BY id DESC LIMIT 1",
                        (invoice_id,)).fetchone()
    row = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    seal = invoice_seal(prev[0] if prev else "", row)
    conn.execute("UPDATE invoices SET seal=? WHERE id=?", (seal, invoice_id))
    return seal


def next_audit_chain(conn, user_id, action, details, created_at):
    prev = conn.execute("SELECT chain FROM audit_log WHERE chain IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return audit_chain(prev[0] if prev else "", user_id, action, details, created_at)


def verify_invoices(conn=None):
    """يرجع (عدد المختوم، قائمة المشاكل [(رقم الفاتورة، الوصف)])"""
    from core import db
    own = conn is None
    conn = conn or db.get_connection()
    problems, prev, n = [], "", 0
    try:
        cols = ", ".join(("id", "seal") + _INVOICE_FIELDS)
        for row in conn.execute(f"SELECT {cols} FROM invoices WHERE seal IS NOT NULL ORDER BY id"):
            n += 1
            if invoice_seal(prev, row) != row["seal"]:
                problems.append((row["invoice_number"], "تغيّرت بياناتها أو حُذفت فاتورة قبلها"))
            prev = row["seal"]
        # فاتورة بلا ختم بعد بدء الختم = أُدخلت مباشرة في الملف
        first = conn.execute("SELECT MIN(id) FROM invoices WHERE seal IS NOT NULL").fetchone()[0]
        if first:
            for r in conn.execute("SELECT invoice_number FROM invoices WHERE seal IS NULL AND id > ? LIMIT 20", (first,)):
                problems.append((r[0], "أُضيفت بدون ختم (من خارج البرنامج)"))
    finally:
        if own:
            conn.close()
    return n, problems


def verify_audit_log(conn=None):
    from core import db
    own = conn is None
    conn = conn or db.get_connection()
    problems, prev, n = [], "", 0
    try:
        for r in conn.execute("SELECT id, user_id, action, details, created_at, chain FROM audit_log "
                              "WHERE chain IS NOT NULL ORDER BY id"):
            n += 1
            if audit_chain(prev, r["user_id"], r["action"], r["details"], r["created_at"]) != r["chain"]:
                problems.append((r["id"], "تغيّر نص السطر أو حُذف سطر قبله"))
            prev = r["chain"]
        first = conn.execute("SELECT MIN(id) FROM audit_log WHERE chain IS NOT NULL").fetchone()[0]
        if first:
            for r in conn.execute("SELECT id FROM audit_log WHERE chain IS NULL AND id > ? LIMIT 20", (first,)):
                problems.append((r[0], "أُضيف بدون ختم (من خارج البرنامج)"))
    finally:
        if own:
            conn.close()
    return n, problems
