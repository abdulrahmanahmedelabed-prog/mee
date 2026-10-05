# -*- coding: utf-8 -*-
"""
التنبؤ: مبيعات الأيام القادمة، والسيولة (هل سيكفي النقد؟)، والأصناف التي ستنفد.

المبيعات: مستوى آخر 4 أسابيع × معامل يوم الأسبوع (الجمعة غير الإثنين) + اتجاه آخر 12 أسبوعاً (محدود)،
مع نطاق ثقة من تذبذب الأيام الماضية. بسيط ومفهوم ويعمل بدون إنترنت.

السيولة: النقد الآن (الصندوق + البنك + المحافظ) + المقبوض المتوقع (المبيعات غير الآجلة + تحصيل الديون المعتاد +
الشيكات الواردة في مواعيدها) − المدفوع المتوقع (المشتريات والمصاريف المعتادة + الرواتب في موعدها + الشيكات الصادرة).
"""

import math
import statistics
from datetime import date, timedelta

from core import db, ledger
from core.utils import money

WEEKDAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def _daily(start, end):
    rows = {r["d"]: r["t"] for r in db.query("""SELECT date(created_at) AS d, SUM(total) AS t FROM invoices
                                               WHERE date(created_at) BETWEEN date(?) AND date(?) GROUP BY d""",
                                            (start.isoformat(), end.isoformat()))}
    ret = {r["d"]: r["t"] for r in db.query("""SELECT date(created_at) AS d, SUM(total) AS t FROM returns
                                              WHERE date(created_at) BETWEEN date(?) AND date(?) GROUP BY d""",
                                           (start.isoformat(), end.isoformat()))}
    out, d = [], start
    while d <= end:
        k = d.isoformat()
        out.append((d, (rows.get(k) or 0) - (ret.get(k) or 0)))
        d += timedelta(days=1)
    return out


def sales_forecast(days=30, history=112, today=None):
    today = today or date.fromisoformat(db.today())
    end = today - timedelta(days=1)                       # اليوم لم يكتمل بعد
    first = db.scalar("SELECT MIN(date(created_at)) FROM invoices")
    if not first:
        return {"days": [], "total": 0.0, "enough_data": False}
    start = max(date.fromisoformat(str(first)), end - timedelta(days=history - 1))
    series = _daily(start, end)
    vals = [v for _, v in series]
    if len(vals) < 14 or sum(vals) <= 0:
        return {"days": [], "total": 0.0, "enough_data": False}
    mean = sum(vals) / len(vals)
    by_wd = {i: [] for i in range(7)}
    for d, v in series:
        by_wd[d.weekday()].append(v)
    factor = {i: ((sum(x) / len(x)) / mean if x and mean else 1.0) for i, x in by_wd.items()}
    des = [v / (factor[d.weekday()] or 1) for d, v in series]
    level = sum(des[-28:]) / len(des[-28:])
    # الاتجاه: انحدار خطي على المتوسط الأسبوعي لآخر 12 أسبوعاً (محدود بـ ±3% أسبوعياً)
    weeks = [sum(des[i:i + 7]) / 7 for i in range(max(0, len(des) - 84), len(des) - 6, 7)]
    slope = 0.0
    if len(weeks) >= 4:
        n = len(weeks)
        xm, ym = (n - 1) / 2, sum(weeks) / n
        den = sum((i - xm) ** 2 for i in range(n))
        slope = sum((i - xm) * (w - ym) for i, w in enumerate(weeks)) / den if den else 0.0
        slope = max(-0.03 * level, min(0.03 * level, slope)) / 7          # لكل يوم
    resid = [v - (sum(des[-28:]) / len(des[-28:])) * factor[d.weekday()] for d, v in series[-56:]]
    sd = statistics.pstdev(resid) if len(resid) > 2 else 0.0
    out = []
    for t in range(1, days + 1):
        d = end + timedelta(days=t)
        v = max(0.0, (level + slope * (t + 14)) * factor[d.weekday()])
        band = 1.28 * sd * math.sqrt(1 + t / 30)            # نطاق ثقة 80% يتسع مع البعد
        out.append({"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "value": money(v),
                    "low": money(max(0.0, v - band)), "high": money(v + band)})
    total = money(sum(x["value"] for x in out))
    last = money(sum(vals[-days:])) if len(vals) >= days else None
    best = max(range(7), key=lambda i: factor[i])
    worst = min(range(7), key=lambda i: factor[i])
    return {"days": out, "total": total, "low": money(sum(x["low"] for x in out)),
            "high": money(sum(x["high"] for x in out)), "last_period": last,
            "change_pct": round((total / last - 1) * 100, 1) if last else None,
            "weekday_factors": {WEEKDAYS[i]: round(factor[i], 2) for i in range(7)},
            "best_day": WEEKDAYS[best], "worst_day": WEEKDAYS[worst], "daily_avg": money(level),
            "trend_pct_week": round(slope * 7 / level * 100, 1) if level else 0.0, "enough_data": True}


def _avg_daily(sql, since, today):
    v = db.scalar(sql, (since.isoformat(), today.isoformat())) or 0
    return v / max(1, (today - since).days)


def cash_forecast(days=30, today=None):
    """النقد المتوقع يوماً بيوم، وأدنى نقطة، وأول يوم قد ينقص فيه النقد"""
    today = today or date.fromisoformat(db.today())
    bal = {a: v[1] - v[2] for a, v in ledger._balances(None, today.isoformat()).items()}
    start_cash = money(sum(bal.get(c, 0.0) for c in (ledger.CASH, ledger.BANK, ledger.WALLETS)))
    since = today - timedelta(days=60)
    sf = sales_forecast(days, today=today)
    mix = db.query_one("""SELECT COALESCE(SUM(total),0) AS t, COALESCE(SUM(credit_amount),0) AS c FROM invoices
                          WHERE date(created_at) BETWEEN date(?) AND date(?)""", (since.isoformat(), today.isoformat()))
    paid_share = 1 - (mix["c"] / mix["t"]) if mix["t"] else 1.0
    collect = _avg_daily("""SELECT -SUM(amount) FROM customer_transactions WHERE type='payment'
                            AND date(created_at) BETWEEN date(?) AND date(?)""", since, today)
    purchases = _avg_daily("""SELECT SUM(total) FROM purchases WHERE date(created_at) BETWEEN date(?) AND date(?)""",
                           since, today)
    expenses = _avg_daily("""SELECT SUM(amount) FROM expenses WHERE date(expense_date) BETWEEN date(?) AND date(?)""",
                          since, today)
    salaries = money(db.scalar("SELECT SUM(salary) FROM employees WHERE is_active=1"))
    pay_day = int(db.scalar("""SELECT CAST(strftime('%d', created_at) AS INTEGER) FROM payroll_payments
                               ORDER BY id DESC LIMIT 1""") or 1)
    cheq = db.query("""SELECT direction, amount, due_date FROM cheques WHERE status='pending'
                       AND date(due_date) <= date(?)""", ((today + timedelta(days=days)).isoformat(),))
    sales = {x["date"]: x["value"] for x in sf.get("days", [])}
    rows, cash = [], start_cash
    low = (start_cash, today.isoformat())
    first_negative = None
    for t in range(1, days + 1):
        d = today + timedelta(days=t)
        k = d.isoformat()
        inflow = sales.get(k, 0.0) * paid_share + collect
        outflow = purchases + expenses
        if d.day == min(pay_day, 28):
            outflow += salaries
        for c in cheq:
            if c["due_date"] == k or (t == 1 and c["due_date"] < k):
                if c["direction"] == "in":
                    inflow += c["amount"]
                else:
                    outflow += c["amount"]
        cash = money(cash + inflow - outflow)
        rows.append({"date": k, "in": money(inflow), "out": money(outflow), "balance": cash})
        if cash < low[0]:
            low = (cash, k)
        if cash < 0 and not first_negative:
            first_negative = k
    return {"start": start_cash, "end": cash, "rows": rows, "lowest": low[0], "lowest_date": low[1],
            "first_negative": first_negative, "salaries": salaries, "pay_day": pay_day,
            "avg_purchases": money(purchases), "avg_expenses": money(expenses), "avg_collect": money(collect),
            "paid_share": round(paid_share * 100, 1)}


def stockouts(days=14):
    """الأصناف التي ستنفد خلال المدة بمعدل بيعها الحالي"""
    from core import reorder
    rows = [r for r in reorder.suggestions(days=30, cover_days=14, include_all_low=False)
            if r["days_left"] is not None and r["days_left"] <= days]
    return sorted(rows, key=lambda r: r["days_left"])
