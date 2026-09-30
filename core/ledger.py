# -*- coding: utf-8 -*-
"""
المحاسبة بالقيد المزدوج (دفتر الأستاذ):

صاحب المحل لا يكتب أي قيد بنفسه. كل عملية في البرنامج (بيع، مرتجع، شراء، تسديد، مصروف، شيك، جرد...)
تتحول تلقائياً إلى قيد محاسبي متوازن (مدين = دائن) حسب دليل الحسابات أدناه. لذلك:
- القيود تُولَّد من البيانات مباشرة فتبقى مطابقة لها دائماً (لا يوجد قيد "ينسى" البرنامج تسجيله).
- القيود اليدوية (رأس مال، إيداع في البنك، شراء أصل، قرض...) تُحفظ في جدول journal_entries.
- الناتج: دفتر اليومية، ميزان المراجعة، كشف أي حساب، قائمة الدخل، والميزانية العمومية.

الحساب يُعرَّف برقمه، ومصاريف التشغيل لها حساب فرعي لكل نوع: "6100:كهرباء".
"""

from core import db, auth, audit
from core.utils import money

# ---------------------------------------------------------------------------
# دليل الحسابات
# ---------------------------------------------------------------------------

CASH = "1110"            # النقد في أدراج الكاشير
BANK = "1120"            # البنك: البطاقات والتحويلات والشيكات المحصلة
CHEQUES_IN = "1130"      # شيكات مستلمة من العملاء لم تُصرف بعد
WALLETS = "1140"         # أرصدة المحافظ الإلكترونية (قبل تحويلها للبنك)
RECEIVABLES = "1210"     # ديون العملاء
INVENTORY = "1310"
VAT_INPUT = "1410"       # ضريبة مدخلات على المشتريات قابلة للخصم
FIXED_ASSETS = "1510"
PAYABLES = "2110"        # مستحقات الموردين
CHEQUES_OUT = "2120"     # شيكات أعطيناها للموردين ولم تُصرف بعد
VAT = "2210"
LOANS = "2310"
CAPITAL = "3110"
OWNER = "3120"           # جاري المالك: ما يسحبه المالك أو يدفعه من جيبه للمحل
OPENING = "3130"         # أرصدة افتتاحية (بضاعة وديون كانت موجودة قبل البرنامج)
SALES = "4110"
SALES_RETURNS = "4120"
OTHER_INCOME = "4210"
COGS = "5110"
STOCK_LOSS = "5120"
CASH_SHORT = "5130"
EXPENSES = "6100"
ADJUSTMENTS = "6900"

TYPES = {"asset": "أصول", "liability": "خصوم (التزامات)", "equity": "حقوق الملكية", "revenue": "إيرادات",
         "expense": "مصروفات"}

SYSTEM_ACCOUNTS = [
    (CASH, "الصندوق (النقد في الأدراج)", "asset"),
    (BANK, "البنك (بطاقات وتحويلات)", "asset"),
    (CHEQUES_IN, "شيكات واردة برسم التحصيل", "asset"),
    (WALLETS, "المحافظ الإلكترونية", "asset"),
    (RECEIVABLES, "ذمم العملاء (الديون)", "asset"),
    (INVENTORY, "المخزون (البضاعة)", "asset"),
    (VAT_INPUT, "ضريبة مدخلات قابلة للخصم", "asset"),
    (FIXED_ASSETS, "أصول ثابتة (أثاث ومعدات)", "asset"),
    (PAYABLES, "ذمم الموردين", "liability"),
    (CHEQUES_OUT, "شيكات صادرة مؤجلة", "liability"),
    (VAT, "ضريبة القيمة المضافة المستحقة", "liability"),
    (LOANS, "قروض", "liability"),
    (CAPITAL, "رأس المال", "equity"),
    (OWNER, "جاري المالك (سحوبات وإيداعات)", "equity"),
    (OPENING, "أرصدة افتتاحية", "equity"),
    (SALES, "المبيعات", "revenue"),
    (SALES_RETURNS, "مردودات المبيعات", "revenue"),
    (OTHER_INCOME, "إيرادات أخرى (زيادة صندوق، خصم مكتسب)", "revenue"),
    (COGS, "تكلفة البضاعة المباعة", "expense"),
    (STOCK_LOSS, "خسائر المخزون (تالف، منتهي، عجز)", "expense"),
    (CASH_SHORT, "عجز الصندوق", "expense"),
    (EXPENSES, "المصاريف التشغيلية", "expense"),
    (ADJUSTMENTS, "تسويات وديون معدومة", "expense"),
]

# طرق الدفع ← الحساب المقابل
CUSTOMER_METHOD_ACCOUNT = {"نقدي": CASH, "بطاقة": BANK, "تحويل": BANK, "شيك": CHEQUES_IN}
PAYMENT_FEES = EXPENSES + ":عمولات الدفع الإلكتروني"
DEPRECIATION = EXPENSES + ":إهلاك الأصول"
BANK_FEES = EXPENSES + ":عمولات ومصاريف بنكية"
EXTRA_EXPENSE_ACCOUNTS = (PAYMENT_FEES, DEPRECIATION, BANK_FEES)


def customer_method_account(method):
    """الحساب المقابل لتسديد عميل: الطرق الثابتة، أو محفظة إلكترونية/تطبيق بنكي معرّف في الإعدادات"""
    if method in CUSTOMER_METHOD_ACCOUNT:
        return CUSTOMER_METHOD_ACCOUNT[method]
    from core import wallets
    w = wallets.get(method)
    if w:
        return BANK if w["dest"] == wallets.DEST_BANK else WALLETS
    return BANK
SUPPLIER_METHOD_ACCOUNT = {"نقدي من الصندوق": CASH, "نقدي من خارج الصندوق": OWNER, "تحويل بنكي / شيك": BANK,
                           "شيك مؤجل": CHEQUES_OUT}

# أسباب حركات المخزون التي يغطيها مستند آخر (فاتورة/مرتجع/مشتريات) فلا تُقيَّد مرتين
DOC_STOCK_REASONS = ("بيع - فاتورة %", "مشتريات %", "مرتجع RET-%", "مرتجع مشتريات %")


def ensure_accounts():
    with db.tx() as conn:
        for code, name, typ in SYSTEM_ACCOUNTS:
            conn.execute("INSERT OR IGNORE INTO accounts(code, name, type, is_system) VALUES (?, ?, ?, 1)",
                         (code, name, typ))


def account_type(code):
    code = str(code)
    return {"1": "asset", "2": "liability", "3": "equity", "4": "revenue"}.get(code[:1], "expense")


def is_debit_normal(code):
    return account_type(code) in ("asset", "expense")


def _names():
    return {r["code"]: r["name"] for r in db.query("SELECT code, name FROM accounts")}


def account_name(code, names=None):
    if ":" in str(code):
        return f"مصاريف - {code.split(':', 1)[1]}"
    names = names if names is not None else _names()
    return names.get(code, code)


def list_accounts(active_only=True):
    """دليل الحسابات مع الحسابات الفرعية للمصاريف (للاختيار في القيد اليدوي)"""
    sql = "SELECT * FROM accounts" + (" WHERE is_active=1" if active_only else "") + " ORDER BY code"
    rows = [dict(r) for r in db.query(sql)]
    from core import settings
    for cat in list(dict.fromkeys(settings.expense_categories() + [a.split(":", 1)[1] for a in EXTRA_EXPENSE_ACCOUNTS])):
        rows.append({"code": f"{EXPENSES}:{cat}", "name": f"مصاريف - {cat}", "type": "expense", "is_system": 1,
                     "is_active": 1})
    rows.sort(key=lambda r: r["code"])
    return rows


def add_account(code, name, typ):
    code, name = (code or "").strip(), (name or "").strip()
    if not code.isdigit() or len(code) != 4:
        raise ValueError("رقم الحساب يجب أن يكون 4 أرقام، مثل 1520")
    if not name:
        raise ValueError("اسم الحساب مطلوب")
    if typ not in TYPES:
        raise ValueError("نوع حساب غير معروف")
    if account_type(code) != typ and not (typ == "expense" and code[0] in "56789"):
        raise ValueError("الرقم الأول يحدد النوع: 1 أصول، 2 خصوم، 3 حقوق ملكية، 4 إيرادات، 5-9 مصروفات")
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE code=?", (code,)).fetchone():
            raise ValueError("رقم الحساب مستخدم")
        conn.execute("INSERT INTO accounts(code, name, type, is_system) VALUES (?, ?, ?, 0)", (code, name, typ))


# ---------------------------------------------------------------------------
# القيود اليدوية
# ---------------------------------------------------------------------------

def add_manual_entry(entry_date, description, lines):
    """lines: قائمة dict: account, debit, credit, note — يجب أن يتساوى المدين والدائن"""
    clean = []
    valid = {a["code"] for a in list_accounts()}
    for ln in lines:
        d, c = money(ln.get("debit") or 0), money(ln.get("credit") or 0)
        if not d and not c:
            continue
        if d < 0 or c < 0 or (d and c):
            raise ValueError("كل سطر إما مدين أو دائن بمبلغ موجب")
        if ln.get("account") not in valid:
            raise ValueError(f"حساب غير معروف: {ln.get('account')}")
        clean.append((ln["account"], d, c, ln.get("note") or ""))
    if len(clean) < 2:
        raise ValueError("القيد يحتاج سطرين على الأقل (مدين ودائن)")
    td, tc = money(sum(x[1] for x in clean)), money(sum(x[2] for x in clean))
    if abs(td - tc) > 0.009:
        raise ValueError(f"القيد غير متوازن: المدين {td} والدائن {tc}")
    if not (description or "").strip():
        raise ValueError("اكتب بيان القيد")
    with db.tx() as conn:
        number = db.next_number(conn, "journal", "JV")
        cur = conn.execute("""INSERT INTO journal_entries(entry_number, entry_date, description, user_id, created_at)
                              VALUES (?, ?, ?, ?, ?)""",
                           (number, entry_date or db.today(), description.strip(), auth.current_user_id(), db.now()))
        eid = cur.lastrowid
        for acc, d, c, note in clean:
            conn.execute("INSERT INTO journal_lines(entry_id, account_code, debit, credit, note) VALUES (?, ?, ?, ?, ?)",
                         (eid, acc, d, c, note))
        audit.log("قيد يدوي", f"{number}: {description} ({td})", conn)
    return {"entry_id": eid, "entry_number": number}


def void_entry(entry_id):
    with db.tx() as conn:
        e = conn.execute("SELECT * FROM journal_entries WHERE id=?", (entry_id,)).fetchone()
        if not e:
            raise ValueError("القيد غير موجود")
        conn.execute("UPDATE journal_entries SET is_void=1 WHERE id=?", (entry_id,))
        audit.log("إلغاء قيد يدوي", e["entry_number"], conn)


def list_manual_entries(date_from=None, date_to=None):
    sql = """SELECT e.*, u.username, (SELECT SUM(debit) FROM journal_lines l WHERE l.entry_id=e.id) AS amount
             FROM journal_entries e LEFT JOIN users u ON u.id=e.user_id"""
    params = []
    if date_from and date_to:
        sql += " WHERE date(e.entry_date) BETWEEN date(?) AND date(?)"
        params = [date_from, date_to]
    return db.query(sql + " ORDER BY e.entry_date DESC, e.id DESC", params)


# قوالب جاهزة لغير المحاسب: يختار العملية ويكتب المبلغ فقط
TEMPLATES = [
    ("إيداع رأس مال نقداً في الصندوق", CASH, CAPITAL),
    ("إيداع رأس مال في البنك", BANK, CAPITAL),
    ("إيداع مال من المالك في البنك (من جاري المالك)", BANK, OWNER),
    ("سحب المالك من البنك لنفسه", OWNER, BANK),
    ("شراء أثاث أو معدات نقداً من المالك", FIXED_ASSETS, OWNER),
    ("شراء أثاث أو معدات من البنك", FIXED_ASSETS, BANK),
    ("استلام قرض في البنك", BANK, LOANS),
    ("سداد قسط قرض من البنك", LOANS, BANK),
    ("دفع مصروف من البنك", EXPENSES, BANK),
    ("رصيد بنك افتتاحي", BANK, OPENING),
    ("تحويل رصيد المحافظ الإلكترونية إلى البنك", BANK, WALLETS),
    ("عمولة خصمتها المحفظة الإلكترونية", PAYMENT_FEES, WALLETS),
    ("عمولة خصمها البنك على الدفع الإلكتروني أو البطاقات", PAYMENT_FEES, BANK),
    ("سحب المالك من رصيد المحفظة الإلكترونية", OWNER, WALLETS),
    ("رصيد محفظة إلكترونية افتتاحي", WALLETS, OPENING),
    ("مقاصة ضريبة المدخلات مع الضريبة المستحقة (عند تقديم الإقرار)", VAT, VAT_INPUT),
    ("دفع ضريبة القيمة المضافة المستحقة من البنك", VAT, BANK),
    ("إهلاك الأصول الثابتة (الأثاث والمعدات)", DEPRECIATION, FIXED_ASSETS),
    ("عمولات ومصاريف بنكية خصمها البنك", BANK_FEES, BANK),
]


# ---------------------------------------------------------------------------
# توليد القيود من العمليات
# ---------------------------------------------------------------------------

def _pair(debit_acc, credit_acc, amount):
    amount = money(amount)
    if not amount:
        return []
    if amount < 0:
        debit_acc, credit_acc, amount = credit_acc, debit_acc, -amount
    return [(debit_acc, amount, 0.0), (credit_acc, 0.0, amount)]


def _range(col, date_from, date_to):
    cond, params = [], []
    if date_from:
        cond.append(f"date({col}) >= date(?)")
        params.append(date_from)
    if date_to:
        cond.append(f"date({col}) <= date(?)")
        params.append(date_to)
    return (" AND " + " AND ".join(cond)) if cond else "", params


def _daily_sales_entries(conn, date_from, date_to):
    """قيد يومي واحد للمبيعات وآخر للمرتجعات (مثل تقرير Z) بدل قيد لكل فاتورة: مطابق تماماً لمجموع قيود الفواتير"""
    cond, params = _range("created_at", date_from, date_to)
    out = []
    for r in conn.execute(f"""SELECT date(created_at) AS d, COUNT(*) AS n, SUM(cash_amount) AS cash,
                                     SUM(card_amount) AS card, SUM(credit_amount) AS credit,
                                     SUM(CASE WHEN wallet_bank=1 THEN wallet_amount ELSE 0 END) AS wbank,
                                     SUM(CASE WHEN wallet_bank=0 THEN wallet_amount ELSE 0 END) AS wallet,
                                     SUM(total - tax) AS net, SUM(tax) AS tax, SUM(cost_total) AS cost
                              FROM invoices WHERE 1=1 {cond} GROUP BY d""", params):
        out.append({"date": r["d"] + " 23:59:00", "ref": f"Z-{r['d']}", "description": f"مبيعات اليوم ({r['n']} فاتورة)",
                    "source": "sale", "lines": [ln for ln in [
                        (CASH, money(r["cash"]), 0.0), (BANK, money(r["card"] + r["wbank"]), 0.0),
                        (WALLETS, money(r["wallet"]), 0.0), (RECEIVABLES, money(r["credit"]), 0.0),
                        (SALES, 0.0, money(r["net"])), (VAT, 0.0, money(r["tax"])),
                        (COGS, money(r["cost"]), 0.0), (INVENTORY, 0.0, money(r["cost"]))] if ln[1] or ln[2]]})
    for r in conn.execute(f"""SELECT date(created_at) AS d, COUNT(*) AS n,
                                     SUM(CASE WHEN refund_method='نقدي' THEN total ELSE 0 END) AS cash,
                                     SUM(CASE WHEN refund_method!='نقدي' THEN total ELSE 0 END) AS debt,
                                     SUM(total - tax) AS net, SUM(tax) AS tax, SUM(cost_total) AS cost
                              FROM returns WHERE 1=1 {cond} GROUP BY d""", params):
        out.append({"date": r["d"] + " 23:59:30", "ref": f"ZR-{r['d']}", "description": f"مرتجعات اليوم ({r['n']})",
                    "source": "return", "lines": [ln for ln in [
                        (SALES_RETURNS, money(r["net"]), 0.0), (VAT, money(r["tax"]), 0.0),
                        (CASH, 0.0, money(r["cash"])), (RECEIVABLES, 0.0, money(r["debt"])),
                        (INVENTORY, money(r["cost"]), 0.0), (COGS, 0.0, money(r["cost"]))] if ln[1] or ln[2]]})
    return out


def entries(date_from=None, date_to=None, skip_bulk=False, daily_sales=False):
    """كل القيود (المولّدة واليدوية) في الفترة، مرتبة زمنياً.
    كل قيد: dict(date, ref, description, source, lines=[(account, debit, credit)])
    skip_bulk: تخطي فواتير البيع والمرتجعات (تُجمع بـ SQL مباشرة في الأرصدة لسرعة الحساب مع البيانات الكبيرة)"""
    out = []
    conn = db.get_connection()
    try:
        def q(sql, col, extra_params=()):
            cond, params = _range(col, date_from, date_to)
            return conn.execute(sql.format(cond=cond), list(extra_params) + params).fetchall()

        def add(date, ref, desc, source, lines):
            lines = [ln for ln in lines if ln[1] or ln[2]]
            if lines:
                out.append({"date": date, "ref": ref, "description": desc, "source": source, "lines": lines})

        if daily_sales and not skip_bulk:
            out.extend(_daily_sales_entries(conn, date_from, date_to))
            skip_bulk = True
        # 1) فواتير البيع
        for r in ([] if skip_bulk else q("""SELECT * FROM invoices WHERE 1=1 {cond}""", "created_at")):
            add(r["created_at"], r["invoice_number"], "فاتورة بيع", "sale", [
                (CASH, money(r["cash_amount"]), 0.0), (BANK, money(r["card_amount"]), 0.0),
                (BANK if r["wallet_bank"] else WALLETS, money(r["wallet_amount"]), 0.0),
                (RECEIVABLES, money(r["credit_amount"]), 0.0),
                (SALES, 0.0, money(r["total"] - r["tax"])), (VAT, 0.0, money(r["tax"])),
                (COGS, money(r["cost_total"]), 0.0), (INVENTORY, 0.0, money(r["cost_total"]))])

        # 2) مرتجعات البيع
        for r in ([] if skip_bulk else q("""SELECT r.*, i.invoice_number FROM returns r JOIN invoices i ON i.id=r.invoice_id
                      WHERE 1=1 {cond}""", "r.created_at")):
            refund_acc = CASH if r["refund_method"] == "نقدي" else RECEIVABLES
            add(r["created_at"], r["return_number"], f"مرتجع من الفاتورة {r['invoice_number']}", "return", [
                (SALES_RETURNS, money(r["total"] - r["tax"]), 0.0), (VAT, money(r["tax"]), 0.0),
                (refund_acc, 0.0, money(r["total"])),
                (INVENTORY, money(r["cost_total"]), 0.0), (COGS, 0.0, money(r["cost_total"]))])

        # 3) حركات حسابات العملاء (غير الفواتير والمرتجعات)
        for r in q("""SELECT t.*, c.name FROM customer_transactions t JOIN customers c ON c.id=t.customer_id
                      WHERE t.type IN ('payment','opening','adjust','bounced') {cond}""", "t.created_at"):
            a = r["amount"]
            if r["type"] == "payment":
                lines = _pair(customer_method_account(r["method"]), RECEIVABLES, -a)
                desc = f"تسديد من العميل {r['name']} ({r['method'] or ''})"
            elif r["type"] == "opening":
                lines, desc = _pair(RECEIVABLES, OPENING, a), f"رصيد افتتاحي للعميل {r['name']}"
            elif r["type"] == "bounced":
                lines, desc = _pair(RECEIVABLES, CHEQUES_IN, a), f"شيك مرتجع من العميل {r['name']}"
            else:
                lines = _pair(RECEIVABLES, OTHER_INCOME, a) if a > 0 else _pair(ADJUSTMENTS, RECEIVABLES, -a)
                desc = f"تسوية حساب العميل {r['name']}: {r['note'] or ''}"
            add(r["created_at"], f"C-{r['id']}", desc, "customer", lines)

        # 4) حركات حسابات الموردين
        for r in q("""SELECT t.*, s.name, COALESCE(p.tax, 0) AS tax FROM supplier_transactions t
                      JOIN suppliers s ON s.id=t.supplier_id LEFT JOIN purchases p ON p.id=t.purchase_id AND t.type='purchase'
                      WHERE t.type IN ('purchase','payment','opening','adjust','bounced') {cond}""", "t.created_at"):
            a = r["amount"]
            if r["type"] == "purchase":
                tax = money(r["tax"])
                lines = [(INVENTORY, money(a - tax), 0.0), (VAT_INPUT, tax, 0.0), (PAYABLES, 0.0, money(a))]
                desc = f"مشتريات من المورد {r['name']}"
            elif r["type"] == "payment":
                lines = _pair(PAYABLES, SUPPLIER_METHOD_ACCOUNT.get(r["method"], CASH), -a)
                desc = f"دفعة للمورد {r['name']} ({r['method'] or ''})"
            elif r["type"] == "opening":
                lines, desc = _pair(OPENING, PAYABLES, a), f"رصيد افتتاحي للمورد {r['name']}"
            elif r["type"] == "bounced":
                lines, desc = _pair(CHEQUES_OUT, PAYABLES, a), f"شيك صادر مرتجع للمورد {r['name']}"
            else:
                lines = _pair(ADJUSTMENTS, PAYABLES, a) if a > 0 else _pair(PAYABLES, OTHER_INCOME, -a)
                desc = f"تسوية حساب المورد {r['name']}: {r['note'] or ''}"
            add(r["created_at"], f"S-{r['id']}", desc, "supplier", lines)

        # 5) مشتريات نقدية بدون مورد
        for r in q("""SELECT * FROM purchases WHERE supplier_id IS NULL {cond}""", "created_at"):
            tax = money(r["tax"] or 0)
            add(r["created_at"], r["purchase_number"], "مشتريات نقدية", "purchase",
                [(INVENTORY, money(r["total"] - tax), 0.0), (VAT_INPUT, tax, 0.0),
                 (SUPPLIER_METHOD_ACCOUNT.get(r["payment_method"], CASH), 0.0, money(r["total"]))])

        # 6) مرتجعات المشتريات (إرجاع بضاعة للمورد)
        for r in q("""SELECT p.*, s.name FROM purchase_returns p JOIN suppliers s ON s.id=p.supplier_id
                      WHERE 1=1 {cond}""", "p.created_at"):
            diff = money(r["total"] - r["cost_total"])
            lines = [(PAYABLES, money(r["total"]), 0.0), (INVENTORY, 0.0, money(r["cost_total"]))]
            if diff > 0:
                lines.append((OTHER_INCOME, 0.0, diff))
            elif diff < 0:
                lines.append((STOCK_LOSS, -diff, 0.0))
            add(r["created_at"], r["return_number"], f"مرتجع بضاعة للمورد {r['name']}", "purchase_return", lines)

        # 7) المصاريف
        for r in q("""SELECT * FROM expenses WHERE 1=1 {cond}""", "expense_date"):
            add(r["expense_date"] + r["created_at"][10:] if r["created_at"] else r["expense_date"], f"E-{r['id']}",
                f"مصروف {r['category']} {r['note'] or ''}".strip(), "expense",
                _pair(f"{EXPENSES}:{r['category']}", CASH if r["from_drawer"] else OWNER, r["amount"]))

        # 8) حركات المخزون غير المرتبطة بمستند (رصيد افتتاحي، جرد، تالف، تعديل)
        not_doc = " AND ".join("m.reason NOT LIKE ?" for _ in DOC_STOCK_REASONS)
        for r in q(f"""SELECT m.*, p.name, p.cost_price FROM stock_movements m JOIN products p ON p.id=m.product_id
                       WHERE COALESCE(m.reason,'') != '' AND {not_doc} {{cond}}""", "m.created_at", DOC_STOCK_REASONS):
            if r["loss_value"]:
                lines = _pair(STOCK_LOSS, INVENTORY, r["loss_value"])
            else:
                cost = r["unit_cost"] if r["unit_cost"] is not None else r["cost_price"]
                lines = _pair(INVENTORY, OPENING, (r["change_qty"] or 0) * (cost or 0))
            add(r["created_at"], f"M-{r['id']}", f"{r['reason']}: {r['name']}", "stock", lines)

        # 9) الورديات: تسليم النقد بين الورديات وعجز/زيادة الصندوق عند الإغلاق
        prev_counted = {}
        for s in conn.execute("SELECT * FROM shifts ORDER BY id").fetchall():
            term = s["terminal"] or ""
            diff = money(s["opening_cash"] - prev_counted.get(term, 0.0))
            if _in_range(s["opened_at"], date_from, date_to):
                desc = ("رصيد افتتاحي للصندوق من المالك" if diff > 0 else "نقد أخذه المالك من الصندوق بين الورديات")
                add(s["opened_at"], f"SH-{s['id']}", f"{desc} ({term})", "shift", _pair(CASH, OWNER, diff))
            if s["status"] == "closed":
                prev_counted[term] = money(s["counted_cash"] or 0)
                d = money(s["difference"] or 0)
                if d and _in_range(s["closed_at"], date_from, date_to):
                    lines = _pair(CASH, OTHER_INCOME, d) if d > 0 else _pair(CASH_SHORT, CASH, -d)
                    add(s["closed_at"], f"SH-{s['id']}", f"{'زيادة' if d > 0 else 'عجز'} صندوق عند إغلاق الوردية",
                        "shift", lines)

        # 10) إدخال وسحب نقدي من الصندوق (فكّة، سحب المالك...)
        for r in q("""SELECT * FROM cash_movements WHERE 1=1 {cond}""", "created_at"):
            add(r["created_at"], f"CM-{r['id']}", f"حركة صندوق: {r['reason'] or ''}", "cash",
                _pair(CASH, OWNER, r["amount"]))

        # 11) الشيكات المصروفة
        for r in q("""SELECT * FROM cheques WHERE status='cleared' {cond}""", "status_date"):
            lines = _pair(BANK, CHEQUES_IN, r["amount"]) if r["direction"] == "in" else _pair(CHEQUES_OUT, BANK, r["amount"])
            add(r["status_date"], f"CHQ-{r['cheque_number'] or r['id']}",
                "تحصيل شيك وارد في البنك" if r["direction"] == "in" else "صرف شيك صادر من البنك", "cheque", lines)

        # 12) القيود اليدوية
        for e in q("""SELECT * FROM journal_entries WHERE is_void=0 {cond}""", "entry_date"):
            lines = [(l["account_code"], money(l["debit"]), money(l["credit"]))
                     for l in conn.execute("SELECT * FROM journal_lines WHERE entry_id=? ORDER BY id", (e["id"],))]
            add(e["entry_date"], e["entry_number"], e["description"], "manual", lines)
    finally:
        conn.close()
    out.sort(key=lambda e: (e["date"] or "", e["ref"]))
    return out


def _in_range(ts, date_from, date_to):
    if not ts:
        return False
    d = ts[:10]
    return (not date_from or d >= date_from) and (not date_to or d <= date_to)


# ---------------------------------------------------------------------------
# التقارير المحاسبية
# ---------------------------------------------------------------------------

def journal(date_from, date_to, daily_sales=False):
    """دفتر اليومية مع أسماء الحسابات. daily_sales: قيد مبيعات واحد لكل يوم بدل قيد لكل فاتورة"""
    names = _names()
    out = []
    for e in entries(date_from, date_to, daily_sales=daily_sales):
        e = dict(e)
        e["lines"] = [{"account": a, "name": account_name(a, names), "debit": d, "credit": c} for a, d, c in e["lines"]]
        out.append(e)
    return out


def _bulk_lines(conn, date_from, date_to):
    """مجاميع فواتير البيع والمرتجعات في الفترة كأسطر قيد (مكافئة تماماً لقيودها التفصيلية)"""
    cond, params = _range("created_at", date_from, date_to)
    i = conn.execute(f"""SELECT COALESCE(SUM(cash_amount),0), COALESCE(SUM(card_amount),0), COALESCE(SUM(credit_amount),0),
                                COALESCE(SUM(total - tax),0), COALESCE(SUM(tax),0), COALESCE(SUM(cost_total),0),
                                COALESCE(SUM(CASE WHEN wallet_bank=1 THEN wallet_amount END),0),
                                COALESCE(SUM(CASE WHEN wallet_bank=0 THEN wallet_amount END),0)
                         FROM invoices WHERE 1=1 {cond}""", params).fetchone()
    r = conn.execute(f"""SELECT COALESCE(SUM(CASE WHEN refund_method='نقدي' THEN total END),0),
                                COALESCE(SUM(CASE WHEN refund_method!='نقدي' THEN total END),0),
                                COALESCE(SUM(total - tax),0), COALESCE(SUM(tax),0), COALESCE(SUM(cost_total),0)
                         FROM returns WHERE 1=1 {cond}""", params).fetchone()
    return [(CASH, i[0], 0.0), (BANK, i[1] + i[6], 0.0), (WALLETS, i[7], 0.0), (RECEIVABLES, i[2], 0.0), (SALES, 0.0, i[3]), (VAT, 0.0, i[4]),
            (COGS, i[5], 0.0), (INVENTORY, 0.0, i[5]),
            (SALES_RETURNS, r[2], 0.0), (VAT, r[3], 0.0), (CASH, 0.0, r[0]), (RECEIVABLES, 0.0, r[1]),
            (INVENTORY, r[4], 0.0), (COGS, 0.0, r[4])]


def _balances(date_from, date_to):
    """{حساب: [رصيد ما قبل الفترة (مدين-دائن)، مدين الفترة، دائن الفترة]}"""
    from datetime import date as _d, timedelta as _td
    acc = {}
    conn = db.get_connection()
    try:
        before_to = (_d.fromisoformat(date_from) - _td(days=1)).isoformat() if date_from else None
        chunks = ([(True, _bulk_lines(conn, None, before_to))] if date_from else []) + \
            [(False, _bulk_lines(conn, date_from, date_to))]
    finally:
        conn.close()
    for before, lines in chunks:
        for a, d, c in lines:
            if not d and not c:
                continue
            row = acc.setdefault(a, [0.0, 0.0, 0.0])
            if before:
                row[0] += d - c
            else:
                row[1] += d
                row[2] += c
    for e in entries(None, date_to, skip_bulk=True):
        before = bool(date_from) and e["date"][:10] < date_from
        for a, d, c in e["lines"]:
            row = acc.setdefault(a, [0.0, 0.0, 0.0])
            if before:
                row[0] += d - c
            else:
                row[1] += d
                row[2] += c
    return acc


def trial_balance(date_from, date_to):
    """ميزان المراجعة: لكل حساب رصيده الافتتاحي وحركة الفترة والرصيد الختامي"""
    names = _names()
    rows = []
    for code, (opening, d, c) in sorted(_balances(date_from, date_to).items()):
        closing = money(opening + d - c)
        rows.append({"code": code, "name": account_name(code, names), "type": account_type(code),
                     "opening": money(opening), "debit": money(d), "credit": money(c), "closing": closing,
                     "closing_debit": closing if closing > 0 else 0.0, "closing_credit": -closing if closing < 0 else 0.0})
    totals = {k: money(sum(r[k] for r in rows)) for k in ("debit", "credit", "closing_debit", "closing_credit")}
    totals["balanced"] = abs(totals["debit"] - totals["credit"]) < 0.01 and \
        abs(totals["closing_debit"] - totals["closing_credit"]) < 0.01
    return {"rows": rows, "totals": totals}


def account_statement(code, date_from, date_to, daily_sales=False):
    """كشف حساب (دفتر الأستاذ) لحساب واحد مع الرصيد التراكمي. daily_sales: مبيعات كل يوم في سطر واحد"""
    match = lambda a: a == code or (code == EXPENSES and str(a).startswith(EXPENSES + ":"))
    opening = 0.0
    if date_from:   # الرصيد الافتتاحي من الأرصدة المجمّعة (سريع حتى مع سنوات من البيانات)
        opening = sum(v[0] for a, v in _balances(date_from, date_to).items() if match(a))
    rows = []
    for e in entries(date_from, date_to, daily_sales=daily_sales):
        for a, d, c in e["lines"]:
            if match(a):
                rows.append({"date": e["date"], "ref": e["ref"], "description": e["description"], "debit": d, "credit": c})
    sign = 1 if is_debit_normal(code) else -1
    running = opening
    for r in rows:
        running += r["debit"] - r["credit"]
        r["balance"] = money(running * sign)
    return {"opening": money(opening * sign), "rows": rows, "closing": money(running * sign),
            "normal": "مدين" if sign == 1 else "دائن"}


def income_statement(date_from, date_to):
    """قائمة الدخل من دفتر الأستاذ"""
    names = _names()
    bal = {a: v[1] - v[2] for a, v in _balances(date_from, date_to).items()}
    get = lambda a: money(bal.get(a, 0.0))
    sales_ = -get(SALES)
    returns_ = get(SALES_RETURNS)
    net_sales = money(sales_ - returns_)
    cogs = get(COGS)
    gross = money(net_sales - cogs)
    other_income = -get(OTHER_INCOME)
    expenses = []
    for a in sorted(bal):
        if account_type(a) == "expense" and a not in (COGS,) and abs(bal[a]) > 0.004:
            expenses.append({"code": a, "name": account_name(a, names), "amount": money(bal[a])})
    for a in sorted(bal):  # إيرادات أخرى أضافها المستخدم (4xxx)
        if account_type(a) == "revenue" and a not in (SALES, SALES_RETURNS, OTHER_INCOME) and abs(bal[a]) > 0.004:
            other_income = money(other_income - bal[a])
    total_exp = money(sum(e["amount"] for e in expenses))
    return {"sales": sales_, "returns": returns_, "net_sales": net_sales, "cogs": cogs, "gross_profit": gross,
            "other_income": other_income, "expenses": expenses, "total_expenses": total_exp,
            "net_income": money(gross + other_income - total_exp)}


def balance_sheet(as_of=None):
    """الميزانية العمومية في تاريخ معين: ما يملكه المحل = ما عليه + حق المالك"""
    as_of = as_of or db.today()
    names = _names()
    bal = {a: v[1] - v[2] for a, v in _balances(None, as_of).items()}
    sections = {"asset": [], "liability": [], "equity": []}
    profit = 0.0
    for a, v in sorted(bal.items()):
        t = account_type(a)
        if t in ("revenue", "expense"):
            profit -= v
            continue
        amount = money(v if t == "asset" else -v)
        if abs(amount) > 0.004:
            sections[t].append({"code": a, "name": account_name(a, names), "amount": amount})
    profit = money(profit)
    sections["equity"].append({"code": "", "name": "الأرباح المتراكمة (صافي الربح حتى تاريخه)", "amount": profit})
    total_assets = money(sum(x["amount"] for x in sections["asset"]))
    total_liab = money(sum(x["amount"] for x in sections["liability"]))
    total_eq = money(sum(x["amount"] for x in sections["equity"]))
    from core import products
    physical = money(products.inventory_value()["cost_value"]) if as_of >= db.today() else None
    book_inventory = money(bal.get(INVENTORY, 0.0))
    return {"as_of": as_of, "assets": sections["asset"], "liabilities": sections["liability"],
            "equity": sections["equity"], "total_assets": total_assets, "total_liabilities": total_liab,
            "total_equity": total_eq, "balanced": abs(total_assets - total_liab - total_eq) < 0.01,
            "net_worth": money(total_assets - total_liab),
            "inventory_book": book_inventory, "inventory_physical": physical}
