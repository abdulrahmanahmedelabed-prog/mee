# -*- coding: utf-8 -*-
"""
المحاسب الآلي: ما يفعله المحاسب كل شهر، يقوم به البرنامج وحده.

- الأصول الثابتة (أثاث، ثلاجات، كاشير، سيارة...) مع إهلاك شهري تلقائي بالقسط الثابت، والبيع/الاستبعاد.
- قائمة التدفقات النقدية (من أين جاء النقد وأين ذهب).
- إقفال الشهر بضغطة: تدقيق كامل للشهر، ثم حزمة القوائم المالية للطباعة، ثم قفل الدفاتر حتى نهايته
  (لا يمكن بعدها إضافة أو حذف قيد أو مصروف بتاريخ داخل فترة مقفلة — كما يفعل المحاسب والمدقق).
- تدقيق يومي تلقائي في الخلفية مع تنبيه عند ملاحظة مهمة.
"""

import calendar
from datetime import date, timedelta

from core import db, audit
from core.utils import money

ACC_DEPRECIATION = "1590"

PAY_SOURCES = {"1110": "نقداً من الصندوق", "1120": "من البنك", "3120": "دفعها المالك من جيبه",
               "2110": "دين على المحل (للمورد)", "2310": "بقرض", "": "مسجّل مسبقاً في الدفاتر (بلا قيد شراء)"}


# ---------------------------------------------------------------------------
# قفل الفترات
# ---------------------------------------------------------------------------

def locked_until():
    return db.get_meta("books_locked_until") or ""


def assert_open(day, what="العملية"):
    """يرفع خطأ إن كان التاريخ داخل فترة مقفلة"""
    lock = locked_until()
    if lock and day and str(day)[:10] <= lock:
        raise ValueError(f"الدفاتر مقفلة حتى {lock}: لا يمكن تسجيل أو تعديل {what} بتاريخ {str(day)[:10]}.\n"
                         f"سجّلها بتاريخ اليوم، أو افتح الفترة من المحاسبة ← إقفال الشهر (يحتاج صلاحية المحاسبة).")


def lock_books(until):
    until = str(until)[:10]
    date.fromisoformat(until)
    if until >= db.today():
        raise ValueError("لا يمكن قفل فترة لم تنتهِ بعد")
    old = locked_until()
    db.set_meta("books_locked_until", until)
    audit.log("قفل الدفاتر", f"حتى {until} (كانت {old or 'مفتوحة'})")
    return until


def unlock_books(until=None):
    """فتح الفترة (أو إرجاع القفل لتاريخ أقدم) — يُسجَّل في سجل العمليات"""
    old = locked_until()
    new = str(until)[:10] if until else ""
    if new and old and new >= old:
        return old
    db.set_meta("books_locked_until", new or None)
    audit.log("فتح الدفاتر", f"من {old or '-'} إلى {new or 'مفتوحة بالكامل'}")
    return new


# ---------------------------------------------------------------------------
# الأصول الثابتة والإهلاك
# ---------------------------------------------------------------------------

def _month_end(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return _month_end(d.year + y, m + 1)


def schedule(asset, upto=None):
    """أقساط الإهلاك [(نهاية الشهر، المبلغ)] حتى upto (افتراضياً اليوم). يبدأ من نهاية شهر الشراء
    للأصول المشتراة في النصف الأول من الشهر، وإلا من الشهر التالي، ويتوقف عند البيع أو انتهاء العمر"""
    upto = date.fromisoformat(str(upto)[:10]) if upto else date.fromisoformat(db.today())
    bought = date.fromisoformat(asset["purchase_date"][:10])
    base = money(asset["cost"] - (asset["salvage"] or 0))
    life = int(asset["life_months"] or 0)
    if base <= 0 or life <= 0:
        return []
    first = _month_end(bought.year, bought.month) if bought.day <= 15 else _add_months(bought, 1)
    stop = date.fromisoformat(asset["disposed_at"][:10]) if asset["disposed_at"] else None
    monthly = money(base / life)
    out, done = [], 0.0
    for k in range(life):
        d = _add_months(first, k) if k else first
        if d > upto or (stop and d > _month_end(stop.year, stop.month)):
            break
        if stop and d > stop:
            d = stop                                  # قسط شهر البيع حتى تاريخه
        amt = money(base - done) if k == life - 1 else monthly
        out.append((d.isoformat(), amt))
        done = money(done + amt)
    return out


def add_asset(name, cost, purchase_date, life_years, salvage=0.0, paid_from="1110", note=""):
    name = (name or "").strip()
    cost, salvage = money(cost), money(salvage or 0)
    if not name:
        raise ValueError("اكتب اسم الأصل")
    if cost <= 0:
        raise ValueError("التكلفة يجب أن تكون أكبر من صفر")
    if salvage < 0 or salvage >= cost:
        raise ValueError("القيمة المتبقية (الخردة) يجب أن تكون أقل من التكلفة")
    life = int(round(float(life_years) * 12))
    if life < 1 or life > 600:
        raise ValueError("العمر الإنتاجي بين شهر و50 سنة")
    purchase_date = str(purchase_date or db.today())[:10]
    date.fromisoformat(purchase_date)
    if paid_from not in PAY_SOURCES:
        raise ValueError("اختر طريقة الدفع")
    if paid_from:
        assert_open(purchase_date, "شراء أصل")
    from core import auth
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO fixed_assets(name, cost, salvage, purchase_date, life_months, paid_from, note,
                                                        user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (name, cost, salvage, purchase_date, life, paid_from or None, note or "",
                            auth.current_user_id(), db.now()))
        audit.log("إضافة أصل ثابت", f"{name} بتكلفة {cost} وعمر {life} شهراً", conn)
    return cur.lastrowid


def dispose_asset(asset_id, disposal_date=None, proceeds=0.0, received_into="1110"):
    """بيع الأصل أو استبعاده: يُلغى من الدفاتر، والفرق بين ثمن البيع وقيمته الدفترية ربح أو خسارة"""
    disposal_date = str(disposal_date or db.today())[:10]
    date.fromisoformat(disposal_date)
    assert_open(disposal_date, "بيع أصل")
    a = db.query_one("SELECT * FROM fixed_assets WHERE id=?", (asset_id,))
    if not a:
        raise ValueError("الأصل غير موجود")
    if a["disposed_at"]:
        raise ValueError("هذا الأصل مستبعد من قبل")
    if disposal_date < a["purchase_date"][:10]:
        raise ValueError("تاريخ البيع قبل تاريخ الشراء")
    with db.tx() as conn:
        conn.execute("UPDATE fixed_assets SET disposed_at=?, disposal_proceeds=?, disposal_account=? WHERE id=?",
                     (disposal_date, money(proceeds or 0), received_into if proceeds else None, asset_id))
        audit.log("بيع/استبعاد أصل", f"{a['name']} بتاريخ {disposal_date} بمبلغ {money(proceeds or 0)}", conn)


def list_assets(as_of=None):
    rows = []
    for a in db.query("SELECT * FROM fixed_assets ORDER BY purchase_date, id"):
        sch = schedule(a, as_of)
        acc = money(sum(x[1] for x in sch))
        d = dict(a)
        d.update({"accumulated": acc, "book_value": money(a["cost"] - acc) if not a["disposed_at"] else 0.0,
                  "monthly": money((a["cost"] - (a["salvage"] or 0)) / a["life_months"]) if a["life_months"] else 0.0,
                  "months_done": len(sch), "paid_from_name": PAY_SOURCES.get(a["paid_from"] or "", "")})
        rows.append(d)
    return rows


def ledger_entries(date_from=None, date_to=None):
    """قيود الأصول المولّدة تلقائياً (شراء، إهلاك شهري، بيع) بصيغة ledger.entries"""
    from core import ledger
    out = []

    def inside(day):
        return (not date_from or day >= date_from[:10]) and (not date_to or day <= date_to[:10])
    upto = min(date_to[:10], db.today()) if date_to else db.today()
    for a in db.query("SELECT * FROM fixed_assets"):
        ref = f"FA-{a['id']}"
        if a["paid_from"] and inside(a["purchase_date"][:10]):
            out.append({"date": a["purchase_date"][:10] + " 00:00:00", "ref": ref, "description": f"شراء أصل: {a['name']}",
                        "source": "asset", "lines": [(ledger.FIXED_ASSETS, money(a["cost"]), 0.0),
                                                     (a["paid_from"], 0.0, money(a["cost"]))]})
        acc = 0.0
        for day, amt in schedule(a, upto):
            acc = money(acc + amt)
            if inside(day):
                out.append({"date": day + " 23:59:00", "ref": ref, "description": f"إهلاك شهري: {a['name']}",
                            "source": "asset", "lines": [(ledger.DEPRECIATION, amt, 0.0), (ACC_DEPRECIATION, 0.0, amt)]})
        if a["disposed_at"] and inside(a["disposed_at"][:10]) and a["disposed_at"][:10] <= upto:
            cost, proceeds = money(a["cost"]), money(a["disposal_proceeds"] or 0)
            book = money(cost - acc)
            lines = [(ACC_DEPRECIATION, acc, 0.0), (ledger.FIXED_ASSETS, 0.0, cost)]
            if proceeds:
                lines.append((a["disposal_account"] or ledger.CASH, proceeds, 0.0))
            diff = money(proceeds - book)
            if diff > 0:
                lines.append((ledger.OTHER_INCOME, 0.0, diff))
            elif diff < 0:
                lines.append((ledger.ADJUSTMENTS, -diff, 0.0))
            out.append({"date": a["disposed_at"][:10] + " 23:59:30", "ref": ref,
                        "description": f"بيع/استبعاد أصل: {a['name']}", "source": "asset",
                        "lines": [ln for ln in lines if ln[1] or ln[2]]})
    return out


# ---------------------------------------------------------------------------
# قائمة التدفقات النقدية (الطريقة غير المباشرة)
# ---------------------------------------------------------------------------

CASH_ACCOUNTS = ("1110", "1120", "1140")


def _cf_section(code):
    if code == ACC_DEPRECIATION:
        return "operating"
    if code.startswith("15"):
        return "investing"
    if code.startswith("23") or code.startswith("3"):
        return "financing"
    return "operating"


def cash_flow(date_from, date_to):
    from core import ledger
    names = ledger._names()
    bal = ledger._balances(date_from, date_to)
    pl = ledger.income_statement(date_from, date_to)
    sections = {"operating": [], "investing": [], "financing": []}
    cash_open = cash_close = 0.0
    for code, (opening, d, c) in sorted(bal.items()):
        t = ledger.account_type(code)
        if t in ("revenue", "expense"):
            continue
        if code in CASH_ACCOUNTS:
            cash_open += opening
            cash_close += opening + d - c
            continue
        effect = money(-(d - c))                 # زيادة أصل غير نقدي تستهلك نقداً، وزيادة التزام توفّره
        if abs(effect) >= 0.005:
            label = ledger.account_name(code, names)
            if code == ACC_DEPRECIATION:
                label = "إضافة الإهلاك (مصروف لا يُدفع نقداً)"
            sections[_cf_section(code)].append({"code": code, "name": label, "amount": effect})
    net_income = money(pl["net_income"])
    sections["operating"].insert(0, {"code": "", "name": "صافي الربح للفترة", "amount": net_income})
    totals = {k: money(sum(x["amount"] for x in v)) for k, v in sections.items()}
    change = money(sum(totals.values()))
    actual = money(cash_close - cash_open)
    return {"date_from": date_from, "date_to": date_to, "sections": sections, "totals": totals,
            "net_change": change, "cash_open": money(cash_open), "cash_close": money(cash_close),
            "reconciled": abs(change - actual) < 0.05}


# ---------------------------------------------------------------------------
# إقفال الشهر
# ---------------------------------------------------------------------------

def month_range(y, m):
    return date(y, m, 1).isoformat(), _month_end(y, m).isoformat()


def status():
    """حالة الإقفال: آخر يوم مقفل، وأقدم شهر منتهٍ لم يُقفل بعد"""
    lock = locked_until()
    today = date.fromisoformat(db.today())
    last_done = _add_months(date(today.year, today.month, 1), -1)        # نهاية الشهر الماضي
    first_sale = db.scalar("SELECT MIN(date(created_at)) FROM invoices")
    if lock:
        nxt = date.fromisoformat(lock) + timedelta(days=1)
    elif first_sale:
        nxt = date.fromisoformat(first_sale)
    else:
        nxt = None
    pending = []
    if nxt:
        d = date(nxt.year, nxt.month, 1)
        while _month_end(d.year, d.month) <= last_done and len(pending) < 1200:
            pending.append((d.year, d.month))
            d = _month_end(d.year, d.month) + timedelta(days=1)
    return {"locked_until": lock, "pending": pending, "next": pending[0] if pending else None}


def close_month(year, month, force=False):
    """إقفال حتى نهاية شهر: تدقيق كامل لكل ما لم يُقفل حتى نهايته، ثم قفل الدفاتر.
    إن كانت عدة أشهر منتهية بانتظار الإقفال تُقفل كلها معاً حتى الشهر المختار.
    لا يُقفل مع ملاحظات حرجة إلا بتأكيد صاحب المحل (force)"""
    from core import financial_audit
    _, b = month_range(int(year), int(month))
    if b >= db.today():
        raise ValueError("لا يمكن إقفال شهر لم ينتهِ بعد")
    lock = locked_until()
    if lock and b <= lock:
        raise ValueError(f"هذا الشهر مقفل من قبل (الدفاتر مقفلة حتى {lock})")
    st = status()
    if lock:
        a = (date.fromisoformat(lock) + timedelta(days=1)).isoformat()
    elif st["pending"]:
        a = month_range(*st["pending"][0])[0]
    else:
        a = month_range(int(year), int(month))[0]
    a = min(a, month_range(int(year), int(month))[0])
    r = financial_audit.run(a, b)
    if r["counts"]["critical"] and not force:
        return {"closed": False, "audit": r, "date_from": a, "date_to": b}
    lock_books(b)
    if r["counts"]["critical"]:
        audit.log("إقفال مع ملاحظات حرجة", f"{a} - {b} بقرار صاحب المحل")
    return {"closed": True, "audit": r, "date_from": a, "date_to": b}


def package_html(date_from, date_to, audit_result=None, shop_name=""):
    """حزمة نهاية الشهر: قائمة الدخل، الميزانية، التدفقات النقدية، إقرار الضريبة، ميزان المراجعة، ورأي المدقق"""
    from html import escape
    from core import ledger, reports, branding, i18n
    from core.utils import fmt_money
    tr = i18n.tr

    def mny(v):
        return escape(fmt_money(v))

    def table(rows, head=None):
        h = "".join(f"<th>{escape(tr(x))}</th>" for x in head) if head else ""
        body = "".join("<tr>" + "".join(
            f"<td style='{'text-align:left' if isinstance(c, (int, float)) else ''}{';font-weight:700' if bold else ''}'>"
            f"{mny(c) if isinstance(c, (int, float)) else escape(tr(str(c)))}</td>" for c in cells) + "</tr>"
            for cells, bold in rows)
        return (f"<table width='100%' border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;"
                f"margin-bottom:14px'>{('<tr style=background:#eee>' + h + '</tr>') if h else ''}{body}</table>")

    s = ledger.income_statement(date_from, date_to)
    is_rows = [(("المبيعات", s["sales"]), False), (("مردودات المبيعات", -s["returns"]), False),
               (("صافي المبيعات", s["net_sales"]), True), (("تكلفة البضاعة المباعة", -s["cogs"]), False),
               (("مجمل الربح", s["gross_profit"]), True), (("إيرادات أخرى", s["other_income"]), False)]
    is_rows += [((e["name"], -e["amount"]), False) for e in s["expenses"]]
    is_rows += [(("صافي الربح", s["net_income"]), True)]

    bs = ledger.balance_sheet(date_to)
    bs_rows = []
    for title, items, total in (("الأصول", bs["assets"], bs["total_assets"]),
                                ("الالتزامات", bs["liabilities"], bs["total_liabilities"]),
                                ("حقوق الملكية", bs["equity"], bs["total_equity"])):
        bs_rows.append(((title, ""), True))
        bs_rows += [((f"    {x['name']}", x["amount"]), False) for x in items]
        bs_rows.append(((f"مجموع {title}", total), True))

    cf = cash_flow(date_from, date_to)
    cf_rows = []
    for key, title in (("operating", "التدفقات من التشغيل"), ("investing", "التدفقات من الاستثمار"),
                       ("financing", "التدفقات من التمويل")):
        cf_rows.append(((title, ""), True))
        cf_rows += [((f"    {x['name']}", x["amount"]), False) for x in cf["sections"][key]]
        cf_rows.append(((f"صافي {title}", cf["totals"][key]), True))
    cf_rows += [(("النقد أول الفترة", cf["cash_open"]), False), (("صافي التغير في النقد", cf["net_change"]), True),
                (("النقد آخر الفترة", cf["cash_close"]), True)]

    v = reports.vat_report(date_from, date_to)
    vat_rows = [(("ضريبة المبيعات (المخرجات)", v["output_tax"]), False),
                (("ضريبة المشتريات (المدخلات)", v["input_tax"]), False),
                (("الصافي المستحق للدفع", v["net_due"]), True)]

    tb = ledger.trial_balance(date_from, date_to)["totals"]
    tb_rows = [(("مجموع المدين", tb["debit"]), False), (("مجموع الدائن", tb["credit"]), False),
               (("ميزان المراجعة متوازن" if tb["balanced"] else "ميزان المراجعة غير متوازن!", ""), True)]

    body = (f"<h3>{escape(tr('قائمة الدخل'))}</h3>{table(is_rows)}"
            f"<h3>{escape(tr('الميزانية العمومية'))} — {escape(date_to)}</h3>{table(bs_rows)}"
            f"<h3>{escape(tr('قائمة التدفقات النقدية'))}</h3>{table(cf_rows)}"
            f"<h3>{escape(tr('إقرار ضريبة القيمة المضافة'))}</h3>{table(vat_rows)}"
            f"<h3>{escape(tr('ميزان المراجعة'))}</h3>{table(tb_rows)}")
    if audit_result:
        r = audit_result
        body += (f"<h3>{escape(tr('رأي المدقق المالي الآلي'))}</h3>"
                 f"<p><b>{escape(tr(r['opinion']))}</b> — {escape(tr(r['opinion_text']))}</p>"
                 f"<p>{escape(tr('الدرجة'))}: {r['score']}/100 ({escape(tr(r['grade']))}) • "
                 f"{escape(tr('إجراءات التدقيق'))}: {r['procedures']}</p>")
        top = [f for f in r["findings"] if f["severity"] in ("critical", "high", "medium")][:12]
        if top:
            body += "<ul>" + "".join(f"<li><b>{escape(tr(f['title']))}</b>: {escape(tr(f['detail']))}</li>" for f in top) + "</ul>"
    body += (f"<p style='color:#666;font-size:8pt'>{escape(tr('أُعدّت هذه الحزمة آلياً من دفاتر البرنامج. الدفاتر مقفلة حتى'))} "
             f"{escape(locked_until() or '-')}.</p>")
    html = branding.document(body, tr("حزمة إقفال الشهر"), tr(f"من {date_from} إلى {date_to}"))
    return i18n.tr_html(html)


# ---------------------------------------------------------------------------
# التدقيق اليومي التلقائي
# ---------------------------------------------------------------------------

def daily_audit(days=30, force=False):
    """يُشغَّل مرة يومياً في الخلفية على جهاز المحل الرئيسي: تدقيق آخر 30 يوماً. يرجع الملخص المحفوظ"""
    import json
    from core import financial_audit
    saved = db.get_meta("auto_audit")
    try:
        saved = json.loads(saved) if saved else None
    except ValueError:
        saved = None
    if saved and saved.get("date") == db.today() and not force:
        return saved
    b = db.today()
    a = (date.fromisoformat(b) - timedelta(days=days - 1)).isoformat()
    r = financial_audit.run(a, b)
    top = [{"title": f["title"], "severity": f["severity"]} for f in r["findings"]
           if f["severity"] in ("critical", "high")][:5]
    out = {"date": b, "from": a, "to": b, "score": r["score"], "critical": r["counts"]["critical"],
           "high": r["counts"]["high"], "top": top}
    db.set_meta("auto_audit", json.dumps(out, ensure_ascii=False))
    return out


# ---------------------------------------------------------------------------
# المؤشرات المالية (ما يحسبه المحاسب ويشرحه لصاحب المحل)
# ---------------------------------------------------------------------------

def _bal_at(bal, prefixes):
    tot = 0.0
    for code, (opening, d, c) in bal.items():
        if any(code.startswith(p) for p in prefixes):
            tot += opening + d - c
    return money(tot)


def ratios(date_from, date_to):
    """مؤشرات الأداء والسيولة مع حكم (جيد/انتبه/خطر) وشرح بسيط لكل مؤشر"""
    from core import ledger
    a, b = date.fromisoformat(date_from[:10]), date.fromisoformat(date_to[:10])
    n = max(1, (b - a).days + 1)
    pl = ledger.income_statement(date_from, date_to)
    bal = ledger._balances(None, date_to)
    sales = pl["net_sales"] or 0.0
    cogs = pl["cogs"] or 0.0
    cash = _bal_at(bal, ("1110", "1120", "1140"))
    inventory = _bal_at(bal, ("13",))
    receivables = _bal_at(bal, ("1210", "1130"))
    current_assets = _bal_at(bal, ("11", "12", "13", "14"))
    current_liab = -_bal_at(bal, ("21", "22"))
    payables = -_bal_at(bal, ("2110", "2120"))
    equity = -_bal_at(bal, ("3",)) + money(-sum(v[0] + v[1] - v[2] for k, v in bal.items()
                                                if ledger.account_type(k) in ("revenue", "expense")))
    opex = pl["total_expenses"] or 0.0
    out = []

    def add(key, name, value, fmt, verdict, explain):
        out.append({"key": key, "name": name, "value": value, "display": fmt, "verdict": verdict, "explain": explain})

    def pct(x):
        return f"{x:.1f}%"
    gm = pl["gross_profit"] / sales * 100 if sales else 0.0
    add("gross_margin", "هامش الربح الإجمالي", gm, pct(gm), "good" if gm >= 18 else "watch" if gm >= 12 else "bad",
        "من كل 100 تبيعها، كم يبقى بعد تكلفة البضاعة. البقالات والسوبرماركت عادة 15–25%.")
    nm = pl["net_income"] / sales * 100 if sales else 0.0
    add("net_margin", "هامش صافي الربح", nm, pct(nm), "good" if nm >= 4 else "watch" if nm >= 1 else "bad",
        "ما يبقى لك فعلاً بعد كل المصاريف. أقل من 1% يعني أن المحل بالكاد يغطي نفسه.")
    er = opex / sales * 100 if sales else 0.0
    add("expense_ratio", "نسبة المصاريف إلى المبيعات", er, pct(er), "good" if er <= 14 else "watch" if er <= 20 else "bad",
        "إيجار ورواتب وكهرباء... كنسبة من المبيعات. كلما قلّت زاد ربحك.")
    cr = current_assets / current_liab if current_liab > 0.01 else None
    add("current_ratio", "نسبة السيولة (الأصول المتداولة ÷ الالتزامات القصيرة)", cr,
        f"{cr:.2f}" if cr is not None else "لا التزامات", "good" if cr is None or cr >= 1.5 else "watch" if cr >= 1 else "bad",
        "هل يكفي ما عندك (نقد وبضاعة وديون لك) لسداد ما عليك قريباً؟ أقل من 1 خطر.")
    qr = (current_assets - inventory) / current_liab if current_liab > 0.01 else None
    add("quick_ratio", "السيولة السريعة (بدون البضاعة)", qr, f"{qr:.2f}" if qr is not None else "لا التزامات",
        "good" if qr is None or qr >= 0.8 else "watch" if qr >= 0.4 else "bad",
        "نفس السابق لكن بدون البضاعة: كم تستطيع أن تسدد فوراً لو طولبت.")
    dio = inventory / cogs * n if cogs > 0 else None
    add("dio", "أيام بقاء البضاعة على الرف", dio, f"{dio:.0f} يوماً" if dio is not None else "—",
        "good" if dio is not None and dio <= 30 else "watch" if dio is not None and dio <= 60 else "bad",
        "كم يوماً تبقى البضاعة حتى تُباع. أقل = رأس مال يدور أسرع وتلف أقل.")
    dso = receivables / sales * n if sales > 0 else None
    add("dso", "أيام تحصيل ديون الزبائن", dso, f"{dso:.0f} يوماً" if dso is not None else "—",
        "good" if dso is not None and dso <= 7 else "watch" if dso is not None and dso <= 20 else "bad",
        "متوسط الأيام حتى يدفع الزبائن ما عليهم. ارتفاعها يعني أن مالك عالق عند الناس.")
    dpo = payables / cogs * n if cogs > 0 else None
    add("dpo", "أيام السداد للموردين", dpo, f"{dpo:.0f} يوماً" if dpo is not None else "—",
        "good" if dpo is not None and 7 <= dpo <= 45 else "watch",
        "كم يوماً تأخذ حتى تدفع للمورد. مهلة معقولة تموّل البضاعة دون إضرار بعلاقتك به.")
    if dio is not None and dso is not None and dpo is not None:
        ccc = dio + dso - dpo
        add("ccc", "دورة النقد", ccc, f"{ccc:.0f} يوماً", "good" if ccc <= 20 else "watch" if ccc <= 45 else "bad",
            "من دفع ثمن البضاعة حتى عودة المال إليك. كلما قصرت احتجت رأس مال أقل.")
    be = opex / (gm / 100) if gm > 0 else None
    add("break_even", "مبيعات التعادل للفترة", be, f"{money(be):,.2f}" if be is not None else "—",
        "good" if be is not None and sales >= be * 1.1 else "watch" if be is not None and sales >= be else "bad",
        f"أقل مبيعات تغطي كل المصاريف دون ربح ولا خسارة. مبيعاتك في الفترة {money(sales):,.2f}.")
    daily_out = (opex + cogs) / n
    runway = cash / daily_out if daily_out > 0 else None
    add("runway", "النقد يكفي لتغطية", runway, f"{runway:.0f} يوماً" if runway is not None else "—",
        "good" if runway is not None and runway >= 30 else "watch" if runway is not None and runway >= 10 else "bad",
        "لو توقفت المبيعات، كم يوماً يكفي النقد في الصندوق والبنك والمحافظ لتغطية المصاريف والمشتريات.")
    roe = pl["net_income"] / equity * 100 * 365 / n if equity > 0 else None
    add("roe", "العائد السنوي على رأس المال", roe, pct(roe) if roe is not None else "—",
        "good" if roe is not None and roe >= 15 else "watch" if roe is not None and roe >= 5 else "bad",
        "كم يكسب مالك المستثمر في المحل سنوياً، قارنه بعائد البنك أو أي استثمار آخر.")
    return {"date_from": date_from, "date_to": date_to, "days": n, "items": out,
            "summary": {"good": sum(1 for x in out if x["verdict"] == "good"),
                        "watch": sum(1 for x in out if x["verdict"] == "watch"),
                        "bad": sum(1 for x in out if x["verdict"] == "bad")}}


def comparative_income(date_from, date_to):
    """قائمة الدخل للفترة مقابل الفترة السابقة المماثلة مع نسبة التغير"""
    from core import ledger, assistant
    a, b = date.fromisoformat(date_from[:10]), date.fromisoformat(date_to[:10])
    pa, pb = assistant.previous_period(a, b)
    cur = ledger.income_statement(a.isoformat(), b.isoformat())
    prev = ledger.income_statement(pa.isoformat(), pb.isoformat())
    return {"current": cur, "previous": prev, "prev_from": pa.isoformat(), "prev_to": pb.isoformat()}


# ---------------------------------------------------------------------------
# مطابقة البنك
# ---------------------------------------------------------------------------

def bank_reconciliation(as_of, statement_balance):
    """رصيد البنك في الدفاتر مقابل كشف البنك: المبالغ في الطريق (بطاقات ومحافظ تُسوّى في اليوم التالي) والفرق المتبقي"""
    from core import ledger
    as_of = str(as_of)[:10]
    bal = ledger._balances(None, as_of)
    book = _bal_at(bal, (ledger.BANK,))
    since = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
    transit = money(db.scalar("""SELECT SUM(card_amount + CASE WHEN wallet_bank=1 THEN wallet_amount ELSE 0 END)
                                 FROM invoices WHERE date(created_at) BETWEEN date(?) AND date(?)""", (since, as_of)) or 0)
    adjusted = money(book - transit)
    diff = money(float(statement_balance) - adjusted)
    return {"as_of": as_of, "statement": money(statement_balance), "book": book, "in_transit": transit,
            "adjusted_book": adjusted, "difference": diff, "matched": abs(diff) < 0.01}


def save_bank_reconciliation(as_of, statement_balance, record_fees=False):
    """حفظ المطابقة؛ والفرق السالب الصغير (عمولات بنكية غير مسجلة) يُسجَّل قيداً إن طُلب"""
    import json
    from core import ledger
    r = bank_reconciliation(as_of, statement_balance)
    if record_fees and r["difference"] < -0.009:
        ledger.add_manual_entry(r["as_of"], "عمولات ومصاريف بنكية من مطابقة كشف البنك",
                                [{"account": ledger.BANK_FEES, "debit": -r["difference"]},
                                 {"account": ledger.BANK, "credit": -r["difference"]}])
        r = bank_reconciliation(as_of, statement_balance)
    hist = json.loads(db.get_meta("bank_recs") or "[]")
    hist.append(dict(r, saved_at=db.now()))
    db.set_meta("bank_recs", json.dumps(hist[-60:], ensure_ascii=False))
    audit.log("مطابقة البنك", f"{r['as_of']}: الكشف {r['statement']} والدفاتر المعدّلة {r['adjusted_book']} والفرق {r['difference']}")
    return r


def bank_reconciliations():
    import json
    return list(reversed(json.loads(db.get_meta("bank_recs") or "[]")))
