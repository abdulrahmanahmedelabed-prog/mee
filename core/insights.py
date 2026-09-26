# -*- coding: utf-8 -*-
"""
المستشار الذكي: يقرأ بيانات المحل ويعطي توصيات عملية مرتبة حسب الأهمية، مثل:
أصناف تُباع بخسارة، أصناف الأكثر مبيعاً على وشك النفاد، بضاعة راكدة، زبائن توقفوا عن الشراء،
ديون متأخرة، كاشير خصوماته غير طبيعية، عجز صندوق متكرر، اتجاه المبيعات، وأصناف تُشترى معاً.

كل توصية: severity (danger/warning/info/success)، title، detail، items، action (الشاشة المقترحة).
إضافة لذلك: تحليل ABC للأصناف، و«تُشترى معاً»، وتحديث الأسعار الجماعي.
"""

import math
from datetime import date, timedelta

from core import db, settings, audit
from core.utils import money, fmt_qty

SEVERITY_ORDER = {"danger": 0, "warning": 1, "info": 2, "success": 3}


def _since(days):
    return (date.today() - timedelta(days=days - 1)).isoformat()


def _sold_since(since):
    return {r["product_id"]: r for r in db.query("""
        SELECT ii.product_id, SUM((ii.quantity - ii.returned_qty) * ii.factor) AS q,
               SUM((ii.quantity - ii.returned_qty) * ii.unit_price) AS revenue,
               SUM((ii.quantity - ii.returned_qty) * (ii.unit_price - ii.cost_price)) AS profit
        FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
        WHERE date(i.created_at) >= date(?) GROUP BY ii.product_id""", (since,))}


def _card(severity, key, title, detail, items=None, action=None, action_label=None):
    return {"severity": severity, "key": key, "title": title, "detail": detail, "items": items or [],
            "action": action, "action_label": action_label}


def insights(days=30):
    out = []
    since = _since(days)
    sold = _sold_since(since)
    prods = db.query("SELECT * FROM products WHERE is_active=1")
    target_margin = settings.get_float("target_margin_percent", 15)

    # 1) أصناف تُباع بخسارة أو بهامش ضعيف
    loss = [p for p in prods if p["sale_price"] > 0 and p["cost_price"] > p["sale_price"] + 0.004]
    if loss:
        out.append(_card("danger", "loss_pricing", f"{len(loss)} صنف يُباع بأقل من تكلفته",
                         "كل قطعة تبيعها منها تخسر فيها. غالباً ارتفع سعر الشراء ولم يُعدَّل سعر البيع.",
                         [f"{p['name']}: التكلفة {money(p['cost_price'])} والبيع {money(p['sale_price'])}" for p in loss[:12]],
                         "insights:prices", "تحديث الأسعار"))
    loss_ids = {p["id"] for p in loss}
    thin = [p for p in prods if p["sale_price"] > 0 and p["cost_price"] > 0 and p["id"] not in loss_ids
            and (p["sale_price"] - p["cost_price"]) / p["sale_price"] * 100 < target_margin and p["id"] in sold]
    if thin:
        out.append(_card("warning", "thin_margin", f"{len(thin)} صنف هامش ربحه أقل من {target_margin:g}%",
                         "أصناف تُباع فعلاً لكن ربحها ضعيف؛ راجع أسعارها أو ابحث عن مورد أرخص.",
                         [f"{p['name']}: هامش {(p['sale_price'] - p['cost_price']) / p['sale_price'] * 100:.1f}%"
                          for p in sorted(thin, key=lambda p: -(sold[p['id']]['revenue'] or 0))[:12]],
                         "insights:prices", "تحديث الأسعار"))

    # 2) الأكثر مبيعاً على وشك النفاد
    top = sorted(sold.items(), key=lambda kv: -(kv[1]["revenue"] or 0))[:30]
    pmap = {p["id"]: p for p in prods}
    risk = []
    for pid, s in top:
        p = pmap.get(pid)
        if not p or p["is_weighted"]:
            continue
        rate = max(s["q"] or 0, 0) / days
        left = p["quantity"] / rate if rate > 0 else None
        if p["quantity"] <= 0 or (left is not None and left <= 3):
            risk.append(f"{p['name']}: الموجود {fmt_qty(p['quantity'])} (يكفي {left:.1f} يوم)" if left is not None and p["quantity"] > 0
                        else f"{p['name']}: نفد!")
    if risk:
        out.append(_card("danger", "stockout", f"{len(risk)} من أكثر أصنافك مبيعاً سينفد خلال 3 أيام",
                         "نفاد الصنف الرابح يعني زبوناً يذهب لمحل آخر وقد لا يعود.", risk[:12], "reorder", "الطلبيات الذكية"))

    # 3) بضاعة راكدة
    since60 = _since(60)
    sold60 = _sold_since(since60)
    dead = sorted([p for p in prods if p["quantity"] > 0 and p["id"] not in sold60 and p["cost_price"] > 0],
                  key=lambda p: -p["quantity"] * p["cost_price"])
    dead_value = money(sum(p["quantity"] * p["cost_price"] for p in dead))
    if dead and dead_value > 0:
        out.append(_card("warning", "dead_stock", f"بضاعة راكدة بقيمة {dead_value:,.2f} لم يُبع منها شيء منذ 60 يوماً",
                         "مال مجمّد على الرفوف. اعمل عليها عرضاً أو أرجعها للمورد، ولا تُعِد طلبها.",
                         [f"{p['name']}: {fmt_qty(p['quantity'])} بقيمة {money(p['quantity'] * p['cost_price']):,.2f}" for p in dead[:12]],
                         "promotions", "إنشاء عرض"))

    # 4) صلاحية
    from core import products
    exp = products.expiring_batches()
    if exp:
        value = money(sum(b["value"] or 0 for b in exp))
        expired = [b for b in exp if b["days_left"] < 0]
        out.append(_card("danger" if expired else "warning", "expiry",
                         f"بضاعة منتهية أو قريبة الانتهاء بقيمة {value:,.2f}",
                         "اعرضها بخصم الآن قبل أن تصبح خسارة كاملة، وأتلف المنتهي منها.",
                         [f"{b['name']}: {fmt_qty(b['remaining'])} — {b['expiry_date']} ({b['days_left']} يوم)" for b in exp[:12]],
                         "expiry", "شاشة الصلاحية"))

    # 5) زبائن توقفوا عن الشراء
    churn = db.query("""
        SELECT c.id, c.name, c.phone, COUNT(i.id) AS cnt, MAX(i.created_at) AS last_buy, SUM(i.total) AS total
        FROM customers c JOIN invoices i ON i.customer_id=c.id
        WHERE c.is_active=1 AND date(i.created_at) >= date('now','localtime','-120 days')
        GROUP BY c.id HAVING cnt >= 3 AND date(last_buy) < date('now','localtime','-30 days')
        ORDER BY total DESC LIMIT 20""")
    if churn:
        out.append(_card("info", "churn", f"{len(churn)} زبون دائم لم يشترِ منذ أكثر من شهر",
                         "كانوا يشترون بانتظام ثم توقفوا. رسالة واتساب لطيفة أو عرض خاص قد يعيدهم.",
                         [f"{c['name']} — آخر شراء {c['last_buy'][:10]}، مشترياته {money(c['total']):,.2f}" for c in churn[:12]],
                         "customers", "العملاء"))

    # 6) ديون متأخرة
    late = db.query("""
        SELECT c.id, c.name, c.phone, SUM(t.amount) AS bal, MAX(CASE WHEN t.type='payment' THEN t.created_at END) AS last_pay,
               MIN(t.created_at) AS first_tx
        FROM customers c JOIN customer_transactions t ON t.customer_id=c.id WHERE c.is_active=1
        GROUP BY c.id HAVING bal > 0.009 AND date(COALESCE(last_pay, first_tx)) < date('now','localtime','-30 days')
        ORDER BY bal DESC LIMIT 20""")
    if late:
        total = money(sum(r["bal"] for r in late))
        out.append(_card("warning", "late_debts", f"ديون متأخرة بقيمة {total:,.2f} لم يُسدَّد منها شيء منذ شهر",
                         "استخدم «تذكير جماعي للمدينين» بالواتساب، وأوقف البيع الآجل لمن تجاوز حده.",
                         [f"{r['name']}: {money(r['bal']):,.2f} (آخر دفعة {(r['last_pay'] or 'لا يوجد')[:10]})" for r in late[:12]],
                         "customers", "العملاء والديون"))

    # 7) خصومات الكاشير
    rows = db.query("""SELECT COALESCE(u.full_name, u.username) AS name, SUM(i.discount - i.promo_discount - i.points_value) AS disc,
                              SUM(i.subtotal) AS gross, COUNT(*) AS cnt
                       FROM invoices i JOIN users u ON u.id=i.user_id WHERE date(i.created_at) >= date(?)
                       GROUP BY i.user_id HAVING gross > 0""", (since,))
    if len(rows) >= 1:
        total_d = sum(r["disc"] or 0 for r in rows)
        total_g = sum(r["gross"] or 0 for r in rows)
        avg = total_d / total_g * 100 if total_g else 0
        odd = [r for r in rows if (r["disc"] or 0) / r["gross"] * 100 > max(2 * avg, 3) and len(rows) > 1
               or (r["disc"] or 0) / r["gross"] * 100 > 5]
        if odd:
            out.append(_card("warning", "discounts", "خصومات يدوية مرتفعة عند بعض الكاشيرات",
                             f"متوسط الخصم اليدوي في المحل {avg:.1f}% من المبيعات.",
                             [f"{r['name']}: {(r['disc'] or 0) / r['gross'] * 100:.1f}% ({money(r['disc']):,.2f})" for r in odd],
                             "reports", "التقارير"))

    # 8) عجز الصندوق المتكرر
    short = db.query("""SELECT COALESCE(u.full_name, u.username) AS name, COUNT(*) AS n, SUM(s.difference) AS total
                        FROM shifts s JOIN users u ON u.id=s.user_id
                        WHERE s.status='closed' AND s.difference < -0.009 AND date(s.closed_at) >= date(?)
                        GROUP BY s.user_id HAVING n >= 2 OR total < -50""", (since,))
    if short:
        out.append(_card("warning", "cash_short", "عجز متكرر في الصندوق",
                         "راجع سجل العمليات (فتح الدرج، المرتجعات النقدية) لهذه الورديات.",
                         [f"{r['name']}: {r['n']} مرات بمجموع {money(r['total']):,.2f}" for r in short], "cash", "الصندوق"))

    # 9) اتجاه المبيعات
    this_w = db.scalar("SELECT SUM(total) FROM invoices WHERE date(created_at) >= date('now','localtime','-6 days')") or 0
    prev_w = db.scalar("""SELECT SUM(total) FROM invoices WHERE date(created_at) BETWEEN date('now','localtime','-13 days')
                          AND date('now','localtime','-7 days')""") or 0
    if prev_w > 0:
        ch = (this_w - prev_w) / prev_w * 100
        sev = "success" if ch >= 5 else ("warning" if ch <= -10 else "info")
        word = "ارتفعت" if ch >= 0 else "انخفضت"
        out.append(_card(sev, "trend", f"مبيعات آخر 7 أيام {word} {abs(ch):.1f}%",
                         f"هذا الأسبوع {money(this_w):,.2f} مقابل {money(prev_w):,.2f} في الأسبوع السابق.", [], "reports", "التقارير"))

    # 10) ساعة الذروة وأفضل يوم
    peak = db.query_one("""SELECT CAST(strftime('%H', created_at) AS INTEGER) AS h, SUM(total) AS t FROM invoices
                           WHERE date(created_at) >= date(?) GROUP BY h ORDER BY t DESC LIMIT 1""", (since,))
    wd = db.query_one("""SELECT CAST(strftime('%w', created_at) AS INTEGER) AS d, SUM(total) AS t FROM invoices
                         WHERE date(created_at) >= date(?) GROUP BY d ORDER BY t DESC LIMIT 1""", (since,))
    if peak and wd:
        days_ar = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
        out.append(_card("info", "peak", f"ذروة البيع الساعة {peak['h']:02d}:00، وأفضل يوم {days_ar[wd['d']]}",
                         "رتّب دوام الكاشيرات واستلام البضاعة بعيداً عن هذا الوقت، وضع العروض قبله.", [], "reports", "ساعات الذروة"))

    # 11) أصناف تُشترى معاً
    pairs = bought_together(60, 3)
    if pairs:
        out.append(_card("info", "bundles", "أصناف يشتريها الزبائن معاً — فرصة لعرض مشترك",
                         "ضعها متجاورة على الرف، أو اعمل عرض «الاثنين بسعر مميز».",
                         [f"{p['a']} + {p['b']} ({p['count']} فاتورة)" for p in pairs], "promotions", "إنشاء عرض"))

    # 12) شيكات مستحقة
    from core import cheques
    due = cheques.due_soon(7)
    if due:
        out.append(_card("warning", "cheques", f"{len(due)} شيك يستحق خلال أسبوع",
                         "تأكد من رصيد البنك للشيكات الصادرة، وجهّز إيداع الشيكات الواردة.",
                         [f"{'وارد من' if c['direction'] == 'in' else 'صادر إلى'} {c['party']}: {money(c['amount']):,.2f} — {c['due_date']}"
                          for c in due[:12]], "cheques", "الشيكات"))

    # 13) هامش الربح العام
    rev = sum((s["revenue"] or 0) for s in sold.values())
    prof = sum((s["profit"] or 0) for s in sold.values())
    if rev > 0:
        margin = prof / rev * 100
        if margin < 12:
            out.append(_card("warning", "margin", f"هامش الربح العام منخفض: {margin:.1f}%",
                             "المحلات الغذائية الصحية عادة بين 15% و25%. راجع الأصناف ضعيفة الهامش والأسعار.",
                             [], "insights:prices", "تحديث الأسعار"))
        elif margin >= 18:
            out.append(_card("success", "margin", f"هامش ربح ممتاز: {margin:.1f}%",
                             "استمر، وركّز على زيادة عدد الزبائن ومتوسط السلة بالعروض ونقاط الولاء.", [], None, None))

    if not out:
        out.append(_card("success", "ok", "كل شيء على ما يرام 👌", "لا توجد تنبيهات مهمة حالياً.", [], None, None))
    out.sort(key=lambda c: SEVERITY_ORDER[c["severity"]])
    return out


def abc_analysis(days=90):
    """تصنيف الأصناف: A تصنع 80% من المبيعات، B التالية 15%، C الباقي 5%"""
    sold = _sold_since(_since(days))
    names = {r["id"]: r for r in db.query("SELECT id, name, category, quantity FROM products")}
    rows = sorted([(pid, s) for pid, s in sold.items() if (s["revenue"] or 0) > 0], key=lambda kv: -kv[1]["revenue"])
    total = sum(s["revenue"] for _, s in rows) or 1
    out, cum = [], 0.0
    for pid, s in rows:
        cum += s["revenue"]
        share = cum / total * 100
        cls = "A" if share <= 80 or not out else ("B" if share <= 95 else "C")
        p = names.get(pid, {})
        out.append({"product_id": pid, "name": p["name"] if p else "?", "category": p["category"] if p else "",
                    "stock": p["quantity"] if p else 0, "qty": s["q"], "revenue": money(s["revenue"]),
                    "profit": money(s["profit"] or 0), "share": round(s["revenue"] / total * 100, 2),
                    "cumulative": round(share, 2), "class": cls})
    return out


def bought_together(days=60, limit=10):
    return [dict(r) for r in db.query("""
        SELECT a.product_id AS pa, b.product_id AS pb, MAX(a.product_name) AS a, MAX(b.product_name) AS b,
               COUNT(DISTINCT a.invoice_id) AS count
        FROM invoice_items a JOIN invoice_items b ON a.invoice_id=b.invoice_id AND a.product_id < b.product_id
        JOIN invoices i ON i.id=a.invoice_id
        WHERE date(i.created_at) >= date('now','localtime', ?)
        GROUP BY a.product_id, b.product_id HAVING count >= 3 ORDER BY count DESC LIMIT ?""", (f"-{int(days)} days", limit))]


# ---------------------------------------------------------------------------
# تحديث الأسعار الجماعي
# ---------------------------------------------------------------------------

def _round_step(v, step):
    if not step:
        return money(v)
    return money(math.ceil(v / step - 1e-9) * step)


def price_update_preview(mode, value, category=None, product_ids=None, rounding=0.0, only_below_target=False):
    """
    mode: percent = رفع/خفض سعر البيع بنسبة | margin = سعر البيع ليحقق هامش ربح مستهدف من التكلفة
    يرجع قائمة: id, name, cost, old, new
    """
    sql, params = "SELECT * FROM products WHERE is_active=1", []
    if category:
        sql += " AND category=?"
        params.append(category)
    if product_ids:
        sql += f" AND id IN ({','.join('?' * len(product_ids))})"
        params += list(product_ids)
    out = []
    for p in db.query(sql + " ORDER BY name", params):
        if mode == "percent":
            new = p["sale_price"] * (1 + value / 100)
        elif mode == "margin":
            if not (0 <= value < 100) or p["cost_price"] <= 0:
                continue
            if only_below_target and p["sale_price"] > 0 and \
                    (p["sale_price"] - p["cost_price"]) / p["sale_price"] * 100 >= value:
                continue
            new = p["cost_price"] / (1 - value / 100)
        else:
            raise ValueError("طريقة غير معروفة")
        new = _round_step(new, rounding)
        if new > 0 and money(new) != money(p["sale_price"]):
            out.append({"id": p["id"], "name": p["name"], "cost": p["cost_price"], "old": p["sale_price"], "new": new})
    return out


def apply_price_update(changes):
    """changes: قائمة (id, new) من المعاينة"""
    if not changes:
        return 0
    with db.tx() as conn:
        for c in changes:
            conn.execute("UPDATE products SET sale_price=?, updated_at=? WHERE id=?", (money(c["new"]), db.now(), c["id"]))
        audit.log("تحديث أسعار جماعي", f"{len(changes)} صنف", conn)
    return len(changes)
