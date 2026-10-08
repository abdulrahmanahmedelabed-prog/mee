# -*- coding: utf-8 -*-
"""الملاحظات والتذكيرات: قائمة وتحرير في نافذة واحدة، وتنبيه منبثق عند حلول الموعد"""

from PySide6.QtCore import QDateTime, Qt, QTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QTextEdit, QVBoxLayout, QWidget)

from core import i18n, notes
from ui.widgets import ask, button, card, error, hint, title

COLOR_NAMES = ["أزرق", "أخضر", "برتقالي", "أحمر", "بنفسجي", "سماوي"]


def _line(n):
    parts = [("📌 " if n["pinned"] else "") + n["title"]]
    if n["due_at"]:
        parts.append("⏰ " + i18n.tr(notes.describe_due(n["due_at"])))
    if n["repeat"]:
        parts.append("🔁 " + i18n.tr(notes.REPEATS[n["repeat"]]))
    if n["shared"]:
        parts.append("👥")
    if n["done_at"]:
        parts.append("✓ " + i18n.tr("منجزة"))
    return "   ".join(parts)


class NotesDialog(QDialog):
    def __init__(self, parent=None, select_id=None):
        super().__init__(parent)
        self.setWindowTitle("📝 الملاحظات والتذكيرات")
        self.resize(940, 600)
        self.current = None
        outer = QVBoxLayout(self)
        outer.addWidget(title("📝 الملاحظات والتذكيرات", "pageTitle"))
        outer.addWidget(hint("دوّن ما تريد تذكّره: موعد مورد، دفع فاتورة الكهرباء كل شهر، جرد الثلاجة كل أسبوع... "
                             "يظهر تنبيه عند حلول الموعد. اجعلها «مشتركة» ليراها كل الموظفين."))
        row = QHBoxLayout()
        outer.addLayout(row, 1)

        # ---- القائمة
        left = QVBoxLayout()
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 بحث في الملاحظات...")
        self.search.textChanged.connect(self.load)
        bar.addWidget(self.search, 1)
        self.show_done = QCheckBox("المنجزة")
        self.show_done.toggled.connect(self.load)
        bar.addWidget(self.show_done)
        left.addLayout(bar)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(self._picked)
        left.addWidget(self.list, 1)
        left.addWidget(button("+ ملاحظة جديدة", "primaryBtn", self.new_note))
        row.addLayout(left, 5)

        # ---- التحرير
        box, form_lay = card()
        form = QFormLayout()
        form.setSpacing(8)
        self.title_in = QLineEdit()
        self.title_in.setPlaceholderText("مثال: دفع فاتورة الكهرباء")
        self.body = QTextEdit()
        self.body.setPlaceholderText("تفاصيل (اختياري)")
        self.body.setMinimumHeight(110)
        self.has_due = QCheckBox("ذكّرني في:")
        self.due = QDateTimeEdit(calendarPopup=True)
        self.due.setDisplayFormat("yyyy-MM-dd  HH:mm")
        self.due.setLayoutDirection(Qt.LeftToRight)
        self.has_due.toggled.connect(self.due.setEnabled)
        due_row = QHBoxLayout()
        due_row.addWidget(self.has_due)
        due_row.addWidget(self.due, 1)
        self.repeat = QComboBox()
        for key, label in notes.REPEATS.items():
            self.repeat.addItem(i18n.tr(label), key)
        self.color = QComboBox()
        for name, c in zip(COLOR_NAMES, notes.COLORS):
            self.color.addItem("●  " + i18n.tr(name), c)
            self.color.setItemData(self.color.count() - 1, QColor(c), Qt.ForegroundRole)
        self.shared = QCheckBox("مشتركة لكل موظفي المحل")
        self.pinned = QCheckBox("تثبيت في الأعلى")
        form.addRow(i18n.tr("العنوان:"), self.title_in)
        form.addRow(i18n.tr("التفاصيل:"), self.body)
        form.addRow(due_row)
        form.addRow(i18n.tr("التكرار:"), self.repeat)
        form.addRow(i18n.tr("اللون:"), self.color)
        form.addRow(self.shared)
        form.addRow(self.pinned)
        form_lay.addLayout(form)
        acts = QHBoxLayout()
        acts.addWidget(button("💾 حفظ", "primaryBtn", self.save))
        self.done_btn = button("✓ تم", "successBtn", self.mark_done, "تم: المتكرر ينتقل لموعده القادم")
        acts.addWidget(self.done_btn)
        self.later_btn = button("⏰ لاحقاً", "secondaryBtn", self.later)
        acts.addWidget(self.later_btn)
        acts.addStretch()
        self.del_btn = button("حذف", "dangerBtn", self.delete)
        acts.addWidget(self.del_btn)
        form_lay.addLayout(acts)
        self.info = QLabel("")
        self.info.setObjectName("hint")
        form_lay.addWidget(self.info)
        row.addWidget(box, 6)

        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(button("إغلاق", "secondaryBtn", self.accept))
        outer.addLayout(foot)
        self.load(select_id=select_id)
        if self.list.count() == 0:
            self.new_note()

    # ------------------------------------------------------------------
    def load(self, *_a, select_id=None):
        keep = select_id or (self.current["id"] if self.current else None)
        self.list.blockSignals(True)
        self.list.clear()
        rows = notes.list_notes(self.show_done.isChecked(), self.search.text())
        pick = None
        for n in rows:
            it = QListWidgetItem(_line(n))
            it.setData(Qt.UserRole, n)
            it.setForeground(QColor(n["color"] or notes.COLORS[0]))
            if n["due_at"] and not n["done_at"] and notes.describe_due(n["due_at"]).startswith(("مستحق", "متأخر")):
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            if n["done_at"]:
                f = it.font()
                f.setStrikeOut(True)
                it.setFont(f)
            if n.get("body"):
                it.setToolTip(n["body"])
            self.list.addItem(it)
            if n["id"] == keep:
                pick = it
        self.list.blockSignals(False)
        if pick is not None:
            self.list.setCurrentItem(pick)
        elif self.current is not None and keep is not None:
            self.new_note()

    def _picked(self, item, _prev=None):
        if item is None:
            return
        n = item.data(Qt.UserRole)
        self.current = n
        self.title_in.setText(n["title"])
        self.body.setPlainText(n["body"] or "")
        self.has_due.setChecked(bool(n["due_at"]))
        self.due.setEnabled(bool(n["due_at"]))
        if n["due_at"]:
            self.due.setDateTime(QDateTime.fromString(n["due_at"], "yyyy-MM-dd HH:mm"))
        self.repeat.setCurrentIndex(max(self.repeat.findData(n["repeat"] or ""), 0))
        self.color.setCurrentIndex(max(self.color.findData(n["color"] or notes.COLORS[0]), 0))
        self.shared.setChecked(bool(n["shared"]))
        self.pinned.setChecked(bool(n["pinned"]))
        by = n.get("author") or ""
        done = n["done_count"]
        self.info.setText(i18n.tr("كتبها: {0}").format(by) + (f"   •   ✓ ×{done}" if done else "")
                          if by else (f"✓ ×{done}" if done else ""))
        for b in (self.done_btn, self.later_btn, self.del_btn):
            b.setEnabled(True)
        self.done_btn.setText(i18n.tr("↺ إعادة فتح") if n["done_at"] else i18n.tr("✓ تم"))

    def new_note(self):
        self.current = None
        self.list.blockSignals(True)
        self.list.setCurrentItem(None)
        self.list.clearSelection()
        self.list.blockSignals(False)
        self.title_in.clear()
        self.body.clear()
        self.has_due.setChecked(False)
        self.due.setEnabled(False)
        tomorrow = QDateTime.currentDateTime().addDays(1)
        tomorrow.setTime(QTime(9, 0))
        self.due.setDateTime(tomorrow)
        self.repeat.setCurrentIndex(0)
        self.color.setCurrentIndex(0)
        self.shared.setChecked(False)
        self.pinned.setChecked(False)
        self.info.setText("")
        for b in (self.done_btn, self.later_btn, self.del_btn):
            b.setEnabled(False)
        self.done_btn.setText(i18n.tr("✓ تم"))
        self.title_in.setFocus()

    def _values(self):
        due = self.due.dateTime().toString("yyyy-MM-dd HH:mm") if self.has_due.isChecked() else None
        return dict(title=self.title_in.text(), body=self.body.toPlainText(), due=due,
                    repeat=self.repeat.currentData() or "", shared=self.shared.isChecked(),
                    color=self.color.currentData(), pinned=self.pinned.isChecked())

    def save(self):
        try:
            if self.current:
                notes.update_note(self.current["id"], **self._values())
                nid = self.current["id"]
            else:
                nid = notes.add_note(**self._values())
        except ValueError as e:
            return error(self, i18n.tr(str(e)))
        self.load(select_id=nid)
        return nid

    def mark_done(self):
        if not self.current:
            return
        if self.current["done_at"]:
            notes.reopen(self.current["id"])
        else:
            notes.complete(self.current["id"])
        self.load(select_id=self.current["id"])

    def later(self):
        if not self.current:
            return
        menu = QMenu(self)
        for label, minutes in (("بعد ساعة", 60), ("بعد 3 ساعات", 180), ("غداً", 24 * 60), ("بعد أسبوع", 7 * 24 * 60)):
            menu.addAction(i18n.tr(label), lambda m=minutes: self._snooze(m))
        menu.exec(self.later_btn.mapToGlobal(self.later_btn.rect().bottomLeft()))

    def _snooze(self, minutes):
        notes.snooze(self.current["id"], minutes)
        self.load(select_id=self.current["id"])

    def delete(self):
        if self.current and ask(self, i18n.tr("حذف الملاحظة «{0}»؟").format(self.current["title"])):
            notes.delete_note(self.current["id"])
            self.current = None
            self.load()
            self.new_note()


# ---------------------------------------------------------------------------
class ReminderPopup(QFrame):
    """تنبيه صغير أسفل النافذة عند حلول موعد تذكير، دون مقاطعة البيع"""

    def __init__(self, win, rows):
        super().__init__(win)
        self.win = win
        self.setObjectName("card")
        self.setStyleSheet("QFrame#card { border: 2px solid #F59E0B; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        head = QHBoxLayout()
        head.addWidget(title("⏰ " + i18n.tr("تذكير"), "subTitle"), 1)
        head.addWidget(button("✕", "ghostBtn", self.close_popup))
        lay.addLayout(head)
        self.items = []
        for n in rows[:4]:
            w = QWidget()
            self.items.append(w)
            r = QHBoxLayout(w)
            r.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(n["title"] + (f"\n{n['body']}" if n.get("body") else ""))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{n['color'] or notes.COLORS[0]}; font-weight:600;")
            r.addWidget(lbl, 1)
            r.addWidget(button("✓ تم", "successBtn", lambda _=False, i=n["id"], w=w: self._act(w, notes.complete, i)))
            r.addWidget(button("⏰ بعد ساعة", "secondaryBtn",
                               lambda _=False, i=n["id"], w=w: self._act(w, notes.snooze, i)))
            lay.addWidget(w)
        if len(rows) > 4:
            lay.addWidget(hint(i18n.tr("و{0} تذكيرات أخرى").format(len(rows) - 4)))
        lay.addWidget(button("📝 فتح الملاحظات", "ghostBtn", self.open_all))
        self.setFixedWidth(380)
        self.adjustSize()
        self.place()
        self.show()
        self.raise_()

    def place(self):
        g = self.win.rect()
        x = 24 if i18n.is_rtl() else g.width() - self.width() - 24
        self.move(x, g.height() - self.height() - 64)

    def _act(self, w, fn, note_id):
        try:
            fn(note_id)
        except ValueError:
            pass
        w.hide()
        if all(x.isHidden() for x in self.items):
            self.close_popup()
        if hasattr(self.win, "refresh_notes"):
            self.win.refresh_notes()

    def open_all(self):
        self.close_popup()
        open_notes(self.win)

    def close_popup(self):
        self.hide()
        self.deleteLater()


def open_notes(parent, select_id=None):
    dlg = NotesDialog(parent, select_id)
    dlg.exec()
    if hasattr(parent, "refresh_notes"):
        parent.refresh_notes()
    return dlg
