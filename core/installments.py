# -*- coding: utf-8 -*-
"""
تقسيط ديون الزبائن: جدول أقساط بمواعيد لدين قائم.
- الخطة لا تغيّر المحاسبة: الدين نفسه في ذمم العملاء، والتسديد بالطرق المعتادة (تسديد دفعة، محفظة، شيك).
- كل ما يسدده الزبون بعد إنشاء الخطة يُوزَّع على الأقساط من الأقدم، فيُعرف المسدَّد والمتأخر والقادم.
- تنتهي الخطة وحدها عند سداد مجموعها.
"""

from datetime import date, timedelta

from core import db, auth, audit, customers
from core.utils import money, fmt_money

STATUS = {"paid": "مسدَّد", "partial": "مسدَّد جزئياً", "overdue": "متأخر", "due": "مستحق اليوم", "upcoming": "قادم"}


def active_plan(customer_id):
    return db.query_one("SELECT * FROM installment_plans WHERE customer_id=? AND status='active' ORDER BY id DESC LIMIT 1",
                        (customer_id,))


def create_plan(customer_id, count, first_due, every_days=30, total=None, note=""):
    count, every_days = int(count), int(every_days)
    if count < 2 or count > 60:
        raise ValueError("عدد الأقساط من 2 إلى 60")
    if every_days not in (7, 14, 30):
        raise ValueError("المدة بين الأقساط: أسبوع أو أسبوعان أو شهر")
    date.fromisoformat(first_due)
    bal = customers.balance(customer_id)
    total = money(bal if total is None else total)
    if total <= 0 or total > bal + 0.009:
        raise ValueError(f"مبلغ التقسيط يجب أن يكون أكبر من صفر ولا يتجاوز دين العميل ({fmt_money(bal)})")
    if active_plan(customer_id):
        raise ValueError("للعميل خطة تقسيط قائمة. ألغها أولاً لإنشاء خطة جديدة.")
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO installment_plans(customer_id, total, count, first_due, every_days, note,
                                                            start_balance, user_id, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (customer_id, total, count, first_due, every_days, note, bal, auth.current_user_id(), db.now()))
        audit.log("خطة تقسيط", f"عميل #{customer_id}: {total} على {count} أقساط من {first_due}", conn)
        return cur.lastrowid


def cancel_plan(plan_id):
    with db.tx() as conn:
        conn.execute("UPDATE installment_plans SET status='cancelled' WHERE id=?", (plan_id,))
        audit.log("إلغاء خطة تقسيط", f"#{plan_id}", conn)


def _due_dates(plan):
    d0 = date.fromisoformat(plan["first_due"])
    out = []
    for i in range(plan["count"]):
        if plan["every_days"] == 30:          # شهرياً بنفس اليوم من الشهر
            m = d0.month - 1 + i
            y, mo = d0.year + m // 12, m % 12 + 1
            day = min(d0.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30,
                               31, 30, 31][mo - 1])
            out.append(date(y, mo, day))
        else:
            out.append(d0 + timedelta(days=plan["every_days"] * i))
    return out


def paid_toward(plan):
    """ما سدده العميل منذ إنشاء الخطة (تسديدات ومرتجعات خُصمت من دينه وتسويات تنقصه)"""
    return money(-db.scalar("""SELECT SUM(amount) FROM customer_transactions
                               WHERE customer_id=? AND amount < 0 AND type IN ('payment','return','adjust')
                               AND created_at >= ?""", (plan["customer_id"], plan["created_at"])))


def schedule(plan, today=None):
    """الأقساط مع حالتها: [{seq, due, amount, paid, status}]"""
    today = today or date.today()
    per = money(plan["total"] / plan["count"])
    amounts = [per] * (plan["count"] - 1) + [money(plan["total"] - per * (plan["count"] - 1))]
    left = min(paid_toward(plan), plan["total"])
    out = []
    for i, (due, amt) in enumerate(zip(_due_dates(plan), amounts), 1):
        paid = money(min(left, amt))
        left = money(left - paid)
        if paid >= amt - 0.009:
            st = "paid"
        elif due < today:
            st = "overdue"
        elif due == today:
            st = "due"
        else:
            st = "partial" if paid > 0 else "upcoming"
        out.append({"seq": i, "due": due.isoformat(), "amount": amt, "paid": paid, "status": st})
    return out


def summary(plan, today=None):
    rows = schedule(plan, today)
    paid = money(sum(r["paid"] for r in rows))
    overdue = [r for r in rows if r["status"] in ("overdue", "due")]
    nxt = next((r for r in rows if r["status"] != "paid"), None)
    return {"plan": dict(plan), "rows": rows, "paid": paid, "remaining": money(plan["total"] - paid),
            "overdue_amount": money(sum(r["amount"] - r["paid"] for r in overdue)), "overdue_count": len(overdue),
            "next": nxt}


def refresh_status():
    """إنهاء الخطط التي سُددت بالكامل"""
    for p in db.query("SELECT * FROM installment_plans WHERE status='active'"):
        if paid_toward(p) >= p["total"] - 0.009:
            with db.tx() as conn:
                conn.execute("UPDATE installment_plans SET status='done' WHERE id=?", (p["id"],))


def overdue(today=None):
    """العملاء المتأخرون عن أقساطهم: [{customer, phone, amount, count, since}]"""
    out = []
    for p in db.query("""SELECT ip.*, c.name, c.phone FROM installment_plans ip JOIN customers c ON c.id=ip.customer_id
                         WHERE ip.status='active'"""):
        s = summary(p, today)
        late = [r for r in s["rows"] if r["status"] == "overdue"]
        if late:
            out.append({"customer_id": p["customer_id"], "name": p["name"], "phone": p["phone"], "count": len(late),
                        "amount": money(sum(r["amount"] - r["paid"] for r in late)), "since": late[0]["due"]})
    return sorted(out, key=lambda r: r["since"])


def reminder_message(customer_id):
    from core import settings
    p = active_plan(customer_id)
    c = customers.get_customer(customer_id)
    if not p:
        return customers.reminder_message(customer_id)
    s = summary(p)
    shop = settings.get("shop_name")
    lines = [f"مرحباً {c['name']}،"]
    if s["overdue_count"]:
        lines.append(f"نذكّركم بقسط مستحق لدى {shop} بقيمة {fmt_money(s['overdue_amount'])}.")
    elif s["next"]:
        lines.append(f"نذكّركم بالقسط القادم لدى {shop}: {fmt_money(s['next']['amount'] - s['next']['paid'])} "
                     f"بتاريخ {s['next']['due']}.")
    lines.append(f"المتبقي من التقسيط: {fmt_money(s['remaining'])}. شاكرين لكم 🌷")
    return "\n".join(lines)


def schedule_html(plan_id):
    from html import escape
    from core import settings
    p = db.query_one("""SELECT ip.*, c.name, c.phone FROM installment_plans ip JOIN customers c ON c.id=ip.customer_id
                        WHERE ip.id=?""", (plan_id,))
    s = summary(p)
    body = "".join(f"<tr><td>{r['seq']}</td><td>{r['due']}</td><td>{r['amount']:,.2f}</td><td>{r['paid']:,.2f}</td>"
                   f"<td>{STATUS[r['status']]}</td></tr>" for r in s["rows"])
    return (f"<html><body dir='rtl' style='font-family:Tahoma;font-size:11pt'>"
            f"<h2 style='text-align:center'>{escape(settings.get('shop_name') or '')}</h2>"
            f"<h3 style='text-align:center'>جدول أقساط</h3>"
            f"<p>العميل: <b>{escape(p['name'])}</b> {escape(p['phone'] or '')}<br>"
            f"المبلغ المقسط: {p['total']:,.2f} على {p['count']} أقساط • المسدَّد {s['paid']:,.2f} • المتبقي {s['remaining']:,.2f}</p>"
            f"<table width='100%' border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse'>"
            f"<tr style='background:#eee'><th>#</th><th>تاريخ الاستحقاق</th><th>القسط</th><th>المسدَّد</th><th>الحالة</th></tr>"
            f"{body}</table><p style='margin-top:40px'>توقيع العميل: ____________</p></body></html>")
