# -*- coding: utf-8 -*-
"""المصاريف التشغيلية (إيجار، كهرباء، رواتب...)"""

from core import db, auth, audit
from core.utils import money


def add_expense(category, amount, note="", from_drawer=True, expense_date=None, shift_id=None):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    if not (category or "").strip():
        raise ValueError("اختر نوع المصروف")
    from core import accountant
    accountant.assert_open(expense_date or db.today(), "مصروف")
    if from_drawer:
        from core import shifts
        shift_id = shifts.cash_shift(shift_id)
    with db.tx() as conn:
        cur = conn.execute("""INSERT INTO expenses(category, amount, note, from_drawer, expense_date, user_id, shift_id, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                           (category.strip(), amount, note, 1 if from_drawer else 0, expense_date or db.today(),
                            auth.current_user_id(), shift_id if from_drawer else None, db.now()))
        return cur.lastrowid


def delete_expense(expense_id):
    with db.tx() as conn:
        e = conn.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if e:
            from core import accountant
            accountant.assert_open(e["expense_date"], "حذف مصروف")
        if e and e["from_drawer"] and e["shift_id"]:
            s = conn.execute("SELECT status FROM shifts WHERE id=?", (e["shift_id"],)).fetchone()
            if s and s["status"] == "closed":
                raise ValueError("هذا المصروف دُفع من درج وردية مغلقة وعُدّ نقدها، وحذفه يغيّر نتيجة الوردية بأثر رجعي.\n"
                                 "إن كان خطأً: سجّل «إدخال نقدي» في الوردية الحالية بنفس المبلغ مع السبب.")
        conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        if e:
            audit.log("حذف مصروف", f"{e['category']} {e['amount']} بتاريخ {e['expense_date']}", conn)


def list_expenses(date_from, date_to, category=None):
    sql = """SELECT e.*, u.username FROM expenses e LEFT JOIN users u ON u.id=e.user_id
             WHERE date(e.expense_date) BETWEEN date(?) AND date(?)"""
    params = [date_from, date_to]
    if category:
        sql += " AND e.category=?"
        params.append(category)
    return db.query(sql + " ORDER BY e.expense_date DESC, e.id DESC", params)


def totals_by_category(date_from, date_to):
    return db.query("""SELECT category, SUM(amount) AS total, COUNT(*) AS cnt FROM expenses
                       WHERE date(expense_date) BETWEEN date(?) AND date(?)
                       GROUP BY category ORDER BY total DESC""", (date_from, date_to))
