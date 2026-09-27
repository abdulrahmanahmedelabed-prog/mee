# -*- coding: utf-8 -*-
"""سجل الفواتير: بحث، تفاصيل، إعادة طباعة، مرتجعات"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QDialog, QFormLayout, QComboBox,
                               QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QDoubleSpinBox)

from core import sales, receipts, shifts
from core.utils import money, fmt_qty
from ui import printing
from ui.widgets import (Table, button, page, title, hint, warn, info, error, m, card, DateRange, qty_cell,
                        require_permission, ok_cancel, open_whatsapp)


class ReturnDialog(QDialog):
    def __init__(self, parent, invoice):
        super().__init__(parent)
        self.inv = invoice
        self.setWindowTitle(f"مرتجع من الفاتورة {invoice['invoice_number']}")
        self.resize(720, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(hint("حدد الكمية المرتجعة لكل صنف. يُحسب المبلغ بنفس نسبة الخصم في الفاتورة الأصلية، وتعود الكمية للمخزون."))
        self.items = [i for i in sales.returnable_items(invoice["id"]) if i["remaining"] > 1e-9]
        self.table = QTableWidget(len(self.items), 4)
        self.table.setHorizontalHeaderLabels(["الصنف", "المتبقي", "السعر", "الكمية المرتجعة"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.spins = []
        for r, it in enumerate(self.items):
            self.table.setItem(r, 0, QTableWidgetItem(it["product_name"]))
            self.table.setItem(r, 1, QTableWidgetItem(fmt_qty(it["remaining"])))
            self.table.setItem(r, 2, QTableWidgetItem(m(it["unit_price"])))
            s = QDoubleSpinBox()
            s.setDecimals(3)
            s.setMaximum(it["remaining"])
            s.valueChanged.connect(self.update_total)
            self.table.setCellWidget(r, 3, s)
            self.spins.append(s)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("إرجاع الكل", "secondaryBtn", self.select_all))
        row.addStretch()
        lay.addLayout(row)
        form = QFormLayout()
        self.method = QComboBox()
        self.method.addItem(sales.REFUND_CASH)
        if invoice["customer_id"]:
            self.method.addItem(sales.REFUND_DEBT)
            if invoice["credit_amount"] > 0:
                self.method.setCurrentText(sales.REFUND_DEBT)
        self.reason = QLineEdit()
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setObjectName("bigNumber")
        form.addRow("طريقة الإرجاع:", self.method)
        form.addRow("السبب:", self.reason)
        form.addRow("المبلغ المُرجع (تقريبي):", self.total_lbl)
        lay.addLayout(form)
        ok_cancel(self, lay, "تنفيذ المرتجع")
        self.result = None

    def select_all(self):
        for s, it in zip(self.spins, self.items):
            s.setValue(it["remaining"])

    def update_total(self):
        ratio = self.inv["total"] / self.inv["subtotal"] if self.inv["subtotal"] else 0
        t = sum(s.value() * it["unit_price"] * ratio for s, it in zip(self.spins, self.items))
        self.total_lbl.setText(m(t))

    def accept(self):
        lines = [{"invoice_item_id": it["id"], "quantity": s.value()} for s, it in zip(self.spins, self.items) if s.value() > 0]
        if not lines:
            warn(self, "حدد كمية واحدة على الأقل")
            return
        try:
            self.result = sales.create_return(self.inv["id"], lines, self.method.currentText(), self.reason.text(),
                                              shift_id=shifts.current_shift_id())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class InvoicesScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.range = DateRange("اليوم")
        self.range.changed.connect(self.load)
        row.addWidget(self.range)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 رقم الفاتورة أو اسم/هاتف العميل")
        self.search.textChanged.connect(self.load)
        row.addWidget(self.search, 1)
        lay.addLayout(row)

        split = QSplitter(Qt.Vertical)
        self.table = Table(["رقم الفاتورة", "التاريخ", "العميل", "الكاشير", "الإجمالي", "الخصم", "الدفع", "الحالة", "المرتجع"])
        self.table.itemSelectionChanged.connect(self.show_details)
        self.table.doubleClicked.connect(self.reprint)
        split.addWidget(self.table)

        det, dl = card()
        top = QHBoxLayout()
        self.det_title = QLabel("اختر فاتورة")
        self.det_title.setObjectName("subTitle")
        top.addWidget(self.det_title)
        top.addStretch()
        top.addWidget(button("🖨 إعادة طباعة", "secondaryBtn", self.reprint))
        top.addWidget(button("💾 حفظ PDF", "secondaryBtn", self.save_pdf))
        top.addWidget(button("📱 واتساب", "secondaryBtn", self.send_whatsapp))
        top.addWidget(button("↩ مرتجع", "warnBtn", self.do_return))
        dl.addLayout(top)
        inner = QHBoxLayout()
        self.items = Table(["الصنف", "الكمية", "السعر", "الإجمالي", "مُرتجع"])
        inner.addWidget(self.items, 3)
        self.returns = Table(["رقم المرتجع", "التاريخ", "المبلغ", "الطريقة"])
        self.returns.doubleClicked.connect(self.print_return)
        inner.addWidget(self.returns, 2)
        dl.addLayout(inner)
        split.addWidget(det)
        split.setSizes([420, 300])
        lay.addWidget(split, 1)
        self.summary = QLabel("")
        self.summary.setObjectName("subTitle")
        lay.addWidget(self.summary)

    def refresh(self):
        self.load()

    def load(self):
        a, b = self.range.range()
        rows = sales.get_invoices(a, b, self.search.text().strip() or None)
        self.table.set_rows([[r["invoice_number"], r["created_at"][:16], r["customer_name"] or "-", r["cashier"] or "",
                              float(r["total"]), float(r["discount"]), r["payment_method"],
                              sales.STATUS_LABELS.get(r["status"], r["status"]),
                              float(r["returned_total"]) if r["returned_total"] else ""] for r in rows], rows,
                            colors=[("#FEF3C7" if r["status"] != "completed" else None) for r in rows])
        total = sum(r["total"] for r in rows)
        ret = sum(r["returned_total"] for r in rows)
        self.summary.setText(f"عدد الفواتير: {len(rows)}   |   الإجمالي: {m(total)}   |   المرتجعات: {m(ret)}   |   الصافي: {m(total - ret)}")

    def current(self):
        return self.table.selected_data()

    def show_details(self):
        inv = self.current()
        if not inv:
            return
        full = sales.get_invoice(inv["id"])
        pay = []
        for k, lbl in (("cash_amount", "نقدي"), ("card_amount", "بطاقة"), ("credit_amount", "آجل")):
            if full[k]:
                pay.append(f"{lbl} {m(full[k])}")
        if full["wallet_amount"]:
            pay.append(f"{full['wallet_name'] or 'إلكتروني'} {m(full['wallet_amount'])}"
                       + (f" (#{full['wallet_ref']})" if full["wallet_ref"] else ""))
        self.det_title.setText(f"{full['invoice_number']} — {full['created_at']} — {' + '.join(pay)}")
        items = sales.get_invoice_items(inv["id"])
        self.items.set_rows([[i["product_name"], qty_cell(i["quantity"]), float(i["unit_price"]), float(i["total"]),
                              qty_cell(i["returned_qty"]) if i["returned_qty"] else ""] for i in items])
        rets = sales.get_returns(inv["id"])
        self.returns.set_rows([[r["return_number"], r["created_at"][:16], float(r["total"]), r["refund_method"]]
                               for r in rets], rets)

    def reprint(self):
        inv = self.current()
        if inv:
            printing.print_html(self, receipts.invoice_html(inv["id"], copy=True), preview=True)

    def save_pdf(self):
        inv = self.current()
        if not inv:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", f"{inv['invoice_number']}.pdf", "PDF (*.pdf)")
        if path:
            printing.save_pdf(receipts.invoice_html(inv["id"]), path, 80)
            info(self, "تم الحفظ")

    def send_whatsapp(self):
        inv = self.current()
        if not inv:
            return
        from core import whatsapp
        from PySide6.QtWidgets import QInputDialog
        full = sales.get_invoice(inv["id"])
        phone = full["customer_phone"] or ""
        if not phone:
            phone, ok = QInputDialog.getText(self, "إرسال الفاتورة", "رقم واتساب الزبون:")
            if not ok:
                return
        open_whatsapp(self, whatsapp.link(phone, whatsapp.invoice_text(inv["id"])), whatsapp.invoice_text(inv["id"]))

    def print_return(self):
        r = self.returns.selected_data()
        if r:
            printing.print_html(self, receipts.return_html(r["id"]), preview=True)

    def do_return(self):
        inv = self.current()
        if not inv:
            warn(self, "اختر فاتورة أولاً")
            return
        if inv["status"] == "returned":
            warn(self, "هذه الفاتورة مرتجعة بالكامل")
            return
        if not require_permission(self, "returns"):
            return
        dlg = ReturnDialog(self, sales.get_invoice(inv["id"]))
        if dlg.exec() == QDialog.Accepted and dlg.result:
            info(self, f"تم المرتجع {dlg.result['return_number']} بقيمة {m(dlg.result['total'])}")
            self.load()
