# -*- coding: utf-8 -*-
"""سجل العمليات الحساسة (حذف، مرتجع، تعديل أسعار، فتح/إغلاق وردية...)"""

from core import db


def log(action, details="", conn=None):
    from core import auth
    params = (auth.current_user_id(), action, details, db.now())
    sql = "INSERT INTO audit_log(user_id, action, details, created_at) VALUES (?, ?, ?, ?)"
    if conn is not None:
        conn.execute(sql, params)
    else:
        with db.tx() as c:
            c.execute(sql, params)


def recent(limit=300, date_from=None, date_to=None):
    sql = """SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id"""
    params = []
    if date_from and date_to:
        sql += " WHERE date(a.created_at) BETWEEN date(?) AND date(?)"
        params += [date_from, date_to]
    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)
