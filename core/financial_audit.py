# -*- coding: utf-8 -*-
"""
التدقيق المالي الآلي: ينفّذ إجراءات المدقق الخارجي على بيانات المحل ويصدر تقريراً برأي ودرجة.

كل فحص يرجع ملاحظة واحدة أو أكثر:
    {"area", "title", "severity", "detail", "action", "amount", "count", "samples": [نصوص]}
الخطورة: critical (حرج) / high (مرتفع) / medium (متوسط) / low (منخفض) / ok (سليم).

الإجراءات مبنية على معايير التدقيق المعتادة: توازن الدفاتر، مطابقة الدفاتر الفرعية مع الأستاذ، اكتمال التسلسل،
مؤشرات الاحتيال عند الكاشير، أعمار الديون، تقييم المخزون، المراجعة التحليلية للهوامش، قانون بنفورد، الضريبة، والنسخ الاحتياطي.
"""

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from core import db, ledger, reports, settings
from core.utils import money

SEVERITY = {"critical": "حرج", "high": "مرتفع", "medium": "متوسط", "low": "منخفض", "ok": "سليم"}
WEIGHT = {"critical": 15, "high": 8, "medium": 4, "low": 1, "ok": 0}
ORDER = ["critical", "high", "medium", "low", "ok"]

A_BOOKS = "الدفاتر والقيود"
A_SEQ = "اكتمال المستندات"
A_CASH = "الصندوق والكاشير"
A_SALES = "المبيعات والخصومات"
A_STOCK = "المخزون"
A_DEBTS = "الذمم والشيكات"
A_EXP = "المصاريف والمشتريات"
A_TREND = "المراجعة التحليلية"
A_TAX = "الضريبة"
A_CONTROL = "بيئة الرقابة"
AREAS = [A_BOOKS, A_SEQ, A_CASH, A_SALES, A_STOCK, A_DEBTS, A_EXP, A_TREND, A_TAX, A_CONTROL]


def _f(area, title, severity, detail, action="", amount=None, count=None, samples=None):
    return {"area": area, "title": title, "severity": severity, "detail": detail, "action": action,
            "amount": None if amount is None else money(amount), "count": count, "samples": list(samples or [])[:12]}


def n(x):
    """رقم مالي منسّق للنصوص: 1,234.50"""
    return f"{money(x or 0):,.2f}"


def _ok(area, title, detail):
    return _f(area, title, "ok", detail)


def _users():
    return {r["id"]: (r["full_name"] or r["username"]) for r in db.query("SELECT id, username, full_name FROM users")}


def _in(col):
    return f"date({col}) BETWEEN date(?) AND date(?)"


class _Ctx:
    def __init__(self, date_from, date_to):
        self.a, self.b = date_from, date_to
        self.p = (date_from, date_to)
        self.users = _users()
        self.bal = ledger._balances(None, date_to)
        self.pl = reports.profit_and_loss(date_from, date_to)
        self.sales = max(self.pl["net_sales"], 0.0)

    def balance(self, code):
        row = self.bal.get(code, [0.0, 0.0, 0.0])
        return money(row[0] + row[1] - row[2])

    def user(self, uid):
        return self.users.get(uid, "غير معروف")


# ---------------------------------------------------------------------------
# 1) الدفاتر
# ---------------------------------------------------------------------------

def check_books_balance(c):
    diff = money(sum(v[0] + v[1] - v[2] for v in c.bal.values()))
    bs = ledger.balance_sheet(c.b)
    if abs(diff) > 0.05 or not bs["balanced"]:
        return [_f(A_BOOKS, "الدفاتر غير متوازنة", "critical",
                   f"مجموع المدين لا يساوي مجموع الدائن (الفرق {n(diff)})، أو الميزانية لا تحقق: الأصول = الالتزامات + حقوق الملكية.",
                   "لا تعتمد على التقارير قبل تصحيح الخلل. راجع القيود اليدوية الأخيرة، ثم تواصل مع الدعم.", diff)]
    return [_ok(A_BOOKS, "توازن الدفاتر", "ميزان المراجعة متوازن، والميزانية العمومية تحقق المعادلة المحاسبية.")]


def check_receivables(c):
    sub = money(db.scalar("SELECT SUM(amount) FROM customer_transactions WHERE date(created_at) <= date(?)", (c.b,)))
    gl = c.balance(ledger.RECEIVABLES)
    if abs(sub - gl) > 0.05:
        return [_f(A_BOOKS, "ديون العملاء لا تطابق حسابها في الأستاذ", "high",
                   f"مجموع أرصدة العملاء {n(sub)} بينما حساب ذمم العملاء {n(gl)}.",
                   "راجع حركات العملاء المعدّلة يدوياً والقيود اليدوية على حساب 1210.", sub - gl)]
    return [_ok(A_BOOKS, "مطابقة ديون العملاء", f"مجموع أرصدة العملاء ({n(sub)}) يطابق حساب الذمم في الأستاذ.")]


def check_payables(c):
    sub = money(db.scalar("SELECT SUM(amount) FROM supplier_transactions WHERE date(created_at) <= date(?)", (c.b,)))
    gl = -c.balance(ledger.PAYABLES)
    if abs(sub - gl) > 0.05:
        return [_f(A_BOOKS, "مستحقات الموردين لا تطابق حسابها في الأستاذ", "high",
                   f"مجموع أرصدة الموردين {n(sub)} بينما حساب ذمم الموردين {n(gl)}.",
                   "راجع حركات الموردين والقيود اليدوية على حساب 2110.", sub - gl)]
    return [_ok(A_BOOKS, "مطابقة مستحقات الموردين", f"مجموع أرصدة الموردين ({n(sub)}) يطابق حسابهم في الأستاذ.")]


def check_inventory_value(c):
    if c.b < db.today():
        return []            # الكميات المخزنة حالية فقط؛ المطابقة ممكنة حتى تاريخ اليوم
    book = money(db.scalar("""SELECT SUM(quantity * cost_price) FROM products WHERE COALESCE(is_service,0)=0"""))
    gl = c.balance(ledger.INVENTORY)
    diff = money(book - gl)
    tol = max(5.0, abs(gl) * 0.005)
    if abs(diff) > tol:
        return [_f(A_BOOKS, "قيمة المخزون على الرفوف لا تطابق حساب المخزون", "medium",
                   f"الكميات × التكلفة = {n(book)}، وحساب المخزون في الأستاذ = {n(gl)}. "
                   "يحدث عادة عند البيع بكميات سالبة (بضاعة لم تُسجَّل مشترياتها) أو قيود يدوية على حساب المخزون.",
                   "سجّل المشتريات قبل البيع، وصحّح الأصناف ذات الكميات السالبة بجرد فعلي.", diff)]
    return [_ok(A_BOOKS, "مطابقة قيمة المخزون", f"قيمة البضاعة بالتكلفة ({n(book)}) تطابق حساب المخزون.")]


def check_impossible_balances(c):
    out = []
    for code, name in ((ledger.CASH, "الصندوق"), (ledger.WALLETS, "المحافظ الإلكترونية"),
                       (ledger.CHEQUES_IN, "الشيكات الواردة")):
        v = c.balance(code)
        if v < -0.05:
            out.append(_f(A_BOOKS, f"رصيد {name} سالب", "high",
                          f"رصيد {name} في {c.b} = {n(v)}. لا يمكن أن يخرج نقد أكثر مما دخل: عملية مسجّلة خطأ أو دخل ناقص.",
                          "راجع كشف الحساب في المحاسبة ← كشف حساب، وابحث عن دفعات أو مصاريف مسجّلة على الطريقة الخطأ.", v))
    neg = db.query("""SELECT name, quantity FROM products WHERE quantity < -0.0005 AND COALESCE(is_service,0)=0
                      AND is_active=1 ORDER BY quantity LIMIT 50""")
    if neg:
        out.append(_f(A_STOCK, "أصناف بكميات سالبة", "medium",
                      "بيعت كميات أكثر من المسجّل في المخزون: بضاعة دخلت بدون فاتورة مشتريات، فتكلفتها وربحها غير دقيقين.",
                      "سجّل فاتورة المشتريات الناقصة أو اعمل جرداً لهذه الأصناف.", count=len(neg),
                      samples=[f"{r['name']}: {r['quantity']:g}" for r in neg]))
    if not out:
        out.append(_ok(A_BOOKS, "أرصدة منطقية", "لا يوجد رصيد سالب في الصندوق أو المحافظ أو الشيكات، ولا أصناف بكميات سالبة."))
    return out


# ---------------------------------------------------------------------------
# 2) اكتمال المستندات
# ---------------------------------------------------------------------------

def _gaps(table, col, prefix):
    nums = sorted(int(r[0].split("-")[-1]) for r in db.get_connection().execute(
        f"SELECT {col} FROM {table} WHERE {col} LIKE ?", (prefix + "-%",)) if r[0].split("-")[-1].isdigit())
    if not nums:
        return []
    have = set(nums)
    return [n for n in range(nums[0], nums[-1] + 1) if n not in have]


def check_sequences(c):
    out = []
    for table, col, prefix, name in (("invoices", "invoice_number", "INV", "فواتير البيع"),
                                     ("returns", "return_number", "RET", "المرتجعات"),
                                     ("purchases", "purchase_number", "PUR", "فواتير المشتريات")):
        miss = _gaps(table, col, prefix)
        if miss:
            out.append(_f(A_SEQ, f"أرقام مفقودة في تسلسل {name}", "high",
                          f"{len(miss)} رقماً مفقوداً. البرنامج لا يحذف المستندات، فالرقم المفقود يعني حذفاً من قاعدة البيانات مباشرة.",
                          "اسأل من لديه صلاحية الوصول للجهاز، واسترجع نسخة احتياطية للمقارنة.", count=len(miss),
                          samples=[f"{prefix}-{n:06d}" for n in miss]))
    if not out:
        out.append(_ok(A_SEQ, "تسلسل المستندات", "أرقام فواتير البيع والمرتجعات والمشتريات متسلسلة بلا أرقام مفقودة."))
    return out


def check_invoice_integrity(c):
    bad_pay = db.query(f"""SELECT invoice_number, total, cash_amount + card_amount + wallet_amount + credit_amount AS paid
                           FROM invoices WHERE {_in('created_at')}
                           AND ABS(cash_amount + card_amount + wallet_amount + credit_amount - total) > 0.011""", c.p)
    bad_items = db.query(f"""SELECT i.invoice_number, i.subtotal, s.t FROM invoices i
                             JOIN (SELECT invoice_id, SUM(total) AS t FROM invoice_items GROUP BY invoice_id) s
                               ON s.invoice_id = i.id
                             WHERE {_in('i.created_at')} AND ABS(i.subtotal - s.t) > 0.011""", c.p)
    out = []
    if bad_pay:
        out.append(_f(A_SEQ, "فواتير لا يساوي مجموع دفعاتها إجماليها", "high",
                      "مجموع النقد والبطاقة والمحفظة والآجل يختلف عن إجمالي الفاتورة.",
                      "راجع هذه الفواتير؛ قد تكون عُدّلت خارج البرنامج.", count=len(bad_pay),
                      samples=[f"{r['invoice_number']}: الإجمالي {n(r['total'])} المدفوع {n(r['paid'])}" for r in bad_pay]))
    if bad_items:
        out.append(_f(A_SEQ, "فواتير لا يطابق مجموع أصنافها", "high",
                      "مجموع أسطر الأصناف يختلف عن مجموع الفاتورة.", "راجع هذه الفواتير.", count=len(bad_items),
                      samples=[f"{r['invoice_number']}: {r['subtotal']} ≠ {n(r['t'])}" for r in bad_items]))
    if not out:
        out.append(_ok(A_SEQ, "سلامة الفواتير", "كل فاتورة: مجموع أصنافها = مجموعها، ومجموع دفعاتها = إجماليها."))
    return out


def check_duplicate_refs(c):
    rows = db.query(f"""SELECT wallet_name, wallet_ref, COUNT(*) AS n, GROUP_CONCAT(invoice_number, '، ') AS invs
                        FROM invoices WHERE wallet_amount > 0 AND TRIM(COALESCE(wallet_ref,'')) != ''
                        AND {_in('created_at')} GROUP BY wallet_name, wallet_ref HAVING n > 1""", c.p)
    if rows:
        return [_f(A_CASH, "رقم عملية محفظة مستخدم لأكثر من فاتورة", "high",
                   "نفس إشعار التحويل استُخدم لفاتورتين أو أكثر: قد يكون زبون أظهر الإشعار نفسه مرتين، أو إدخالاً خاطئاً.",
                   "طابق هذه العمليات مع كشف المحفظة أو البنك من تقرير الدفع الإلكتروني.", count=len(rows),
                   samples=[f"{r['wallet_name']} {r['wallet_ref']}: {r['invs']}" for r in rows])]
    return [_ok(A_CASH, "أرقام عمليات المحافظ", "لا يوجد رقم عملية مكرر بين فواتير الدفع الإلكتروني.")]


# ---------------------------------------------------------------------------
# 3) الصندوق والكاشير
# ---------------------------------------------------------------------------

def check_shifts(c):
    out = []
    rows = db.query(f"""SELECT user_id, COUNT(*) AS n, SUM(CASE WHEN difference < -0.009 THEN 1 ELSE 0 END) AS short_n,
                               SUM(CASE WHEN difference < 0 THEN difference ELSE 0 END) AS short
                        FROM shifts WHERE status='closed' AND {_in('closed_at')} GROUP BY user_id""", c.p)
    total_short = money(-sum(r["short"] or 0 for r in rows))
    shifts_n = sum(r["n"] for r in rows) or 1
    avg = total_short / shifts_n                  # متوسط العجز لكل وردية في المحل
    rate = total_short / max(c.pl["cash_sales"], 1.0)
    # كاشير عجزه لكل وردية أكثر من ضعف متوسط المحل ويتكرر: مؤشر يستحق المتابعة
    odd = [r for r in rows if (r["short_n"] or 0) >= 3 and -(r["short"] or 0) / r["n"] > 2 * avg]
    if total_short > 0:
        sev = "high" if odd or rate > 0.005 else ("medium" if rate > 0.002 else "low")
        out.append(_f(A_CASH, "عجز في الصندوق", sev,
                      f"مجموع العجز عند إغلاق الورديات {n(total_short)} ({round(rate * 100, 2)}% من المبيعات النقدية)، "
                      f"بمتوسط {n(avg)} للوردية."
                      + (" عجز بعض الكاشيرات أعلى بكثير من غيرهم، وهذا مؤشر يستحق المتابعة." if odd else
                         " العجز موزّع بين الكاشيرات بشكل متقارب (فكّة وأخطاء عدّ غالباً)."),
                      "اطلب عدّ الصندوق بالفئات أمام المدير عند كل إغلاق، وراجع تقارير الورديات.", total_short,
                      samples=[f"{c.user(r['user_id'])}: {r['short_n']} من {r['n']} وردية بعجز، المجموع "
                               f"{n(-(r['short'] or 0))}" for r in sorted(rows, key=lambda r: r["short"] or 0)
                               if (r["short_n"] or 0)]))
    else:
        out.append(_ok(A_CASH, "عدّ الصندوق", "لا يوجد عجز في الورديات المغلقة خلال الفترة."))
    stale = db.query("""SELECT id, user_id, opened_at FROM shifts WHERE status='open'
                        AND julianday('now', 'localtime') - julianday(opened_at) > 1.5""")
    if stale:
        out.append(_f(A_CASH, "ورديات مفتوحة منذ أكثر من يوم", "medium",
                      "الوردية التي لا تُغلق لا يُعدّ صندوقها، فلا يُكتشف العجز في وقته.",
                      "أغلق هذه الورديات وعدّ الصندوق.", count=len(stale),
                      samples=[f"وردية #{r['id']} — {c.user(r['user_id'])} منذ {r['opened_at'][:16]}" for r in stale]))
    return out


def check_cash_refund_on_electronic(c):
    rows = db.query(f"""SELECT r.return_number, i.invoice_number, r.total, r.user_id FROM returns r
                        JOIN invoices i ON i.id = r.invoice_id
                        WHERE r.refund_method = 'نقدي' AND {_in('r.created_at')}
                        AND r.total > (i.cash_amount - COALESCE((SELECT SUM(x.total) FROM returns x
                             WHERE x.invoice_id = i.id AND x.refund_method = 'نقدي' AND x.id < r.id), 0)) + 0.01""", c.p)
    if rows:
        amt = sum(r["total"] for r in rows)
        return [_f(A_CASH, "مرتجع نقدي لفاتورة دُفعت ببطاقة أو محفظة أو آجلاً", "high",
                   "أُعيد للزبون نقداً من الدرج أكثر مما دفعه نقداً. هذا من أشهر أساليب سحب النقد من الصندوق.",
                   "راجع هذه المرتجعات مع الكاشير، واجعل الإرجاع بنفس طريقة الدفع.", amt, len(rows),
                   [f"{r['return_number']} من {r['invoice_number']}: {n(r['total'])} — {c.user(r['user_id'])}" for r in rows])]
    return [_ok(A_CASH, "المرتجعات النقدية", "كل مرتجع نقدي كان لفاتورة دُفعت نقداً.")]


def check_refunds_by_cashier(c):
    sales = {r["user_id"]: r["t"] for r in db.query(
        f"SELECT user_id, SUM(total) AS t FROM invoices WHERE {_in('created_at')} GROUP BY user_id", c.p)}
    rets = db.query(f"SELECT user_id, SUM(total) AS t, COUNT(*) AS n FROM returns WHERE {_in('created_at')} GROUP BY user_id",
                    c.p)
    tot_s, tot_r = sum(sales.values()) or 0, sum(r["t"] for r in rets) or 0
    avg = tot_r / tot_s if tot_s else 0
    flag = [r for r in rets if sales.get(r["user_id"]) and r["n"] >= 5
            and r["t"] / sales[r["user_id"]] > max(2 * avg, 0.015)]
    if flag:
        return [_f(A_CASH, "نسبة مرتجعات مرتفعة عند كاشير", "medium",
                   f"متوسط المرتجعات في المحل {round(avg * 100, 2)}% من المبيعات، وهؤلاء أعلى بكثير.",
                   "افحص مرتجعاتهم: هل للزبون وجود فعلي؟ هل البضاعة عادت للرف؟",
                   count=len(flag), samples=[f"{c.user(r['user_id'])}: {round(r['t'] / sales[r['user_id']] * 100, 2)}% "
                                             f"({r['n']} مرتجع بـ {n(r['t'])})" for r in flag])]
    return [_ok(A_CASH, "المرتجعات حسب الكاشير", f"نسب المرتجعات متقاربة بين الكاشيرات (المتوسط {round(avg * 100, 2)}%).")]


def check_drawer_and_prices(c):
    out = []
    for action, title, limit in (("فتح درج النقود", "فتح الدرج بدون بيع", 20),
                                 ("تغيير سعر في البيع", "تغيير الأسعار أثناء البيع", 30)):
        rows = db.query(f"""SELECT user_id, COUNT(*) AS n FROM audit_log WHERE action=? AND {_in('created_at')}
                            GROUP BY user_id ORDER BY n DESC""", (action, *c.p))
        many = [r for r in rows if r["n"] > limit]
        if many:
            out.append(_f(A_CASH, title, "medium" if action == "فتح درج النقود" else "low",
                          f"تكرر {sum(r['n'] for r in rows)} مرة في الفترة. التكرار الكثير يستحق السؤال عنه.",
                          "راجع سجل العمليات في الإعدادات، واطلب إذن المدير لهذه العملية.", count=sum(r["n"] for r in rows),
                          samples=[f"{c.user(r['user_id'])}: {r['n']} مرة" for r in rows]))
    if not out:
        out.append(_ok(A_CASH, "فتح الدرج وتغيير الأسعار", "لا يوجد تكرار لافت لفتح الدرج بدون بيع أو لتغيير الأسعار."))
    return out


# ---------------------------------------------------------------------------
# 4) المبيعات والخصومات
# ---------------------------------------------------------------------------

def check_discounts(c):
    rows = db.query(f"""SELECT user_id, SUM(subtotal) AS s,
                               SUM(MAX(discount - promo_discount - points_value, 0)) AS manual,
                               SUM(CASE WHEN subtotal > 0 AND (discount - promo_discount - points_value) > subtotal * 0.2
                                        THEN 1 ELSE 0 END) AS big
                        FROM invoices WHERE {_in('created_at')} GROUP BY user_id""", c.p)
    tot_s = sum(r["s"] or 0 for r in rows)
    tot_d = sum(r["manual"] or 0 for r in rows)
    avg = tot_d / tot_s if tot_s else 0
    flag = [r for r in rows if r["s"] and (r["manual"] or 0) / r["s"] > max(2 * avg, 0.02)]
    big = sum(r["big"] or 0 for r in rows)
    out = []
    if flag or big:
        out.append(_f(A_SALES, "خصومات يدوية مرتفعة", "medium" if flag else "low",
                      f"الخصم اليدوي {n(tot_d)} ({round(avg * 100, 2)}% من المبيعات)، و{big} فاتورة بخصم يزيد عن 20%.",
                      "حدّد سقف خصم للكاشير في الإعدادات (يُطلب إذن المدير عند تجاوزه).", tot_d, big,
                      [f"{c.user(r['user_id'])}: {round((r['manual'] or 0) / r['s'] * 100, 2)}% خصم يدوي" for r in rows if r["s"]]))
    else:
        out.append(_ok(A_SALES, "الخصومات اليدوية", f"الخصم اليدوي معتدل ({round(avg * 100, 2)}% من المبيعات)."))
    return out


def check_below_cost(c):
    r = db.query_one(f"""SELECT COUNT(*) AS n, SUM((ii.cost_price - ii.unit_price) * ii.quantity) AS loss
                         FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id
                         WHERE {_in('i.created_at')} AND ii.unit_price < ii.cost_price - 0.001""", c.p)
    if r["n"]:
        top = db.query(f"""SELECT ii.product_name AS name, SUM((ii.cost_price - ii.unit_price) * ii.quantity) AS loss
                           FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id
                           WHERE {_in('i.created_at')} AND ii.unit_price < ii.cost_price - 0.001
                           GROUP BY ii.product_name ORDER BY loss DESC LIMIT 10""", c.p)
        loss = money(r["loss"])
        sev = "medium" if loss > c.sales * 0.005 else "low"
        return [_f(A_SALES, "بيع بأقل من التكلفة", sev,
                   f"{r['n']} سطر بيع بسعر أقل من التكلفة، والخسارة {n(loss)}.",
                   "حدّث أسعار البيع بعد ارتفاع أسعار الموردين (المستشار الذكي ← تحديث الأسعار الجماعي).", loss, r["n"],
                   [f"{t['name']}: {n(t['loss'])}" for t in top])]
    return [_ok(A_SALES, "أسعار البيع مقابل التكلفة", "لم يُبع أي صنف بأقل من تكلفته.")]


# ---------------------------------------------------------------------------
# 5) المخزون
# ---------------------------------------------------------------------------

def check_expired_stock(c):
    rows = db.query("""SELECT p.name, b.remaining, b.expiry_date, b.remaining * p.cost_price AS v
                       FROM product_batches b JOIN products p ON p.id = b.product_id
                       WHERE b.remaining > 0.0005 AND b.expiry_date IS NOT NULL AND b.expiry_date < date('now', 'localtime')
                       ORDER BY v DESC""")
    if rows:
        v = money(sum(r["v"] for r in rows))
        return [_f(A_STOCK, "بضاعة منتهية الصلاحية ما زالت في المخزون", "medium" if v > 100 else "low",
                   f"قيمتها بالتكلفة {n(v)}، وهي محسوبة ضمن أصول المحل رغم أنها لا تُباع.",
                   "أتلفها من شاشة الصلاحية (تُسجَّل خسارة)، أو أرجعها للمورد.", v, len(rows),
                   [f"{r['name']}: {r['remaining']:g} (انتهت {r['expiry_date']})" for r in rows])]
    return [_ok(A_STOCK, "الصلاحية", "لا توجد بضاعة منتهية الصلاحية في المخزون.")]


def check_dead_stock(c):
    rows = db.query("""SELECT p.name, p.quantity * p.cost_price AS v, MAX(i.created_at) AS last_sale
                       FROM products p
                       LEFT JOIN invoice_items ii ON ii.product_id = p.id
                       LEFT JOIN invoices i ON i.id = ii.invoice_id
                       WHERE p.quantity > 0 AND p.is_active = 1 AND COALESCE(p.is_service,0)=0
                       GROUP BY p.id HAVING last_sale IS NULL OR julianday(?) - julianday(last_sale) > 90
                       ORDER BY v DESC""", (c.b,))
    v = money(sum(r["v"] or 0 for r in rows))
    if rows and v > 0:
        return [_f(A_STOCK, "بضاعة راكدة (لم تُبع منذ 90 يوماً)", "low",
                   f"قيمتها بالتكلفة {n(v)}. المال المجمّد فيها قد لا يُسترد كاملاً.",
                   "اعمل عليها عرضاً، أو أرجعها للمورد، أو خفّض سعرها.", v, len(rows),
                   [f"{r['name']}: {n(r['v'] or 0)}" for r in rows])]
    return [_ok(A_STOCK, "حركة المخزون", "كل الأصناف الموجودة بيعت خلال آخر 90 يوماً.")]


def check_shrinkage(c):
    loss = c.pl["stock_loss"]
    rate = loss / c.sales if c.sales else 0
    if rate > 0.01:
        return [_f(A_STOCK, "خسائر المخزون (تالف، منتهي، عجز جرد)", "medium" if rate > 0.02 else "low",
                   f"الخسائر {n(loss)} = {round(rate * 100, 2)}% من المبيعات. المعدل الطبيعي للبقالة أقل من 1-2%.",
                   "راجع أسباب التالف والعجز في حركة الأصناف، وقلّل كميات الطلب للأصناف سريعة التلف.", loss)]
    return [_ok(A_STOCK, "خسائر المخزون", f"خسائر المخزون {n(loss)} ({round(rate * 100, 2)}% من المبيعات) ضمن الحد الطبيعي.")]


# ---------------------------------------------------------------------------
# 6) الذمم والشيكات
# ---------------------------------------------------------------------------

def aging(as_of):
    """أعمار ديون العملاء (FIFO: التسديد يُطفئ أقدم دين أولاً). [{name, balance, buckets:[0-30,31-60,61-90,>90]}]"""
    end = date.fromisoformat(as_of)
    rows = db.query("""SELECT t.customer_id, c.name, c.credit_limit, t.amount, date(t.created_at) AS d
                       FROM customer_transactions t JOIN customers c ON c.id = t.customer_id
                       WHERE date(t.created_at) <= date(?) ORDER BY t.customer_id, t.created_at, t.id""", (as_of,))
    per = defaultdict(list)
    info = {}
    for r in rows:
        per[r["customer_id"]].append((r["amount"], r["d"]))
        info[r["customer_id"]] = (r["name"], r["credit_limit"])
    out = []
    for cid, txs in per.items():
        open_debts, credit = [], 0.0
        for amt, d in txs:
            if amt > 0:
                if credit > 0:
                    use = min(credit, amt)
                    amt, credit = amt - use, credit - use
                if amt > 0:
                    open_debts.append([amt, d])
            else:
                pay = -amt
                while pay > 0 and open_debts:
                    use = min(pay, open_debts[0][0])
                    open_debts[0][0] -= use
                    pay -= use
                    if open_debts[0][0] <= 1e-9:
                        open_debts.pop(0)
                credit += pay
        bal = money(sum(a for a, _ in open_debts) - credit)
        if bal <= 0.009:
            continue
        b = [0.0, 0.0, 0.0, 0.0]
        for amt, d in open_debts:
            age = (end - date.fromisoformat(d)).days
            b[0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3] += amt
        name, limit = info[cid]
        out.append({"customer_id": cid, "name": name, "balance": bal, "credit_limit": limit or 0,
                    "buckets": [money(x) for x in b]})
    return sorted(out, key=lambda r: -r["balance"])


def check_receivables_aging(c):
    rows = aging(c.b)
    total = money(sum(r["balance"] for r in rows))
    if total <= 0:
        return [_ok(A_DEBTS, "أعمار الديون", "لا توجد ديون على العملاء.")]
    old = money(sum(r["buckets"][3] for r in rows))
    mid = money(sum(r["buckets"][2] for r in rows))
    provision = money(old * 0.5 + mid * 0.2)
    out = []
    share = old / total
    if share > 0.1:
        out.append(_f(A_DEBTS, "ديون متأخرة أكثر من 90 يوماً", "medium" if share > 0.25 else "low",
                      f"{n(old)} من أصل {n(total)} ({round(share * 100)}%) عمرها أكثر من 90 يوماً. "
                      f"المخصص المقترح للديون المشكوك في تحصيلها: {n(provision)}.",
                      "أرسل تذكيراً جماعياً بواتساب، وأوقف البيع الآجل لهؤلاء حتى يسددوا. "
                      "ما تيقنت أنه لن يُحصَّل سجّله «تسوية» في حساب العميل.", old,
                      len([r for r in rows if r["buckets"][3] > 0]),
                      [f"{r['name']}: {n(r['buckets'][3])} متأخر من {n(r['balance'])}" for r in rows if r["buckets"][3] > 0]))
    else:
        out.append(_ok(A_DEBTS, "أعمار الديون", f"معظم الديون حديثة: المتأخر أكثر من 90 يوماً {n(old)} من {n(total)}."))
    over = [r for r in rows if r["credit_limit"] and r["balance"] > r["credit_limit"] + 0.01]
    if over:
        out.append(_f(A_DEBTS, "عملاء تجاوزوا حد الدين", "low",
                      "البيع الآجل تجاوز الحد المسموح (بإذن مدير أو قبل تحديد الحد).",
                      "راجع حدود الدين، ولا تمنح إذن التجاوز إلا نادراً.", count=len(over),
                      samples=[f"{r['name']}: {n(r['balance'])} (الحد {r['credit_limit']:g})" for r in over]))
    return out


def check_credit_balances(c):
    cust = db.query("""SELECT c.name, SUM(t.amount) AS b FROM customer_transactions t JOIN customers c ON c.id=t.customer_id
                       WHERE date(t.created_at) <= date(?) GROUP BY t.customer_id HAVING b < -0.009""", (c.b,))
    sup = db.query("""SELECT s.name, SUM(t.amount) AS b FROM supplier_transactions t JOIN suppliers s ON s.id=t.supplier_id
                      WHERE date(t.created_at) <= date(?) GROUP BY t.supplier_id HAVING b < -0.009""", (c.b,))
    out = []
    if cust:
        out.append(_f(A_DEBTS, "عملاء لهم رصيد دائن (المحل مدين لهم)", "low",
                      "دفعوا أكثر مما عليهم أو أرجعوا بضاعة على الحساب.", "خصم الرصيد من مشترياتهم القادمة أو أعد لهم المبلغ.",
                      -sum(r["b"] for r in cust), len(cust), [f"{r['name']}: {n(-r['b'])}" for r in cust]))
    if sup:
        out.append(_f(A_DEBTS, "موردون عليهم رصيد لصالح المحل", "low",
                      "دُفع لهم أكثر من فواتيرهم أو أُرجعت لهم بضاعة بعد السداد.", "اطلب المبلغ أو اخصمه من الفاتورة القادمة.",
                      -sum(r["b"] for r in sup), len(sup), [f"{r['name']}: {n(-r['b'])}" for r in sup]))
    return out


def check_cheques(c):
    limit = (date.fromisoformat(c.b) - timedelta(days=3)).isoformat()
    rows = db.query("""SELECT ch.direction, ch.cheque_number, ch.amount, ch.due_date,
                              COALESCE(cu.name, su.name, '') AS party
                       FROM cheques ch LEFT JOIN customers cu ON cu.id = ch.customer_id
                       LEFT JOIN suppliers su ON su.id = ch.supplier_id
                       WHERE ch.status = 'pending' AND ch.due_date < ? ORDER BY ch.due_date""", (limit,))
    bounced = db.query_one(f"SELECT COUNT(*) AS n, SUM(amount) AS a FROM cheques WHERE status='bounced' AND {_in('status_date')}",
                           c.p)
    out = []
    if rows:
        out.append(_f(A_DEBTS, "شيكات تجاوزت تاريخ استحقاقها ولم تُسجَّل", "medium",
                      "شيكات مر استحقاقها ولم تُسجَّل كمصروفة أو راجعة، فأرصدة البنك والذمم قد تكون غير دقيقة.",
                      "راجع كشف البنك وسجّل كل شيك: صُرف أو رجع.", sum(r["amount"] for r in rows), len(rows),
                      [f"{'وارد من' if r['direction'] == 'in' else 'صادر إلى'} {r['party']}: {n(r['amount'])} استحقاق {r['due_date']}"
                       for r in rows]))
    if bounced["n"]:
        out.append(_f(A_DEBTS, "شيكات راجعة في الفترة", "low",
                      f"{bounced['n']} شيك راجع بقيمة {n(bounced['a'])}.", "لا تقبل شيكات جديدة من نفس العميل إلا بضمان.",
                      bounced["a"], bounced["n"]))
    if not out:
        out.append(_ok(A_DEBTS, "الشيكات", "كل الشيكات المستحقة سُجّلت (مصروفة أو راجعة)."))
    return out


# ---------------------------------------------------------------------------
# 7) المصاريف والمشتريات
# ---------------------------------------------------------------------------

def check_expense_duplicates(c):
    rows = db.query(f"""SELECT category, amount, expense_date, COUNT(*) AS n FROM expenses WHERE {_in('expense_date')}
                        GROUP BY category, amount, expense_date HAVING n > 1""", c.p)
    if rows:
        return [_f(A_EXP, "مصاريف مكررة محتملة", "medium",
                   "نفس النوع ونفس المبلغ في نفس اليوم أكثر من مرة: قد تكون الفاتورة سُجّلت مرتين.",
                   "تحقق من المستندات الأصلية واحذف المكرر.", sum(r["amount"] * (r["n"] - 1) for r in rows), len(rows),
                   [f"{r['expense_date']} {r['category']}: {r['amount']} × {r['n']}" for r in rows])]
    return [_ok(A_EXP, "تكرار المصاريف", "لا توجد مصاريف مكررة بنفس النوع والمبلغ والتاريخ.")]


def check_expense_spikes(c):
    rows = db.query(f"""SELECT category, strftime('%Y-%m', expense_date) AS m, SUM(amount) AS t FROM expenses
                        WHERE {_in('expense_date')} GROUP BY category, m""", c.p)
    by = defaultdict(dict)
    for r in rows:
        by[r["category"]][r["m"]] = r["t"]
    out = []
    for cat, months in by.items():
        if len(months) < 4:
            continue
        vals = sorted(months.values())
        med = vals[len(vals) // 2]
        for m, t in months.items():
            if med > 0 and t > 2.5 * med and t - med > 200:
                out.append(f"{cat} في {m}: {n(t)} (المعتاد {n(med)})")
    if out:
        return [_f(A_EXP, "قفزات غير معتادة في المصاريف", "low", "شهور زادت فيها مصاريف نوع معيّن عن ضعفين ونصف معدله.",
                   "تأكد أنها مصاريف حقيقية وموثقة (فاتورة كهرباء، عقد صيانة...).", count=len(out), samples=out)]
    return [_ok(A_EXP, "انتظام المصاريف", "لا توجد قفزات لافتة في المصاريف الشهرية.")]


BENFORD = [math.log10(1 + 1 / d) for d in range(1, 10)]


def benford(amounts):
    """اختبار بنفورد للرقم الأول: يرجع (MAD، التوزيع الفعلي). MAD > 0.015 = عدم مطابقة (معيار Nigrini)"""
    firsts = [int(str(f"{a:.2f}").lstrip("0.")[0]) for a in amounts if a >= 10]
    firsts = [d for d in firsts if 1 <= d <= 9]
    if len(firsts) < 100:
        return None, []
    n = len(firsts)
    actual = [firsts.count(d) / n for d in range(1, 10)]
    return sum(abs(a - e) for a, e in zip(actual, BENFORD)) / 9, actual


def check_benford(c):
    # تُستبعد المبالغ الثابتة المتكررة (إيجار، رواتب، اشتراكات) لأنها لا تخضع للتوزيع الطبيعي
    amounts = [r[0] for r in db.get_connection().execute(
        f"""SELECT amount FROM expenses WHERE {_in('expense_date')}
            AND amount NOT IN (SELECT amount FROM expenses WHERE {_in('expense_date')} GROUP BY amount HAVING COUNT(*) >= 3)
            UNION ALL SELECT total FROM purchases WHERE {_in('created_at')}""", c.p * 3)]
    mad, actual = benford(amounts)
    if mad is None:
        return []
    if mad > 0.015:
        top = max(range(9), key=lambda i: actual[i] - BENFORD[i])
        return [_f(A_EXP, "توزيع مبالغ المصاريف والمشتريات غير معتاد (قانون بنفورد)", "low",
                   f"المبالغ الحقيقية تتبع نمطاً إحصائياً معروفاً للرقم الأول. الانحراف هنا {mad:.3f} (الطبيعي أقل من 0.012). "
                   f"الرقم {top + 1} يتكرر أكثر من المتوقع ({round(actual[top] * 100)}% بدل {round(BENFORD[top] * 100)}%).",
                   "هذا مؤشر إحصائي للفحص وليس دليلاً: قد يسببه مورد يومي بمبالغ متقاربة. "
                   "افحص المبالغ التي تبدأ بهذا الرقم للتأكد أنها حقيقية وغير مقدّرة.", count=len(amounts))]
    return [_ok(A_EXP, "قانون بنفورد", f"مبالغ المصاريف والمشتريات تتبع التوزيع الطبيعي (الانحراف {mad:.3f}).")]


def check_manual_entries(c):
    rows = db.query(f"""SELECT e.entry_number, e.entry_date, e.description, e.is_void,
                               (SELECT SUM(debit) FROM journal_lines l WHERE l.entry_id = e.id) AS amt
                        FROM journal_entries e WHERE {_in('e.entry_date')} ORDER BY e.entry_date""", c.p)
    if not rows:
        return [_ok(A_BOOKS, "القيود اليدوية", "لا توجد قيود يدوية في الفترة؛ كل القيود مولّدة من العمليات.")]
    void = [r for r in rows if r["is_void"]]
    return [_f(A_BOOKS, "قيود يدوية تحتاج مراجعة", "low",
               f"{len(rows)} قيداً يدوياً ({len(void)} ملغى). القيود اليدوية أول ما يراجعه المدقق لأنها لا تأتي من مستند.",
               "تأكد أن لكل قيد مستنداً (عقد، كشف بنك، فاتورة).", None, len(rows), [f"{r['entry_number']} {r['entry_date']}: {r['description']} ({n(r['amt'] or 0)})"
                           + (" — ملغى" if r["is_void"] else "") for r in rows])]


def check_deletions(c):
    rows = db.query(f"""SELECT action, COUNT(*) AS n FROM audit_log WHERE action IN ('حذف منتج','حذف مصروف','حذف عميل')
                        AND {_in('created_at')} GROUP BY action""", c.p)
    if rows:
        return [_f(A_CONTROL, "عمليات حذف", "low", "حُذفت سجلات خلال الفترة (كل حذف مسجّل باسم من قام به).",
                   "راجع سجل العمليات وتأكد أن الحذف كان مبرراً.", count=sum(r["n"] for r in rows),
                   samples=[f"{r['action']}: {r['n']}" for r in rows])]
    return []


# ---------------------------------------------------------------------------
# 8) المراجعة التحليلية
# ---------------------------------------------------------------------------

def check_margin_trend(c):
    rows = [r for r in reports.period_summary(c.a, c.b, "month") if r["net_sales"] > 1000]
    if len(rows) < 3:
        return []
    margins = sorted(r["margin"] for r in rows)
    med = margins[len(margins) // 2]
    odd = [r for r in rows if abs(r["margin"] - med) > 5]
    if odd:
        return [_f(A_TREND, "شهور هامش ربحها بعيد عن المعتاد", "medium",
                   f"الهامش المعتاد {med}%. الانخفاض المفاجئ يعني غالباً سرقة بضاعة أو بيعاً بأسعار قديمة أو مشتريات غير مسجلة، "
                   "والارتفاع المفاجئ قد يعني مشتريات لم تُسجَّل أو أخطاء تكلفة.",
                   "قارن هذه الشهور بالجرد وبفواتير الموردين.", count=len(odd),
                   samples=[f"{r['period']}: {r['margin']}%" for r in odd])]
    return [_ok(A_TREND, "استقرار هامش الربح", f"هامش الربح الشهري مستقر حول {med}%.")]


def check_cash_ratio(c):
    rows = [r for r in reports.period_summary(c.a, c.b, "month") if r["net_sales"] > 1000]
    if len(rows) < 4:
        return []
    ratios = [r["cash"] / r["net_sales"] for r in rows]
    med = sorted(ratios)[len(ratios) // 2]
    last = rows[-1]
    lr = last["cash"] / last["net_sales"]
    if med > 0.2 and lr < med * 0.7:
        return [_f(A_TREND, "انخفاض مفاجئ في المبيعات النقدية", "low",
                   f"نسبة المبيعات النقدية في {last['period']} {round(lr * 100)}% والمعتاد {round(med * 100)}%. "
                   "إن لم يتحول الزبائن فعلاً للدفع الإلكتروني فقد تكون مبيعات نقدية لا تُسجَّل.",
                   "راقب الكاشير في ساعات الذروة وقارن عدد الزبائن بعدد الفواتير.")]
    return [_ok(A_TREND, "نسبة المبيعات النقدية", "نسبة المبيعات النقدية مستقرة عبر الشهور.")]


# ---------------------------------------------------------------------------
# 9) الضريبة وبيئة الرقابة
# ---------------------------------------------------------------------------

def check_vat(c):
    if not settings.get_bool("vat_enabled"):
        return []
    due = money(-c.balance(ledger.VAT) - c.balance(ledger.VAT_INPUT))
    last = db.scalar("""SELECT MAX(e.entry_date) FROM journal_entries e JOIN journal_lines l ON l.entry_id = e.id
                        WHERE e.is_void = 0 AND l.account_code = ? AND l.debit > 0""", (ledger.VAT,))
    age = (date.fromisoformat(c.b) - date.fromisoformat(last)).days if last else None
    if due > 0 and (age is None or age > 62):
        return [_f(A_TAX, "ضريبة مستحقة لم تُسوَّ منذ مدة", "medium",
                   f"صافي الضريبة المستحقة في الدفاتر {n(due)}"
                   + (f"، وآخر تسوية قبل {age} يوماً." if age is not None else "، ولم تُسجَّل أي تسوية أو دفعة ضريبة."),
                   "عند تقديم الإقرار سجّل «مقاصة ضريبة المدخلات» ثم «دفع الضريبة المستحقة» من العمليات المالية الجاهزة.", due)]
    return [_ok(A_TAX, "الضريبة", f"صافي الضريبة المستحقة {n(due)}، والتسويات منتظمة.")]


def check_backups(c):
    from core import backup
    try:
        files = backup.list_backups()
    except Exception:
        files = []
    if not files:
        return [_f(A_CONTROL, "لا توجد نسخ احتياطية", "high", "إذا تعطل القرص أو سُرق الجهاز تضيع كل البيانات.",
                   "الإعدادات ← النسخ الاحتياطي: فعّل النسخة الثانية على فلاشة أو Google Drive.")]
    newest = datetime.strptime(files[0][2], "%Y-%m-%d %H:%M")
    days = (datetime.now() - newest).days
    out = []
    if days > 2:
        out.append(_f(A_CONTROL, "آخر نسخة احتياطية قديمة", "medium", f"آخر نسخة قبل {days} يوماً.",
                      "افتح البرنامج يومياً على الجهاز الرئيسي (ينسخ وحده)، أو انسخ الآن من الإعدادات."))
    if not settings.get("backup_mirror_dir"):
        out.append(_f(A_CONTROL, "النسخ الاحتياطي على نفس الجهاز فقط", "low",
                      "النسخ موجودة على نفس القرص؛ إذا تعطل الجهاز تضيع معه.",
                      "حدّد مجلداً ثانياً (فلاشة أو Google Drive) في إعدادات النسخ الاحتياطي."))
    if not out:
        out.append(_ok(A_CONTROL, "النسخ الاحتياطي", "نسخ يومية حديثة، ونسخة ثانية خارج الجهاز."))
    return out


def check_users(c):
    rows = db.query("""SELECT u.username, u.role FROM users u WHERE u.is_active = 1""")
    admins = [r for r in rows if r["role"] == "admin"]
    shared = db.query_one(f"""SELECT COUNT(DISTINCT user_id) AS n FROM invoices WHERE {_in('created_at')}""", c.p)["n"]
    shifts_users = db.query_one(f"SELECT COUNT(DISTINCT user_id) AS n FROM shifts WHERE {_in('opened_at')}", c.p)["n"]
    out = []
    if len(rows) == 1 and shifts_users <= 1 and db.scalar(f"SELECT COUNT(*) FROM invoices WHERE {_in('created_at')}", c.p) > 3000:
        out.append(_f(A_CONTROL, "كل العمل باسم مستخدم واحد", "low",
                      "عند وجود أكثر من كاشير باسم واحد لا يمكن معرفة من سبّب العجز أو الخصم أو المرتجع.",
                      "أنشئ مستخدماً لكل كاشير بصلاحيات «كاشير» فقط."))
    if len(admins) > 2:
        out.append(_f(A_CONTROL, "عدد كبير من المديرين", "low", f"{len(admins)} مستخدمين بصلاحية مدير كاملة.",
                      "اجعل صلاحية المدير لصاحب المحل ونائبه فقط.", count=len(admins),
                      samples=[r["username"] for r in admins]))
    _ = shared
    return out


CHECKS = [check_books_balance, check_receivables, check_payables, check_inventory_value, check_impossible_balances,
          check_manual_entries, check_sequences, check_invoice_integrity, check_duplicate_refs, check_shifts,
          check_cash_refund_on_electronic, check_refunds_by_cashier, check_drawer_and_prices, check_discounts,
          check_below_cost, check_expired_stock, check_dead_stock, check_shrinkage, check_receivables_aging,
          check_credit_balances, check_cheques, check_expense_duplicates, check_expense_spikes, check_benford,
          check_margin_trend, check_cash_ratio, check_vat, check_deletions, check_backups, check_users]


def run(date_from, date_to, progress=None):
    """تنفيذ كل إجراءات التدقيق على الفترة. يرجع التقرير كاملاً"""
    c = _Ctx(date_from, date_to)
    findings = []
    for i, chk in enumerate(CHECKS):
        try:
            findings += chk(c)
        except Exception as e:  # فحص واحد متعثر لا يوقف التقرير
            findings.append(_f(A_CONTROL, "تعذر تنفيذ أحد الفحوص", "low", f"{chk.__name__}: {e}"))
        if progress:
            progress(i + 1, len(CHECKS))
    findings.sort(key=lambda f: (ORDER.index(f["severity"]), AREAS.index(f["area"]) if f["area"] in AREAS else 99))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ORDER}
    score = max(0, 100 - sum(WEIGHT[f["severity"]] for f in findings))
    if counts["critical"]:
        opinion, text = "رأي سلبي", ("في الدفاتر خلل جوهري يجعل القوائم المالية غير موثوقة. عالج الملاحظات الحرجة أولاً ثم أعد التدقيق.")
    elif counts["high"]:
        opinion, text = "رأي متحفظ", ("القوائم المالية تعبّر بعدالة عن وضع المحل، باستثناء الملاحظات المرتفعة الخطورة "
                                      "التي تحتاج معالجة ومتابعة.")
    else:
        opinion, text = "رأي نظيف", ("القوائم المالية تعبّر بعدالة، من جميع النواحي الجوهرية، عن المركز المالي للمحل "
                                     "ونتيجة أعماله للفترة. الملاحظات الواردة للتحسين.")
    grade = "ممتاز" if score >= 90 else "جيد" if score >= 75 else "مقبول" if score >= 60 else "ضعيف"
    bs = ledger.balance_sheet(date_to)
    return {"date_from": date_from, "date_to": date_to, "generated_at": db.now(), "score": score, "grade": grade,
            "opinion": opinion, "opinion_text": text, "counts": counts, "findings": findings,
            "procedures": len(CHECKS),
            "summary": {"net_sales": c.pl["net_sales"], "net_profit": c.pl["net_profit"],
                        "gross_margin": c.pl["gross_margin"], "assets": bs.get("total_assets"),
                        "liabilities": bs.get("total_liabilities"), "equity": bs.get("total_equity")}}


def report_html(r, shop_name=""):
    """تقرير التدقيق للطباعة (A4)"""
    from html import escape
    colors = {"critical": "#B42318", "high": "#C4320A", "medium": "#B54708", "low": "#175CD3", "ok": "#067647"}
    s = r["summary"]

    def m(v):
        return "—" if v is None else f"{v:,.2f}"
    rows = ""
    for area in AREAS:
        items = [f for f in r["findings"] if f["area"] == area]
        if not items:
            continue
        rows += f"<h3 style='margin:14px 0 4px'>{escape(area)}</h3>"
        for f in items:
            sev = f["severity"]
            extra = ""
            if f["amount"] is not None:
                extra += f" — المبلغ: {m(f['amount'])}"
            if f["count"]:
                extra += f" — العدد: {f['count']}"
            samples = "".join(f"<li>{escape(x)}</li>" for x in f["samples"][:6])
            rows += (f"<div style='border-right:4px solid {colors[sev]};padding:4px 10px;margin:6px 0'>"
                     f"<b style='color:{colors[sev]}'>[{SEVERITY[sev]}]</b> <b>{escape(f['title'])}</b>{extra}<br>"
                     f"{escape(f['detail'])}"
                     + (f"<br><i>الإجراء المقترح: {escape(f['action'])}</i>" if f["action"] else "")
                     + (f"<ul style='margin:2px 0'>{samples}</ul>" if samples else "") + "</div>")
    c = r["counts"]
    return (f"<html><body dir='rtl' style='font-family:Tahoma;font-size:10pt'>"
            f"<h2 style='text-align:center;margin-bottom:0'>تقرير التدقيق المالي</h2>"
            f"<p style='text-align:center;margin-top:2px'>{escape(shop_name)}<br>الفترة من {r['date_from']} إلى {r['date_to']}"
            f" — أُعدّ في {r['generated_at'][:16]}</p>"
            f"<table width='100%' border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse'>"
            f"<tr><td><b>الرأي</b></td><td><b>{escape(r['opinion'])}</b> — {escape(r['opinion_text'])}</td></tr>"
            f"<tr><td><b>الدرجة</b></td><td>{r['score']} / 100 ({escape(r['grade'])}) — {r['procedures']} إجراء تدقيق</td></tr>"
            f"<tr><td><b>الملاحظات</b></td><td>حرج {c['critical']} • مرتفع {c['high']} • متوسط {c['medium']} • "
            f"منخفض {c['low']} • سليم {c['ok']}</td></tr>"
            f"<tr><td><b>صافي المبيعات</b></td><td>{m(s['net_sales'])}</td></tr>"
            f"<tr><td><b>صافي الربح</b></td><td>{m(s['net_profit'])} (هامش إجمالي {s['gross_margin']}%)</td></tr>"
            f"<tr><td><b>الأصول / الالتزامات / حق المالك</b></td><td>{m(s['assets'])} / {m(s['liabilities'])} / {m(s['equity'])}</td></tr>"
            f"</table>{rows}"
            f"<p style='color:#667085;font-size:8pt;margin-top:16px'>تدقيق آلي يطبّق إجراءات المراجعة المعتادة على كل "
            f"العمليات المسجّلة في البرنامج (وليس على عيّنة منها). لا يرى ما لم يُسجَّل أصلاً، ولا يغني عن الجرد الفعلي "
            f"وعدّ الصندوق. الشركات التي يُلزمها القانون بتقرير مدقق مرخّص تقدّم هذا التقرير له ليختصر عمله.</p>"
            f"</body></html>")
