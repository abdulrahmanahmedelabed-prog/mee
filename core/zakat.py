# -*- coding: utf-8 -*-
"""
زكاة عروض التجارة من دفاتر المحل مباشرة.

الوعاء الزكوي = النقد (الصندوق + البنك + المحافظ + الشيكات تحت التحصيل)
              + البضاعة بقيمتها يوم الحَوْل (سعر البيع — قول الجمهور، أو التكلفة إن اختار المالك)
              + الديون المرجوّة على العملاء (والمشكوك فيها لا تُزكّى حتى تُقبض) + سلف الموظفين
              − الديون الحالّة على المحل (الموردون، الشيكات الصادرة، الضريبة المستحقة، الرواتب المستحقة)
النصاب = 85 غرام ذهب بسعر يوم الحَوْل. المقدار = 2.5% للسنة الهجرية (2.577% إن حُسب بالسنة الميلادية).
الأصول الثابتة (الرفوف والثلاجات والأجهزة) لا زكاة فيها.

تنبيه: هذا حساب مساعد من الدفاتر؛ للحالات الخاصة (شركاء، قروض طويلة، أموال أخرى للمالك) يُستشار أهل العلم.
"""

from datetime import date, timedelta

from core import db, ledger, settings, hijri
from core.utils import money

NISAB_GOLD_GRAMS = 85
NISAB_SILVER_GRAMS = 595
RATE_HIJRI = 0.025
RATE_GREGORIAN = 0.02577


def _balances(as_of):
    return {a: v[1] - v[2] for a, v in ledger._balances(None, as_of).items()}


def compute(as_of=None, gold_price=None, valuation="sale", doubtful_days=180, include_doubtful=False,
            calendar="hijri", other_cash=0.0, other_debts=0.0):
    """حساب الزكاة. gold_price: سعر غرام الذهب عيار 24 بعملة المحل (لمعرفة النصاب)"""
    as_of = as_of or db.today()
    bal = _balances(as_of)

    def b(code):
        return money(bal.get(code, 0.0))

    cash = money(b(ledger.CASH) + b(ledger.BANK) + b(ledger.WALLETS) + b(ledger.CHEQUES_IN) + (other_cash or 0))
    inv = db.query_one("""SELECT COALESCE(SUM(quantity * sale_price), 0) AS sale, COALESCE(SUM(quantity * cost_price), 0) AS cost
                          FROM products WHERE is_active=1 AND is_service=0 AND quantity > 0""")
    # البضاعة تُقوَّم بسعر البيع بعد استبعاد ضريبة القيمة المضافة إن كانت الأسعار شاملة لها
    vat = settings.get_float("vat_rate", 0) if settings.get_bool("vat_enabled") else 0
    sale_value = money(inv["sale"] / (1 + vat / 100)) if vat and settings.get_bool("prices_include_vat") else money(inv["sale"])
    inventory = sale_value if valuation == "sale" else money(inv["cost"])

    from core import financial_audit
    good, doubtful = 0.0, 0.0
    cutoff = date.fromisoformat(as_of) - timedelta(days=doubtful_days)
    for r in financial_audit.aging(as_of):
        # الديون الأقدم من المدة المحددة تُعتبر مشكوكاً فيها (لا تُزكّى حتى تُقبض)
        old = r["buckets"][3] if doubtful_days <= 90 else 0.0
        if doubtful_days > 90:
            last = db.scalar("""SELECT MAX(date(created_at)) FROM customer_transactions
                                WHERE customer_id=? AND amount < 0""", (r["customer_id"],))
            if not last or date.fromisoformat(str(last)) < cutoff:
                old = r["buckets"][3]
        doubtful += old
        good += r["balance"] - old
    good, doubtful = money(good), money(doubtful)
    receivables = money(good + (doubtful if include_doubtful else 0))
    advances = max(b(ledger.EMP_ADVANCES), 0.0)

    payables = max(-b(ledger.PAYABLES), 0.0)
    cheques_out = max(-b(ledger.CHEQUES_OUT), 0.0)
    vat_due = max(-(b(ledger.VAT) + b(ledger.VAT_INPUT)), 0.0)
    loyalty = max(-b(ledger.LOYALTY), 0.0)
    debts = money(payables + cheques_out + vat_due + loyalty + (other_debts or 0))

    assets = [("النقد (الصندوق والبنك والمحافظ والشيكات تحت التحصيل)", cash),
              (f"البضاعة بـ{'سعر البيع' if valuation == 'sale' else 'التكلفة'}", inventory),
              ("ديون مرجوّة على العملاء", receivables),
              ("سلف الموظفين", money(advances))]
    deductions = [("مستحقات الموردين", money(payables)), ("شيكات صادرة لم تُصرف", money(cheques_out)),
                  ("ضريبة مستحقة للدولة", money(vat_due)), ("نقاط ولاء مستحقة للعملاء", money(loyalty))]
    if other_debts:
        deductions.append(("ديون أخرى حالّة", money(other_debts)))
    base = money(sum(v for _, v in assets) - debts)
    gold_price = gold_price if gold_price is not None else settings.get_float("zakat_gold_price", 0)
    nisab = money(NISAB_GOLD_GRAMS * gold_price) if gold_price else None
    rate = RATE_HIJRI if calendar == "hijri" else RATE_GREGORIAN
    due = base > 0 and (nisab is None or base >= nisab)
    return {"as_of": as_of, "hijri": hijri.fmt(date.fromisoformat(as_of)), "assets": assets, "deductions": deductions,
            "doubtful": doubtful, "include_doubtful": include_doubtful, "base": base, "nisab": nisab,
            "gold_price": gold_price, "rate": rate, "calendar": calendar, "reaches_nisab": due,
            "zakat": money(base * rate) if due else 0.0, "valuation": valuation,
            "inventory_cost": money(inv["cost"]), "inventory_sale": sale_value,
            "next_hawl": next_hawl(as_of)}


def next_hawl(as_of=None):
    """موعد الحَوْل القادم (من تاريخ بداية الحَوْل في الإعدادات، أو من أول عملية في البرنامج)"""
    as_of = date.fromisoformat(as_of or db.today())
    start = settings.get("zakat_hawl_start") or db.scalar("SELECT MIN(date(created_at)) FROM invoices") or as_of.isoformat()
    d = date.fromisoformat(str(start)[:10])
    while d <= as_of:
        d = hijri.hijri_year_later(d)
    return {"date": d.isoformat(), "hijri": hijri.fmt(d), "days_left": (d - as_of).days}


def report_html(r):
    from html import escape
    from core import branding

    def m(v):
        return f"{v:,.2f}"
    rows = "".join(f"<tr><td>{escape(k)}</td><td style='text-align:left'>{m(v)}</td></tr>" for k, v in r["assets"])
    rows += "".join(f"<tr><td>− {escape(k)}</td><td style='text-align:left'>{m(-v)}</td></tr>" for k, v in r["deductions"])
    rows += f"<tr style='background:#EEF4FF'><td><b>= الوعاء الزكوي</b></td><td style='text-align:left'><b>{m(r['base'])}</b></td></tr>"
    nisab = (f"{m(r['nisab'])} (85 غرام ذهب × {m(r['gold_price'])})" if r["nisab"] else "لم يُدخل سعر الذهب")
    rate = "2.5% (سنة هجرية)" if r["calendar"] == "hijri" else "2.577% (سنة ميلادية)"
    verdict = (f"<h2 style='text-align:center;color:#067647'>الزكاة الواجبة: {m(r['zakat'])}</h2>" if r["reaches_nisab"]
               else "<h3 style='text-align:center'>الوعاء أقل من النصاب: لا زكاة واجبة في هذا الحَوْل</h3>")
    body = (f"<p>تاريخ الحَوْل: {r['as_of']} — {escape(r['hijri'])}</p>"
            f"<table width='100%' border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse'>{rows}</table>"
            f"<p>النصاب: {nisab}<br>المقدار: {rate}<br>ديون مشكوك في تحصيلها لم تُحسب: {m(r['doubtful'])} "
            f"(تُزكّى عند قبضها)</p>{verdict}"
            f"<p style='color:#667085;font-size:9pt'>حُسبت من دفاتر المحل كما هي في تاريخ الحَوْل. الأصول الثابتة لا زكاة فيها. "
            f"للحالات الخاصة (شركاء، قروض طويلة الأجل، أموال أخرى للمالك) استشر أهل العلم.</p>")
    return branding.document(body, "حساب زكاة عروض التجارة", "")
