# -*- coding: utf-8 -*-
"""
جلسات الويب (تطبيق الجوال /m ولوحة المالك /owner) محفوظة في قاعدة البيانات:
لا يُطلب تسجيل الدخول من جديد كل مرة يُعاد فيها تشغيل جهاز المحل. تنتهي بعد 90 يوماً بلا استخدام،
أو بالخروج، أو إذا عُطّل المستخدم أو تغيّرت كلمة مروره.
"""

import secrets
from datetime import datetime, timedelta

from core import db

MAX_AGE_DAYS = 90
MAX_AGE_SECONDS = MAX_AGE_DAYS * 24 * 3600


def create(user_id, kind):
    token = secrets.token_urlsafe(32)
    now = db.now()
    with db.tx() as conn:
        conn.execute("INSERT INTO web_sessions(token, user_id, kind, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
                     (token, user_id, kind, now, now))
        cutoff = (datetime.now() - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM web_sessions WHERE last_seen < ?", (cutoff,))
    return token


def user(token, kind):
    """المستخدم صاحب الجلسة إن كانت صالحة، وإلا None"""
    if not token:
        return None
    row = db.query_one("""SELECT s.last_seen, u.* FROM web_sessions s JOIN users u ON u.id = s.user_id
                          WHERE s.token=? AND s.kind=? AND u.is_active=1""", (token, kind))
    if not row:
        return None
    last = datetime.strptime(row["last_seen"][:19], "%Y-%m-%d %H:%M:%S")
    if datetime.now() - last > timedelta(days=MAX_AGE_DAYS):
        delete(token)
        return None
    if datetime.now() - last > timedelta(hours=12):        # لا نكتب في كل طلب
        with db.tx() as conn:
            conn.execute("UPDATE web_sessions SET last_seen=? WHERE token=?", (db.now(), token))
    d = dict(row)
    d.pop("last_seen", None)
    return d


def delete(token):
    with db.tx() as conn:
        conn.execute("DELETE FROM web_sessions WHERE token=?", (token,))


def revoke_user(user_id):
    """عند تغيير كلمة المرور أو تعطيل المستخدم: تُغلق جلساته على الجوالات"""
    with db.tx() as conn:
        conn.execute("DELETE FROM web_sessions WHERE user_id=?", (user_id,))


def cookie_value(cookie_header, name):
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None
