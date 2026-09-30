# -*- coding: utf-8 -*-
"""شاشة المخزون: المنتجات، تعديل الكميات، الجرد، حركة الصنف، الملصقات، استيراد/تصدير Excel"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QDialog, QVBoxLayout, QFormLayout, QLabel, QFileDialog,
    QSpinBox, QWidget, QDateEdit
)
from PySide6.QtCore import QDate

from core import products
from core.utils import fmt_qty
from ui import printing
from ui.dialogs import ProductDialog
from ui.widgets import (Table, button, page, title, hint, warn, info, ask, error, MoneySpin, ok_cancel, m, qty_cell,
                        require_permission)


class StockDialog(QDialog):
    """إضافة/خصم كمية أو جرد (إدخال الكمية الفعلية)"""
    REASONS = ["استلام بضاعة", "تالف", "منتهي الصلاحية", "هدية / استهلاك شخصي", "سرقة / فقدان", "تصحيح خطأ", "أخرى"]

    def __init__(self, parent, product, count_mode=False):
        super().__init__(parent)
        self.product = product
        self.count_mode = count_mode
        self.setWindowTitle("جرد الصنف" if count_mode else "تعديل الكمية")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"<b>{product['name']}</b> — الكمية الحالية: {fmt_qty(product['quantity'])} {product['unit']}"))
        self.value = MoneySpin(decimals=3, allow_negative=not count_mode, big=True)
        if count_mode:
            self.value.setValue(product["quantity"])
            lay.addRow("الكمية الفعلية على الرف:", self.value)
        else:
            lay.addRow("الكمية (+ إضافة / − خصم):", self.value)
        self.reason = QComboBox()
        self.reason.setEditable(True)
        self.reason.addItems(["جرد دوري"] if count_mode else self.REASONS)
        lay.addRow("السبب:", self.reason)
        if not count_mode:
            self.has_expiry = QCheckBox("للكمية المضافة تاريخ صلاحية")
            self.expiry = QDateEdit(calendarPopup=True)
            self.expiry.setDisplayFormat("yyyy-MM-dd")
            self.expiry.setDate(QDate.currentDate().addMonths(6))
            self.expiry.setEnabled(False)
            self.has_expiry.toggled.connect(self.expiry.setEnabled)
            lay.addRow("", self.has_expiry)
            lay.addRow("تاريخ الانتهاء:", self.expiry)
            lay.addRow("", hint("أي نقص بلا فاتورة يُسجَّل خسارة في تقرير الأرباح، وأي زيادة مكسباً. "
                                "استثناء: «استلام بضاعة» (بضاعة بلا فاتورة شراء) ولتصحيح استلام خاطئ اختر نفس السبب بالسالب. "
                                "الأفضل دائماً تسجيل البضاعة بفاتورة مشتريات."))
        ok_cancel(self, lay)
        self.value.setFocus()

    def accept(self):
        try:
            if self.count_mode:
                diff = products.set_stock_count(self.product["id"], self.value.value(), self.reason.currentText())
                info(self, f"تم الجرد. الفرق: {fmt_qty(diff)}")
            else:
                if not self.value.value():
                    return
                expiry = None
                if self.value.value() > 0 and self.has_expiry.isChecked():
                    expiry = self.expiry.date().toString("yyyy-MM-dd")
                products.adjust_stock(self.product["id"], self.value.value(), self.reason.currentText(), expiry_date=expiry)
        except Exception as e:
            error(self, e)
            return
        super().accept()


class MovementsDialog(QDialog):
    def __init__(self, parent, product):
        super().__init__(parent)
        self.setWindowTitle(f"حركة الصنف: {product['name']}")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        t = Table(["التاريخ", "التغيير", "الرصيد بعدها", "السبب", "المستخدم"], stretch=3)
        rows = products.stock_movements(product["id"])
        t.set_rows([[r["created_at"], (f"{r['change_qty']:+g}", r["change_qty"]),
                     qty_cell(r["balance_after"]) if r["balance_after"] is not None else "",
                     r["reason"] or "", r["username"] or ""] for r in rows], rows,
                   colors=[("#F0FDF4" if r["change_qty"] > 0 else "#FEF2F2") for r in rows])
        lay.addWidget(t)


class BatchesDialog(QDialog):
    """دفعات الصنف وتواريخ صلاحيتها"""

    def __init__(self, parent, product):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle(f"الدفعات والصلاحية: {product['name']}")
        self.resize(720, 420)
        lay = QVBoxLayout(self)
        self.table = Table(["تاريخ الانتهاء", "المتبقي", "المستلم", "رقم الدفعة", "تاريخ الاستلام", "الحالة"])
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("🗑 إتلاف الدفعة المحددة (خسارة)", "dangerBtn", self.write_off))
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(hint("البيع يخصم تلقائياً من الدفعة الأقرب انتهاءً أولاً (FEFO)."))
        self.load()

    def load(self):
        from core import db
        rows = products.get_batches(self.product["id"])
        today = db.today()
        def status(b):
            return "منتهية" if b["expiry_date"] < today else "سارية"
        self.table.set_rows([[b["expiry_date"], qty_cell(b["remaining"]), qty_cell(b["quantity"]), b["batch_no"] or "",
                              (b["created_at"] or "")[:10], status(b)] for b in rows], rows,
                            colors=[("#FEE2E2" if b["expiry_date"] < today else None) for b in rows])

    def write_off(self):
        b = self.table.selected_data()
        if b and require_permission(self, "inventory") and \
                ask(self, f"إتلاف {fmt_qty(b['remaining'])} من الدفعة المنتهية في {b['expiry_date']}؟"):
            try:
                products.write_off_batch(b["id"])
            except ValueError as e:
                warn(self, str(e))
            self.load()


class LabelsDialog(QDialog):
    def __init__(self, parent, product_rows):
        super().__init__(parent)
        self.setWindowTitle("طباعة ملصقات الأسعار")
        self.rows = product_rows
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"عدد المنتجات المحددة: {len(product_rows)}"))
        self.copies = QSpinBox()
        self.copies.setRange(1, 500)
        self.copies.setValue(1)
        lay.addRow("عدد النسخ لكل منتج:", self.copies)
        self.use_qty = QCheckBox("عدد النسخ = الكمية في المخزون (للأصناف الجديدة)")
        lay.addRow("", self.use_qty)
        lay.addRow("", hint("المقاس الافتراضي 50×30 مم. المنتجات التي بلا باركود يُولَّد لها باركود داخلي تلقائياً."))
        ok_cancel(self, lay, "معاينة وطباعة")

    def items(self):
        out = []
        for p in self.rows:
            code = p["barcode"] or products.assign_internal_barcode(p["id"])
            n = max(1, int(p["quantity"])) if self.use_qty.isChecked() else self.copies.value()
            out += [(p["name"], p["sale_price"], code)] * min(n, 500)
        return out


class InventoryScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

        head = QHBoxLayout()
        head.addStretch()
        head.addWidget(button("📥 استيراد من Excel", "secondaryBtn", self.import_csv))
        head.addWidget(button("📤 تصدير إلى Excel", "secondaryBtn", self.export_csv))
        head.addWidget(button("+ منتج جديد", "successBtn", self.add_product))
        lay.addLayout(head)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 بحث بالاسم أو الباركود أو رمز الميزان...")
        self.search.textChanged.connect(self.load)
        self.category = QComboBox()
        self.category.currentTextChanged.connect(self.load)
        self.low_only = QCheckBox("النواقص فقط")
        self.low_only.toggled.connect(self.load)
        filters.addWidget(self.search, 1)
        filters.addWidget(QLabel("الفئة:"))
        filters.addWidget(self.category)
        filters.addWidget(self.low_only)
        lay.addLayout(filters)

        self.table = Table(["المنتج", "الباركود", "الفئة", "الوحدة", "التكلفة", "سعر البيع", "هامش الربح",
                            "الكمية", "حد التنبيه", "قيمة المخزون", "أقرب صلاحية"])
        self.table.setSelectionMode(Table.ExtendedSelection)
        self.table.doubleClicked.connect(self.edit_product)
        lay.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for text, obj, slot in [("✏ تعديل", None, self.edit_product), ("± تعديل الكمية", "secondaryBtn", self.adjust),
                                ("📋 جرد", "secondaryBtn", self.count), ("📜 حركة الصنف", "secondaryBtn", self.movements),
                                ("⏳ الدفعات", "secondaryBtn", self.batches),
                                ("🏷 طباعة ملصقات", "secondaryBtn", self.labels), ("🗑 حذف", "dangerBtn", self.delete)]:
            actions.addWidget(button(text, obj, slot))
        actions.addStretch()
        lay.addLayout(actions)
        self.summary = QLabel("")
        self.summary.setObjectName("subTitle")
        lay.addWidget(self.summary)

    def refresh(self):
        current = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItems(["الكل"] + products.get_categories())
        self.category.setCurrentText(current or "الكل")
        self.category.blockSignals(False)
        self.load()

    def load(self):
        cat = self.category.currentText()
        rows = products.get_all_products(search=self.search.text().strip() or None,
                                         category=None if cat in ("", "الكل") else cat, low_only=self.low_only.isChecked())
        data, colors = [], []
        for p in rows:
            margin = ((p["sale_price"] - p["cost_price"]) / p["sale_price"] * 100) if p["sale_price"] else 0
            unit = (p["unit"] or "") + (f" +{p['units_count']}" if p["units_count"] else "")
            data.append([p["name"], p["barcode"] or "", p["category"] or "", unit, float(p["cost_price"]),
                         float(p["sale_price"]), (f"{margin:.0f}%", margin), qty_cell(p["quantity"]),
                         qty_cell(p["min_quantity"]), float(max(p["quantity"], 0) * p["cost_price"]),
                         p["next_expiry"] or ""])
            colors.append("#FEE2E2" if p["quantity"] <= 0 else ("#FEF3C7" if p["quantity"] <= p["min_quantity"] else None))
        self.table.set_rows(data, rows, colors)
        v = products.inventory_value()
        self.summary.setText(f"الأصناف: {len(rows)}   |   قيمة المخزون بالتكلفة: {m(v['cost_value'])}   |   بسعر البيع: {m(v['sale_value'])}")

    def selected(self):
        p = self.table.selected_data()
        if not p:
            warn(self, "اختر منتجاً من الجدول أولاً")
        return p

    def selected_many(self):
        rows = sorted({i.row() for i in self.table.selectedItems()})
        out = []
        for r in rows:
            idx = self.table.item(r, 0).data(Qt.UserRole)
            out.append(self.table._data[idx])
        return out

    def add_product(self):
        if ProductDialog(self).exec() == QDialog.Accepted:
            self.refresh()

    def edit_product(self):
        p = self.selected()
        if p and ProductDialog(self, products.get_product(p["id"])).exec() == QDialog.Accepted:
            self.refresh()

    def adjust(self):
        p = self.selected()
        if p and StockDialog(self, products.get_product(p["id"])).exec() == QDialog.Accepted:
            self.load()

    def count(self):
        p = self.selected()
        if p and StockDialog(self, products.get_product(p["id"]), count_mode=True).exec() == QDialog.Accepted:
            self.load()

    def movements(self):
        p = self.selected()
        if p:
            MovementsDialog(self, p).exec()

    def batches(self):
        p = self.selected()
        if p:
            BatchesDialog(self, p).exec()
            self.load()

    def labels(self):
        rows = self.selected_many()
        if not rows:
            warn(self, "حدد منتجاً أو أكثر (Ctrl + نقر لتحديد عدة منتجات)")
            return
        dlg = LabelsDialog(self, rows)
        if dlg.exec() == QDialog.Accepted:
            printing.print_labels(self, dlg.items())
            self.load()

    def delete(self):
        p = self.selected()
        extra = (f"\n\nالكمية الموجودة ({fmt_qty(p['quantity'])}) ستُسجَّل خسارة في تقرير الأرباح."
                 if p and abs(p["quantity"] or 0) > 1e-9 else "")
        if p and ask(self, f"حذف المنتج '{p['name']}'؟\n(يبقى ظاهراً في الفواتير القديمة){extra}"):
            products.delete_product(p["id"])
            self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "تصدير المنتجات", "المنتجات.csv", "CSV (*.csv)")
        if path:
            n = products.export_csv(path if path.endswith(".csv") else path + ".csv")
            info(self, f"تم تصدير {n} منتج. يمكنك فتح الملف في Excel وتعديله ثم استيراده مجدداً.")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "استيراد منتجات", "", "CSV (*.csv)")
        if not path:
            return
        try:
            added, updated, errors = products.import_csv(path)
        except Exception as e:
            error(self, f"تعذر قراءة الملف:\n{e}")
            return
        msg = f"تمت إضافة {added} منتج وتحديث {updated} منتج."
        if errors:
            msg += "\n\nأخطاء:\n" + "\n".join(errors[:15])
        info(self, msg + "\n\nترتيب الأعمدة: " + "، ".join(products.CSV_HEADERS))
        self.refresh()
