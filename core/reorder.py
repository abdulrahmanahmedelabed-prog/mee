# -*- coding: utf-8 -*-
"""
الطلبيات الذكية: ماذا أطلب من كل مورد، وبأي كمية؟

الحساب بسيط ومفهوم لصاحب المحل:
  معدل البيع اليومي = ما بيع من الصنف في آخر N يوماً ÷ N
  الكمية المقترحة = (معدل البيع × أيام التغطية) + الحد الأدنى − الموجود الآن
ثم تُقرَّب للكرتونة إن كان للصنف وحدة كرتونة، وتُجمَّع حسب آخر مورد اشترينا منه الصنف،
ويمكن إرسالها للمورد عبر واتساب مباشرة.
"""

import math
from datetime import date, timedelta

from core import db, settings
from core.utils import money, qty, fmt_qty


def suggestions(days=30, cover_days=14, include_all_low=True):
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    sold = {r["product_id"]: r["q"] for r in db.query("""
        SELECT ii.product_id, SUM((ii.quantity - ii.returned_qty) * ii.factor) AS q
        FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
        WHERE i.created_at >= date(?) GROUP BY ii.product_id""", (since,))}
    last_sup = {r["product_id"]: r for r in db.query("""
        SELECT pi.product_id, p.supplier_id, s.name AS supplier_name, s.phone AS supplier_phone,
               pi.unit_cost / COALESCE(NULLIF(pi.factor,0),1) AS base_cost
        FROM purchase_items pi JOIN purchases p ON p.id=pi.purchase_id LEFT JOIN suppliers s ON s.id=p.supplier_id
        WHERE pi.id IN (SELECT MAX(pi2.id) FROM purchase_items pi2 JOIN purchases p2 ON p2.id=pi2.purchase_id
                        WHERE p2.supplier_id IS NOT NULL GROUP BY pi2.product_id)""")}
    cartons = {}
    for r in db.query("SELECT product_id, name, factor FROM product_units ORDER BY factor"):
        cartons[r["product_id"]] = (r["name"], r["factor"])  # أكبر وحدة (آخر واحدة بالترتيب)

    out = []
    for p in db.query("SELECT * FROM products WHERE is_active=1 AND is_weighted=0 AND is_service=0"):
        q_sold = max(sold.get(p["id"], 0) or 0, 0)
        rate = q_sold / days
        stock = p["quantity"]
        target = rate * cover_days + (p["min_quantity"] or 0)
        need = target - stock
        low = stock <= (p["min_quantity"] or 0)
        if need <= 0.0001 or (rate == 0 and not (include_all_low and low and p["min_quantity"])):
            continue
        need = math.ceil(need - 1e-9)
        unit_name, factor = cartons.get(p["id"], (p["unit"] or "قطعة", 1))
        order_units = math.ceil(need / factor) if factor > 1 else need
        order_base = order_units * factor
        sup = last_sup.get(p["id"])
        cost = sup["base_cost"] if sup else p["cost_price"]
        out.append({
            "product_id": p["id"], "name": p["name"], "stock": qty(stock), "min_quantity": p["min_quantity"],
            "sold": qty(q_sold), "daily_rate": round(rate, 2),
            "days_left": (round(stock / rate, 1) if rate > 0 else None),
            "order_units": order_units, "unit_name": unit_name, "factor": factor, "order_base": qty(order_base),
            "est_cost": money(order_base * (cost or 0)),
            "supplier_id": sup["supplier_id"] if sup else None,
            "supplier_name": (sup["supplier_name"] if sup else None) or "بدون مورد محدد",
            "supplier_phone": sup["supplier_phone"] if sup else None,
        })
    out.sort(key=lambda r: (r["supplier_name"], r["days_left"] if r["days_left"] is not None else -1))
    return out


def order_message(items, supplier_name=""):
    shop = settings.get("shop_name")
    lines = [f"السلام عليكم {supplier_name}".strip(), f"طلبية جديدة من {shop}:", ""]
    for i, it in enumerate(items, 1):
        unit = it["unit_name"] if it["factor"] == 1 else f"{it['unit_name']} ({fmt_qty(it['factor'])})"
        lines.append(f"{i}. {it['name']} — {fmt_qty(it['order_units'])} {unit}")
    lines += ["", "يرجى تأكيد الطلبية وموعد التوصيل. شكراً لكم 🌷"]
    return "\n".join(lines)
