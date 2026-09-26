# -*- coding: utf-8 -*-
"""شاشة الشيكات المؤجلة: الواردة من العملاء والصادرة للموردين، مع الاستحقاقات"""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QDialog, QFormLayout, QLineEdit,
                               QDateEdit, QGridLayout)

from core import cheques, customers, suppliers
from ui.widgets import Table, button, page, hint, warn, info, ask, MoneySpin, ok_cancel, m, KpiCard, require_permission


class ChequeDialog(QDialog):
    """استلام شيك من عميل أو إعطاء شيك لمورد"""

    def __init__(self, parent, direction, party_id=None):
        super().__init__(parent)
        self.direction = direction
        self.setWindowTitle("استلام شيك من عميل" if direction == "in" else "إعطاء شيك مؤجل لمورد")
        self.setMinimumWidth(440)
        lay = QFormLayout(self)
        self.party = QComboBox()
        if direction == "in":
            for c in customers.list_customers():
                self.party.addItem(f"{c['name']}  (عليه {m(c['balance_due'])})", c["id"])
        else:
            for s in suppliers.list_suppliers():
                self.party.addItem(f"{s['name']}  (له {m(s['balance_due'])})", s["id"])
        if party_id:
            self.party.setCurrentIndex(max(0, self.party.findData(party_id)))
        self.amount = MoneySpin(big=True)
        self.number = QLineEdit()
        self.bank = QLineEdit()
        self.bank.setPlaceholderText("مثل: بنك فلسطين - فرع نابلس")
        self.due = QDateEdit(calendarPopup=True)
        self.due.setDisplayFormat("yyyy-MM-dd")
        self.due.setDate(QDate.currentDate().addDays(30))
        self.note = QLineEdit()
        lay.addRow("العميل:" if direction == "in" else "المورد:", self.party)
        lay.addRow("المبلغ:", self.amount)
        lay.addRow("رقم الشيك:", self.number)
        lay.addRow("البنك:", self.bank)
        lay.addRow("تاريخ الاستحقاق:", self.due)
        lay.addRow("ملاحظة:", self.note)
        lay.addRow("", hint("يُخصم المبلغ من رصيد العميل فوراً. إذا رجع الشيك اضغط «راجع» ويعود الدين تلقائياً."
                            if direction == "in" else
                            "يُخصم المبلغ من مستحقات المورد فوراً، ويبقى التزاماً عليك حتى يُصرف من البنك."))
        ok_cancel(self, lay, "حفظ الشيك")

    def accept(self):
        if self.party.currentData() is None:
            warn(self, "اختر الجهة")
            return
        args = (self.party.currentData(), self.amount.value(), self.due.date().toString("yyyy-MM-dd"),
                self.number.text(), self.bank.text(), self.note.text())
        try:
            (cheques.receive_cheque if self.direction == "in" else cheques.issue_cheque)(*args)
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class ChequesScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        g = QGridLayout()
        self.k_in = KpiCard("شيكات واردة برسم التحصيل", "#16A34A", "📥")
        self.k_out = KpiCard("شيكات صادرة لم تُصرف", "#DC2626", "📤")
        self.k_due = KpiCard("تستحق خلال 7 أيام", "#D97706", "⏰")
        for i, k in enumerate((self.k_in, self.k_out, self.k_due)):
            g.addWidget(k, 0, i)
        lay.addLayout(g)

        row = QHBoxLayout()
        row.addWidget(button("📥 استلام شيك من عميل", "successBtn", lambda: self.new("in")))
        row.addWidget(button("📤 إعطاء شيك لمورد", "warnBtn", lambda: self.new("out")))
        row.addStretch()
        self.dir_filter = QComboBox()
        self.dir_filter.addItem("كل الشيكات", None)
        self.dir_filter.addItem("الواردة", "in")
        self.dir_filter.addItem("الصادرة", "out")
        self.status_filter = QComboBox()
        self.status_filter.addItem("كل الحالات", None)
        for k, v in cheques.STATUS_LABELS.items():
            self.status_filter.addItem(v, k)
        self.status_filter.setCurrentIndex(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 رقم الشيك / البنك / الاسم")
        for wdg in (self.dir_filter, self.status_filter):
            wdg.currentIndexChanged.connect(self.load)
        self.search.textChanged.connect(self.load)
        row.addWidget(self.dir_filter)
        row.addWidget(self.status_filter)
        row.addWidget(self.search)
        lay.addLayout(row)

        self.table = Table(["النوع", "الجهة", "رقم الشيك", "البنك", "المبلغ", "الاستحقاق", "متبقٍ (يوم)", "الحالة",
                            "ملاحظة"], stretch=8)
        lay.addWidget(self.table, 1)
        b = QHBoxLayout()
        b.addWidget(button("✓ صُرف في البنك", "successBtn", self.clear))
        b.addWidget(button("↩ راجع (مرتجع)", "dangerBtn", self.bounce))
        b.addStretch()
        lay.addLayout(b)
        lay.addWidget(hint("الأحمر: فات موعده ولم يُحدَّث. البرتقالي: يستحق خلال أسبوع. "
                           "راجع الشيكات يومياً واضغط «صُرف» عند دخولها البنك."))

    def refresh(self):
        self.load()

    def load(self):
        t = cheques.totals()
        due = cheques.due_soon(7)
        self.k_in.set(m(t["incoming"]))
        self.k_out.set(m(t["outgoing"]))
        self.k_due.set(str(len(due)), f"وارد {m(sum(c['amount'] for c in due if c['direction'] == 'in'))} • "
                                      f"صادر {m(sum(c['amount'] for c in due if c['direction'] == 'out'))}")
        rows = cheques.list_cheques(self.dir_filter.currentData(), self.status_filter.currentData(),
                                    self.search.text().strip() or None)
        colors = []
        for r in rows:
            if r["status"] != "pending":
                colors.append("#F1F5F9")
            elif r["days_left"] < 0:
                colors.append("#FEE2E2")
            elif r["days_left"] <= 7:
                colors.append("#FEF3C7")
            else:
                colors.append(None)
        self.table.set_rows([[cheques.DIRECTION_LABELS[r["direction"]], r["party"] or "-", r["cheque_number"] or "",
                              r["bank"] or "", float(r["amount"]), r["due_date"],
                              r["days_left"] if r["status"] == "pending" else "",
                              cheques.STATUS_LABELS.get(r["status"], r["status"]), r["note"] or ""] for r in rows],
                            rows, colors)

    def new(self, direction):
        if require_permission(self, "cheques") and ChequeDialog(self, direction).exec() == QDialog.Accepted:
            self.load()

    def clear(self):
        r = self.table.selected_data()
        if r and require_permission(self, "cheques") and ask(self, f"تأكيد صرف الشيك {r['cheque_number']} بقيمة {m(r['amount'])}؟"):
            try:
                cheques.clear_cheque(r["id"])
            except ValueError as e:
                warn(self, str(e))
            self.load()

    def bounce(self):
        r = self.table.selected_data()
        if not r or not require_permission(self, "cheques"):
            return
        msg = ("سيعود المبلغ ديناً على العميل." if r["direction"] == "in" else "سيعود المبلغ مستحقاً للمورد.")
        if ask(self, f"الشيك {r['cheque_number']} رجع؟ {msg}"):
            try:
                cheques.bounce_cheque(r["id"])
            except ValueError as e:
                warn(self, str(e))
            self.load()
