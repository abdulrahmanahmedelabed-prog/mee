# -*- coding: utf-8 -*-
"""العروض التلقائية ونقاط الولاء"""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QDialog, QFormLayout, QLineEdit,
                               QDateEdit, QCheckBox, QDoubleSpinBox, QTabWidget, QStackedWidget)

from core import promotions, products, loyalty, settings
from ui.dialogs import ProductPicker
from ui.widgets import CalcDoubleSpinBox
from ui.widgets import Table, button, page, hint, warn, ask, MoneySpin, ok_cancel, m, card, title, require_permission


class PromotionDialog(QDialog):
    def __init__(self, parent, promo=None):
        super().__init__(parent)
        self.promo = promo
        self.product_id = promo["product_id"] if promo else None
        self.setWindowTitle("تعديل عرض" if promo else "عرض جديد")
        self.setMinimumWidth(480)
        lay = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("يظهر للزبون على الفاتورة، مثل: اشترِ 2 واحصل على 1")
        self.type = QComboBox()
        for k, v in promotions.TYPES.items():
            self.type.addItem(v, k)
        self.product_btn = button("اختيار صنف...", "secondaryBtn", self.pick_product)
        self.category = QComboBox()
        self.category.addItem("— لا شيء —", None)
        for c in products.get_categories():
            self.category.addItem(c, c)
        self.buy = self._spin(1, 1000, 0)
        self.get = self._spin(1, 1000, 0)
        self.bundle_qty = self._spin(2, 1000, 0)
        self.bundle_price = MoneySpin()
        self.percent = self._spin(1, 99, 1)
        self.start = QDateEdit(calendarPopup=True)
        self.end = QDateEdit(calendarPopup=True)
        for d in (self.start, self.end):
            d.setDisplayFormat("yyyy-MM-dd")
        self.start.setDate(QDate.currentDate())
        self.end.setDate(QDate.currentDate().addDays(30))
        self.no_end = QCheckBox("بدون تاريخ انتهاء")
        self.active = QCheckBox("فعّال")
        self.active.setChecked(True)
        lay.addRow("اسم العرض:", self.name)
        lay.addRow("نوع العرض:", self.type)
        lay.addRow("الصنف:", self.product_btn)
        self.cat_row_label = QLabel("أو فئة كاملة:")
        lay.addRow(self.cat_row_label, self.category)
        self.rows = {"buy_get": [("اشترِ (كمية):", self.buy), ("واحصل مجاناً على:", self.get)],
                     "bundle": [("عدد القطع:", self.bundle_qty), ("بسعر إجمالي:", self.bundle_price)],
                     "percent": [("نسبة الخصم %:", self.percent)]}
        self.labels = {}
        for t, fields in self.rows.items():
            for label, wdg in fields:
                lbl = QLabel(label)
                self.labels[wdg] = lbl
                lay.addRow(lbl, wdg)
        lay.addRow("يبدأ:", self.start)
        lay.addRow("ينتهي:", self.end)
        lay.addRow("", self.no_end)
        lay.addRow("", self.active)
        lay.addRow("", hint("يُطبَّق العرض تلقائياً عند مسح الصنف في نقطة البيع ويظهر في الفاتورة. "
                            "العروض بالقطعة لا تنطبق على البيع بالكرتونة."))
        self.type.currentIndexChanged.connect(self.update_visibility)
        self.no_end.toggled.connect(lambda v: self.end.setEnabled(not v))
        if promo:
            self.name.setText(promo["name"])
            self.type.setCurrentIndex(self.type.findData(promo["type"]))
            if promo["category"]:
                self.category.setCurrentIndex(max(0, self.category.findData(promo["category"])))
            self.buy.setValue(promo["buy_qty"] or 1)
            self.get.setValue(promo["get_qty"] or 1)
            self.bundle_qty.setValue(promo["bundle_qty"] or 2)
            self.bundle_price.setValue(promo["bundle_price"] or 0)
            self.percent.setValue(promo["percent"] or 10)
            if promo["start_date"]:
                self.start.setDate(QDate.fromString(promo["start_date"], "yyyy-MM-dd"))
            if promo["end_date"]:
                self.end.setDate(QDate.fromString(promo["end_date"], "yyyy-MM-dd"))
            else:
                self.no_end.setChecked(True)
            self.active.setChecked(bool(promo["is_active"]))
            if promo["product_id"]:
                p = products.get_product(promo["product_id"])
                self.product_btn.setText(p["name"] if p else "اختيار صنف...")
        else:
            self.percent.setValue(10)
        ok_cancel(self, lay)
        self.update_visibility()

    def _spin(self, lo, hi, dec):
        s = CalcDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        return s

    def pick_product(self):
        dlg = ProductPicker(self)
        if dlg.exec() == QDialog.Accepted and dlg.selected:
            self.product_id = dlg.selected["id"]
            self.product_btn.setText(dlg.selected["name"])

    def update_visibility(self):
        t = self.type.currentData()
        for typ, fields in self.rows.items():
            for _, wdg in fields:
                wdg.setVisible(typ == t)
                self.labels[wdg].setVisible(typ == t)
        self.category.setVisible(t == "percent")
        self.cat_row_label.setVisible(t == "percent")

    def accept(self):
        kw = dict(name=self.name.text(), type=self.type.currentData(), product_id=self.product_id,
                  category=self.category.currentData() if self.type.currentData() == "percent" else None,
                  buy_qty=self.buy.value(), get_qty=self.get.value(), bundle_qty=self.bundle_qty.value(),
                  bundle_price=self.bundle_price.value(), percent=self.percent.value(),
                  start_date=self.start.date().toString("yyyy-MM-dd"),
                  end_date=None if self.no_end.isChecked() else self.end.date().toString("yyyy-MM-dd"))
        if kw["type"] == "percent" and kw["category"]:
            kw["product_id"] = None
        try:
            if self.promo:
                promotions.update_promotion(self.promo["id"], is_active=self.active.isChecked(), **kw)
            else:
                promotions.add_promotion(**kw)
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class PromotionsScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # --- العروض
        pr = QWidget()
        pl = QVBoxLayout(pr)
        pl.setContentsMargins(0, 8, 0, 0)
        row = QHBoxLayout()
        row.addWidget(button("+ عرض جديد", "successBtn", self.add))
        row.addWidget(button("✏ تعديل", "secondaryBtn", self.edit))
        row.addWidget(button("⏹ إيقاف", "dangerBtn", self.stop))
        row.addStretch()
        self.enabled_lbl = QLabel("")
        row.addWidget(self.enabled_lbl)
        pl.addLayout(row)
        self.table = Table(["العرض", "النوع", "الصنف / الفئة", "التفاصيل", "من", "إلى", "الحالة"], stretch=0)
        self.table.doubleClicked.connect(self.edit)
        pl.addWidget(self.table, 1)
        pl.addWidget(hint("أمثلة: «اشترِ 2 واحصل على 1» لتصريف بضاعة قريبة الانتهاء، «3 علب بـ 10» لزيادة السلة، "
                          "«15% على المنظفات» لعطلة نهاية الأسبوع. العروض المنتهية تتوقف تلقائياً."))
        tabs.addTab(pr, "العروض التلقائية")

        # --- نقاط الولاء
        ly = QWidget()
        ll = QVBoxLayout(ly)
        ll.setContentsMargins(0, 8, 0, 0)
        c, cl = card()
        self.loyalty_info = QLabel("")
        self.loyalty_info.setWordWrap(True)
        self.loyalty_info.setObjectName("subTitle")
        cl.addWidget(self.loyalty_info)
        cl.addWidget(hint("غيّر إعدادات النقاط من: الإعدادات ← نقاط الولاء ولوحة المالك."))
        ll.addWidget(c)
        ll.addWidget(title("أكثر العملاء نقاطاً", "subTitle"))
        self.members = Table(["العميل", "الهاتف", "النقاط", "قيمتها"], stretch=0)
        ll.addWidget(self.members, 1)
        r2 = QHBoxLayout()
        r2.addWidget(button("± تعديل نقاط العميل المحدد", "secondaryBtn", self.adjust_points))
        r2.addStretch()
        ll.addLayout(r2)
        tabs.addTab(ly, "نقاط الولاء")

    def refresh(self):
        self.load()

    def load(self):
        rows = promotions.list_promotions()
        today = QDate.currentDate().toString("yyyy-MM-dd")

        def details(r):
            if r["type"] == "buy_get":
                return f"اشترِ {r['buy_qty']:g} واحصل على {r['get_qty']:g}"
            if r["type"] == "bundle":
                return f"{r['bundle_qty']:g} قطع بـ {m(r['bundle_price'])}"
            return f"خصم {r['percent']:g}%"

        def state(r):
            if not r["is_active"]:
                return "موقوف"
            if r["end_date"] and r["end_date"] < today:
                return "منتهي"
            if r["start_date"] and r["start_date"] > today:
                return "لم يبدأ"
            return "ساري ✓"
        states = [state(r) for r in rows]
        self.table.set_rows([[r["name"], promotions.TYPES.get(r["type"], r["type"]),
                              r["product_name"] or (f"فئة: {r['category']}" if r["category"] else "-"), details(r),
                              r["start_date"] or "", r["end_date"] or "مفتوح", s] for r, s in zip(rows, states)], rows,
                            colors=[("#DCFCE7" if s.startswith("ساري") else "#F1F5F9") for s in states])
        self.enabled_lbl.setText("✓ العروض مفعّلة" if settings.get_bool("promotions_enabled")
                                 else "⚠ العروض معطّلة من الإعدادات")
        if loyalty.enabled():
            self.loyalty_info.setText(
                f"✓ نقاط الولاء مفعّلة: {settings.get('loyalty_points_per_unit')} نقطة لكل 1 {settings.get('currency_name')}"
                f"، قيمة النقطة {settings.get('loyalty_point_value')}، أقل استبدال {settings.get('loyalty_min_redeem')} نقطة.")
        else:
            self.loyalty_info.setText("نقاط الولاء غير مفعّلة. فعّلها من الإعدادات لتكافئ زبائنك الدائمين.")
        members = loyalty.top_members(200)
        self.members.set_rows([[r["name"], r["phone"] or "", float(r["points"]), float(loyalty.value_of(r["points"]))]
                               for r in members], members)

    def add(self):
        if require_permission(self, "promotions") and PromotionDialog(self).exec() == QDialog.Accepted:
            self.load()

    def edit(self):
        r = self.table.selected_data()
        if r and require_permission(self, "promotions") and PromotionDialog(self, r).exec() == QDialog.Accepted:
            self.load()

    def stop(self):
        r = self.table.selected_data()
        if r and require_permission(self, "promotions") and ask(self, f"إيقاف العرض «{r['name']}»؟"):
            promotions.delete_promotion(r["id"])
            self.load()

    def adjust_points(self):
        r = self.members.selected_data()
        if not r or not require_permission(self, "promotions"):
            return
        from PySide6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(self, "تعديل النقاط", f"النقاط المضافة (+) أو المخصومة (−) للعميل {r['name']}:",
                                         0, -1_000_000, 1_000_000, 0)
        if ok and val:
            loyalty.adjust(r["id"], val)
            self.load()
