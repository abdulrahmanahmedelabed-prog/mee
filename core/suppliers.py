# -*- coding: utf-8 -*-
"""الموردون وفواتير المشتريات (تزيد المخزون وتحدّث متوسط التكلفة تلقائياً)"""

from core import db, auth, audit
from core.products import _move_stock
from core.utils import money, qty

PAY_DRAWER = "نقدي من الصندوق"
PAY_OUTSIDE = "نقدي من خارج الصندوق"
PAY_BANK = "تحويل بنكي / شيك"
PAYMENT_METHODS = [PAY_DRAWER, PAY_OUTSIDE, PAY_BANK]
TYPE_LABELS = {"purchase": "فاتورة مشتريات", "payment": "دفعة للمورد", "return": "مرتجع مشتريات",
               "opening": "رصيد سابق", "adjust": "تسوية", "bounced": "شيك راجع"}


def add_supplier(name, phone="", address="", notes="", opening_balance=0):
    if not (name or "").strip():
        raise ValueError("اسم المورد مطلوب")
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO suppliers(name, phone, address, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                           (name.strip(), phone.strip(), address.strip(), notes, db.now()))
        sid = cur.lastrowid
        if opening_balance:
            conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, note, user_id, created_at)
                            VALUES (?, 'opening', ?, 'رصيد سابق', ?, ?)""",
                         (sid, money(opening_balance), auth.current_user_id(), db.now()))
    return sid


def update_supplier(supplier_id, name, phone, address, notes):
    if not (name or "").strip():
        raise ValueError("اسم المورد مطلوب")
    with db.tx() as conn:
        conn.execute("UPDATE suppliers SET name=?, phone=?, address=?, notes=? WHERE id=?",
                     (name.strip(), phone.strip(), address.strip(), notes, supplier_id))


def deactivate_supplier(supplier_id):
    if abs(balance(supplier_id)) > 0.009:
        raise ValueError("لا يمكن حذف مورد له رصيد مستحق")
    with db.tx() as conn:
        conn.execute("UPDATE suppliers SET is_active=0 WHERE id=?", (supplier_id,))


def balance(supplier_id):
    return money(db.scalar("SELECT SUM(amount) FROM supplier_transactions WHERE supplier_id=?", (supplier_id,)))


def get_supplier(supplier_id):
    return db.query_one("SELECT * FROM suppliers WHERE id=?", (supplier_id,))


def list_suppliers(search=None):
    sql = """SELECT s.*, COALESCE((SELECT SUM(amount) FROM supplier_transactions t WHERE t.supplier_id=s.id),0) AS balance_due
             FROM suppliers s WHERE s.is_active=1"""
    params = []
    if search:
        sql += " AND (s.name LIKE ? OR s.phone LIKE ?)"
        params += [f"%{search}%"] * 2
    return db.query(sql + " ORDER BY s.name", params)


def create_purchase(supplier_id, items, paid=0.0, payment_method=PAY_DRAWER, supplier_ref="", note="",
                    shift_id=None, update_sale_prices=True):
    """
    items: dict: product_id, quantity, unit_cost, (اختياري) sale_price للحبة،
           factor + unit_name عند الشراء بالكرتونة، expiry_date + batch_no لتتبع الصلاحية
    - يزيد المخزون
    - يحدّث سعر التكلفة بطريقة المتوسط المرجّح (أدق لحساب الأرباح)
    - الجزء غير المدفوع يُسجّل ديناً للمورد
    """
    items = [i for i in items if i["quantity"] > 0]
    if not items:
        raise ValueError("أضف منتجاً واحداً على الأقل")
    total = money(sum(money(i["quantity"] * i["unit_cost"]) for i in items))
    paid = money(paid)
    if paid < 0 or paid > total + 0.009:
        raise ValueError("المبلغ المدفوع غير صحيح")
    if not supplier_id and abs(paid - total) > 0.009:
        raise ValueError("المشتريات بدون مورد يجب أن تُدفع كاملة")
    user_id = auth.current_user_id()
    created = db.now()
    with db.tx() as conn:
        number = db.next_number(conn, "purchase", "PUR")
        cur = conn.execute("""INSERT INTO purchases(purchase_number, supplier_id, supplier_ref, total, paid, payment_method,
                                                    note, user_id, shift_id, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (number, supplier_id, supplier_ref, total, paid, payment_method, note, user_id, shift_id, created))
        pid = cur.lastrowid
        for it in items:
            p = conn.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            factor = float(it.get("factor", 1) or 1)
            entered_q, entered_cost = qty(it["quantity"]), money(it["unit_cost"])
            q = qty(entered_q * factor)                    # بالوحدة الأساسية
            cost = entered_cost / factor                   # تكلفة الحبة
            old_q = max(p["quantity"], 0)
            new_cost = money((old_q * p["cost_price"] + q * cost) / (old_q + q)) if (old_q + q) > 0 else money(cost)
            conn.execute("""INSERT INTO purchase_items(purchase_id, product_id, product_name, quantity, unit_cost, total,
                                                       unit_name, factor, expiry_date, batch_no)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (pid, p["id"], p["name"], entered_q, entered_cost, money(entered_q * entered_cost),
                          it.get("unit_name") or p["unit"], factor, it.get("expiry_date") or None, it.get("batch_no") or None))
            conn.execute("UPDATE products SET cost_price=?, updated_at=? WHERE id=?", (new_cost, created, p["id"]))
            if update_sale_prices and it.get("sale_price") and money(it["sale_price"]) != money(p["sale_price"]):
                conn.execute("UPDATE products SET sale_price=? WHERE id=?", (money(it["sale_price"]), p["id"]))
                audit.log("تعديل سعر", f"{p['name']}: {p['sale_price']} ← {it['sale_price']} (من فاتورة مشتريات)", conn)
            _move_stock(conn, p["id"], q, f"مشتريات {number}", expiry_date=it.get("expiry_date") or None,
                        batch_no=it.get("batch_no"), purchase_id=pid)

        if supplier_id:
            conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, purchase_id, note, user_id, shift_id, created_at)
                            VALUES (?, 'purchase', ?, ?, ?, ?, ?, ?)""",
                         (supplier_id, total, pid, f"فاتورة {number} {supplier_ref or ''}".strip(), user_id, shift_id, created))
            if paid > 0:
                conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, method, purchase_id, note, user_id, shift_id, created_at)
                                VALUES (?, 'payment', ?, ?, ?, ?, ?, ?, ?)""",
                             (supplier_id, -paid, payment_method, pid, f"دفعة مع فاتورة {number}", user_id, shift_id, created))
        # ملاحظة: المشتريات النقدية بدون مورد تُحسب في الصندوق مباشرة من جدول purchases
        audit.log("فاتورة مشتريات", f"{number} بقيمة {total} مدفوع {paid}", conn)
    return {"purchase_id": pid, "purchase_number": number, "total": total}


def create_purchase_return(supplier_id, items, reason="", shift_id=None):
    """
    إرجاع بضاعة للمورد (تالف، منتهي، زائد عن الحاجة): تُخصم من المخزون ومن حساب المورد.
    items: dict: product_id, quantity (بالحبة)، (اختياري) unit_cost = السعر الذي سيخصمه المورد (افتراضياً تكلفتنا)
    """
    items = [i for i in items if i.get("quantity", 0) > 0]
    if not supplier_id:
        raise ValueError("اختر المورد")
    if not items:
        raise ValueError("أضف منتجاً واحداً على الأقل")
    user_id, created = auth.current_user_id(), db.now()
    with db.tx() as conn:
        if not conn.execute("SELECT 1 FROM suppliers WHERE id=?", (supplier_id,)).fetchone():
            raise ValueError("المورد غير موجود")
        number = db.next_number(conn, "purchase_return", "PRT")
        lines = []
        for it in items:
            p = conn.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            if not p:
                raise ValueError("منتج غير موجود")
            q = qty(it["quantity"])
            if q > p["quantity"] + 1e-9:
                raise ValueError(f"الكمية المرتجعة من {p['name']} أكبر من الموجود ({p['quantity']:g})")
            unit_cost = money(it.get("unit_cost") if it.get("unit_cost") is not None else p["cost_price"])
            lines.append((p, q, unit_cost, money(q * unit_cost), money(q * p["cost_price"])))
        total = money(sum(l[3] for l in lines))
        cost_total = money(sum(l[4] for l in lines))
        cur = conn.execute("""INSERT INTO purchase_returns(return_number, supplier_id, total, cost_total, reason, user_id,
                                                           shift_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                           (number, supplier_id, total, cost_total, reason, user_id, shift_id, created))
        rid = cur.lastrowid
        for p, q, unit_cost, line_total, book in lines:
            conn.execute("""INSERT INTO purchase_return_items(return_id, product_id, product_name, quantity, unit_cost,
                                                              book_cost, total) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (rid, p["id"], p["name"], q, unit_cost, p["cost_price"], line_total))
            _move_stock(conn, p["id"], -q, f"مرتجع مشتريات {number}")
        conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, note, user_id, shift_id, created_at)
                        VALUES (?, 'return', ?, ?, ?, ?, ?)""",
                     (supplier_id, -total, f"مرتجع {number} {reason or ''}".strip(), user_id, shift_id, created))
        audit.log("مرتجع مشتريات", f"{number} للمورد #{supplier_id} بقيمة {total}", conn)
    return {"return_id": rid, "return_number": number, "total": total}


def list_purchase_returns(supplier_id=None):
    sql = """SELECT r.*, s.name AS supplier_name FROM purchase_returns r JOIN suppliers s ON s.id=r.supplier_id"""
    params = []
    if supplier_id:
        sql += " WHERE r.supplier_id=?"
        params.append(supplier_id)
    return db.query(sql + " ORDER BY r.id DESC", params)


def purchase_return_items(return_id):
    return db.query("SELECT * FROM purchase_return_items WHERE return_id=?", (return_id,))


def pay_supplier(supplier_id, amount, method=PAY_DRAWER, note="", shift_id=None):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    with db.tx() as conn:
        conn.execute("""INSERT INTO supplier_transactions(supplier_id, type, amount, method, note, user_id, shift_id, created_at)
                        VALUES (?, 'payment', ?, ?, ?, ?, ?, ?)""",
                     (supplier_id, -amount, method, note or "دفعة للمورد", auth.current_user_id(), shift_id, db.now()))
        audit.log("دفعة لمورد", f"مورد #{supplier_id}: {amount} ({method})", conn)


def statement(supplier_id):
    rows, running = [], 0.0
    for r in db.query("""SELECT t.*, p.purchase_number FROM supplier_transactions t LEFT JOIN purchases p ON p.id=t.purchase_id
                         WHERE t.supplier_id=? ORDER BY t.created_at, t.id""", (supplier_id,)):
        running = money(running + r["amount"])
        d = dict(r)
        d["type_label"] = TYPE_LABELS.get(r["type"], r["type"])
        d["running"] = running
        rows.append(d)
    return rows


def list_purchases(date_from=None, date_to=None, supplier_id=None):
    sql = """SELECT p.*, s.name AS supplier_name FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id"""
    cond, params = [], []
    if date_from and date_to:
        cond.append("date(p.created_at) BETWEEN date(?) AND date(?)")
        params += [date_from, date_to]
    if supplier_id:
        cond.append("p.supplier_id=?")
        params.append(supplier_id)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return db.query(sql + " ORDER BY p.id DESC", params)


def purchase_items(purchase_id):
    return db.query("SELECT * FROM purchase_items WHERE purchase_id=?", (purchase_id,))


def total_dues():
    return money(db.scalar("SELECT SUM(b) FROM (SELECT SUM(amount) b FROM supplier_transactions GROUP BY supplier_id HAVING b > 0)"))
