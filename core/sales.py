# -*- coding: utf-8 -*-
"""
المبيعات: الفواتير، الدفع المختلط/الآجل، المرتجعات، الفواتير المعلّقة.

قواعد محاسبية مطبّقة:
- الإجمالي = المجموع - الخصم (+ الضريبة إن كانت الأسعار غير شاملة لها).
- الدفع يُقسَّم: نقدي + بطاقة + آجل = الإجمالي بالضبط. الجزء الآجل يُسجَّل ديناً على العميل.
- الربح = (صافي المبيعات بدون ضريبة) - تكلفة البضاعة المباعة، أي أن الخصم يُطرح من الربح.
- المرتجع يعيد الكمية للمخزون ويُرجع المبلغ نقداً أو يخصمه من دين العميل.
"""

import json
import math

from core import db, auth, audit, settings, context, loyalty, promotions, license
from core.products import _move_stock
from core.utils import money, qty, fmt_qty, unit_cost

METHOD_CASH = "نقدي"
METHOD_CARD = "بطاقة"
METHOD_CREDIT = "آجل"
METHOD_MIXED = "مختلط"

REFUND_CASH = "نقدي"
REFUND_DEBT = "خصم من الدين"


class SaleError(ValueError):
    pass


def compute_totals(cart, discount=0.0):
    """حساب المجموع والخصم والضريبة والإجمالي لسلة (يُستخدم في الواجهة وعند الحفظ)"""
    subtotal = money(sum(money(i["quantity"] * i["unit_price"]) for i in cart))
    discount = money(min(max(discount or 0, 0), subtotal))
    net = money(subtotal - discount)
    tax = 0.0
    total = net
    if settings.get_bool("vat_enabled"):
        rate = settings.get_float("vat_rate", 0)
        if settings.get_bool("prices_include_vat"):
            tax = money(net * rate / (100 + rate))
        else:
            tax = money(net * rate / 100)
            total = money(net + tax)
    return {"subtotal": subtotal, "discount": discount, "tax": tax, "total": total}


def payment_label(cash, card, credit, wallet=0.0, wallet_name=""):
    used = [m for m, v in ((METHOD_CASH, cash), (METHOD_CARD, card), (METHOD_CREDIT, credit),
                           (wallet_name or "محفظة إلكترونية", wallet)) if v > 0.004]
    if len(used) == 1:
        return used[0]
    if not used:
        return METHOD_CASH
    return METHOD_MIXED


def _customer_balance(conn, customer_id):
    return conn.execute("SELECT COALESCE(SUM(amount),0) FROM customer_transactions WHERE customer_id=?",
                        (customer_id,)).fetchone()[0]


def cart_discounts(cart, manual_discount=0.0, points=0.0):
    """كل خصومات السلة: اليدوي + العروض التلقائية + قيمة نقاط الولاء المستبدلة"""
    promo = promotions.apply(cart)
    points_value = loyalty.value_of(points) if points else 0.0
    manual = money(max(manual_discount or 0, 0))
    return {"manual": manual, "promo": promo["total"], "promo_lines": promo["lines"], "points_value": points_value,
            "total": money(manual + promo["total"] + points_value)}


def create_sale(cart, discount=0.0, customer_id=None, cash_amount=None, card_amount=0.0, credit_amount=0.0,
                cash_received=None, note="", shift_id=None, allow_over_limit=False, points_redeemed=0.0,
                offline=None, card_ref="", wallet_amount=0.0, wallet_name="", wallet_ref="", sale_ref=None):
    """
    cart: قائمة dict: product_id, product_name, quantity, unit_price
          (اختياري) factor, unit_name للبيع بوحدة أكبر مثل الكرتونة
    discount: الخصم اليدوي فقط؛ خصم العروض وقيمة نقاط الولاء تُضاف تلقائياً.
    إذا لم يُحدد cash_amount يُعتبر الباقي كله نقداً.
    يرجع dict فيه رقم الفاتورة ومعرّفها والإجماليات.
    """
    if not cart:
        raise SaleError("السلة فارغة")
    # offline: فاتورة بيعت فعلاً على جهاز فرعي أثناء انقطاع الشبكة وتُرحَّل الآن
    # {"ref": معرّف فريد، "created_at": وقت البيع، "promo_discount": خصم العروض كما حُسب وقتها}
    # sale_ref: معرّف فريد يولّده جهاز الكاشير لكل فاتورة. إن حُفظت الفاتورة وانقطع الاتصال قبل وصول الرد،
    # ثم أُعيد إرسالها (أو رُحّلت من طابور عدم الاتصال بنفس المعرّف) فلا تُسجَّل مرتين.
    ref = (offline or {}).get("ref") or sale_ref
    if ref:
        existing = db.query_one("SELECT * FROM invoices WHERE offline_ref=?", (ref,))
        if existing:   # رُحّلت سابقاً (انقطع الاتصال قبل وصول الرد): لا نكررها
            return {"invoice_id": existing["id"], "invoice_number": existing["invoice_number"],
                    "total": existing["total"], "duplicate": True}
    try:
        license.require_active()   # حتى الفواتير المرحّلة: تبقى في الانتظار حتى التفعيل (لا تجاوز للترخيص)
    except license.LicenseError as e:
        raise SaleError(str(e))
    for item in cart:
        if item["quantity"] <= 0:
            raise SaleError(f"كمية غير صحيحة للمنتج {item['product_name']}")
        if item["unit_price"] < 0:
            raise SaleError(f"سعر غير صحيح للمنتج {item['product_name']}")

    points_redeemed = float(points_redeemed or 0)
    if offline:
        promo = money(offline.get("promo_discount") or 0)
        disc = {"manual": money(discount or 0), "promo": promo, "promo_lines": [], "points_value": 0.0,
                "total": money(money(discount or 0) + promo)}
    else:
        disc = cart_discounts(cart, discount, points_redeemed)
    subtotal = compute_totals(cart)["subtotal"]
    if points_redeemed and disc["total"] > subtotal + 0.009:
        raise SaleError("قيمة النقاط المستبدلة أكبر من قيمة الفاتورة بعد الخصم")
    t = compute_totals(cart, disc["total"])
    total = t["total"]
    card_amount = money(card_amount or 0)
    credit_amount = money(credit_amount or 0)
    wallet_amount = money(wallet_amount or 0)
    wallet_name = (wallet_name or "").strip()
    wallet_bank = 0
    if wallet_amount:
        if not wallet_name:
            raise SaleError("اختر طريقة الدفع الإلكتروني")
        from core import wallets
        w = wallets.get(wallet_name)
        wallet_bank = 1 if w and w["dest"] == wallets.DEST_BANK else 0
        if settings.get_bool("wallet_ref_required") and not (wallet_ref or "").strip() and not offline:
            raise SaleError("اكتب رقم العملية من إشعار الدفع الإلكتروني")
    else:
        wallet_name, wallet_ref = "", ""
    if cash_amount is None:
        cash_amount = money(total - card_amount - credit_amount - wallet_amount)
    cash_amount = money(cash_amount)
    if min(cash_amount, card_amount, credit_amount, wallet_amount) < 0:
        raise SaleError("مبالغ الدفع لا يمكن أن تكون سالبة")
    if abs(money(cash_amount + card_amount + credit_amount + wallet_amount) - total) > 0.009:
        raise SaleError("مجموع المدفوع لا يساوي إجمالي الفاتورة")
    if credit_amount > 0 and not customer_id:
        raise SaleError("البيع الآجل يتطلب اختيار عميل")
    if cash_received is None or cash_received < cash_amount:
        cash_received = cash_amount
    change = money(cash_received - cash_amount)

    user_id = auth.current_user_id()
    if cash_amount > 0 and not offline and not shift_id:
        from core import shifts
        shift_id = shifts.current_shift_id()      # نقطة البيع تفتح الوردية بنفسها قبل البيع
    allow_negative = settings.get_bool("allow_negative_stock") or bool(offline)

    with db.tx() as conn:
        if ref:
            dup = conn.execute("SELECT id, invoice_number, total FROM invoices WHERE offline_ref=?", (ref,)).fetchone()
            if dup:
                return {"invoice_id": dup["id"], "invoice_number": dup["invoice_number"], "total": dup["total"],
                        "duplicate": True}
        # ---- التحقق من المخزون (مجمّع لكل منتج) ----
        needed = {}
        for item in cart:
            needed[item["product_id"]] = needed.get(item["product_id"], 0) + item["quantity"] * item.get("factor", 1)
        products = {}
        short = []
        for pid, q in needed.items():
            p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not p:
                raise SaleError("منتج غير موجود")
            products[pid] = p
            if not allow_negative and not p["is_service"] and p["quantity"] + 1e-9 < q:
                short.append(f"{p['name']} (المتوفر {fmt_qty(p['quantity'])})")
        if short:
            raise SaleError("الكمية غير كافية في المخزون:\n" + "\n".join(short))
        if settings.get_bool("block_expired_sale") and not offline:
            expired = []
            for pid in needed:
                r = conn.execute("""SELECT MIN(expiry_date) FROM product_batches WHERE product_id=? AND remaining > 0""",
                                 (pid,)).fetchone()[0]
                if r and r < db.today():
                    expired.append(products[pid]["name"])
            if expired:
                raise SaleError("يوجد في المخزون دفعات منتهية الصلاحية من:\n" + "\n".join(expired) +
                                "\nقم بإتلافها أولاً من شاشة الصلاحية.")

        # ---- حد الدين للعميل ----
        if credit_amount > 0:
            cust = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not cust:
                raise SaleError("العميل غير موجود")
            limit = cust["credit_limit"] or 0
            if limit > 0 and not allow_over_limit:
                bal = _customer_balance(conn, customer_id)
                if bal + credit_amount > limit + 0.009:
                    raise SaleError(f"تجاوز حد الدين للعميل {cust['name']}: الرصيد الحالي {money(bal)} والحد {money(limit)}")

        if points_redeemed:
            try:
                loyalty._check_redeem(conn, customer_id, points_redeemed)
            except ValueError as e:
                raise SaleError(str(e))
        points_earned = loyalty.points_for(total) if customer_id else 0.0
        if disc["promo_lines"]:
            promo_note = "عروض: " + "، ".join(l["name"] for l in disc["promo_lines"])
            note = f"{note} | {promo_note}" if note else promo_note

        number = db.next_number(conn, "invoice", "INV")
        created = (offline or {}).get("created_at") or db.now()
        if offline:
            note = (note + " | " if note else "") + "بيع أثناء انقطاع الشبكة"
        cost_total = money(sum(products[i["product_id"]]["cost_price"] * i["quantity"] * i.get("factor", 1) for i in cart))
        cur = conn.execute("""
            INSERT INTO invoices (invoice_number, customer_id, subtotal, discount, tax, total, cost_total, paid,
                                  payment_method, cash_amount, card_amount, credit_amount, cash_received, change_given,
                                  status, note, user_id, shift_id, terminal, promo_discount, points_redeemed,
                                  points_value, points_earned, created_at, wallet_amount, wallet_name, wallet_ref,
                                  wallet_bank)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (number, customer_id, t["subtotal"], t["discount"], t["tax"], total, cost_total,
              money(cash_amount + card_amount + wallet_amount),
              payment_label(cash_amount, card_amount, credit_amount, wallet_amount, wallet_name),
              cash_amount, card_amount, credit_amount, money(cash_received), change, note, user_id, shift_id,
              context.terminal(), disc["promo"], points_redeemed, disc["points_value"], points_earned, created,
              wallet_amount, wallet_name or None, (wallet_ref or "").strip() or None, wallet_bank))
        invoice_id = cur.lastrowid
        if ref:
            conn.execute("UPDATE invoices SET offline_ref=? WHERE id=?", (ref, invoice_id))
        if card_ref:
            conn.execute("UPDATE invoices SET card_ref=? WHERE id=?", (str(card_ref)[:120], invoice_id))
        if points_redeemed:
            loyalty._record(conn, customer_id, -points_redeemed, invoice_id, f"استبدال في الفاتورة {number}", user_id)
        if points_earned:
            loyalty._record(conn, customer_id, points_earned, invoice_id, f"نقاط الفاتورة {number}", user_id)

        for item in cart:
            p = products[item["product_id"]]
            q = qty(item["quantity"])
            factor = float(item.get("factor", 1) or 1)
            conn.execute("""
                INSERT INTO invoice_items (invoice_id, product_id, product_name, quantity, unit_price, cost_price, total,
                                           unit_name, factor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_id, p["id"], item.get("product_name") or p["name"], q, money(item["unit_price"]),
                  unit_cost(p["cost_price"] * factor), money(q * item["unit_price"]),
                  item.get("unit_name") or p["unit"], factor))
            if not p["is_service"]:
                _move_stock(conn, p["id"], -qty(q * factor), f"بيع - فاتورة {number}")
            list_price = item.get("list_price", p["sale_price"] if factor == 1 else item["unit_price"])
            if money(item["unit_price"]) != money(list_price):
                audit.log("تغيير سعر في البيع", f"{number}: {p['name']} {list_price} ← {item['unit_price']}", conn)

        if credit_amount > 0:
            conn.execute("""INSERT INTO customer_transactions (customer_id, type, amount, invoice_id, note, user_id, shift_id, created_at)
                            VALUES (?, 'sale', ?, ?, ?, ?, ?, ?)""",
                         (customer_id, credit_amount, invoice_id, f"فاتورة {number}", user_id, shift_id, created))

    return {"invoice_id": invoice_id, "invoice_number": number, "change": change, **t,
            "cash_amount": cash_amount, "card_amount": card_amount, "credit_amount": credit_amount,
            "wallet_amount": wallet_amount, "wallet_name": wallet_name,
            "promo_discount": disc["promo"], "points_value": disc["points_value"], "points_earned": points_earned}


def import_offline_sale(payload):
    """ترحيل فاتورة بيعت أثناء انقطاع الشبكة (نقدي/بطاقة/محفظة). آمن للتكرار: نفس الفاتورة لا تُسجل مرتين"""
    return create_sale(payload["cart"], discount=payload.get("discount", 0), cash_amount=payload["cash_amount"],
                       card_amount=payload.get("card_amount", 0), cash_received=payload.get("cash_received"),
                       wallet_amount=payload.get("wallet_amount", 0), wallet_name=payload.get("wallet_name", ""),
                       wallet_ref=payload.get("wallet_ref", ""), card_ref=payload.get("card_ref", ""),
                       shift_id=payload.get("shift_id"),
                       offline={"ref": payload["ref"], "created_at": payload["created_at"],
                                "promo_discount": payload.get("promo_discount", 0)})


# ---------------------------------------------------------------------------
# المرتجعات
# ---------------------------------------------------------------------------

def returnable_items(invoice_id):
    return db.query("""SELECT *, (quantity - returned_qty) AS remaining FROM invoice_items
                       WHERE invoice_id=? ORDER BY id""", (invoice_id,))


def create_return(invoice_id, items, refund_method=REFUND_CASH, reason="", shift_id=None):
    """
    items: قائمة dict: invoice_item_id, quantity
    المبلغ المُرجَع يُحسب بنفس نسبة الخصم/الضريبة في الفاتورة الأصلية.
    """
    items = [i for i in items if i["quantity"] > 0]
    if not items:
        raise SaleError("اختر كمية للإرجاع")
    user_id = auth.current_user_id()
    if refund_method == REFUND_CASH:
        from core import shifts
        try:
            shift_id = shifts.cash_shift(shift_id)
        except ValueError as e:
            raise SaleError(str(e))
    with db.tx() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise SaleError("الفاتورة غير موجودة")
        if refund_method == REFUND_DEBT and not inv["customer_id"]:
            raise SaleError("لا يمكن الخصم من الدين لفاتورة بدون عميل")
        ratio = (inv["total"] / inv["subtotal"]) if inv["subtotal"] else 0
        tax_ratio = (inv["tax"] / inv["total"]) if inv["total"] else 0

        lines = []
        for it in items:
            row = conn.execute("SELECT * FROM invoice_items WHERE id=? AND invoice_id=?",
                               (it["invoice_item_id"], invoice_id)).fetchone()
            if not row:
                raise SaleError("بند غير موجود في الفاتورة")
            remaining = qty(row["quantity"] - row["returned_qty"])
            q = qty(it["quantity"])
            if q > remaining + 1e-9:
                raise SaleError(f"الكمية المرتجعة من {row['product_name']} أكبر من المتبقي ({fmt_qty(remaining)})")
            lines.append((row, q, money(row["unit_price"] * q * ratio)))

        total = money(sum(l[2] for l in lines))
        max_refund = money(inv["total"] - inv["returned_total"])
        total = min(total, max_refund)
        if refund_method == REFUND_CASH and inv["credit_amount"] > 0 and inv["customer_id"]:
            # فاتورة بيعت آجلاً: لا يُرد نقداً أكثر مما دفعه الزبون فعلاً ما دام عليه دين
            paid = money(inv["cash_amount"] + inv["card_amount"] + inv["wallet_amount"])
            refunded = conn.execute("""SELECT COALESCE(SUM(total),0) FROM returns WHERE invoice_id=? AND refund_method=?""",
                                    (invoice_id, REFUND_CASH)).fetchone()[0]
            if total > money(paid - refunded) + 0.009 and _customer_balance(conn, inv["customer_id"]) > 0.009:
                raise SaleError("هذه الفاتورة بيعت آجلاً وما زال على العميل دين، فلا يُرد له نقداً أكثر مما دفعه "
                                f"({money(paid - refunded)}). اختر «{REFUND_DEBT}».")
        tax = money(total * tax_ratio)
        cost_total = money(sum(l[0]["cost_price"] * l[1] for l in lines))

        number = db.next_number(conn, "return", "RET")
        created = db.now()
        cur = conn.execute("""INSERT INTO returns (return_number, invoice_id, total, tax, cost_total, refund_method, reason,
                                                   user_id, shift_id, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (number, invoice_id, total, tax, cost_total, refund_method, reason, user_id, shift_id, created))
        ret_id = cur.lastrowid
        for row, q, line_total in lines:
            factor = row["factor"] or 1
            conn.execute("""INSERT INTO return_items (return_id, invoice_item_id, product_id, product_name, quantity,
                                                      unit_price, cost_price, total, factor)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (ret_id, row["id"], row["product_id"], row["product_name"], q, row["unit_price"],
                          row["cost_price"], line_total, factor))
            conn.execute("UPDATE invoice_items SET returned_qty = ROUND(returned_qty + ?, 3) WHERE id=?", (q, row["id"]))
            svc = conn.execute("SELECT is_service FROM products WHERE id=?", (row["product_id"],)).fetchone()
            if not (svc and svc["is_service"]):
                _move_stock(conn, row["product_id"], qty(q * factor), f"مرتجع {number} من فاتورة {inv['invoice_number']}")

        new_returned = money(inv["returned_total"] + total)
        left = conn.execute("SELECT COALESCE(SUM(quantity - returned_qty),0) FROM invoice_items WHERE invoice_id=?",
                            (invoice_id,)).fetchone()[0]
        status = "returned" if left <= 1e-9 else "partially_returned"
        conn.execute("UPDATE invoices SET returned_total=?, status=? WHERE id=?", (new_returned, status, invoice_id))

        if refund_method == REFUND_DEBT:
            conn.execute("""INSERT INTO customer_transactions (customer_id, type, amount, invoice_id, note, user_id, shift_id, created_at)
                            VALUES (?, 'return', ?, ?, ?, ?, ?, ?)""",
                         (inv["customer_id"], -total, invoice_id, f"مرتجع {number}", user_id, shift_id, created))
        if inv["customer_id"] and inv["points_earned"] and inv["total"]:
            lost = float(math.floor(inv["points_earned"] * total / inv["total"] + 0.5))
            loyalty._record(conn, inv["customer_id"], -lost, invoice_id, f"إلغاء نقاط بسبب المرتجع {number}", user_id)
        audit.log("مرتجع", f"{number} من {inv['invoice_number']} بقيمة {total} ({refund_method})", conn)

    return {"return_id": ret_id, "return_number": number, "total": total}


# ---------------------------------------------------------------------------
# الاستعلامات
# ---------------------------------------------------------------------------

STATUS_LABELS = {"completed": "مكتملة", "partially_returned": "مرتجع جزئي", "returned": "مرتجعة بالكامل"}


def get_invoices(date_from=None, date_to=None, search=None, customer_id=None, limit=2000):
    sql = """SELECT i.*, c.name AS customer_name, u.username AS cashier
             FROM invoices i LEFT JOIN customers c ON c.id=i.customer_id LEFT JOIN users u ON u.id=i.user_id"""
    cond, params = [], []
    if date_from and date_to:
        cond.append("date(i.created_at) BETWEEN date(?) AND date(?)")
        params += [date_from, date_to]
    if search:
        cond.append("(i.invoice_number LIKE ? OR c.name LIKE ? OR c.phone LIKE ?)")
        params += [f"%{search}%"] * 3
    if customer_id:
        cond.append("i.customer_id=?")
        params.append(customer_id)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY i.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


def get_invoice(invoice_id):
    return db.query_one("""SELECT i.*, c.name AS customer_name, c.phone AS customer_phone, u.full_name AS cashier_name,
                                  u.username AS cashier
                           FROM invoices i LEFT JOIN customers c ON c.id=i.customer_id
                           LEFT JOIN users u ON u.id=i.user_id WHERE i.id=?""", (invoice_id,))


def get_invoice_by_number(number):
    return db.query_one("SELECT * FROM invoices WHERE invoice_number=?", (number.strip(),))


def get_invoice_items(invoice_id):
    return db.query("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id", (invoice_id,))


def get_return(return_id):
    return db.query_one("SELECT r.*, i.invoice_number FROM returns r JOIN invoices i ON i.id=r.invoice_id WHERE r.id=?",
                        (return_id,))


def get_return_items(return_id):
    return db.query("SELECT * FROM return_items WHERE return_id=?", (return_id,))


def get_returns(invoice_id=None, date_from=None, date_to=None):
    sql = """SELECT r.*, i.invoice_number, u.username FROM returns r JOIN invoices i ON i.id=r.invoice_id
             LEFT JOIN users u ON u.id=r.user_id"""
    cond, params = [], []
    if invoice_id:
        cond.append("r.invoice_id=?")
        params.append(invoice_id)
    if date_from and date_to:
        cond.append("date(r.created_at) BETWEEN date(?) AND date(?)")
        params += [date_from, date_to]
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return db.query(sql + " ORDER BY r.id DESC", params)


# ---------------------------------------------------------------------------
# الفواتير المعلّقة (زبون نسي غرضاً أو سيعود بعد قليل)
# ---------------------------------------------------------------------------

def hold_cart(cart, discount=0, customer_id=None, label=""):
    data = json.dumps({"cart": cart, "discount": discount, "customer_id": customer_id}, ensure_ascii=False)
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO held_carts(label, data, user_id, terminal, created_at) VALUES (?, ?, ?, ?, ?)",
                           (label, data, auth.current_user_id(), context.terminal(), db.now()))
        return cur.lastrowid


def list_held_carts():
    rows = db.query("SELECT * FROM held_carts ORDER BY id")
    out = []
    for r in rows:
        d = json.loads(r["data"])
        out.append({"id": r["id"], "label": r["label"], "created_at": r["created_at"], "terminal": r["terminal"],
                    "items": len(d["cart"]), "total": compute_totals(d["cart"], d.get("discount", 0))["total"]})
    return out


def take_held_cart(held_id):
    with db.tx() as conn:
        r = conn.execute("SELECT data FROM held_carts WHERE id=?", (held_id,)).fetchone()
        if not r:
            return None
        conn.execute("DELETE FROM held_carts WHERE id=?", (held_id,))
    return json.loads(r["data"])
