# -*- coding: utf-8 -*-
"""
الملاحظات والتذكيرات: «اتصل بالمورد الخميس»، «دفع الكهرباء كل شهر يوم 15»، «جرد الثلاجة كل أسبوع».
- لكل تذكير موعد اختياري وتكرار (يومي، أسبوعي، شهري، سنوي).
- الملاحظة خاصة بكاتبها، أو مشتركة لكل موظفي المحل.
- عند الإنجاز يُنقل التذكير المتكرر لموعده القادم تلقائياً، و«لاحقاً» يؤجله.
"""

import calendar
from datetime import datetime, timedelta

from core import auth, db

REPEATS = {"": "مرة واحدة", "daily": "يومياً", "weekly": "أسبوعياً", "monthly": "شهرياً", "yearly": "سنوياً"}
COLORS = ["#2563EB", "#16A34A", "#F59E0B", "#DC2626", "#7C3AED", "#0891B2"]
_FMT = "%Y-%m-%d %H:%M"


def _uid():
    return auth.current_user_id()


def _clean_due(due):
    """يقبل «2026-10-15» أو «2026-10-15 09:30» ويرجع صيغة واحدة، أو None"""
    due = (due or "").strip()
    if not due:
        return None
    for fmt in (_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(due, fmt)
            return d.strftime(_FMT) if fmt != "%Y-%m-%d" else d.strftime("%Y-%m-%d 09:00")
        except ValueError:
            continue
    raise ValueError("صيغة الموعد غير صحيحة")


def _visible():
    return "(n.shared = 1 OR n.user_id = ?)"


def add_note(title, body="", due=None, repeat="", shared=False, color=None, pinned=False):
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب عنوان الملاحظة")
    if repeat not in REPEATS:
        raise ValueError("تكرار غير معروف")
    due = _clean_due(due)
    if repeat and not due:
        raise ValueError("التذكير المتكرر يحتاج موعداً")
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO notes(title, body, due_at, repeat, shared, color, pinned, user_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (title[:200], (body or "").strip()[:4000], due, repeat, 1 if shared else 0, color or COLORS[0],
             1 if pinned else 0, _uid(), db.now()))
        return cur.lastrowid


def _own(c, note_id):
    row = c.execute(f"SELECT n.* FROM notes n WHERE n.id=? AND {_visible()}", (note_id, _uid())).fetchone()
    if row is None:
        raise ValueError("الملاحظة غير موجودة")
    return row


def update_note(note_id, title, body="", due=None, repeat="", shared=False, color=None, pinned=False):
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب عنوان الملاحظة")
    if repeat not in REPEATS:
        raise ValueError("تكرار غير معروف")
    due = _clean_due(due)
    if repeat and not due:
        raise ValueError("التذكير المتكرر يحتاج موعداً")
    with db.tx() as c:
        _own(c, note_id)
        c.execute("UPDATE notes SET title=?, body=?, due_at=?, repeat=?, shared=?, color=?, pinned=?, done_at=NULL, "
                  "notified_at=NULL WHERE id=?",
                  (title[:200], (body or "").strip()[:4000], due, repeat, 1 if shared else 0, color or COLORS[0],
                   1 if pinned else 0, note_id))


def delete_note(note_id):
    with db.tx() as c:
        _own(c, note_id)
        c.execute("DELETE FROM notes WHERE id=?", (note_id,))


def next_due(due, repeat, after=None):
    """الموعد القادم للتذكير المتكرر بعد «after» (افتراضياً الآن). «شهرياً يوم 31» يصبح آخر الشهر القصير"""
    d = datetime.strptime(due, _FMT)
    after = after or datetime.now()
    day = d.day
    while d <= after:
        if repeat == "daily":
            d += timedelta(days=1)
        elif repeat == "weekly":
            d += timedelta(weeks=1)
        elif repeat in ("monthly", "yearly"):
            y, mth = (d.year, d.month + 1) if repeat == "monthly" else (d.year + 1, d.month)
            if mth > 12:
                y, mth = y + 1, 1
            d = d.replace(year=y, month=mth, day=min(day, calendar.monthrange(y, mth)[1]))
        else:
            break
    return d.strftime(_FMT)


def complete(note_id):
    """تم: المتكرر ينتقل لموعده القادم، والعادي يُعلَّم منجزاً. يرجع الموعد القادم أو None"""
    with db.tx() as c:
        n = _own(c, note_id)
        if n["repeat"] and n["due_at"]:
            nxt = next_due(n["due_at"], n["repeat"])
            c.execute("UPDATE notes SET due_at=?, notified_at=NULL, done_count=done_count+1 WHERE id=?", (nxt, note_id))
            return nxt
        c.execute("UPDATE notes SET done_at=?, done_count=done_count+1 WHERE id=?", (db.now(), note_id))
        return None


def reopen(note_id):
    with db.tx() as c:
        _own(c, note_id)
        c.execute("UPDATE notes SET done_at=NULL, notified_at=NULL WHERE id=?", (note_id,))


def snooze(note_id, minutes=60):
    """لاحقاً: تأجيل التذكير (ساعة افتراضياً، أو حتى الغد)"""
    when = (datetime.now() + timedelta(minutes=int(minutes))).strftime(_FMT)
    with db.tx() as c:
        _own(c, note_id)
        c.execute("UPDATE notes SET due_at=?, notified_at=NULL WHERE id=?", (when, note_id))
    return when


def list_notes(show_done=False, search=""):
    """المثبّتة أولاً، ثم المستحقة، ثم بالموعد، ثم الأحدث"""
    sql = (f"SELECT n.*, u.full_name AS author FROM notes n LEFT JOIN users u ON u.id = n.user_id "
           f"WHERE {_visible()}")
    params = [_uid()]
    if not show_done:
        sql += " AND n.done_at IS NULL"
    if search.strip():
        sql += " AND (n.title LIKE ? OR n.body LIKE ?)"
        params += [f"%{search.strip()}%"] * 2
    sql += " ORDER BY n.done_at IS NOT NULL, n.pinned DESC, n.due_at IS NULL, n.due_at, n.id DESC"
    return [dict(r) for r in db.query(sql, params)]


def due_now(now=None):
    """التذكيرات المستحقة الآن (غير المنجزة)"""
    now = now or datetime.now().strftime(_FMT)
    return [dict(r) for r in db.query(
        f"SELECT n.* FROM notes n WHERE {_visible()} AND n.done_at IS NULL AND n.due_at IS NOT NULL AND n.due_at <= ? "
        "ORDER BY n.due_at", (_uid(), now))]


def pop_new_due(now=None):
    """المستحقة التي لم يُنبَّه لها بعد (للتنبيه المنبثق مرة واحدة) وتعليمها كمُنبَّه لها"""
    rows = [r for r in due_now(now) if not r["notified_at"]]
    if rows:
        with db.tx() as c:
            c.executemany("UPDATE notes SET notified_at=? WHERE id=?", [(db.now(), r["id"]) for r in rows])
    return rows


def counts():
    open_ = db.scalar(f"SELECT COUNT(*) FROM notes n WHERE {_visible()} AND n.done_at IS NULL", (_uid(),))
    return {"open": open_, "due": len(due_now())}


def describe_due(due):
    """«اليوم 09:30» / «غداً» / «متأخر منذ 3 أيام» / «2026-11-15»"""
    if not due:
        return ""
    d = datetime.strptime(due, _FMT)
    now = datetime.now()
    days = (d.date() - now.date()).days
    t = d.strftime("%H:%M")
    if d <= now:
        late = (now.date() - d.date()).days
        return "مستحق الآن" if late == 0 else f"متأخر منذ {late} يوم"
    if days == 0:
        return f"اليوم {t}"
    if days == 1:
        return f"غداً {t}"
    if days < 7:
        return f"بعد {days} أيام"
    return d.strftime("%Y-%m-%d")
