# -*- coding: utf-8 -*-
"""
مخطط المواسم: كم تشتري لرمضان والعيدين والعودة للمدارس؟

لكل موسم قادم: نجد نفس الموسم في السنة الماضية (بالتقويم الهجري للمواسم الهجرية)، ونقارن مبيعات كل صنف فيه
بمبيعاته العادية في الأسابيع الأربعة التي سبقته (معامل الموسم)، ثم نقترح الكمية = بيع الموسم الماضي × نمو المحل
، والطلبية الأولى = حاجة أول 10 أيام − الموجود الآن (الطازج يُكمَّل على دفعات خلال الموسم)،
مع تاريخ «اطلب قبل» حتى تصل البضاعة قبل الزحمة.
"""

import math
from datetime import date, timedelta

from core import db, hijri
from core.utils import money, qty

# (المفتاح، الاسم، نوع التقويم، (شهر، يوم)، عدد الأيام، أيقونة)
SEASONS = [
    ("ramadan", "رمضان", "hijri", (9, 1), 30, "🌙"),
    ("eid_fitr", "عيد الفطر", "hijri", (10, 1), 3, "🎉"),
    ("eid_adha", "عيد الأضحى", "hijri", (12, 10), 4, "🐑"),
    ("school", "العودة إلى المدارس", "gregorian", (8, 25), 21, "🎒"),
    ("summer", "الصيف", "gregorian", (6, 15), 75, "☀"),
]
LEAD_DAYS = 10          # اطلب قبل الموسم بعشرة أيام
FIRST_ORDER_DAYS = 10   # الطلبية الأولى تغطي أول 10 أيام (والطازج يُطلب على دفعات خلال الموسم)


def _window(kind, md, length, today):
    """(بداية الموسم القادم أو الحالي، نهايته، بداية نفس الموسم في السنة الماضية)"""
    if kind == "hijri":
        start, hy = hijri.next_occurrence(md[0], md[1], today, span_days=length)
        prev = hijri.to_gregorian(hy - 1, md[0], md[1])
    else:
        start = date(today.year, md[0], md[1])
        if start + timedelta(days=length) <= today:
            start = date(today.year + 1, md[0], md[1])
        prev = date(start.year - 1, md[0], md[1])
    return start, start + timedelta(days=length - 1), prev


def upcoming(today=None):
    today = today or date.fromisoformat(db.today())
    out = []
    for key, name, kind, md, length, icon in SEASONS:
        start, end, prev = _window(kind, md, length, today)
        out.append({"key": key, "name": name, "icon": icon, "start": start.isoformat(), "end": end.isoformat(),
                    "days": length, "days_until": (start - today).days, "in_season": start <= today <= end,
                    "hijri": hijri.fmt(start) if kind == "hijri" else "",
                    "order_by": (start - timedelta(days=LEAD_DAYS)).isoformat(), "last_year_start": prev.isoformat()})
    return sorted(out, key=lambda s: (not s["in_season"], s["days_until"]))


def _sold(a, b):
    return {r["product_id"]: r for r in db.query("""
        SELECT ii.product_id, MAX(ii.product_name) AS name, SUM((ii.quantity - ii.returned_qty) * ii.factor) AS q,
               SUM((ii.quantity - ii.returned_qty) * ii.unit_price) AS t
        FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id
        WHERE date(i.created_at) BETWEEN date(?) AND date(?) AND ii.product_id IS NOT NULL
        GROUP BY ii.product_id""", (a.isoformat(), b.isoformat()))}


def _growth(today):
    """نمو المحل: آخر 90 يوماً مقارنة بنفس الفترة من السنة الماضية (محدود بين −30% و +50%)"""
    a, b = today - timedelta(days=90), today - timedelta(days=1)
    now = db.scalar("SELECT SUM(total) FROM invoices WHERE date(created_at) BETWEEN date(?) AND date(?)",
                    (a.isoformat(), b.isoformat())) or 0
    then = db.scalar("SELECT SUM(total) FROM invoices WHERE date(created_at) BETWEEN date(?) AND date(?)",
                     ((a - timedelta(days=364)).isoformat(), (b - timedelta(days=364)).isoformat())) or 0
    if not then:
        return 0.0
    return max(-0.3, min(0.5, now / then - 1))


def plan(key, today=None, limit=40):
    today = today or date.fromisoformat(db.today())
    season = next(s for s in SEASONS if s[0] == key)
    _, name, kind, md, length, icon = season
    start, end, prev = _window(kind, md, length, today)
    prev_end = prev + timedelta(days=length - 1)
    first = db.scalar("SELECT MIN(date(created_at)) FROM invoices")
    if not first or date.fromisoformat(str(first)) > prev - timedelta(days=28):
        return {"name": name, "icon": icon, "start": start.isoformat(), "end": end.isoformat(),
                "items": [], "enough_data": False,
                "message": f"لا توجد مبيعات مسجّلة من {name} الماضي بعد؛ سيظهر المخطط بعد أول موسم في البرنامج."}
    season_sold = _sold(prev, prev_end)
    base_sold = _sold(prev - timedelta(days=28), prev - timedelta(days=1))
    growth = _growth(today)
    stock = {r["id"]: r for r in db.query("""SELECT id, name, quantity, cost_price, unit FROM products
                                             WHERE is_active=1 AND is_service=0""")}
    items = []
    for pid, r in season_sold.items():
        p = stock.get(pid)
        if not p or (r["q"] or 0) <= 0:
            continue
        s_daily = r["q"] / length
        b_daily = (base_sold[pid]["q"] if pid in base_sold else 0) / 28
        uplift = (s_daily / b_daily) if b_daily > 0 else None
        need = r["q"] * (1 + growth)
        per_day = need / length
        order = max(0, math.ceil(per_day * min(length, FIRST_ORDER_DAYS) - max(p["quantity"], 0)))
        items.append({"product_id": pid, "name": p["name"], "unit": p["unit"] or "", "last_season": qty(r["q"]),
                      "uplift": round(uplift, 2) if uplift else None, "stock": qty(p["quantity"]),
                      "expected": qty(need), "per_day": round(per_day, 1), "order": order, "est_cost": money(order * (p["cost_price"] or 0)),
                      "sales_value": money(r["t"] or 0)})
    # الأهم: ما يرتفع بيعه في الموسم وله وزن في المبيعات
    items.sort(key=lambda x: ((x["uplift"] or 3) >= 1.2, x["sales_value"] * min(x["uplift"] or 3, 3)), reverse=True)
    season_total = sum(r["t"] or 0 for r in season_sold.values())
    base_total = sum(r["t"] or 0 for r in base_sold.values())
    overall = (season_total / length) / (base_total / 28) if base_total else None
    return {"name": name, "icon": icon, "start": start.isoformat(), "end": end.isoformat(),
            "hijri": hijri.fmt(start) if kind == "hijri" else "", "days_until": (start - today).days,
            "order_by": (start - timedelta(days=LEAD_DAYS)).isoformat(),
            "last_year": [prev.isoformat(), prev_end.isoformat()], "growth_pct": round(growth * 100, 1),
            "overall_uplift": round(overall, 2) if overall else None, "last_season_sales": money(season_total),
            "expected_sales": money(season_total * (1 + growth)),
            "items": items[:limit], "order_cost": money(sum(i["est_cost"] for i in items[:limit])),
            "enough_data": True}
