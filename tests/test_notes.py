# -*- coding: utf-8 -*-
"""الملاحظات والتذكيرات: الخصوصية والمشاركة، التكرار، التأجيل، التنبيه مرة واحدة، والواجهة"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core import auth, notes


def _fmt(d):
    return d.strftime("%Y-%m-%d %H:%M")


def test_add_list_complete_and_privacy():
    past = _fmt(datetime.now() - timedelta(minutes=5))
    a = notes.add_note("اتصل بمورد الحليب", "طلبية الخميس", due=past)
    b = notes.add_note("جرد الثلاجة", shared=True)
    notes.add_note("ملاحظة بلا موعد")
    assert [n["id"] for n in notes.due_now()] == [a]
    assert notes.counts() == {"open": 3, "due": 1}
    assert [n["id"] for n in notes.pop_new_due()] == [a]
    assert notes.pop_new_due() == []                     # التنبيه مرة واحدة فقط
    assert notes.complete(a) is None
    assert notes.counts()["due"] == 0
    assert a not in [n["id"] for n in notes.list_notes()]
    assert a in [n["id"] for n in notes.list_notes(show_done=True)]
    notes.reopen(a)
    assert a in [n["id"] for n in notes.list_notes()]

    auth.create_user("cashier1", "كاشير", "1234", "cashier")
    assert auth.login("cashier1", "1234")
    seen = [n["id"] for n in notes.list_notes()]
    assert b in seen and a not in seen                   # الخاصة لا يراها غير كاتبها، والمشتركة للجميع
    with pytest.raises(ValueError):
        notes.delete_note(a)
    auth.login("admin", "admin")


def test_repeat_moves_to_next_due():
    assert notes.next_due("2026-01-31 09:00", "monthly", datetime(2026, 2, 1)) == "2026-02-28 09:00"
    assert notes.next_due("2026-01-31 09:00", "monthly", datetime(2026, 3, 1)) == "2026-03-31 09:00"
    assert notes.next_due("2026-03-02 09:00", "weekly", datetime(2026, 3, 20)) == "2026-03-23 09:00"
    assert notes.next_due("2024-02-29 08:00", "yearly", datetime(2024, 3, 1)) == "2025-02-28 08:00"
    due = _fmt(datetime.now() - timedelta(days=2))
    nid = notes.add_note("دفع الكهرباء", due=due, repeat="daily")
    nxt = notes.complete(nid)
    assert nxt > _fmt(datetime.now())
    n = [x for x in notes.list_notes() if x["id"] == nid][0]
    assert n["done_at"] is None and n["done_count"] == 1


def test_validation_and_snooze():
    with pytest.raises(ValueError):
        notes.add_note("  ")
    with pytest.raises(ValueError):
        notes.add_note("متكرر", repeat="weekly")          # بلا موعد
    with pytest.raises(ValueError):
        notes.add_note("خطأ", due="غداً")
    nid = notes.add_note("موعد", due="2020-01-01")
    assert notes.list_notes()[0]["due_at"] == "2020-01-01 09:00"
    when = notes.snooze(nid, 60)
    assert when > _fmt(datetime.now())
    assert notes.due_now() == []
    assert notes.describe_due(_fmt(datetime.now() + timedelta(days=1))).startswith("غداً")
    assert notes.describe_due(_fmt(datetime.now() - timedelta(days=3))) == "متأخر منذ 3 يوم"


def test_notes_dialog_and_reminder_popup():
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    from ui.notes_dialog import NotesDialog, ReminderPopup
    dlg = NotesDialog()
    dlg.title_in.setText("طلب أكياس")
    dlg.has_due.setChecked(True)
    dlg.repeat.setCurrentIndex(dlg.repeat.findData("weekly"))
    nid = dlg.save()
    assert nid and dlg.list.count() == 1 and dlg.current["repeat"] == "weekly"
    dlg.body.setPlainText("من مورد التغليف")
    dlg.save()
    assert notes.list_notes()[0]["body"] == "من مورد التغليف"
    dlg.mark_done()                                      # متكرر: ينتقل أسبوعاً
    assert notes.list_notes()[0]["done_count"] == 1
    dlg.new_note()
    assert dlg.current is None and not dlg.done_btn.isEnabled()
    dlg.close()

    host = QWidget()
    host.resize(1000, 700)
    notes.add_note("اتصل بالبنك", due="2020-05-05 10:00")
    rows = notes.pop_new_due()
    pop = ReminderPopup(host, rows)
    assert len(pop.items) == 1
    pop._act(pop.items[0], notes.complete, rows[0]["id"])
    assert pop.isHidden()
    host.close()
    app.processEvents()


def test_assistant_lists_reminders():
    from core import assistant
    notes.add_note("زيارة المندوب", due=_fmt(datetime.now() - timedelta(minutes=1)))
    a = assistant.answer("ذكّرني")
    assert a["intent"] == "notes" and "زيارة المندوب" in a["lines"][0]
