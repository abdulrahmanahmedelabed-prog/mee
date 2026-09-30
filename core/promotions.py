# -*- coding: utf-8 -*-
"""
العروض التلقائية في نقطة البيع (لا يحتاج الكاشير أن يتذكر أي عرض):

- buy_get : اشترِ X واحصل على Y مجاناً من نفس الصنف (مثال: اشترِ 2 واحصل على 1).
- bundle  : N قطع بسعر ثابت (مثال: 3 علب تونة بـ 10 شيكل).
- percent : خصم نسبة % على صنف أو على فئة كاملة لفترة محددة (مثال: 15% على المنظفات).

الخصم يُحسب على السلة كاملة ويُضاف لخصم الفاتورة، فتبقى المرتجعات والأرباح والضريبة صحيحة تلقائياً.
"""

import math

from core import db, audit, settings
from core.utils import money

TYPES = {"buy_get": "اشترِ واحصل مجاناً", "bundle": "كمية بسعر ثابت", "percent": "خصم نسبة %"}


def add_promotion(name, type, product_id=None, category=None, buy_qty=0, get_qty=0, bundle_qty=0, bundle_price=0,
                  percent=0, start_date=None, end_date=None):
    data = _validate(name, type, product_id, category, buy_qty, get_qty, bundle_qty, bundle_price, percent)
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO promotions(name, type, product_id, category, buy_qty, get_qty, bundle_qty,
                                                     bundle_price, percent, start_date, end_date, is_active, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                           data + (start_date or None, end_date or None, db.now()))
        audit.log("إضافة عرض", data[0], conn)
        return cur.lastrowid


def update_promotion(promo_id, name, type, product_id=None, category=None, buy_qty=0, get_qty=0, bundle_qty=0,
                     bundle_price=0, percent=0, start_date=None, end_date=None, is_active=True):
    data = _validate(name, type, product_id, category, buy_qty, get_qty, bundle_qty, bundle_price, percent)
    with db.tx() as conn:
        conn.execute("""UPDATE promotions SET name=?, type=?, product_id=?, category=?, buy_qty=?, get_qty=?, bundle_qty=?,
                        bundle_price=?, percent=?, start_date=?, end_date=?, is_active=? WHERE id=?""",
                     data + (start_date or None, end_date or None, 1 if is_active else 0, promo_id))
        audit.log("تعديل عرض", data[0], conn)


def _validate(name, type, product_id, category, buy_qty, get_qty, bundle_qty, bundle_price, percent):
    name = (name or "").strip()
    if not name:
        raise ValueError("اكتب اسماً للعرض يظهر للزبون، مثل: اشترِ 2 واحصل على 1")
    if type not in TYPES:
        raise ValueError("نوع العرض غير معروف")
    if type in ("buy_get", "bundle") and not product_id:
        raise ValueError("اختر الصنف المشمول بالعرض")
    if type == "percent" and not product_id and not (category or "").strip():
        raise ValueError("اختر صنفاً أو فئة للخصم")
    if type == "buy_get" and (buy_qty < 1 or get_qty < 1):
        raise ValueError("حدد كمية الشراء والكمية المجانية")
    if type == "bundle" and (bundle_qty < 2 or bundle_price <= 0):
        raise ValueError("حدد عدد القطع (2 أو أكثر) وسعر المجموعة")
    if type == "percent" and not (0 < percent < 100):
        raise ValueError("نسبة الخصم بين 1 و 99")
    return (name, type, product_id or None, (category or "").strip() or None, float(buy_qty or 0), float(get_qty or 0),
            float(bundle_qty or 0), money(bundle_price or 0), float(percent or 0))


def delete_promotion(promo_id):
    with db.tx() as conn:
        conn.execute("UPDATE promotions SET is_active=0 WHERE id=?", (promo_id,))


def list_promotions(active_only=False):
    sql = """SELECT pr.*, p.name AS product_name FROM promotions pr LEFT JOIN products p ON p.id=pr.product_id"""
    if active_only:
        sql += " WHERE pr.is_active=1"
    return db.query(sql + " ORDER BY pr.is_active DESC, pr.id DESC")


def active_promotions(day=None):
    day = day or db.today()
    return db.query("""SELECT * FROM promotions WHERE is_active=1
                       AND (start_date IS NULL OR date(start_date) <= date(?))
                       AND (end_date IS NULL OR date(end_date) >= date(?)) ORDER BY id""", (day, day))


def apply(cart):
    """يحسب خصومات العروض على السلة. يرجع {"total": مبلغ، "lines": [{promo_id, name, amount}]}"""
    if not cart or not settings.get_bool("promotions_enabled"):
        return {"total": 0.0, "lines": []}
    promos = active_promotions()
    if not promos:
        return {"total": 0.0, "lines": []}
    ids = sorted({i["product_id"] for i in cart})
    marks = ",".join("?" * len(ids))
    cats = {r["id"]: r["category"] for r in db.query(f"SELECT id, category FROM products WHERE id IN ({marks})", ids)}
    return compute(cart, promos, cats)


def compute(cart, promos, cats):
    """الحساب نفسه بدون قاعدة بيانات (يُستخدم أيضاً في نقطة البيع أثناء انقطاع الشبكة)"""

    # الكمية بالحبة وأقل سعر حبة لكل منتج (العروض بالقطعة لا تنطبق على الكرتونة)
    single = {}
    for it in cart:
        if float(it.get("factor", 1) or 1) == 1 and it["quantity"] > 0:
            q, price = single.get(it["product_id"], (0.0, None))
            p = float(it["unit_price"])
            single[it["product_id"]] = (q + float(it["quantity"]), p if price is None else min(price, p))

    lines, used = [], set()
    for pr in promos:
        if pr["type"] not in ("buy_get", "bundle"):
            continue
        pid = pr["product_id"]
        if pid in used or pid not in single:
            continue
        q, price = single[pid]
        if pr["type"] == "buy_get":
            groups = math.floor(q / (pr["buy_qty"] + pr["get_qty"]) + 1e-9)
            amount = groups * pr["get_qty"] * price
        else:
            groups = math.floor(q / pr["bundle_qty"] + 1e-9)
            amount = groups * (pr["bundle_qty"] * price - pr["bundle_price"])
        amount = money(amount)
        if amount > 0:
            used.add(pid)
            lines.append({"promo_id": pr["id"], "name": pr["name"], "amount": amount})

    # خصم النسبة: لكل صنف أفضل عرض واحد فقط (لا تُجمع نسبة الصنف مع نسبة فئته)
    percent = [pr for pr in promos if pr["type"] not in ("buy_get", "bundle")]
    by_promo = {}
    for it in cart:
        pid = it["product_id"]
        if pid in used:
            continue
        best = None
        for pr in percent:
            if (pr["product_id"] and pid == pr["product_id"]) or \
                    (not pr["product_id"] and pr["category"] and cats.get(pid) == pr["category"]):
                if best is None or pr["percent"] > best["percent"]:
                    best = pr
        if best:
            by_promo[best["id"]] = by_promo.get(best["id"], 0.0) + it["quantity"] * it["unit_price"] * best["percent"] / 100
    for pr in percent:
        amount = money(by_promo.get(pr["id"], 0.0))
        if amount > 0:
            lines.append({"promo_id": pr["id"], "name": pr["name"], "amount": amount})
    return {"total": money(sum(l["amount"] for l in lines)), "lines": lines}
