# -*- coding: utf-8 -*-
"""شاشة العملاء والديون (الدفتر): كشف حساب، تسديد، تذكير واتساب، طباعة"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QCheckBox, QLabel, QDialog, QFormLayout,
                               QComboBox, QSplitter)
from PySide6.QtCore import Qt

from core import customers, receipts, shifts, whatsapp, loyalty
from ui import printing
from ui.dialogs import CustomerDialog, TextDialog
from ui.widgets import (Table, button, page, title, hint, warn, info, ask, error, MoneySpin, ok_cancel, m, card,
                        require_permission, open_whatsapp)


class BulkReminderDialog(QDialog):
    """قائمة المدينين: زر واحد لكل عميل يفتح واتساب والرسالة جاهزة"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("تذكير جماعي عبر واتساب")
        self.resize(640, 480)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("الحد الأدنى للدين:"))
        self.min_amount = MoneySpin()
        self.min_amount.setValue(50)
        self.min_amount.valueChanged.connect(self.load)
        row.addWidget(self.min_amount)
        row.addStretch()
        lay.addLayout(row)
        self.table = Table(["العميل", "الهاتف", "الدين", "الحالة"], stretch=0)
        self.table.doubleClicked.connect(self.send_selected)
        lay.addWidget(self.table)
        b = QHBoxLayout()
        b.addWidget(button("📱 إرسال للمحدد ثم التالي", "successBtn", self.send_selected))
        b.addStretch()
        lay.addLayout(b)
        lay.addWidget(hint("كل ضغطة تفتح واتساب برسالة العميل جاهزة؛ اضغط إرسال في واتساب ثم عد للبرنامج للعميل التالي."))
        self.sent = set()
        self.load()

    def load(self):
        rows = [r for r in customers.list_customers(debtors_only=True) if r["balance_due"] >= self.min_amount.value()]
        self.table.set_rows([[r["name"], r["phone"] or "— لا يوجد —", float(r["balance_due"]),
                              "✓ أُرسلت" if r["id"] in self.sent else ""] for r in rows], rows,
                            colors=[("#DCFCE7" if r["id"] in self.sent else None) for r in rows])
        if rows:
            self.table.selectRow(0)

    def send_selected(self):
        c = self.table.selected_data()
        if not c:
            return
        current = self.table.currentRow()
        if open_whatsapp(self, whatsapp.reminder_link(c["id"]), customers.reminder_message(c["id"])):
            self.sent.add(c["id"])
        self.load()
        if current + 1 < self.table.rowCount():
            self.table.selectRow(current + 1)


class PaymentInDialog(QDialog):
    def __init__(self, parent, customer, balance):
        super().__init__(parent)
        self.setWindowTitle(f"تسديد دفعة - {customer['name']}")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"الرصيد المستحق: <b>{m(balance)}</b>"))
        self.amount = MoneySpin(big=True)
        self.amount.setValue(max(balance, 0))
        self.method = QComboBox()
        self.method.addItems(customers.PAYMENT_METHODS)
        self.note = QLineEdit()
        lay.addRow("المبلغ:", self.amount)
        lay.addRow("طريقة الدفع:", self.method)
        lay.addRow("ملاحظة:", self.note)
        ok_cancel(self, lay, "تسجيل الدفعة")
        self.amount.setFocus()


class CustomersScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        head.addStretch()
        self.total_lbl = QLabel("")
        self.total_lbl.setObjectName("chipWarn")
        head.addWidget(self.total_lbl)
        head.addWidget(button("📣 تذكير جماعي للمدينين", "secondaryBtn", self.bulk_reminders))
        head.addWidget(button("+ عميل جديد", "successBtn", self.add))
        lay.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        # قائمة العملاء
        left, ll = card()
        f = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 بحث بالاسم أو الهاتف...")
        self.search.textChanged.connect(self.load)
        self.debtors = QCheckBox("المدينون فقط")
        self.debtors.toggled.connect(self.load)
        f.addWidget(self.search, 1)
        f.addWidget(self.debtors)
        ll.addLayout(f)
        self.table = Table(["الاسم", "الهاتف", "الرصيد المستحق", "حد الدين", "آخر تسديد"])
        self.table.itemSelectionChanged.connect(self.load_statement)
        self.table.doubleClicked.connect(self.edit)
        ll.addWidget(self.table)
        split.addWidget(left)

        # كشف الحساب
        right, rl = card()
        self.cust_title = QLabel("اختر عميلاً لعرض كشف حسابه")
        self.cust_title.setObjectName("subTitle")
        rl.addWidget(self.cust_title)
        self.balance_lbl = QLabel("")
        self.balance_lbl.setObjectName("bigNumber")
        rl.addWidget(self.balance_lbl)
        btns = QGridLayout()
        for i, (text, obj, slot) in enumerate([("💰 تسديد دفعة", "successBtn", self.pay), ("🖨 طباعة الكشف", "secondaryBtn", self.print_statement),
                                ("💬 تذكير واتساب", "secondaryBtn", self.reminder), ("✏ تعديل", "secondaryBtn", self.edit),
                                ("⚖ تسوية", "secondaryBtn", self.adjust), ("📥 استلام شيك", "secondaryBtn", self.receive_cheque),
                                ("🗑 حذف", "dangerBtn", self.delete)]):
            btns.addWidget(button(text, obj, slot), i // 3, i % 3)
        rl.addLayout(btns)
        self.statement = Table(["التاريخ", "البيان", "عليه (مدين)", "له (دائن)", "الرصيد"], stretch=1, sortable=False)
        rl.addWidget(self.statement)
        split.addWidget(right)
        split.setSizes([480, 560])
        lay.addWidget(split, 1)

    def refresh(self):
        self.load()

    def load(self):
        rows = customers.list_customers(self.search.text().strip() or None, self.debtors.isChecked())
        self.table.set_rows([[r["name"], r["phone"] or "", float(r["balance_due"]),
                              float(r["credit_limit"]) if r["credit_limit"] else "بلا حد",
                              (r["last_payment"] or "")[:10]] for r in rows], rows,
                            colors=[("#FEF2F2" if r["credit_limit"] and r["balance_due"] > r["credit_limit"] else None) for r in rows])
        self.total_lbl.setText(f"إجمالي الديون: {m(customers.total_debts())}")

    def current(self):
        return self.table.selected_data()

    def load_statement(self):
        c = self.current()
        if not c:
            return
        opening, rows = customers.statement(c["id"])
        self.cust_title.setText(f"{c['name']}   {c['phone'] or ''}")
        bal = customers.balance(c["id"])
        pts = loyalty.balance(c["id"]) if loyalty.enabled() else 0
        self.balance_lbl.setText(f"الرصيد: {m(bal)}" + (f"   🎁 {pts:g} نقطة" if pts else ""))
        self.balance_lbl.setStyleSheet(f"color:{'#DC2626' if bal > 0 else '#16A34A'};")
        rows = list(reversed(rows))
        self.statement.set_rows([[r["created_at"][:16], f"{r['type_label']} {r['note'] or ''}".strip(),
                                  float(r["debit"]) if r["debit"] else "", float(r["credit"]) if r["credit"] else "",
                                  float(r["running"])] for r in rows], rows)

    def need(self):
        c = self.current()
        if not c:
            warn(self, "اختر عميلاً أولاً")
        return c

    def add(self):
        if CustomerDialog(self).exec() == QDialog.Accepted:
            self.load()

    def edit(self):
        c = self.need()
        if c and CustomerDialog(self, customers.get_customer(c["id"])).exec() == QDialog.Accepted:
            self.load()

    def pay(self):
        c = self.need()
        if not c:
            return
        bal = customers.balance(c["id"])
        dlg = PaymentInDialog(self, c, bal)
        if dlg.exec() == QDialog.Accepted:
            try:
                customers.receive_payment(c["id"], dlg.amount.value(), dlg.method.currentText(), dlg.note.text(),
                                          shift_id=shifts.current_shift_id())
            except ValueError as e:
                warn(self, str(e))
                return
            self.load()
            self.reselect(c["id"])
            info(self, f"تم تسجيل الدفعة. الرصيد الجديد: {m(customers.balance(c['id']))}")

    def reselect(self, cid):
        for r in range(self.table.rowCount()):
            d = self.table._data[self.table.item(r, 0).data(Qt.UserRole)]
            if d["id"] == cid:
                self.table.selectRow(r)
                break

    def adjust(self):
        c = self.need()
        if not c or not require_permission(self, "reports"):
            return
        from PySide6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(self, "تسوية الحساب", "المبلغ (+ يزيد الدين، − ينقصه مثل مسامحة):", 0, -1e9, 1e9, 2)
        if ok and val:
            note, ok2 = QInputDialog.getText(self, "تسوية", "سبب التسوية:")
            if ok2:
                customers.adjust_balance(c["id"], val, note or "تسوية")
                self.load()
                self.reselect(c["id"])

    def print_statement(self):
        c = self.need()
        if c:
            printing.print_html(self, receipts.statement_html(c["id"]), width_mm=210, preview=True)

    def reminder(self):
        c = self.need()
        if c:
            open_whatsapp(self, whatsapp.reminder_link(c["id"]), customers.reminder_message(c["id"]))

    def bulk_reminders(self):
        BulkReminderDialog(self).exec()

    def delete(self):
        c = self.need()
        if c and ask(self, f"حذف العميل {c['name']}؟"):
            try:
                customers.deactivate_customer(c["id"])
            except ValueError as e:
                warn(self, str(e))
            self.load()

    def receive_cheque(self):
        c = self.need()
        if not c:
            return
        from ui.cheques_screen import ChequeDialog
        if require_permission(self, "cheques") and ChequeDialog(self, "in", c["id"]).exec() == QDialog.Accepted:
            self.load()
            self.reselect(c["id"])
