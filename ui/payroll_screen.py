# -*- coding: utf-8 -*-
"""شاشة الموظفين والرواتب: الموظفون، السلف، صرف الرواتب، قسيمة الراتب"""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QDialog, QFormLayout, QLineEdit,
                               QComboBox, QCheckBox, QSplitter)

from core import payroll, shifts
from core.utils import money
from ui import printing
from ui.widgets import Table, button, page, hint, card, KpiCard, MoneySpin, ok_cancel, warn, info, m


class EmployeeDialog(QDialog):
    def __init__(self, parent, emp=None):
        super().__init__(parent)
        self.setWindowTitle("موظف")
        self.emp = emp
        f = QFormLayout(self)
        self.name = QLineEdit(emp["name"] if emp else "")
        self.job = QLineEdit(emp["job"] or "" if emp else "")
        self.job.setPlaceholderText("كاشير، مخزن، توصيل...")
        self.phone = QLineEdit(emp["phone"] or "" if emp else "")
        self.salary = MoneySpin()
        self.salary.setValue(emp["salary"] if emp else 0)
        self.active = QCheckBox("على رأس عمله")
        self.active.setChecked(bool(emp["is_active"]) if emp else True)
        f.addRow("الاسم:", self.name)
        f.addRow("الوظيفة:", self.job)
        f.addRow("الهاتف:", self.phone)
        f.addRow("الراتب الشهري:", self.salary)
        if emp:
            f.addRow("", self.active)
        ok_cancel(self, f)

    def accept(self):
        try:
            if self.emp:
                payroll.update_employee(self.emp["id"], self.name.text(), self.salary.value(), self.job.text(),
                                        self.phone.text(), self.active.isChecked())
            else:
                payroll.add_employee(self.name.text(), self.salary.value(), self.job.text(), self.phone.text())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class AdvanceDialog(QDialog):
    def __init__(self, parent, emp):
        super().__init__(parent)
        self.setWindowTitle(f"سلفة — {emp['name']}")
        self.emp = emp
        f = QFormLayout(self)
        f.addRow(hint(f"السلف المتبقية عليه حالياً: {m(emp['advances'])}. تُخصم تلقائياً من راتبه القادم."))
        self.amount = MoneySpin()
        self.method = QComboBox()
        self.method.addItems(payroll.METHODS)
        self.note = QLineEdit()
        f.addRow("المبلغ:", self.amount)
        f.addRow("الدفع:", self.method)
        f.addRow("ملاحظة:", self.note)
        ok_cancel(self, f, "صرف السلفة")

    def accept(self):
        try:
            payroll.give_advance(self.emp["id"], self.amount.value(), self.method.currentText(), self.note.text(),
                                 shift_id=shifts.current_shift_id())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class SalaryDialog(QDialog):
    def __init__(self, parent, emp):
        super().__init__(parent)
        self.setWindowTitle(f"صرف راتب — {emp['name']}")
        self.emp = emp
        self.result = None
        f = QFormLayout(self)
        self.period = QComboBox()
        t = date.today()
        for k in range(0, 4):
            y, mo = (t.year, t.month - k) if t.month - k > 0 else (t.year - 1, t.month - k + 12)
            self.period.addItem(f"{y}-{mo:02d}")
        self.base = MoneySpin()
        self.base.setValue(emp["salary"])
        self.bonus = MoneySpin()
        self.deductions = MoneySpin()
        self.advances = MoneySpin()
        self.advances.setValue(min(emp["advances"], emp["salary"]))
        self.method = QComboBox()
        self.method.addItems(payroll.METHODS)
        self.note = QLineEdit()
        self.net = QLabel()
        self.net.setObjectName("bigNumber")
        for w in (self.base, self.bonus, self.deductions, self.advances):
            w.valueChanged.connect(self.update_net)
        f.addRow("عن شهر:", self.period)
        f.addRow("الراتب الأساسي:", self.base)
        f.addRow("مكافأة / إضافي:", self.bonus)
        f.addRow("خصومات (غياب، تأخير):", self.deductions)
        f.addRow(f"خصم من السلف (عليه {m(emp['advances'])}):", self.advances)
        f.addRow("الدفع:", self.method)
        f.addRow("ملاحظة:", self.note)
        f.addRow("الصافي المدفوع:", self.net)
        self.update_net()
        ok_cancel(self, f, "صرف الراتب")

    def update_net(self):
        self.net.setText(m(self.base.value() + self.bonus.value() - self.deductions.value() - self.advances.value()))

    def accept(self):
        try:
            self.result = payroll.pay_salary(self.emp["id"], self.period.currentText(), self.base.value(),
                                             self.bonus.value(), self.deductions.value(), self.advances.value(),
                                             self.method.currentText(), self.note.text(),
                                             shift_id=shifts.current_shift_id())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class PayrollScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        head.addWidget(button("+ موظف جديد", "successBtn", self.new_employee))
        head.addWidget(button("✏ تعديل", "secondaryBtn", self.edit_employee))
        head.addWidget(button("💵 سلفة", "secondaryBtn", self.advance))
        head.addWidget(button("🧾 صرف الراتب", "primaryBtn", self.pay))
        head.addWidget(button("🖨 قسيمة الراتب", "secondaryBtn", self.print_slip))
        head.addStretch()
        self.show_all = QCheckBox("إظهار الموظفين السابقين")
        self.show_all.toggled.connect(self.refresh)
        head.addWidget(self.show_all)
        lay.addLayout(head)

        g = QGridLayout()
        g.setSpacing(14)
        self.k_total = KpiCard("الرواتب الشهرية", "#2563EB", "👔")
        self.k_adv = KpiCard("سلف لم تُسترد", "#D97706", "💵")
        self.k_due = KpiCard("رواتب هذا الشهر لم تُصرف", "#DC2626", "🗓")
        for i, k in enumerate((self.k_total, self.k_adv, self.k_due)):
            g.addWidget(k, 0, i)
        lay.addLayout(g)

        split = QSplitter(Qt.Horizontal)
        self.table = Table(["الموظف", "الوظيفة", "الراتب", "السلف المتبقية", "آخر راتب مصروف"], stretch=0)
        self.table.itemSelectionChanged.connect(self.load_history)
        self.table.doubleClicked.connect(self.edit_employee)
        split.addWidget(self.table)
        hc, hl = card()
        self.h_title = QLabel("اختر موظفاً لعرض كشفه")
        self.h_title.setObjectName("subTitle")
        hl.addWidget(self.h_title)
        self.history = Table(["التاريخ", "البيان", "المستحق", "سلف", "المدفوع"], stretch=1)
        hl.addWidget(self.history, 1)
        split.addWidget(hc)
        split.setSizes([620, 480])
        lay.addWidget(split, 1)
        lay.addWidget(hint("السلفة ليست مصروفاً: تبقى ديناً على الموظف وتُخصم من راتبه. الراتب المستحق يظهر في المصاريف "
                           "وتقرير الأرباح، وما يُدفع من الصندوق يُخصم من النقد المتوقع في الوردية."))

    def refresh(self):
        rows = payroll.list_employees(active_only=not self.show_all.isChecked())
        period = date.today().strftime("%Y-%m")
        self.table.set_rows([[r["name"], r["job"] or "", float(r["salary"]), float(r["advances"]),
                              r["last_period"] or "—"] for r in rows], rows)
        active = [r for r in rows if r["is_active"]]
        self.k_total.set(m(sum(r["salary"] for r in active)), f"{len(active)} موظف")
        self.k_adv.set(m(sum(r["advances"] for r in rows)))
        due = [r for r in active if (r["last_period"] or "") < period and r["salary"] > 0]
        self.k_due.set(str(len(due)), period)
        self.load_history()

    def selected(self):
        r = self.table.selected_data()
        if not r:
            warn(self, "اختر موظفاً")
        return r

    def load_history(self):
        r = self.table.selected_data()
        if not r:
            self.history.set_rows([])
            return
        self.h_title.setText(f"كشف {r['name']}")
        rows = []
        for h in payroll.history(r["id"]):
            if h["kind"] == "advance":
                rows.append([h["created_at"][:10], f"سلفة ({h['method']})", "", float(h["amount"]), ""])
            else:
                rows.append([h["created_at"][:10], f"راتب {h['period']} ({h['method']})",
                             float(money(h["base"] + h["bonus"] - h["deductions"])), float(h["advances"]),
                             float(h["net"])])
        self.history.set_rows(rows)

    def new_employee(self):
        if EmployeeDialog(self).exec() == QDialog.Accepted:
            self.refresh()

    def edit_employee(self, *_):
        r = self.selected()
        if r and EmployeeDialog(self, r).exec() == QDialog.Accepted:
            self.refresh()

    def advance(self):
        r = self.selected()
        if r and AdvanceDialog(self, r).exec() == QDialog.Accepted:
            self.refresh()

    def pay(self):
        r = self.selected()
        if not r:
            return
        dlg = SalaryDialog(self, r)
        if dlg.exec() == QDialog.Accepted:
            res = dlg.result
            info(self, f"تم صرف الراتب: المستحق {m(res['gross'])}، خُصم من السلف {m(res['advances'])}، "
                       f"الصافي المدفوع {m(res['net'])}.")
            self.refresh()
            printing.print_html(self, payroll.payslip_html(res["id"]), width_mm=210, preview=True)

    def print_slip(self):
        r = self.selected()
        if not r:
            return
        last = [h for h in payroll.history(r["id"]) if h["kind"] == "salary"]
        if not last:
            warn(self, "لم يُصرف له راتب بعد")
            return
        printing.print_html(self, payroll.payslip_html(last[0]["id"]), width_mm=210, preview=True)
