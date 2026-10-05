# -*- coding: utf-8 -*-
"""التقارير: قائمة الدخل (الأرباح والخسائر)، المبيعات اليومية، الفئات، الأصناف، ساعات الذروة..."""

from datetime import date, timedelta

from core import db
from core.utils import money

# مقارنة مباشرة على العمود (وليس date(العمود)) حتى يستخدم SQLite فهرس التاريخ: أسرع بكثير مع مئات الآلاف من الفواتير
_RANGE = "{col} >= date(?) AND {col} < date(?, '+1 day')"


def profit_and_loss(date_from, date_to):
    p = (date_from, date_to)
    inv = db.query_one(f"""
        SELECT COUNT(*) AS cnt, COALESCE(SUM(subtotal),0) AS gross, COALESCE(SUM(discount),0) AS discount,
               COALESCE(SUM(total),0) AS net, COALESCE(SUM(tax),0) AS tax, COALESCE(SUM(cost_total),0) AS cogs,
               COALESCE(SUM(cash_amount),0) AS cash, COALESCE(SUM(card_amount),0) AS card,
               COALESCE(SUM(credit_amount),0) AS credit, COALESCE(SUM(wallet_amount),0) AS wallet
        FROM invoices WHERE {_RANGE.format(col='created_at')}""", p)
    ret = db.query_one(f"""SELECT COUNT(*) AS cnt, COALESCE(SUM(total),0) AS total, COALESCE(SUM(tax),0) AS tax,
                                  COALESCE(SUM(cost_total),0) AS cost
                           FROM returns WHERE {_RANGE.format(col='created_at')}""", p)
    payroll = money(db.scalar(f"SELECT SUM(base + bonus - deductions) FROM payroll_payments WHERE {_RANGE.format(col='created_at')}", p))
    expenses = money(db.scalar(f"SELECT SUM(amount) FROM expenses WHERE {_RANGE.format(col='expense_date')}", p) + payroll)
    stock_loss = money(db.scalar(f"SELECT SUM(loss_value) FROM stock_movements WHERE {_RANGE.format(col='created_at')}", p))
    purchases = money(db.scalar(f"SELECT SUM(total) FROM purchases WHERE {_RANGE.format(col='created_at')}", p))
    collected = money(-db.scalar(f"""SELECT SUM(amount) FROM customer_transactions
                                     WHERE type='payment' AND {_RANGE.format(col='created_at')}""", p))

    net_sales = money(inv["net"] - ret["total"])
    tax_due = money(inv["tax"] - ret["tax"])
    net_revenue = money(net_sales - tax_due)          # الإيراد بدون ضريبة
    cogs = money(inv["cogs"] - ret["cost"])
    gross_profit = money(net_revenue - cogs)
    # فروقات أخرى تؤثر على الربح: عجز/زيادة الصندوق، تسويات الحسابات، فرق سعر المرتجع للمورد
    cash_diff = money(db.scalar(f"SELECT SUM(difference) FROM shifts WHERE status='closed' AND {_RANGE.format(col='closed_at')}", p))
    cust_adj = money(db.scalar(f"SELECT SUM(amount) FROM customer_transactions WHERE type='adjust' AND {_RANGE.format(col='created_at')}", p))
    sup_adj = money(db.scalar(f"SELECT SUM(amount) FROM supplier_transactions WHERE type='adjust' AND {_RANGE.format(col='created_at')}", p))
    pr_diff = money(db.scalar(f"SELECT SUM(total - tax - cost_total) FROM purchase_returns WHERE {_RANGE.format(col='created_at')}", p))
    manual = _manual_pl(date_from, date_to).get(None, 0.0)
    other = money(cash_diff + cust_adj - sup_adj + pr_diff)
    from core import loyalty
    loyalty_cost = money(db.scalar(f"SELECT SUM({loyalty.value_sql()}) FROM loyalty_transactions "
                                   f"WHERE {_RANGE.format(col='created_at')}", p))
    net_profit = money(gross_profit - expenses - stock_loss - loyalty_cost + other + manual)
    return {
        "invoice_count": inv["cnt"],
        "gross_sales": money(inv["gross"]),
        "discounts": money(inv["discount"]),
        "sales_after_discount": money(inv["net"]),
        "returns": money(ret["total"]),
        "returns_count": ret["cnt"],
        "net_sales": net_sales,
        "tax": tax_due,
        "net_revenue": net_revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin": round(gross_profit / net_revenue * 100, 1) if net_revenue else 0.0,
        "expenses": expenses,
        "stock_loss": stock_loss,
        "payroll": payroll,
        "loyalty_cost": loyalty_cost,
        "cash_diff": cash_diff,
        "other_adjustments": other,
        "manual_entries": manual,
        "net_profit": net_profit,
        "cash_sales": money(inv["cash"]),
        "card_sales": money(inv["card"]),
        "wallet_sales": money(inv["wallet"]),
        "credit_sales": money(inv["credit"]),
        "debt_collected": collected,
        "purchases": purchases,
        "avg_basket": money(inv["net"] / inv["cnt"]) if inv["cnt"] else 0.0,
    }


PERIODS = {"day": "يومي", "week": "أسبوعي", "month": "شهري", "year": "سنوي"}


def _manual_pl(date_from, date_to, group=None):
    """أثر العمليات المالية اليدوية على الربح (إيرادات − مصروفات)، مثل عمولات المحافظ والبنوك أو إيرادات أخرى.
    يرجع {مفتاح الفترة: المبلغ}، أو {None: المجموع} بدون تجميع"""
    from core.ledger import account_type
    k = _period_key("e.entry_date", group) if group else "NULL"
    out = {}
    for r in db.query(f"""SELECT {k} AS k, l.account_code AS code, SUM(l.credit - l.debit) AS net
                          FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id
                          WHERE e.is_void = 0 AND {_RANGE.format(col='e.entry_date')}
                          GROUP BY k, l.account_code""", (date_from, date_to)):
        if account_type(r["code"]) in ("revenue", "expense"):
            out[r["k"]] = money(out.get(r["k"], 0.0) + (r["net"] or 0))
    return out


def _period_key(col, group):
    if group == "week":        # الأسبوع من السبت إلى الجمعة، ويُسمّى بتاريخ السبت
        return f"date({col}, '-6 days', 'weekday 6')"
    if group == "month":
        return f"strftime('%Y-%m', {col})"
    if group == "year":
        return f"strftime('%Y', {col})"
    return f"date({col})"


def period_summary(date_from, date_to, group="month"):
    """ملخص المبيعات والأرباح وطرق الدفع لكل يوم/أسبوع/شهر/سنة. مجموع الفترات = تقرير الأرباح والخسائر للمدة كلها"""
    if group not in PERIODS:
        raise ValueError("نوع الفترة غير صحيح")
    from core import loyalty
    p = (date_from, date_to)
    rows = {}

    def grouped(sql, col):
        k = _period_key(col, group)
        return db.query(sql.format(k=k, where=_RANGE.format(col=col)), p)

    def row(key):
        return rows.setdefault(key, {"period": key, "count": 0, "net_sales": 0.0, "tax": 0.0, "cogs": 0.0,
                                     "expenses": 0.0, "stock_loss": 0.0, "other": 0.0, "cash": 0.0, "card": 0.0,
                                     "wallet": 0.0, "credit": 0.0})

    for r in grouped("""SELECT {k} AS k, COUNT(*) AS cnt, SUM(total) AS net, SUM(tax) AS tax, SUM(cost_total) AS cogs,
                               SUM(cash_amount) AS cash, SUM(card_amount) AS card, SUM(wallet_amount) AS wallet,
                               SUM(credit_amount) AS credit
                        FROM invoices WHERE {where} GROUP BY k""", "created_at"):
        x = row(r["k"])
        x.update(count=r["cnt"], net_sales=r["net"] or 0, tax=r["tax"] or 0, cogs=r["cogs"] or 0, cash=r["cash"] or 0,
                 card=r["card"] or 0, wallet=r["wallet"] or 0, credit=r["credit"] or 0)
    for r in grouped("""SELECT {k} AS k, SUM(total) AS t, SUM(tax) AS tax, SUM(cost_total) AS c
                        FROM returns WHERE {where} GROUP BY k""", "created_at"):
        x = row(r["k"])
        x["net_sales"] -= r["t"] or 0
        x["tax"] -= r["tax"] or 0
        x["cogs"] -= r["c"] or 0
    for sql, col, field, sign in (
            ("SELECT {k} AS k, SUM(amount) AS v FROM expenses WHERE {where} GROUP BY k", "expense_date", "expenses", 1),
            ("SELECT {k} AS k, SUM(base + bonus - deductions) AS v FROM payroll_payments WHERE {where} GROUP BY k",
             "created_at", "expenses", 1),
            ("SELECT {k} AS k, SUM(loss_value) AS v FROM stock_movements WHERE {where} GROUP BY k", "created_at",
             "stock_loss", 1),
            ("SELECT {k} AS k, SUM(difference) AS v FROM shifts WHERE status='closed' AND {where} GROUP BY k",
             "closed_at", "other", 1),
            ("SELECT {k} AS k, SUM(amount) AS v FROM customer_transactions WHERE type='adjust' AND {where} GROUP BY k",
             "created_at", "other", 1),
            ("SELECT {k} AS k, SUM(amount) AS v FROM supplier_transactions WHERE type='adjust' AND {where} GROUP BY k",
             "created_at", "other", -1),
            ("SELECT {k} AS k, SUM(total - tax - cost_total) AS v FROM purchase_returns WHERE {where} GROUP BY k",
             "created_at", "other", 1),
            ("SELECT {k} AS k, SUM(" + loyalty.value_sql() + ") AS v FROM loyalty_transactions WHERE {where} GROUP BY k",
             "created_at", "other", -1)):
        for r in grouped(sql, col):
            row(r["k"])[field] += sign * (r["v"] or 0)
    for k, v in _manual_pl(date_from, date_to, group).items():
        row(k)["other"] += v
    out = []
    for k in sorted(rows):
        x = rows[k]
        revenue = money(x["net_sales"] - x["tax"])
        gross = money(revenue - x["cogs"])
        x.update({f: money(x[f]) for f in ("net_sales", "tax", "cogs", "expenses", "stock_loss", "other", "cash",
                                           "card", "wallet", "credit")})
        x["gross_profit"] = gross
        x["margin"] = round(gross / revenue * 100, 1) if revenue else 0.0
        x["net_profit"] = money(gross - x["expenses"] - x["stock_loss"] + x["other"])
        out.append(x)
    return out


def daily_sales(date_from, date_to):
    """المبيعات والأرباح لكل يوم (يشمل الأيام التي بلا مبيعات)"""
    rows = {r["d"]: r for r in db.query(f"""
        SELECT date(created_at) AS d, COUNT(*) AS cnt, SUM(total) AS total, SUM(total - tax - cost_total) AS profit
        FROM invoices WHERE {_RANGE.format(col='created_at')} GROUP BY d""", (date_from, date_to))}
    rets = {r["d"]: r for r in db.query(f"""
        SELECT date(created_at) AS d, SUM(total) AS total, SUM(total - tax - cost_total) AS profit
        FROM returns WHERE {_RANGE.format(col='created_at')} GROUP BY d""", (date_from, date_to))}
    out = []
    d = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    while d <= end:
        k = d.isoformat()
        r, rr = rows.get(k), rets.get(k)
        total = (r["total"] if r else 0) - (rr["total"] if rr else 0)
        profit = (r["profit"] if r else 0) - (rr["profit"] if rr else 0)
        out.append({"date": k, "count": r["cnt"] if r else 0, "total": money(total), "profit": money(profit)})
        d += timedelta(days=1)
    return out


def last_n_days(n=14):
    end = date.today()
    return daily_sales((end - timedelta(days=n - 1)).isoformat(), end.isoformat())


def sales_by_category(date_from, date_to):
    return db.query(f"""
        SELECT COALESCE(NULLIF(p.category,''),'بدون فئة') AS category,
               SUM((ii.quantity - ii.returned_qty) * ii.factor) AS qty,
               SUM((ii.quantity - ii.returned_qty) * ii.unit_price) AS total,
               SUM((ii.quantity - ii.returned_qty) * (ii.unit_price - ii.cost_price)) AS profit
        FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id LEFT JOIN products p ON p.id=ii.product_id
        WHERE {_RANGE.format(col='i.created_at')}
        GROUP BY 1 ORDER BY total DESC""", (date_from, date_to))


def top_products(date_from, date_to, limit=20, order="total"):
    order_col = {"total": "total", "qty": "qty", "profit": "profit"}.get(order, "total")
    return db.query(f"""
        SELECT ii.product_id, MAX(ii.product_name) AS product_name,
               SUM((ii.quantity - ii.returned_qty) * ii.factor) AS qty,
               SUM((ii.quantity - ii.returned_qty) * ii.unit_price) AS total,
               SUM((ii.quantity - ii.returned_qty) * (ii.unit_price - ii.cost_price)) AS profit
        FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
        WHERE {_RANGE.format(col='i.created_at')}
        GROUP BY ii.product_id ORDER BY {order_col} DESC LIMIT ?""", (date_from, date_to, limit))


def slow_products(date_from, date_to):
    """أصناف راكدة: موجودة بالمخزون ولم يُبع منها شيء خلال الفترة (رأس مال مجمّد)"""
    return db.query(f"""
        SELECT p.*, p.quantity * p.cost_price AS stock_value,
               (SELECT MAX(i.created_at) FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                WHERE ii.product_id=p.id) AS last_sold
        FROM products p
        WHERE p.is_active=1 AND p.quantity > 0 AND p.id NOT IN (
            SELECT ii.product_id FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
            WHERE {_RANGE.format(col='i.created_at')})
        ORDER BY stock_value DESC""", (date_from, date_to))


def sales_by_cashier(date_from, date_to):
    return db.query(f"""
        SELECT COALESCE(u.full_name, u.username, '-') AS cashier, COUNT(*) AS cnt, SUM(i.total) AS total,
               SUM(i.discount) AS discount
        FROM invoices i LEFT JOIN users u ON u.id=i.user_id
        WHERE {_RANGE.format(col='i.created_at')} GROUP BY i.user_id ORDER BY total DESC""", (date_from, date_to))


def sales_by_terminal(date_from, date_to):
    return db.query(f"""
        SELECT COALESCE(terminal, '-') AS terminal, COUNT(*) AS cnt, SUM(total) AS total
        FROM invoices WHERE {_RANGE.format(col='created_at')} GROUP BY terminal ORDER BY total DESC""", (date_from, date_to))


def sales_by_hour(date_from, date_to):
    """ساعات الذروة - تساعد في تنظيم الدوام وتوفر البضاعة"""
    rows = {r["h"]: r for r in db.query(f"""
        SELECT CAST(strftime('%H', created_at) AS INTEGER) AS h, COUNT(*) AS cnt, SUM(total) AS total
        FROM invoices WHERE {_RANGE.format(col='created_at')} GROUP BY h""", (date_from, date_to))}
    return [{"hour": h, "count": rows[h]["cnt"] if h in rows else 0,
             "total": money(rows[h]["total"]) if h in rows else 0.0} for h in range(24)]


def dashboard(today=None):
    today = today or db.today()
    from core import customers, suppliers, products, shifts, cheques, license
    pl = profit_and_loss(today, today)
    shift = shifts.current_shift()
    cash = shifts.summary(shift["id"])["expected_cash"] if shift else None
    due = cheques.due_soon(7)
    return {
        "today": pl,
        "expiring": len(products.expiring_batches()),
        "customer_debts": customers.total_debts(),
        "supplier_dues": suppliers.total_dues(),
        "low_stock": len(products.get_low_stock_products()),
        "inventory": products.inventory_value(),
        "drawer_cash": cash,
        "shift": shift,
        "cheques_due": len(due),
        "cheques_in_due": money(sum(c["amount"] for c in due if c["direction"] == "in")),
        "cheques_out_due": money(sum(c["amount"] for c in due if c["direction"] == "out")),
        "license": license.status(),
    }


def daily_summary_text(day=None):
    """ملخص اليوم للمالك (يُرسل عبر واتساب بضغطة)"""
    from core import settings, products, shifts, customers, cheques
    from core.utils import fmt_qty
    day = day or db.today()
    p = profit_and_loss(day, day)
    cur = settings.get("currency_symbol", "")
    drawers = money(sum(shifts.summary(s["id"])["expected_cash"] for s in shifts.open_shifts()))
    lines = [f"📊 ملخص يوم {day} — {settings.get('shop_name')}", "",
             f"🧾 المبيعات: {p['net_sales']:,.2f} {cur} ({p['invoice_count']} فاتورة)",
             f"   نقدي {p['cash_sales']:,.2f} • بطاقة {p['card_sales']:,.2f} • إلكتروني {p['wallet_sales']:,.2f}"
             f" • آجل {p['credit_sales']:,.2f}",
             f"📈 مجمل الربح: {p['gross_profit']:,.2f} (هامش {p['gross_margin']}%)",
             f"💸 المصاريف: {p['expenses']:,.2f}",
             f"💰 صافي الربح: {p['net_profit']:,.2f}",
             f"📒 ديون محصّلة: {p['debt_collected']:,.2f} • إجمالي ديون العملاء: {customers.total_debts():,.2f}",
             f"💵 النقد في الأدراج الآن: {drawers:,.2f}"]
    top = top_products(day, day, 3, "total")
    if top:
        lines += ["", "🏆 الأكثر مبيعاً:"] + [f"   {i + 1}. {r['product_name']} ×{fmt_qty(r['qty'])}" for i, r in enumerate(top)]
    low = len(products.get_low_stock_products())
    due = cheques.due_soon(3)
    if low or due:
        lines.append("")
    if low:
        lines.append(f"⚠ {low} صنف تحت الحد الأدنى")
    if due:
        lines.append(f"🏦 {len(due)} شيك يستحق خلال 3 أيام بقيمة {sum(c['amount'] for c in due):,.2f}")
    return "\n".join(lines)


def vat_report(date_from, date_to):
    """إقرار ضريبة القيمة المضافة: ضريبة المخرجات (المبيعات) − ضريبة المدخلات (المشتريات) = الصافي المستحق"""
    p = (date_from, date_to)
    sales_ = db.query_one(f"""SELECT COUNT(*) AS cnt, COALESCE(SUM(total),0) AS total, COALESCE(SUM(tax),0) AS tax
                              FROM invoices WHERE {_RANGE.format(col='created_at')}""", p)
    rets = db.query_one(f"""SELECT COALESCE(SUM(total),0) AS total, COALESCE(SUM(tax),0) AS tax
                            FROM returns WHERE {_RANGE.format(col='created_at')}""", p)
    pur = db.query_one(f"""SELECT COUNT(*) AS cnt, COALESCE(SUM(total),0) AS total, COALESCE(SUM(tax),0) AS tax
                           FROM purchases WHERE {_RANGE.format(col='created_at')}""", p)
    pret = db.query_one(f"""SELECT COALESCE(SUM(total),0) AS total, COALESCE(SUM(tax),0) AS tax
                            FROM purchase_returns WHERE {_RANGE.format(col='created_at')}""", p)
    output_tax = money(sales_["tax"] - rets["tax"])
    input_tax = money(pur["tax"] - pret["tax"])          # مرتجعات المشتريات تعكس ضريبة مدخلاتها
    taxable_sales = money(sales_["total"] - rets["total"] - output_tax)
    return {"sales_count": sales_["cnt"], "sales_total": money(sales_["total"] - rets["total"]),
            "taxable_sales": taxable_sales, "output_tax": output_tax,
            "purchases_count": pur["cnt"], "purchases_total": money(pur["total"] - pret["total"]),
            "taxable_purchases": money(pur["total"] - pret["total"] - input_tax), "input_tax": input_tax,
            "net_due": money(output_tax - input_tax)}
