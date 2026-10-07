# -*- coding: utf-8 -*-
"""الطلبيات الذكية: اقتراح كميات الشراء حسب سرعة البيع، وإرسالها للمورد عبر واتساب أو تحويلها لفاتورة مشتريات"""

from html import escape

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QDialog, QGridLayout

from core import reorder, settings, whatsapp, products
from core.utils import fmt_qty
from ui import printing
from ui.widgets import Table, button, page, hint, warn, info, m, qty_cell, open_whatsapp, card, KpiCard


class ReorderScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.rows = []

        # ---- كيف تعمل؟ (ثلاث خطوات بلغة بسيطة)
        how, hl = card(QHBoxLayout, margins=14)
        for icon, head, text in (("📈", "1. يقيس سرعة البيع", "كم تبيع يومياً من كل صنف حسب مبيعاتك الفعلية"),
                                 ("🧮", "2. يقترح الكمية", "ما يكفيك للأيام التي تختارها + الحد الأدنى − الموجود، مقرّباً للكرتونة"),
                                 ("📱", "3. ترسلها للمورد", "اختر المورد ثم أرسل الطلبية بواتساب أو حوّلها لفاتورة شراء")):
            box = QVBoxLayout()
            t = QLabel(f"{icon}  {head}")
            t.setObjectName("subTitle")
            box.addWidget(t)
            box.addWidget(hint(text))
            hl.addLayout(box, 1)
        lay.addWidget(how)

        # ---- الإعدادات بجملة واحدة
        row = QHBoxLayout()
        row.addWidget(QLabel("احسب على أساس مبيعات آخر"))
        self.days = QSpinBox()
        self.days.setRange(7, 180)
        self.days.setValue(30)
        self.days.setSuffix(" يوماً")
        row.addWidget(self.days)
        row.addWidget(QLabel("، واطلب ما يكفي"))
        self.cover = QSpinBox()
        self.cover.setRange(1, 90)
        self.cover.setValue(14)
        self.cover.setSuffix(" يوماً")
        row.addWidget(self.cover)
        row.addWidget(button("🔄 احسب الطلبية", "primaryBtn", self.load))
        row.addStretch()
        row.addWidget(QLabel("المورد:"))
        self.supplier = QComboBox()
        self.supplier.setMinimumWidth(220)
        self.supplier.currentIndexChanged.connect(self.render)
        row.addWidget(self.supplier)
        lay.addLayout(row)

        # ---- ملخص بالأرقام
        g = QGridLayout()
        g.setSpacing(12)
        self.k_urgent = KpiCard("عاجل: ينفد خلال 3 أيام أو نفد", "#DC2626", "🚨")
        self.k_items = KpiCard("أصناف تحتاج طلبية", "#2563EB", "📦")
        self.k_cost = KpiCard("قيمة الطلبية التقديرية", "#16A34A", "💰")
        self.k_sup = KpiCard("موردون", "#7C3AED", "🚚")
        for i, k in enumerate((self.k_urgent, self.k_items, self.k_cost, self.k_sup)):
            g.addWidget(k, 0, i)
        lay.addLayout(g)

        self.table = Table(["الحالة", "الصنف", "الموجود الآن", "تبيع يومياً", "يكفيك (يوم)", "اطلب", "الوحدة",
                            "بالحبة", "التكلفة التقديرية", "المورد"], stretch=1)
        self.table.doubleClicked.connect(self.edit_qty)
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
        lay.addWidget(hint("انقر مرتين على أي صنف لتعديل كميته (0 = استبعاده). المورد = آخر مورد اشتريت منه الصنف."))

    def refresh(self):
        self.load()

    def load(self):
        rows = reorder.suggestions(self.days.value(), self.cover.value())
        for r in rows:
            d = r["days_left"]
            r["urgency"] = 0 if r["stock"] <= 0 or (d is not None and d <= 3) else 1 if (d is not None and d <= 7) else 2
        rows.sort(key=lambda r: (r["urgency"], r["days_left"] if r["days_left"] is not None else 999))
        self.rows = rows
        cur = self.supplier.currentText()
        self.supplier.blockSignals(True)
        self.supplier.clear()
        self.supplier.addItem("كل الموردين", None)
        by = {}
        for r in self.rows:
            by.setdefault(r["supplier_name"], []).append(r)
        for name in sorted(by):
            self.supplier.addItem(f"{name} ({len(by[name])})", name)
        idx = next((i for i in range(self.supplier.count()) if self.supplier.itemText(i) == cur), 0)
        self.supplier.setCurrentIndex(max(idx, 0))
        self.supplier.blockSignals(False)
        self.render()

    def visible_rows(self):
        s = self.supplier.currentData()
        return [r for r in self.rows if (not s or r["supplier_name"] == s) and r["order_units"] > 0]

    def render(self):
        rows = self.visible_rows()
        labels = {0: "🚨 عاجل", 1: "⚠ قريب", 2: "✓ عادي"}
        self.table.set_rows([[labels[r["urgency"]], r["name"], qty_cell(r["stock"]), (f"{r['daily_rate']:g}", r["daily_rate"]),
                              (f"{r['days_left']:g}" if r["days_left"] is not None else "-", r["days_left"] or 0),
                              qty_cell(r["order_units"]), r["unit_name"], qty_cell(r["order_base"]), float(r["est_cost"]),
                              r["supplier_name"]]
                             for r in rows], rows,
                            colors=[("#FEE2E2" if r["urgency"] == 0 else "#FEF3C7" if r["urgency"] == 1 else None)
                                    for r in rows])
        allr = [r for r in self.rows if r["order_units"] > 0]
        self.k_urgent.set(str(sum(1 for r in allr if r["urgency"] == 0)), "اطلبها اليوم")
        self.k_items.set(str(len(allr)), f"لتغطية {self.cover.value()} يوماً")
        self.k_cost.set(m(sum(r["est_cost"] for r in allr)))
        self.k_sup.set(str(len({r["supplier_name"] for r in allr})), "كل مورد بطلبية مستقلة")
        self.total.setText(f"المعروض: {len(rows)} صنف — التكلفة التقديرية: {m(sum(r['est_cost'] for r in rows))}")

    def edit_qty(self):
        r = self.table.selected_data()
        if not r:
            return
        from PySide6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(self, "تعديل الكمية", f"{r['name']} — الكمية ({r['unit_name']}):",
                                         float(r["order_units"]), 0, 100000, 0)
        if ok:
            unit_cost = r.get("unit_cost") or ((r["est_cost"] / r["order_base"]) if r.get("order_base") else 0)
            r["unit_cost"] = unit_cost
            r["order_units"] = val
            r["order_base"] = val * (r["factor"] or 1)
            r["est_cost"] = round(r["order_base"] * unit_cost, 2)
            self.render()

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
