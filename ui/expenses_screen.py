# -*- coding: utf-8 -*-
"""شاشة المصاريف"""

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QComboBox, QCheckBox, QDateEdit, QSplitter

from core import expenses, settings, shifts
from ui.widgets import Table, button, page, title, warn, ask, MoneySpin, m, card, DateRange, require_permission


class ExpensesScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        form_card, fl = card(QHBoxLayout)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setMinimumWidth(160)
        self.amount = MoneySpin()
        self.amount.setMinimumWidth(120)
        self.note = QLineEdit()
        self.note.setPlaceholderText("ملاحظة (مثال: فاتورة كهرباء شهر 9)")
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(QDate.currentDate())
        self.from_drawer = QCheckBox("من الصندوق")
        self.from_drawer.setChecked(True)
        self.from_drawer.setToolTip("إذا دُفع المبلغ من نقود الصندوق فسيُخصم من النقد المتوقع في الوردية")
        for lbl, wdg in [("النوع:", self.category), ("المبلغ:", self.amount), ("", self.note), ("التاريخ:", self.date)]:
            if lbl:
                fl.addWidget(QLabel(lbl))
            fl.addWidget(wdg, 1 if wdg is self.note else 0)
        fl.addWidget(self.from_drawer)
        fl.addWidget(button("+ إضافة مصروف", "successBtn", self.add))
        lay.addWidget(form_card)

        self.range = DateRange("هذا الشهر")
        self.range.changed.connect(self.load)
        lay.addWidget(self.range)

        split = QSplitter(Qt.Horizontal)
        self.table = Table(["التاريخ", "النوع", "المبلغ", "ملاحظة", "من الصندوق", "المستخدم"], stretch=3)
        split.addWidget(self.table)
        self.by_cat = Table(["النوع", "العدد", "الإجمالي"])
        split.addWidget(self.by_cat)
        split.setSizes([750, 350])
        lay.addWidget(split, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(button("🗑 حذف المحدد", "dangerBtn", self.delete))
        bottom.addStretch()
        self.total = QLabel("")
        self.total.setObjectName("subTitle")
        bottom.addWidget(self.total)
        lay.addLayout(bottom)

    def refresh(self):
        cur = self.category.currentText()
        self.category.clear()
        self.category.addItems(settings.expense_categories())
        if cur:
            self.category.setCurrentText(cur)
        self.load()

    def load(self):
        a, b = self.range.range()
        rows = expenses.list_expenses(a, b)
        self.table.set_rows([[r["expense_date"], r["category"], float(r["amount"]), r["note"] or "",
                              "نعم" if r["from_drawer"] else "لا", r["username"] or ""] for r in rows], rows)
        cats = expenses.totals_by_category(a, b)
        self.by_cat.set_rows([[c["category"], c["cnt"], float(c["total"])] for c in cats])
        self.total.setText(f"إجمالي المصاريف: {m(sum(r['amount'] for r in rows))}")

    def add(self):
        from_drawer = self.from_drawer.isChecked()
        shift_id = shifts.current_shift_id()
        if from_drawer and not shift_id and settings.get_bool("require_shift"):
            warn(self, "لا توجد وردية مفتوحة. افتح وردية من شاشة الصندوق، أو ألغِ خيار (من الصندوق).")
            return
        try:
            expenses.add_expense(self.category.currentText(), self.amount.value(), self.note.text(), from_drawer,
                                 self.date.date().toString("yyyy-MM-dd"), shift_id)
        except ValueError as e:
            warn(self, str(e))
            return
        self.amount.setValue(0)
        self.note.clear()
        self.load()

    def delete(self):
        r = self.table.selected_data()
        if r and require_permission(self, "expenses") and ask(self, f"حذف مصروف {r['category']} بقيمة {m(r['amount'])}؟"):
            expenses.delete_expense(r["id"])
            self.load()
