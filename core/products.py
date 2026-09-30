# -*- coding: utf-8 -*-
"""المنتجات والمخزون"""

import csv

from core import db, auth, audit
from core.barcode import internal_barcode, parse_scale_barcode
from core.utils import money, qty, unit_cost

UNITS = ["قطعة", "كغم", "غرام", "لتر", "علبة", "كرتونة", "ربطة", "كيس", "درزن", "متر"]


def _clean_barcode(barcode):
    barcode = (barcode or "").strip()
    return barcode or None


def add_product(name, barcode=None, category="", cost_price=0, sale_price=0, quantity=0, min_quantity=0,
                unit="قطعة", plu_code=None, is_weighted=False, is_favorite=False, opening_expiry=None,
                wholesale_price=0):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المنتج مطلوب")
    if sale_price < 0 or cost_price < 0:
        raise ValueError("الأسعار لا يمكن أن تكون سالبة")
    barcode = _clean_barcode(barcode)
    plu_code = (str(plu_code).strip().lstrip("0") or None) if plu_code else None
    with db.tx() as conn:
        _check_unique(conn, barcode, plu_code)
        cur = conn.execute("""
            INSERT INTO products (name, barcode, category, cost_price, sale_price, quantity, min_quantity, unit,
                                  plu_code, is_weighted, is_favorite, created_at, updated_at, wholesale_price)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, barcode, (category or "").strip(), unit_cost(cost_price), money(sale_price), qty(min_quantity),
              unit or "قطعة", plu_code, 1 if is_weighted else 0, 1 if is_favorite else 0, db.now(), db.now(),
              money(wholesale_price or 0)))
        pid = cur.lastrowid
        if quantity:
            _move_stock(conn, pid, quantity, "رصيد افتتاحي", expiry_date=opening_expiry)
    return pid


def _check_unique(conn, barcode, plu_code, exclude_id=None):
    if barcode:
        row = conn.execute("SELECT id, name FROM products WHERE barcode=? AND id != ?",
                           (barcode, exclude_id or -1)).fetchone()
        if row:
            raise ValueError(f"الباركود مستخدم مسبقاً للمنتج: {row['name']}")
        row = conn.execute("""SELECT p.name, u.name AS unit FROM product_units u JOIN products p ON p.id=u.product_id
                              WHERE u.barcode=? AND u.product_id != ?""", (barcode, exclude_id or -1)).fetchone()
        if row:
            raise ValueError(f"الباركود مستخدم مسبقاً لوحدة ({row['unit']}) من المنتج: {row['name']}")
    if plu_code:
        row = conn.execute("SELECT id, name FROM products WHERE plu_code=? AND is_active=1 AND id != ?",
                           (plu_code, exclude_id or -1)).fetchone()
        if row:
            raise ValueError(f"رمز الميزان مستخدم مسبقاً للمنتج: {row['name']}")


def update_product(product_id, name, barcode, category, cost_price, sale_price, min_quantity, unit,
                   plu_code=None, is_weighted=False, is_favorite=False, wholesale_price=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المنتج مطلوب")
    barcode = _clean_barcode(barcode)
    plu_code = (str(plu_code).strip().lstrip("0") or None) if plu_code else None
    with db.tx() as conn:
        _check_unique(conn, barcode, plu_code, exclude_id=product_id)
        old = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        conn.execute("""
            UPDATE products SET name=?, barcode=?, category=?, cost_price=?, sale_price=?, min_quantity=?, unit=?,
                   plu_code=?, is_weighted=?, is_favorite=?, updated_at=?
            WHERE id=?
        """, (name, barcode, (category or "").strip(), unit_cost(cost_price), money(sale_price), qty(min_quantity),
              unit or "قطعة", plu_code, 1 if is_weighted else 0, 1 if is_favorite else 0, db.now(), product_id))
        if wholesale_price is not None:
            conn.execute("UPDATE products SET wholesale_price=? WHERE id=?", (money(wholesale_price), product_id))
        if old and unit_cost(old["cost_price"]) != unit_cost(cost_price) and old["quantity"] > 0:
            # إعادة تقييم البضاعة الموجودة بالتكلفة الجديدة: الفرق خسارة (أو مكسب) حتى تبقى قيمة المخزون في الدفاتر
            # مطابقة لقيمته الفعلية
            diff = money((old["cost_price"] - unit_cost(cost_price)) * old["quantity"])
            if diff:
                conn.execute("""INSERT INTO stock_movements (product_id, change_qty, reason, user_id, balance_after,
                                                             loss_value, unit_cost, created_at)
                                VALUES (?, 0, ?, ?, ?, ?, ?, ?)""",
                             (product_id, f"إعادة تقييم التكلفة {old['cost_price']:g} ← {unit_cost(cost_price):g}",
                              auth.current_user_id(), old["quantity"], diff, unit_cost(cost_price), db.now()))
        if old and (money(old["sale_price"]) != money(sale_price) or unit_cost(old["cost_price"]) != unit_cost(cost_price)):
            audit.log("تعديل سعر", f"{name}: البيع {old['sale_price']} ← {sale_price} | التكلفة {old['cost_price']} ← {cost_price}", conn)


def delete_product(product_id):
    """حذف ناعم: يبقى المنتج في الفواتير القديمة، ويتحرر الباركود لاستخدامه لمنتج جديد"""
    with db.tx() as conn:
        p = conn.execute("SELECT name, barcode, quantity, is_service FROM products WHERE id=?", (product_id,)).fetchone()
        if p and not p["is_service"] and abs(p["quantity"] or 0) > 1e-9:
            # الكمية الباقية تُشطب خسارة حتى لا تبقى قيمتها في الدفاتر لصنف محذوف
            _move_stock(conn, product_id, -p["quantity"], "حذف صنف: شطب الكمية المتبقية", loss=True)
        conn.execute("DELETE FROM product_units WHERE product_id=?", (product_id,))
        conn.execute("""UPDATE products SET is_active=0, is_favorite=0, plu_code=NULL,
                        barcode = CASE WHEN barcode IS NULL THEN NULL ELSE barcode || '#حذف' || id END
                        WHERE id=?""", (product_id,))
        audit.log("حذف منتج", p["name"] if p else str(product_id), conn)


def assign_internal_barcode(product_id):
    code = internal_barcode(product_id)
    with db.tx() as conn:
        conn.execute("UPDATE products SET barcode=? WHERE id=? AND (barcode IS NULL OR barcode='')", (code, product_id))
    return code


LOSS_KEYWORDS = ("تالف", "منتهي", "إتلاف", "سرقة", "فقدان", "هدية", "استهلاك", "جرد")


def is_loss_reason(reason):
    return any(k in (reason or "") for k in LOSS_KEYWORDS)


def _move_stock(conn, product_id, change, reason, expiry_date=None, batch_no=None, purchase_id=None, batch_id=None,
                loss=False):
    """
    كل تغيير في المخزون يمر من هنا:
    - الزيادة مع تاريخ صلاحية تُنشئ دفعة جديدة
    - النقص يُستهلك من الدفعات الأقرب انتهاءً أولاً (FEFO) أو من دفعة محددة
    """
    change = qty(change)
    conn.execute("UPDATE products SET quantity = ROUND(quantity + ?, 3) WHERE id=?", (change, product_id))
    bal = conn.execute("SELECT quantity FROM products WHERE id=?", (product_id,)).fetchone()[0]
    cost = conn.execute("SELECT cost_price FROM products WHERE id=?", (product_id,)).fetchone()[0] or 0
    loss_value = money(-change * cost) if loss else 0.0  # نقص = خسارة موجبة، زيادة في الجرد = ربح (سالب)
    conn.execute("""INSERT INTO stock_movements (product_id, change_qty, reason, user_id, balance_after, loss_value,
                                                 unit_cost, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                 (product_id, change, reason, auth.current_user_id(), bal, loss_value, cost, db.now()))
    if change > 0 and expiry_date:
        conn.execute("""INSERT INTO product_batches(product_id, batch_no, expiry_date, quantity, remaining, purchase_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (product_id, batch_no or None, expiry_date, change, change, purchase_id, db.now()))
    elif change < 0:
        _consume_batches(conn, product_id, -change, batch_id)
    return bal


def _consume_batches(conn, product_id, amount, batch_id=None):
    if batch_id:
        rows = conn.execute("SELECT id, remaining FROM product_batches WHERE id=? AND remaining > 0", (batch_id,)).fetchall()
    else:
        rows = conn.execute("""SELECT id, remaining FROM product_batches WHERE product_id=? AND remaining > 0
                               ORDER BY expiry_date, id""", (product_id,)).fetchall()
    for r in rows:
        if amount <= 1e-9:
            break
        take = min(r["remaining"], amount)
        conn.execute("UPDATE product_batches SET remaining = ROUND(remaining - ?, 3) WHERE id=?", (take, r["id"]))
        amount -= take


def adjust_stock(product_id, change_qty, reason="تعديل يدوي", expiry_date=None, batch_no=None):
    # كل تعديل كمية بدون مستند يؤثر على الربح (النقص خسارة والزيادة مكسب)، إلا الرصيد الافتتاحي
    # والبضاعة المستلمة بدون فاتورة فتُقيَّد كرأس مال/أرصدة افتتاحية
    loss = not any(k in (reason or "") for k in ("افتتاحي", "استلام"))
    with db.tx() as conn:
        bal = _move_stock(conn, product_id, change_qty, reason, expiry_date, batch_no, loss=loss)
        audit.log("تعديل مخزون", f"منتج #{product_id}: {change_qty:+} ({reason})", conn)
    return bal


def set_stock_count(product_id, counted_qty, reason="جرد"):
    """جرد: إدخال الكمية الفعلية على الرف، والبرنامج يحسب الفرق ويسجله"""
    with db.tx() as conn:
        current = conn.execute("SELECT quantity FROM products WHERE id=?", (product_id,)).fetchone()[0]
        diff = qty(counted_qty - current)
        if diff:
            _move_stock(conn, product_id, diff, reason, loss=True)
            audit.log("جرد", f"منتج #{product_id}: {current} ← {counted_qty}", conn)
    return diff


def get_product(product_id):
    return db.query_one("SELECT * FROM products WHERE id=?", (product_id,))


def get_all_products(active_only=True, search=None, category=None, low_only=False, favorites_only=False):
    sql = """SELECT *, (SELECT MIN(expiry_date) FROM product_batches b WHERE b.product_id=products.id AND b.remaining > 0)
                       AS next_expiry,
                    (SELECT COUNT(*) FROM product_units u WHERE u.product_id=products.id) AS units_count
             FROM products"""
    cond, params = [], []
    if active_only:
        cond.append("is_active=1")
    if search:
        words = search.split()
        for w in words:
            cond.append("(name LIKE ? OR barcode LIKE ? OR plu_code = ? OR id IN (SELECT product_id FROM product_units WHERE barcode LIKE ?))")
            params += [f"%{w}%", f"{w}%", w.lstrip("0"), f"{w}%"]
    if category:
        cond.append("category = ?")
        params.append(category)
    if low_only:
        cond.append("quantity <= min_quantity AND is_service=0")
    if favorites_only:
        cond.append("is_favorite = 1")
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY name COLLATE NOCASE"
    return db.query(sql, params)


def get_categories():
    return [r[0] for r in db.query(
        "SELECT DISTINCT category FROM products WHERE is_active=1 AND category IS NOT NULL AND category != '' ORDER BY category")]


def get_product_by_barcode(barcode):
    return db.query_one("SELECT * FROM products WHERE barcode=? AND is_active=1", (barcode.strip(),))


def lookup_code(code):
    """
    البحث بالكود الممسوح: باركود المنتج، ثم باركود وحدة (كرتونة...)، ثم باركود الميزان.
    يرجع (product, quantity, unit) — unit قاموس الوحدة أو None للوحدة الأساسية
    """
    code = (code or "").strip()
    p = get_product_by_barcode(code)
    if p:
        return p, None, None
    u = db.query_one("""SELECT u.* FROM product_units u JOIN products p ON p.id=u.product_id
                        WHERE u.barcode=? AND p.is_active=1""", (code,))
    if u:
        return get_product(u["product_id"]), None, dict(u)
    parsed = parse_scale_barcode(code)
    if parsed:
        plu, value, mode = parsed
        p = db.query_one("SELECT * FROM products WHERE plu_code=? AND is_active=1", (plu,))
        if p:
            if mode == "weight":
                return p, qty(value), None
            price = p["sale_price"] or 1
            return p, qty(value / price), None
    return None, None, None


# ---------------- الوحدات المتعددة (حبة / علبة / كرتونة) ----------------

def get_units(product_id):
    return [dict(r) for r in db.query("SELECT * FROM product_units WHERE product_id=? ORDER BY factor", (product_id,))]


def set_units(product_id, units):
    """units: قائمة dict: name, factor, barcode, sale_price — تستبدل الوحدات الحالية"""
    clean = []
    for u in units:
        name = (u.get("name") or "").strip()
        factor = float(u.get("factor") or 0)
        if not name:
            continue
        if factor <= 1:
            raise ValueError(f"الوحدة '{name}': عدد الحبات يجب أن يكون أكبر من 1")
        clean.append((name, qty(factor), _clean_barcode(u.get("barcode")), money(u.get("sale_price") or 0)))
    codes = [c[2] for c in clean if c[2]]
    if len(codes) != len(set(codes)):
        raise ValueError("يوجد باركود مكرر بين الوحدات")
    with db.tx() as conn:
        conn.execute("DELETE FROM product_units WHERE product_id=?", (product_id,))
        for name, factor, barcode, price in clean:
            if barcode:
                _check_unique(conn, barcode, None, exclude_id=product_id)
                own = conn.execute("SELECT 1 FROM products WHERE id=? AND barcode=?", (product_id, barcode)).fetchone()
                if own:
                    raise ValueError("باركود الوحدة لا يمكن أن يكون نفس باركود الحبة")
            conn.execute("INSERT INTO product_units(product_id, name, factor, barcode, sale_price) VALUES (?, ?, ?, ?, ?)",
                         (product_id, name, factor, barcode, price))


def unit_choices(product_id):
    """كل وحدات البيع للمنتج بما فيها الأساسية: [(الاسم، المعامل، السعر، الباركود)]"""
    p = get_product(product_id)
    out = [{"name": p["unit"] or "قطعة", "factor": 1.0, "sale_price": p["sale_price"], "barcode": p["barcode"]}]
    out += [{"name": u["name"], "factor": u["factor"], "sale_price": u["sale_price"], "barcode": u["barcode"]}
            for u in get_units(product_id)]
    return out


# ---------------- الصلاحية والدفعات ----------------

def get_batches(product_id, include_empty=False):
    sql = "SELECT * FROM product_batches WHERE product_id=?"
    if not include_empty:
        sql += " AND remaining > 0"
    return db.query(sql + " ORDER BY expiry_date, id", (product_id,))


def expiring_batches(days=None):
    """الدفعات المنتهية أو التي ستنتهي خلال عدد الأيام المحدد (افتراضياً من الإعدادات)"""
    from core import settings
    if days is None:
        days = int(settings.get_float("expiry_alert_days", 30))
    return db.query("""
        SELECT b.*, p.name, p.unit, p.cost_price, p.category, b.remaining * p.cost_price AS value,
               CAST(julianday(b.expiry_date) - julianday(date('now','localtime')) AS INTEGER) AS days_left
        FROM product_batches b JOIN products p ON p.id=b.product_id
        WHERE b.remaining > 0 AND p.is_active=1 AND date(b.expiry_date) <= date('now','localtime', ?)
        ORDER BY b.expiry_date""", (f"+{int(days)} days",))


def expiry_status(product_id):
    """أقرب تاريخ انتهاء لمنتج (للتنبيه في نقطة البيع): (التاريخ، الأيام المتبقية) أو None"""
    r = db.query_one("""SELECT expiry_date, CAST(julianday(expiry_date) - julianday(date('now','localtime')) AS INTEGER) AS d
                        FROM product_batches WHERE product_id=? AND remaining > 0 ORDER BY expiry_date LIMIT 1""",
                     (product_id,))
    return (r["expiry_date"], r["d"]) if r else None


def write_off_batch(batch_id, reason="إتلاف - منتهي الصلاحية"):
    """إتلاف كامل المتبقي من دفعة (يخصم من المخزون ويُسجل كخسارة)"""
    with db.tx() as conn:
        b = conn.execute("SELECT * FROM product_batches WHERE id=?", (batch_id,)).fetchone()
        if not b or b["remaining"] <= 0:
            raise ValueError("الدفعة غير موجودة أو فارغة")
        _move_stock(conn, b["product_id"], -b["remaining"], f"{reason} (دفعة {b['expiry_date']})", batch_id=batch_id,
                    loss=True)
        audit.log("إتلاف دفعة", f"منتج #{b['product_id']} كمية {b['remaining']} صلاحية {b['expiry_date']}", conn)
        return b["remaining"]


def next_internal_barcode(product_id=None):
    if product_id is None:
        product_id = (db.scalar("SELECT MAX(id) FROM products") or 0) + 1
    return internal_barcode(product_id)


def get_low_stock_products():
    return db.query("SELECT * FROM products WHERE is_active=1 AND is_service=0 AND quantity <= min_quantity "
                    "ORDER BY quantity ASC")


def service_product(name, price=0.0):
    """صنف خدمة بلا مخزون (مثل رسوم التوصيل): يُنشأ أول مرة ويُعاد استخدامه"""
    row = db.query_one("SELECT id FROM products WHERE name=? AND is_service=1 AND is_active=1", (name,))
    if row:
        return row["id"]
    pid = add_product(name, None, "خدمات", 0, price, 0, 0, "خدمة")
    with db.tx() as conn:
        conn.execute("UPDATE products SET is_service=1 WHERE id=?", (pid,))
    return pid


def stock_movements(product_id, limit=500):
    return db.query("""SELECT m.*, u.username FROM stock_movements m LEFT JOIN users u ON u.id=m.user_id
                       WHERE product_id=? ORDER BY m.id DESC LIMIT ?""", (product_id, limit))


def inventory_value():
    row = db.query_one("""SELECT COUNT(*) AS items,
                                 COALESCE(SUM(CASE WHEN quantity>0 THEN quantity*cost_price END),0) AS cost_value,
                                 COALESCE(SUM(CASE WHEN quantity>0 THEN quantity*sale_price END),0) AS sale_value
                          FROM products WHERE is_active=1""")
    return dict(row)


# ---------------- استيراد وتصدير CSV (يفتح في Excel) ----------------

CSV_HEADERS = ["الاسم", "الباركود", "الفئة", "الوحدة", "سعر التكلفة", "سعر البيع", "الكمية", "الحد الأدنى", "رمز الميزان",
               "سعر الجملة"]


def export_csv(path):
    rows = get_all_products()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        for p in rows:
            w.writerow([p["name"], p["barcode"] or "", p["category"] or "", p["unit"] or "", p["cost_price"],
                        p["sale_price"], p["quantity"], p["min_quantity"], p["plu_code"] or "", p["wholesale_price"] or ""])
    return len(rows)


def import_csv(path):
    """استيراد/تحديث المنتجات: إذا وُجد الباركود يُحدَّث السعر، وإلا يُضاف منتج جديد"""
    from core.utils import to_float
    added, updated, errors = 0, 0, []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for i, row in enumerate(reader, start=2):
            if not row or not any(c.strip() for c in row):
                continue
            row = (row + [""] * 10)[:10]
            name, barcode, category, unit, cost, price, q, minq, plu, wholesale = [c.strip() for c in row]
            try:
                existing = get_product_by_barcode(barcode) if barcode else None
                if existing:
                    update_product(existing["id"], name or existing["name"], barcode, category or existing["category"],
                                   to_float(cost, existing["cost_price"]), to_float(price, existing["sale_price"]),
                                   to_float(minq, existing["min_quantity"]), unit or existing["unit"],
                                   plu or existing["plu_code"], existing["is_weighted"], existing["is_favorite"],
                                   to_float(wholesale, existing["wholesale_price"]) if wholesale else None)
                    updated += 1
                else:
                    add_product(name, barcode, category, to_float(cost), to_float(price), to_float(q),
                                to_float(minq), unit or "قطعة", plu or None, is_weighted=(unit in ("كغم", "غرام")),
                                wholesale_price=to_float(wholesale, 0))
                    added += 1
            except Exception as e:
                errors.append(f"سطر {i}: {e}")
    return added, updated, errors


def price_for(product, customer=None):
    """سعر بيع الحبة حسب مستوى سعر العميل (جملة أو مفرق)"""
    if customer is not None and _level(customer) == "wholesale" and (product["wholesale_price"] or 0) > 0:
        return product["wholesale_price"]
    return product["sale_price"]


def _level(customer):
    try:
        return customer["price_level"] or "retail"
    except (KeyError, IndexError, TypeError):
        return "retail"


def all_units():
    """كل وحدات البيع (للنسخة المحلية في وضع عدم الاتصال)"""
    return [dict(r) for r in db.query("SELECT * FROM product_units")]
