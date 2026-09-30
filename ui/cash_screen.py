# -*- coding: utf-8 -*-
"""الصندوق والورديات: فتح/إغلاق، إدخال/سحب نقدي، تقرير Z"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDialog, QInputDialog, QGridLayout

from core import shifts, receipts
from ui import printing
from ui.dialogs import OpenShiftDialog, CashCountDialog
from ui.widgets import Table, button, page, title, hint, warn, info, ask, m, card, KpiCard, require_permission


class CashScreen(QWidget):
    shift_changed = Signal()

    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        head.addStretch()
        self.status = QLabel("")
        head.addWidget(self.status)
        lay.addLayout(head)

        btns = QHBoxLayout()
        self.open_btn = button("🔓 فتح وردية", "successBtn", self.open_shift)
        self.in_btn = button("⬇ إدخال نقدي", "secondaryBtn", lambda: self.move(1))
        self.out_btn = button("⬆ سحب نقدي", "secondaryBtn", lambda: self.move(-1))
        self.close_btn = button("🔒 إغلاق الوردية وعدّ النقود", "dangerBtn", self.close_shift)
        self.print_btn = button("🖨 طباعة تقرير الوردية", "secondaryBtn", self.print_current)
        for b in (self.open_btn, self.in_btn, self.out_btn, self.close_btn, self.print_btn):
            btns.addWidget(b)
        btns.addStretch()
        lay.addLayout(btns)

        kpis = QGridLayout()
        self.k_expected = KpiCard("النقد المتوقع في الصندوق", "#16A34A", "💵")
        self.k_sales = KpiCard("مبيعات الوردية", "#2563EB", "🧾")
        self.k_card = KpiCard("بطاقة", "#7C3AED", "💳")
        self.k_credit = KpiCard("آجل", "#D97706", "📒")
        for i, k in enumerate((self.k_expected, self.k_sales, self.k_card, self.k_credit)):
            kpis.addWidget(k, 0, i)
        lay.addLayout(kpis)

        body = QHBoxLayout()
        c1, l1 = card()
        l1.addWidget(title("تفاصيل الوردية الحالية", "subTitle"))
        self.details = Table(["البند", "المبلغ"], stretch=0, sortable=False)
        l1.addWidget(self.details)
        body.addWidget(c1, 1)
        c2, l2 = card()
        l2.addWidget(title("الورديات السابقة", "subTitle"))
        self.history = Table(["#", "الكاشير", "الفتح", "الإغلاق", "الافتتاحي", "المتوقع", "المعدود", "الفرق"])
        self.history.doubleClicked.connect(self.print_selected)
        l2.addWidget(self.history)
        l2.addWidget(hint("انقر مرتين على وردية لطباعة تقريرها"))
        body.addWidget(c2, 2)
        lay.addLayout(body, 1)

    def refresh(self):
        s = shifts.current_shift()
        for b in (self.in_btn, self.out_btn, self.close_btn, self.print_btn):
            b.setEnabled(bool(s))
        self.open_btn.setEnabled(not s)
        if s:
            d = shifts.summary(s["id"])
            self.status.setText(f"وردية #{s['id']} مفتوحة منذ {s['opened_at'][11:16]} — {s['full_name'] or s['username'] or ''}")
            self.status.setObjectName("chipOk")
            self.k_expected.set(m(d["expected_cash"]), f"افتتاحي {m(d['opening_cash'])}")
            self.k_sales.set(m(d["sales_total"]), f"{d['invoice_count']} فاتورة")
            self.k_card.set(m(d["card_sales"]))
            self.k_credit.set(m(d["credit_sales"]))
            rows = [("الرصيد الافتتاحي", d["opening_cash"]), ("+ مبيعات نقدية", d["cash_sales"]),
                    ("+ تسديدات عملاء نقداً", d["customer_payments_cash"]), ("+ إدخال نقدي", d["cash_in"]),
                    ("− مرتجعات نقدية", d["cash_refunds"]), ("− مصاريف من الصندوق", d["expenses_cash"]),
                    ("− دفعات موردين من الصندوق", d["supplier_payments_cash"]), ("− سحب نقدي", d["cash_out"]),
                    ("= النقد المتوقع", d["expected_cash"]), ("", None), ("مبيعات بطاقة", d["card_sales"]),
                    ("مبيعات دفع إلكتروني (محافظ وتطبيقات)", d["wallet_sales"]),
                    ("مبيعات آجلة", d["credit_sales"]), ("الخصومات الممنوحة", d["discounts"]),
                    ("تسديدات عملاء (غير نقدية)", d["customer_payments_other"]),
                    ("مرتجعات أُعيدت للبطاقة أو المحفظة", d["electronic_refunds"]),
                    ("مرتجعات خُصمت من الدين", d["debt_refunds"])]
            self.details.set_rows([[a, float(b) if b is not None else ""] for a, b in rows])
        else:
            self.status.setText("لا توجد وردية مفتوحة")
            self.status.setObjectName("chipWarn")
            for k in (self.k_expected, self.k_sales, self.k_card, self.k_credit):
                k.set("—")
            self.details.set_rows([])
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        hist = shifts.list_shifts()
        self.history.set_rows([[h["id"], h["username"] or "", h["opened_at"][:16], (h["closed_at"] or "مفتوحة")[:16],
                                float(h["opening_cash"]), float(h["expected_cash"]) if h["expected_cash"] is not None else "",
                                float(h["counted_cash"]) if h["counted_cash"] is not None else "",
                                float(h["difference"]) if h["difference"] is not None else ""] for h in hist], hist,
                              colors=[("#FEE2E2" if (h["difference"] or 0) < -0.009 else None) for h in hist])

    def open_shift(self):
        if OpenShiftDialog(self).exec() == QDialog.Accepted:
            self.refresh()
            self.shift_changed.emit()

    def move(self, sign):
        label = "إدخال نقدي للصندوق" if sign > 0 else "سحب نقدي من الصندوق"
        val, ok = QInputDialog.getDouble(self, label, "المبلغ:", 0, 0, 1e9, 2)
        if not ok or not val:
            return
        reason, ok = QInputDialog.getText(self, label, "السبب (مثال: سحب المالك، إضافة فكّة):")
        if not ok:
            return
        try:
            shifts.cash_movement(sign * val, reason)
        except ValueError as e:
            warn(self, str(e))
        self.refresh()

    def close_shift(self):
        s = shifts.current_shift()
        if not s:
            return
        expected = shifts.summary(s["id"])["expected_cash"]
        dlg = CashCountDialog(self, expected)
        if dlg.exec() == QDialog.Accepted:
            sid, diff = shifts.close_shift(dlg.total.value(), dlg.note.text())
            self.refresh()
            self.shift_changed.emit()
            msg = "الصندوق مطابق ✓" if abs(diff) < 0.01 else (f"يوجد {'زيادة' if diff > 0 else 'عجز'} بمبلغ {m(abs(diff))}")
            if ask(self, f"تم إغلاق الوردية. {msg}\n\nهل تريد طباعة تقرير الوردية؟"):
                printing.print_html(self, receipts.shift_html(sid))

    def print_current(self):
        s = shifts.current_shift()
        if s:
            printing.print_html(self, receipts.shift_html(s["id"]), preview=True)

    def print_selected(self):
        h = self.history.selected_data()
        if h:
            printing.print_html(self, receipts.shift_html(h["id"]), preview=True)
