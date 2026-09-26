# -*- coding: utf-8 -*-
"""الموردون وفواتير المشتريات"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QDialog, QFormLayout, QComboBox,
                               QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QCheckBox,
                               QAbstractItemView)

from datetime import datetime

from core import suppliers, products, shifts
from core.utils import money, to_float, fmt_qty
from ui.dialogs import ProductPicker, ProductDialog
from ui.widgets import (Table, button, page, title, hint, warn, info, ask, error, MoneySpin, ok_cancel, m, card,
                        DateRange, qty_cell)


class SupplierDialog(QDialog):
    def __init__(self, parent, supplier=None):
        super().__init__(parent)
        self.supplier = supplier
        self.setWindowTitle("تعديل مورد" if supplier else "مورد جديد")
        self.setMinimumWidth(400)
        lay = QFormLayout(self)
        self.name, self.phone, self.address, self.notes = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.opening = MoneySpin()
        lay.addRow("اسم المورد / الشركة:", self.name)
        lay.addRow("الهاتف:", self.phone)
        lay.addRow("العنوان:", self.address)
        lay.addRow("ملاحظات:", self.notes)
        if supplier:
            self.name.setText(supplier["name"])
            self.phone.setText(supplier["phone"] or "")
            self.address.setText(supplier["address"] or "")
            self.notes.setText(supplier["notes"] or "")
        else:
            lay.addRow("رصيد سابق مستحق له:", self.opening)
        ok_cancel(self, lay)

    def accept(self):
        try:
            if self.supplier:
                suppliers.update_supplier(self.supplier["id"], self.name.text(), self.phone.text(), self.address.text(),
                                          self.notes.text())
            else:
                suppliers.add_supplier(self.name.text(), self.phone.text(), self.address.text(), self.notes.text(),
                                       self.opening.value())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class PaySupplierDialog(QDialog):
    def __init__(self, parent, supplier, balance):
        super().__init__(parent)
        self.setWindowTitle(f"دفعة للمورد {supplier['name']}")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"المستحق له: <b>{m(balance)}</b>"))
        self.amount = MoneySpin(big=True)
        self.amount.setValue(max(balance, 0))
        self.method = QComboBox()
        self.method.addItems(suppliers.PAYMENT_METHODS)
        self.note = QLineEdit()
        lay.addRow("المبلغ:", self.amount)
        lay.addRow("طريقة الدفع:", self.method)
        lay.addRow("ملاحظة:", self.note)
        ok_cancel(self, lay, "تسجيل الدفعة")


class PurchaseDialog(QDialog):
    """فاتورة مشتريات: تزيد المخزون وتحدّث التكلفة وسعر البيع"""

    def __init__(self, parent, supplier_id=None):
        super().__init__(parent)
        self.setWindowTitle("فاتورة مشتريات جديدة")
        self.resize(900, 620)
        self.lines = []
        lay = QVBoxLayout(self)

        top = QFormLayout()
        self.supplier = QComboBox()
        self.supplier.addItem("— مشتريات نقدية بدون مورد —", None)
        for s in suppliers.list_suppliers():
            self.supplier.addItem(s["name"], s["id"])
        if supplier_id:
            self.supplier.setCurrentIndex(self.supplier.findData(supplier_id))
        self.ref = QLineEdit()
        self.ref.setPlaceholderText("رقم فاتورة المورد (اختياري)")
        top.addRow("المورد:", self.supplier)
        top.addRow("رقم فاتورة المورد:", self.ref)
        lay.addLayout(top)

        row = QHBoxLayout()
        self.scan = QLineEdit()
        self.scan.setPlaceholderText("امسح باركود المنتج أو اكتب اسمه واضغط Enter...")
        self.scan.returnPressed.connect(self.on_scan)
        row.addWidget(self.scan, 1)
        row.addWidget(button("+ منتج جديد", "secondaryBtn", self.new_product))
        lay.addLayout(row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["المنتج", "الوحدة", "الكمية", "تكلفة الوحدة", "الإجمالي",
                                              "سعر بيع الحبة", "الصلاحية", "المخزون"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self.on_edit)
        lay.addWidget(self.table, 1)
        lay.addWidget(hint("انقر مرتين على الكمية أو التكلفة أو سعر البيع أو الصلاحية (بصيغة 2026-12-31) لتعديلها. "
                           "امسح باركود الكرتونة لشرائها كرتونة، أو غيّر وحدة السطر من الزر."))
        rrow = QHBoxLayout()
        rrow.addWidget(button("📦 تغيير الوحدة", "secondaryBtn", self.change_unit))
        rrow.addWidget(button("حذف السطر المحدد", "dangerBtn", self.remove_line))
        rrow.addStretch()
        lay.addLayout(rrow)

        bottom = QFormLayout()
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setObjectName("bigNumber")
        self.paid = MoneySpin()
        self.method = QComboBox()
        self.method.addItems(suppliers.PAYMENT_METHODS)
        self.pay_all = QCheckBox("دفع كامل المبلغ")
        self.pay_all.setChecked(True)
        self.pay_all.toggled.connect(self.update_total)
        self.update_prices = QCheckBox("تحديث أسعار البيع للمنتجات")
        self.update_prices.setChecked(True)
        bottom.addRow("الإجمالي:", self.total_lbl)
        bottom.addRow("", self.pay_all)
        bottom.addRow("المدفوع الآن:", self.paid)
        bottom.addRow("طريقة الدفع:", self.method)
        bottom.addRow("", self.update_prices)
        lay.addLayout(bottom)
        ok_cancel(self, lay, "حفظ الفاتورة")
        self._busy = False
        self.scan.setFocus()

    def on_scan(self):
        text = self.scan.text().strip()
        if not text:
            return
        p, _, unit = products.lookup_code(text)
        if not p:
            dlg = ProductPicker(self, text)
            if dlg.exec() != QDialog.Accepted:
                return
            p = dlg.selected
        self.add_line(products.get_product(p["id"]), unit)
        self.scan.clear()

    def new_product(self):
        dlg = ProductDialog(self, barcode_text=self.scan.text().strip() if self.scan.text().strip().isdigit() else "")
        if dlg.exec() == QDialog.Accepted:
            self.add_line(products.get_product(dlg.saved_id))
            self.scan.clear()

    def add_line(self, p, unit=None):
        factor = float(unit["factor"]) if unit else 1.0
        for ln in self.lines:
            if ln["product_id"] == p["id"] and ln["factor"] == factor:
                ln["quantity"] += 1
                self.render()
                return
        self.lines.append({"product_id": p["id"], "name": p["name"], "quantity": 1.0,
                           "unit_cost": money(p["cost_price"] * factor), "factor": factor,
                           "unit_name": unit["name"] if unit else p["unit"], "base_unit": p["unit"],
                           "sale_price": p["sale_price"], "stock": p["quantity"], "expiry": ""})
        self.render()
        self.table.selectRow(len(self.lines) - 1)

    def render(self):
        self._busy = True
        self.table.setRowCount(len(self.lines))
        for r, ln in enumerate(self.lines):
            unit = ln["unit_name"] if ln["factor"] == 1 else f"{ln['unit_name']} ({fmt_qty(ln['factor'])})"
            vals = [ln["name"], unit, fmt_qty(ln["quantity"]), m(ln["unit_cost"]), m(ln["quantity"] * ln["unit_cost"]),
                    m(ln["sale_price"]), ln["expiry"], fmt_qty(ln["stock"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (0, 1, 4, 7):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 5 and ln["sale_price"] < ln["unit_cost"] / ln["factor"]:
                    it.setBackground(Qt.red)
                    it.setToolTip("سعر البيع أقل من تكلفة الحبة!")
                self.table.setItem(r, c, it)
        self._busy = False
        self.update_total()

    def on_edit(self, item):
        if self._busy:
            return
        r, c = item.row(), item.column()
        if c == 6:
            text = item.text().strip()
            try:
                self.lines[r]["expiry"] = datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d") if text else ""
            except ValueError:
                warn(self, "اكتب التاريخ بالصيغة: سنة-شهر-يوم، مثل 2026-12-31")
        else:
            v = to_float(item.text(), -1)
            key = {2: "quantity", 3: "unit_cost", 5: "sale_price"}.get(c)
            if key and v >= 0:
                self.lines[r][key] = v
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.render)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete and self.table.hasFocus():
            self.remove_line()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            return  # حتى لا تُحفظ الفاتورة بالخطأ عند مسح الباركود
        super().keyPressEvent(e)

    def change_unit(self):
        r = self.table.currentRow()
        if not (0 <= r < len(self.lines)):
            return
        ln = self.lines[r]
        choices = products.unit_choices(ln["product_id"])
        if len(choices) < 2:
            info(self, "لا توجد وحدات إضافية لهذا المنتج. أضفها من بطاقة المنتج (مثل: كرتونة = 24 حبة).")
            return
        from PySide6.QtWidgets import QInputDialog
        labels = [f"{c['name']} ({fmt_qty(c['factor'])} {ln['base_unit']})" for c in choices]
        label, ok = QInputDialog.getItem(self, "وحدة الشراء", ln["name"], labels, 0, False)
        if ok:
            c = choices[labels.index(label)]
            base_cost = ln["unit_cost"] / ln["factor"]
            ln.update(factor=float(c["factor"]), unit_name=c["name"], unit_cost=money(base_cost * c["factor"]))
            self.render()

    def remove_line(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.lines):
            del self.lines[r]
            self.render()

    def total(self):
        return money(sum(money(l["quantity"] * l["unit_cost"]) for l in self.lines))

    def update_total(self):
        t = self.total()
        self.total_lbl.setText(m(t))
        if self.pay_all.isChecked():
            self.paid.setValue(t)
        self.paid.setEnabled(not self.pay_all.isChecked())

    def accept(self):
        if not self.lines:
            warn(self, "أضف منتجات للفاتورة")
            return
        try:
            res = suppliers.create_purchase(
                self.supplier.currentData(),
                [{"product_id": l["product_id"], "quantity": l["quantity"], "unit_cost": l["unit_cost"],
                  "sale_price": l["sale_price"], "factor": l["factor"], "unit_name": l["unit_name"],
                  "expiry_date": l["expiry"] or None} for l in self.lines],
                paid=self.paid.value(), payment_method=self.method.currentText(), supplier_ref=self.ref.text(),
                shift_id=shifts.current_shift_id(), update_sale_prices=self.update_prices.isChecked())
        except ValueError as e:
            warn(self, str(e))
            return
        info(self, f"تم حفظ فاتورة المشتريات {res['purchase_number']} وإضافة الكميات للمخزون.")
        super().accept()


class PurchaseReturnDialog(QDialog):
    """إرجاع بضاعة للمورد: تُخصم من المخزون ومن حسابه"""

    def __init__(self, parent, supplier):
        super().__init__(parent)
        self.supplier = supplier
        self.setWindowTitle(f"مرتجع بضاعة للمورد {supplier['name']}")
        self.resize(720, 460)
        self.lines = []
        lay = QVBoxLayout(self)
        self.scan = QLineEdit()
        self.scan.setPlaceholderText("امسح باركود الصنف المرتجع أو اكتب اسمه واضغط Enter...")
        self.scan.returnPressed.connect(self.on_scan)
        lay.addWidget(self.scan)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الصنف", "الكمية (بالحبة)", "سعر الحبة عند المورد", "الإجمالي", "الموجود"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self.on_edit)
        lay.addWidget(self.table, 1)
        form = QFormLayout()
        self.reason = QComboBox()
        self.reason.setEditable(True)
        self.reason.addItems(["منتهي الصلاحية", "تالف", "خطأ في التوريد", "زائد عن الحاجة"])
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setObjectName("bigNumber")
        form.addRow("السبب:", self.reason)
        form.addRow("يُخصم من حساب المورد:", self.total_lbl)
        lay.addLayout(form)
        lay.addWidget(hint("السعر الافتراضي = تكلفة الحبة عندك. إذا اتفقت مع المورد على سعر آخر عدّله؛ "
                           "الفرق يُسجَّل ربحاً أو خسارة تلقائياً."))
        ok_cancel(self, lay, "حفظ المرتجع")
        self._busy = False

    def on_scan(self):
        text = self.scan.text().strip()
        if not text:
            return
        p, _, _ = products.lookup_code(text)
        if not p:
            dlg = ProductPicker(self, text)
            if dlg.exec() != QDialog.Accepted:
                return
            p = dlg.selected
        p = products.get_product(p["id"])
        for ln in self.lines:
            if ln["product_id"] == p["id"]:
                ln["quantity"] += 1
                break
        else:
            self.lines.append({"product_id": p["id"], "name": p["name"], "quantity": 1.0, "unit_cost": p["cost_price"],
                               "stock": p["quantity"]})
        self.scan.clear()
        self.render()

    def render(self):
        self._busy = True
        self.table.setRowCount(len(self.lines))
        for r, ln in enumerate(self.lines):
            for c, v in enumerate([ln["name"], fmt_qty(ln["quantity"]), m(ln["unit_cost"]),
                                   m(ln["quantity"] * ln["unit_cost"]), fmt_qty(ln["stock"])]):
                it = QTableWidgetItem(v)
                if c in (0, 3, 4):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self._busy = False
        self.total_lbl.setText(m(sum(l["quantity"] * l["unit_cost"] for l in self.lines)))

    def on_edit(self, item):
        if self._busy:
            return
        v = to_float(item.text(), -1)
        key = {1: "quantity", 2: "unit_cost"}.get(item.column())
        if key and v >= 0:
            self.lines[item.row()][key] = v
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.render)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            return
        super().keyPressEvent(e)

    def accept(self):
        try:
            res = suppliers.create_purchase_return(
                self.supplier["id"], [{"product_id": l["product_id"], "quantity": l["quantity"], "unit_cost": l["unit_cost"]}
                                      for l in self.lines], self.reason.currentText(), shift_id=shifts.current_shift_id())
        except ValueError as e:
            warn(self, str(e))
            return
        info(self, f"تم حفظ المرتجع {res['return_number']} بقيمة {m(res['total'])} وخصمه من حساب المورد.")
        super().accept()


class SuppliersScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addStretch()
        self.dues_lbl = QLabel("")
        self.dues_lbl.setObjectName("chipWarn")
        head.addWidget(self.dues_lbl)
        head.addWidget(button("🧾 فاتورة مشتريات جديدة", "successBtn", self.new_purchase))
        lay.addLayout(head)

        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # --- تبويب الموردين
        sup = QWidget()
        sl = QVBoxLayout(sup)
        sl.setContentsMargins(0, 8, 0, 0)
        split = QSplitter(Qt.Horizontal)
        left, ll = card()
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 بحث...")
        self.search.textChanged.connect(self.load)
        row.addWidget(self.search, 1)
        row.addWidget(button("+ مورد", "successBtn", self.add))
        ll.addLayout(row)
        self.table = Table(["المورد", "الهاتف", "المستحق له"])
        self.table.itemSelectionChanged.connect(self.load_statement)
        self.table.doubleClicked.connect(self.edit)
        ll.addWidget(self.table)
        split.addWidget(left)
        right, rl = card()
        self.sup_title = QLabel("اختر مورداً")
        self.sup_title.setObjectName("subTitle")
        rl.addWidget(self.sup_title)
        b = QHBoxLayout()
        b.addWidget(button("💸 دفعة للمورد", "successBtn", self.pay))
        b.addWidget(button("🧾 فاتورة من هذا المورد", "secondaryBtn", lambda: self.new_purchase(True)))
        b.addWidget(button("↩ مرتجع للمورد", "warnBtn", self.purchase_return))
        b.addWidget(button("📤 شيك مؤجل", "secondaryBtn", self.issue_cheque))
        b.addWidget(button("✏ تعديل", "secondaryBtn", self.edit))
        b.addWidget(button("🗑", "dangerBtn", self.delete))
        rl.addLayout(b)
        self.statement = Table(["التاريخ", "البيان", "المبلغ", "الرصيد"], stretch=1, sortable=False)
        rl.addWidget(self.statement)
        split.addWidget(right)
        split.setSizes([450, 650])
        sl.addWidget(split)
        tabs.addTab(sup, "الموردون")

        # --- تبويب فواتير المشتريات
        pur = QWidget()
        pl = QVBoxLayout(pur)
        pl.setContentsMargins(0, 8, 0, 0)
        self.range = DateRange("هذا الشهر")
        self.range.changed.connect(self.load_purchases)
        pl.addWidget(self.range)
        split2 = QSplitter(Qt.Vertical)
        self.purchases = Table(["الرقم", "التاريخ", "المورد", "رقم فاتورة المورد", "الإجمالي", "المدفوع", "طريقة الدفع"])
        self.purchases.itemSelectionChanged.connect(self.load_purchase_items)
        split2.addWidget(self.purchases)
        self.p_items = Table(["المنتج", "الوحدة", "الكمية", "تكلفة الوحدة", "الإجمالي", "الصلاحية"])
        split2.addWidget(self.p_items)
        pl.addWidget(split2)
        self.p_total = QLabel("")
        self.p_total.setObjectName("subTitle")
        pl.addWidget(self.p_total)
        tabs.addTab(pur, "فواتير المشتريات")

    def refresh(self):
        self.load()
        self.load_purchases()

    def load(self):
        rows = suppliers.list_suppliers(self.search.text().strip() or None)
        self.table.set_rows([[r["name"], r["phone"] or "", float(r["balance_due"])] for r in rows], rows)
        self.dues_lbl.setText(f"مستحقات الموردين: {m(suppliers.total_dues())}")

    def load_statement(self):
        s = self.table.selected_data()
        if not s:
            return
        self.sup_title.setText(f"{s['name']} — المستحق: {m(suppliers.balance(s['id']))}")
        rows = list(reversed(suppliers.statement(s["id"])))
        self.statement.set_rows([[r["created_at"][:16], f"{r['type_label']} {r['note'] or ''} {r['method'] or ''}".strip(),
                                  float(r["amount"]), float(r["running"])] for r in rows], rows)

    def load_purchases(self):
        a, b = self.range.range()
        rows = suppliers.list_purchases(a, b)
        self.purchases.set_rows([[r["purchase_number"], r["created_at"][:16], r["supplier_name"] or "نقدي",
                                  r["supplier_ref"] or "", float(r["total"]), float(r["paid"]), r["payment_method"] or ""]
                                 for r in rows], rows)
        self.p_total.setText(f"إجمالي المشتريات في الفترة: {m(sum(r['total'] for r in rows))}")
        self.p_items.set_rows([])

    def load_purchase_items(self):
        p = self.purchases.selected_data()
        if p:
            rows = suppliers.purchase_items(p["id"])
            self.p_items.set_rows([[r["product_name"], r["unit_name"] or "", qty_cell(r["quantity"]), float(r["unit_cost"]),
                                    float(r["total"]), r["expiry_date"] or ""] for r in rows])

    def need(self):
        s = self.table.selected_data()
        if not s:
            warn(self, "اختر مورداً أولاً")
        return s

    def add(self):
        if SupplierDialog(self).exec() == QDialog.Accepted:
            self.load()

    def edit(self):
        s = self.need()
        if s and SupplierDialog(self, suppliers.get_supplier(s["id"])).exec() == QDialog.Accepted:
            self.load()

    def delete(self):
        s = self.need()
        if s and ask(self, f"حذف المورد {s['name']}؟"):
            try:
                suppliers.deactivate_supplier(s["id"])
            except ValueError as e:
                warn(self, str(e))
            self.load()

    def pay(self):
        s = self.need()
        if not s:
            return
        dlg = PaySupplierDialog(self, s, suppliers.balance(s["id"]))
        if dlg.exec() == QDialog.Accepted:
            try:
                suppliers.pay_supplier(s["id"], dlg.amount.value(), dlg.method.currentText(), dlg.note.text(),
                                       shift_id=shifts.current_shift_id())
            except ValueError as e:
                warn(self, str(e))
            self.load()

    def new_purchase(self, for_selected=False):
        sid = None
        if for_selected:
            s = self.need()
            if not s:
                return
            sid = s["id"]
        if PurchaseDialog(self, sid).exec() == QDialog.Accepted:
            self.refresh()

    def purchase_return(self):
        s = self.need()
        if s and PurchaseReturnDialog(self, s).exec() == QDialog.Accepted:
            self.load()
            self.load_statement()

    def issue_cheque(self):
        s = self.need()
        if not s:
            return
        from ui.cheques_screen import ChequeDialog
        from ui.widgets import require_permission
        if require_permission(self, "cheques") and ChequeDialog(self, "out", s["id"]).exec() == QDialog.Accepted:
            self.load()
            self.load_statement()
