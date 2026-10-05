# -*- coding: utf-8 -*-
"""الطلبيات الذكية: اقتراح كميات الشراء حسب سرعة البيع، وإرسالها للمورد عبر واتساب أو تحويلها لفاتورة مشتريات"""

from html import escape

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QDialog

from core import reorder, settings, whatsapp, products
from core.utils import fmt_qty
from ui import printing
from ui.widgets import Table, button, page, hint, warn, info, m, qty_cell, open_whatsapp


class ReorderScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.rows = []

        row = QHBoxLayout()
        row.addWidget(QLabel("احسب سرعة البيع من آخر"))
        self.days = QSpinBox()
        self.days.setRange(7, 180)
        self.days.setValue(30)
        row.addWidget(self.days)
        row.addWidget(QLabel("يوماً، واطلب ما يكفي"))
        self.cover = QSpinBox()
        self.cover.setRange(1, 90)
        self.cover.setValue(14)
        row.addWidget(self.cover)
        row.addWidget(QLabel("يوماً"))
        row.addWidget(button("🔄 احسب", "secondaryBtn", self.load))
        row.addStretch()
        row.addWidget(QLabel("المورد:"))
        self.supplier = QComboBox()
        self.supplier.setMinimumWidth(200)
        self.supplier.currentIndexChanged.connect(self.render)
        row.addWidget(self.supplier)
        lay.addLayout(row)

        self.table = Table(["الصنف", "المورد", "الموجود", "بيع يومي", "يكفي (يوم)", "الكمية المقترحة", "الوحدة",
                            "بالحبة", "التكلفة التقديرية"], stretch=0)
        lay.addWidget(self.table, 1)
        self.total = QLabel("")
        self.total.setObjectName("subTitle")
        lay.addWidget(self.total)
        b = QHBoxLayout()
        b.addWidget(button("📱 إرسال الطلبية للمورد (واتساب)", "successBtn", self.send))
        b.addWidget(button("🧾 تحويلها لفاتورة مشتريات", "secondaryBtn", self.to_purchase))
        b.addWidget(button("🖨 طباعة", "secondaryBtn", self.print_order))
        b.addWidget(button("📤 تصدير", "secondaryBtn", lambda: self.table.export_csv(self, "طلبية مقترحة.csv")))
        b.addStretch()
        lay.addLayout(b)
        lay.addWidget(hint("الكمية المقترحة = (البيع اليومي × أيام التغطية) + الحد الأدنى − الموجود، مقرّبة للكرتونة. "
                           "المورد = آخر مورد اشتريت منه الصنف. الأحمر: سينفد خلال 3 أيام أو نفد."))

    def refresh(self):
        self.load()

    def load(self):
        self.rows = reorder.suggestions(self.days.value(), self.cover.value())
        cur = self.supplier.currentText()
        self.supplier.blockSignals(True)
        self.supplier.clear()
        self.supplier.addItem("كل الموردين", None)
        for name in sorted({r["supplier_name"] for r in self.rows}):
            self.supplier.addItem(name, name)
        idx = self.supplier.findText(cur)
        self.supplier.setCurrentIndex(max(idx, 0))
        self.supplier.blockSignals(False)
        self.render()

    def visible_rows(self):
        s = self.supplier.currentData()
        return [r for r in self.rows if not s or r["supplier_name"] == s]

    def render(self):
        rows = self.visible_rows()
        self.table.set_rows([[r["name"], r["supplier_name"], qty_cell(r["stock"]), (f"{r['daily_rate']:g}", r["daily_rate"]),
                              (f"{r['days_left']:g}" if r["days_left"] is not None else "-", r["days_left"] or 0),
                              qty_cell(r["order_units"]), r["unit_name"], qty_cell(r["order_base"]), float(r["est_cost"])]
                             for r in rows], rows,
                            colors=[("#FEE2E2" if r["stock"] <= 0 or (r["days_left"] is not None and r["days_left"] <= 3)
                                     else None) for r in rows])
        self.total.setText(f"{len(rows)} صنف — التكلفة التقديرية للطلبية: {m(sum(r['est_cost'] for r in rows))}")

    def _need_supplier(self):
        s = self.supplier.currentData()
        if not s:
            warn(self, "اختر مورداً من القائمة أعلاه أولاً (الطلبية تُرسل لكل مورد على حدة).")
            return None
        return s

    def send(self):
        s = self._need_supplier()
        rows = self.visible_rows()
        if not s or not rows:
            return
        msg = reorder.order_message(rows, s)
        open_whatsapp(self, whatsapp.link(rows[0]["supplier_phone"], msg) if rows[0]["supplier_phone"] else None, msg)

    def to_purchase(self):
        s = self._need_supplier()
        rows = self.visible_rows()
        if not s or not rows:
            return
        from ui.suppliers_screen import PurchaseDialog
        dlg = PurchaseDialog(self, rows[0]["supplier_id"])
        for r in rows:
            p = products.get_product(r["product_id"])
            unit = None
            if r["factor"] > 1:
                unit = next((u for u in products.get_units(p["id"]) if u["factor"] == r["factor"]), None)
            dlg.add_line(p, unit)
            dlg.lines[-1]["quantity"] = float(r["order_units"])
        dlg.render()
        if dlg.exec() == QDialog.Accepted:
            self.load()

    def print_order(self):
        rows = self.visible_rows()
        if not rows:
            return
        body = "".join(f"<tr><td>{i}</td><td>{escape(r['name'])}</td><td>{fmt_qty(r['order_units'])}</td>"
                       f"<td>{escape(r['unit_name'])}</td><td>{fmt_qty(r['stock'])}</td></tr>"
                       for i, r in enumerate(rows, 1))
        from core import branding
        html = branding.document(
            f"<table width='100%' border='1' cellspacing='0' cellpadding='5' style='border-collapse:collapse'>"
            f"<tr style='background:#eee'><th>#</th><th>الصنف</th><th>الكمية</th><th>الوحدة</th><th>الموجود</th></tr>"
            f"{body}</table>", f"طلبية شراء — {self.supplier.currentText()}", size_pt=11)
        printing.print_html(self, html, width_mm=210, preview=True)
