# -*- coding: utf-8 -*-
"""
الموظفون والرواتب:
- لكل موظف راتب شهري أساسي.
- السلفة: مال يأخذه الموظف مقدماً (أصل على المحل يُسترد من راتبه، وليست مصروفاً).
- صرف الراتب: الأساسي + مكافأة − خصومات = الراتب المستحق (مصروف)، تُخصم منه السلف، والباقي يُدفع نقداً أو من البنك.

القيود: السلفة ← مدين «سلف الموظفين» دائن الصندوق/البنك.
الراتب ← مدين «مصاريف - رواتب» بالمستحق، دائن «سلف الموظفين» بالمخصوم، ودائن الصندوق/البنك بالصافي.
"""

from core import db, auth, audit
from core.utils import money

PAY_DRAWER = "نقدي من الصندوق"
PAY_OUTSIDE = "نقدي من خارج الصندوق"
PAY_BANK = "تحويل بنكي / شيك"
METHODS = [PAY_DRAWER, PAY_OUTSIDE, PAY_BANK]
CATEGORY = "رواتب"            # نفس نوع المصروف «رواتب» في التقارير ودليل الحسابات


def _shift(method, shift_id):
    if method == PAY_DRAWER:
        from core import shifts
        return shifts.cash_shift(shift_id)
    return None


def add_employee(name, salary=0.0, job="", phone=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الموظف مطلوب")
    if money(salary) < 0:
        raise ValueError("الراتب غير صحيح")
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO employees(name, phone, job, salary, created_at) VALUES (?, ?, ?, ?, ?)",
                           (name, phone, job, money(salary), db.now()))
        audit.log("إضافة موظف", f"{name} براتب {money(salary)}", conn)
        return cur.lastrowid


def update_employee(employee_id, name, salary, job="", phone="", is_active=True):
    if not (name or "").strip():
        raise ValueError("اسم الموظف مطلوب")
    with db.tx() as conn:
        conn.execute("UPDATE employees SET name=?, salary=?, job=?, phone=?, is_active=? WHERE id=?",
                     (name.strip(), money(salary), job, phone, 1 if is_active else 0, employee_id))
        audit.log("تعديل موظف", f"#{employee_id} {name} براتب {money(salary)}", conn)


def get_employee(employee_id):
    return db.query_one("SELECT * FROM employees WHERE id=?", (employee_id,))


def advances_balance(employee_id, conn=None):
    """السلف التي لم تُسترد بعد"""
    q = (conn or db.get_connection()).execute
    given = q("SELECT COALESCE(SUM(amount),0) FROM employee_advances WHERE employee_id=?", (employee_id,)).fetchone()[0]
    taken = q("SELECT COALESCE(SUM(advances),0) FROM payroll_payments WHERE employee_id=?", (employee_id,)).fetchone()[0]
    return money(given - taken)


def list_employees(active_only=True):
    rows = db.query("SELECT * FROM employees" + (" WHERE is_active=1" if active_only else "") + " ORDER BY name")
    out = []
    for r in rows:
        d = dict(r)
        d["advances"] = advances_balance(r["id"])
        last = db.query_one("SELECT MAX(period) AS p FROM payroll_payments WHERE employee_id=?", (r["id"],))
        d["last_period"] = last["p"] if last else None
        out.append(d)
    return out


def give_advance(employee_id, amount, method=PAY_DRAWER, note="", shift_id=None):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    if method not in METHODS:
        raise ValueError("طريقة الدفع غير صحيحة")
    shift_id = _shift(method, shift_id)
    with db.tx() as conn:
        e = conn.execute("SELECT name FROM employees WHERE id=?", (employee_id,)).fetchone()
        if not e:
            raise ValueError("الموظف غير موجود")
        cur = conn.execute("""INSERT INTO employee_advances(employee_id, amount, method, note, user_id, shift_id, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?)""",
                           (employee_id, amount, method, note, auth.current_user_id(), shift_id, db.now()))
        audit.log("سلفة موظف", f"{e['name']}: {amount} ({method})", conn)
        return cur.lastrowid


def pay_salary(employee_id, period, base=None, bonus=0.0, deductions=0.0, advances=None, method=PAY_DRAWER,
               note="", shift_id=None):
    """صرف راتب شهر. advances=None: يُخصم من السلف المستحقة بقدر ما يسمح الراتب"""
    if not period or len(period) != 7 or period[4] != "-":
        raise ValueError("اختر الشهر (YYYY-MM)")
    if method not in METHODS:
        raise ValueError("طريقة الدفع غير صحيحة")
    shift_id = _shift(method, shift_id)
    with db.tx() as conn:
        e = conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
        if not e:
            raise ValueError("الموظف غير موجود")
        if conn.execute("SELECT 1 FROM payroll_payments WHERE employee_id=? AND period=?", (employee_id, period)).fetchone():
            raise ValueError(f"راتب {e['name']} عن {period} مصروف من قبل")
        base = money(e["salary"] if base is None else base)
        bonus, deductions = money(bonus or 0), money(deductions or 0)
        if min(base, bonus, deductions) < 0:
            raise ValueError("المبالغ لا تكون سالبة")
        gross = money(base + bonus - deductions)
        if gross <= 0:
            raise ValueError("الراتب المستحق يجب أن يكون أكبر من صفر")
        owed = advances_balance(employee_id, conn)
        adv = money(min(owed, gross) if advances is None else advances)
        if adv < 0 or adv > owed + 0.009 or adv > gross + 0.009:
            raise ValueError(f"المخصوم من السلف لا يتجاوز السلف المستحقة ({owed}) ولا الراتب ({gross})")
        net = money(gross - adv)
        cur = conn.execute("""INSERT INTO payroll_payments(employee_id, period, base, bonus, deductions, advances, net, method,
                                                           note, user_id, shift_id, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (employee_id, period, base, bonus, deductions, adv, net, method, note,
                            auth.current_user_id(), shift_id, db.now()))
        audit.log("صرف راتب", f"{e['name']} عن {period}: مستحق {gross}، سلف {adv}، صافي {net} ({method})", conn)
        return {"id": cur.lastrowid, "gross": gross, "advances": adv, "net": net}


def history(employee_id):
    """كشف الموظف: السلف والرواتب بالترتيب"""
    rows = [dict(r, kind="advance") for r in db.query(
        "SELECT id, amount, method, note, created_at FROM employee_advances WHERE employee_id=?", (employee_id,))]
    rows += [dict(r, kind="salary") for r in db.query(
        "SELECT * FROM payroll_payments WHERE employee_id=?", (employee_id,))]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def payroll_total(date_from, date_to):
    """الرواتب المستحقة (مصروف) المصروفة في الفترة"""
    return money(db.scalar("""SELECT SUM(base + bonus - deductions) FROM payroll_payments
                              WHERE date(created_at) BETWEEN date(?) AND date(?)""", (date_from, date_to)))


def payslip_html(payment_id):
    from html import escape
    p = db.query_one("""SELECT p.*, e.name, e.job FROM payroll_payments p JOIN employees e ON e.id=p.employee_id
                        WHERE p.id=?""", (payment_id,))
    if not p:
        return ""
    gross = money(p["base"] + p["bonus"] - p["deductions"])
    rows = [("الراتب الأساسي", p["base"]), ("مكافأة / إضافي", p["bonus"]), ("خصومات (غياب، تأخير...)", -p["deductions"]),
            ("= الراتب المستحق", gross), ("خصم من السلف", -p["advances"]), ("= الصافي المدفوع", p["net"])]
    body = "".join(f"<tr><td>{escape(k)}</td><td style='text-align:left'>{v:,.2f}</td></tr>" for k, v in rows)
    from core import branding
    return branding.document(
            f"<p>الموظف: <b>{escape(p['name'])}</b>{(' — ' + escape(p['job'])) if p['job'] else ''}<br>"
            f"تاريخ الصرف: {p['created_at'][:10]} • طريقة الدفع: {escape(p['method'])}<br>"
            f"السلف المتبقية بعد هذا الراتب: {advances_balance(p['employee_id']):,.2f}</p>"
            f"<table width='100%' border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse'>{body}</table>"
            f"<p style='margin-top:40px'>توقيع الموظف: ____________ &nbsp;&nbsp;&nbsp; توقيع المدير: ____________</p>",
            f"قسيمة راتب — {p['period']}", size_pt=11)
