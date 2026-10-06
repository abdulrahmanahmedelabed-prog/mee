# -*- coding: utf-8 -*-
"""سجل العمليات الحساسة (حذف، مرتجع، تعديل أسعار، فتح/إغلاق وردية...)"""

from core import db


def log(action, details="", conn=None):
    """كل سطر مختوم ببصمة تشمل السطر الذي قبله: حذفه أو تعديله من خارج البرنامج يكشفه المدقق"""
    from core import auth, integrity
    uid, now = auth.current_user_id(), db.now()
    sql = "INSERT INTO audit_log(user_id, action, details, created_at, chain) VALUES (?, ?, ?, ?, ?)"

    def write(c):
        c.execute(sql, (uid, action, details, now, integrity.next_audit_chain(c, uid, action, details, now)))
    if conn is not None:
        write(conn)
    else:
        with db.tx() as c:
            write(c)


def recent(limit=300, date_from=None, date_to=None):
    sql = """SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id"""
    params = []
    if date_from and date_to:
        sql += " WHERE date(a.created_at) BETWEEN date(?) AND date(?)"
        params += [date_from, date_to]
    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)
