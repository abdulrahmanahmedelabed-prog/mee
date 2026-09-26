# -*- coding: utf-8 -*-
"""
شاشة نقطة البيع - مصممة للسرعة:
- مسح الباركود يضيف فوراً (ويدعم باركود الميزان للموزونات)
- 3*باركود = إضافة 3 قطع مرة واحدة
- + / - لتغيير كمية السطر المحدد، Delete لحذفه
- F2 دفع | F12 نقدي سريع | F4 عميل | F6 تعليق | F7 المعلّقة | F8 كمية | F9 خصم | F10 سعر | F11 آخر فاتورة
"""

from PySide6.QtCore import Qt, QTimer, Signal, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QGridLayout, QDialog, QFormLayout, QCheckBox, QInputDialog, QAbstractItemView, QApplication,
    QScrollArea, QRadioButton, QButtonGroup
)

from core import products, sales, settings, auth, receipts, customers, drawer, audit, loyalty
from core.sales import SaleError
from core.utils import money, fmt_qty, qty as round_qty
from ui import printing
from ui.dialogs import CustomerPicker, ProductDialog, ensure_shift
from ui.widgets import (MoneySpin, Table, button, hint, warn, error, ask, require_permission, ok_cancel, m, title,
                        qty_cell)


# ---------------------------------------------------------------------------
# نافذة الدفع
# ---------------------------------------------------------------------------

class PaymentDialog(QDialog):
    def __init__(self, parent, total, customer=None):
        super().__init__(parent)
        self.setWindowTitle("الدفع")
        self.setMinimumWidth(480)
        self.total = total
        self.customer = customer
        self.result_data = None
        sym = settings.get("currency_symbol")

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel(f"{m(total)} {sym}")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size:40px; font-weight:900; color:#16A34A;")
        lay.addWidget(QLabel("المطلوب:"))
        lay.addWidget(t)
        if customer:
            bal = customers.balance(customer["id"])
            lay.addWidget(hint(f"العميل: {customer['name']} — رصيده الحالي: {m(bal)}"))

        form = QFormLayout()
        self.cash = MoneySpin(big=True)
        self.cash.setValue(total)
        self.card = MoneySpin()
        form.addRow("النقد المستلم:", self.cash)
        bills = QHBoxLayout()
        for label, val in [("بالضبط", None), ("10", 10), ("20", 20), ("50", 50), ("100", 100), ("200", 200)]:
            b = button(label, "billBtn")
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, v=val: self.cash.setValue(self.total - self.card.value() if v is None else v))
            bills.addWidget(b)
        form.addRow("", bills)
        form.addRow("بطاقة / تحويل:", self.card)
        self.credit_chk = QCheckBox("الباقي دين على العميل (آجل)")
        self.credit_chk.setEnabled(bool(customer))
        if not customer:
            self.credit_chk.setToolTip("اختر عميلاً أولاً (F4) للبيع الآجل")
        form.addRow("", self.credit_chk)
        lay.addLayout(form)

        row = QHBoxLayout()
        full_credit = button("آجل بالكامل", "warnBtn", self.all_credit)
        full_credit.setEnabled(bool(customer))
        all_card = button("بطاقة بالكامل", "secondaryBtn", self.all_card)
        row.addWidget(full_credit)
        row.addWidget(all_card)
        lay.addLayout(row)

        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("font-size:24px; font-weight:800;")
        lay.addWidget(self.status)

        self.print_chk = QCheckBox("طباعة الفاتورة")
        self.print_chk.setChecked(settings.get_bool("auto_print_receipt"))
        lay.addWidget(self.print_chk)

        self.ok_btn = button("إتمام البيع ✓  (Enter)", "payBtn", self.confirm)
        lay.addWidget(self.ok_btn)

        self.cash.valueChanged.connect(self.recalc)
        self.card.valueChanged.connect(self.recalc)
        self.credit_chk.toggled.connect(self.recalc)
        self.cash.lineEdit().returnPressed.connect(self.confirm)
        self.card.lineEdit().returnPressed.connect(self.confirm)
        self.recalc()
        self.cash.setFocus()

    def all_credit(self):
        self.card.setValue(0)
        self.cash.setValue(0)
        self.credit_chk.setChecked(True)

    def all_card(self):
        self.card.setValue(self.total)
        self.cash.setValue(0)

    def compute(self):
        card = money(self.card.value())
        if card > self.total + 0.009:
            return None, "مبلغ البطاقة أكبر من المطلوب"
        due = money(self.total - card)
        received = money(self.cash.value())
        if received >= due:
            return {"cash_amount": due, "card_amount": card, "credit_amount": 0.0, "cash_received": received,
                    "change": money(received - due)}, None
        short = money(due - received)
        if self.credit_chk.isChecked() and self.customer:
            return {"cash_amount": received, "card_amount": card, "credit_amount": short, "cash_received": received,
                    "change": 0.0}, None
        return None, f"ناقص: {m(short)}"

    def recalc(self):
        data, err = self.compute()
        if err:
            self.status.setText(err)
            self.status.setStyleSheet("font-size:24px; font-weight:800; color:#DC2626;")
            self.ok_btn.setEnabled(False)
        else:
            if data["credit_amount"]:
                txt = f"دين على العميل: {m(data['credit_amount'])}"
                color = "#D97706"
            else:
                txt = f"الباقي للزبون: {m(data['change'])}"
                color = "#2563EB"
            self.status.setText(txt)
            self.status.setStyleSheet(f"font-size:24px; font-weight:800; color:{color};")
            self.ok_btn.setEnabled(True)

    def confirm(self):
        data, err = self.compute()
        if err:
            return
        self.result_data = data
        self.accept()


class DiscountDialog(QDialog):
    def __init__(self, parent, subtotal, current=0):
        super().__init__(parent)
        self.setWindowTitle("خصم على الفاتورة")
        self.subtotal = subtotal
        lay = QFormLayout(self)
        self.amount_rb = QRadioButton("مبلغ")
        self.pct_rb = QRadioButton("نسبة %")
        self.amount_rb.setChecked(True)
        g = QButtonGroup(self)
        g.addButton(self.amount_rb)
        g.addButton(self.pct_rb)
        row = QHBoxLayout()
        row.addWidget(self.amount_rb)
        row.addWidget(self.pct_rb)
        lay.addRow("نوع الخصم:", row)
        self.value = MoneySpin(big=True)
        self.value.setValue(current)
        lay.addRow("القيمة:", self.value)
        self.preview = QLabel("")
        lay.addRow("", self.preview)
        self.value.valueChanged.connect(self.update_preview)
        self.pct_rb.toggled.connect(self.update_preview)
        ok_cancel(self, lay, "تطبيق")
        self.update_preview()
        self.value.setFocus()

    def discount(self):
        v = self.value.value()
        return money(self.subtotal * v / 100) if self.pct_rb.isChecked() else money(v)

    def update_preview(self):
        d = min(self.discount(), self.subtotal)
        pct = d / self.subtotal * 100 if self.subtotal else 0
        self.preview.setText(f"الخصم: {m(d)} ({pct:.1f}%) — بعد الخصم: {m(self.subtotal - d)}")


class HeldCartsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("الفواتير المعلّقة")
        self.resize(520, 380)
        self.chosen = None
        lay = QVBoxLayout(self)
        self.table = Table(["#", "الوصف", "الوقت", "عدد الأصناف", "الإجمالي"], stretch=1)
        self.table.doubleClicked.connect(self.resume)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("استرجاع للسلة", "successBtn", self.resume))
        row.addWidget(button("حذف", "dangerBtn", self.delete))
        lay.addLayout(row)
        self.load()

    def load(self):
        rows = sales.list_held_carts()
        self.table.set_rows([[r["id"], r["label"] or "-", r["created_at"][11:16], r["items"], float(r["total"])]
                             for r in rows], rows)
        if rows:
            self.table.selectRow(0)

    def resume(self):
        r = self.table.selected_data()
        if r:
            self.chosen = sales.take_held_cart(r["id"])
            self.accept()

    def delete(self):
        r = self.table.selected_data()
        if r and ask(self, "حذف هذه الفاتورة المعلّقة؟"):
            sales.take_held_cart(r["id"])
            self.load()


# ---------------------------------------------------------------------------
# شاشة البيع
# ---------------------------------------------------------------------------

COL_NAME, COL_QTY, COL_PRICE, COL_TOTAL = range(4)


class POSScreen(QWidget):
    sale_completed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.cart = []
        self.discount = 0.0      # الخصم اليدوي فقط (العروض ونقاط الولاء تُحسب تلقائياً)
        self.points = 0.0        # نقاط ولاء سيستبدلها العميل في هذه الفاتورة
        self.customer = None
        self.last_invoice_id = None
        self._rendering = False
        self.build_ui()
        self.setup_shortcuts()
        self.render_cart()

    # ------------------------------------------------------------------ UI
    def build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(14)

        # ====== المنطقة الرئيسية ======
        main = QVBoxLayout()
        main.setSpacing(10)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("bigSearch")
        self.search.setPlaceholderText("🔍  امسح الباركود أو اكتب اسم المنتج...   (3*باركود لإضافة 3 قطع)")
        self.search.returnPressed.connect(self.on_enter)
        self.search.textChanged.connect(self.on_text)
        self.search.installEventFilter(self)
        top.addWidget(self.search, 1)
        self.customer_btn = button("👤  زبون نقدي (F4)", "ghostBtn", self.pick_customer)
        self.customer_btn.setMinimumHeight(48)
        top.addWidget(self.customer_btn)
        main.addLayout(top)

        self.flash = QLabel("")
        self.flash.setMinimumHeight(22)
        main.addWidget(self.flash)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.flash.setText(""))

        self.results = Table(["المنتج", "الباركود", "السعر", "المتوفر"], sortable=False)
        self.results.setMaximumHeight(230)
        self.results.hide()
        self.results.doubleClicked.connect(self.add_selected_result)
        self.results.installEventFilter(self)
        main.addWidget(self.results)

        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setObjectName("cart")
        self.cart_table.setHorizontalHeaderLabels(["المنتج", "الكمية", "السعر", "الإجمالي"])
        hh = self.cart_table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for c in (COL_QTY, COL_PRICE, COL_TOTAL):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self.cart_table.setColumnWidth(c, 120)
        self.cart_table.verticalHeader().setDefaultSectionSize(42)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cart_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cart_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                                        QAbstractItemView.AnyKeyPressed)
        self.cart_table.setAlternatingRowColors(True)
        self.cart_table.setShowGrid(False)
        self.cart_table.itemChanged.connect(self.on_cart_edit)
        self.cart_table.installEventFilter(self)
        main.addWidget(self.cart_table, 1)

        # أزرار سريعة (المفضلة)
        self.fav_area = QScrollArea()
        self.fav_area.setWidgetResizable(True)
        self.fav_area.setFrameShape(QFrame.NoFrame)
        self.fav_area.setMaximumHeight(130)
        self.fav_widget = QWidget()
        self.fav_grid = QGridLayout(self.fav_widget)
        self.fav_grid.setSpacing(6)
        self.fav_grid.setContentsMargins(0, 0, 0, 0)
        self.fav_area.setWidget(self.fav_widget)
        main.addWidget(self.fav_area)

        root.addLayout(main, 1)

        # ====== اللوحة الجانبية ======
        side_w = QWidget()
        side_w.setFixedWidth(340)
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(10)

        totals = QFrame()
        totals.setObjectName("totalsCard")
        tl = QGridLayout(totals)
        tl.setContentsMargins(16, 10, 16, 10)
        tl.setVerticalSpacing(2)
        self.lbl_sub = QLabel("0.00")
        self.lbl_disc = QLabel("0.00")
        self.lbl_tax = QLabel("0.00")
        self.lbl_items = QLabel("0")
        for i, (name, lbl) in enumerate([("عدد الأصناف", self.lbl_items), ("المجموع", self.lbl_sub),
                                         ("الخصم", self.lbl_disc), ("الضريبة", self.lbl_tax)]):
            a = QLabel(name)
            a.setObjectName("totalsLabel")
            lbl.setObjectName("totalsValue")
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tl.addWidget(a, i, 0)
            tl.addWidget(lbl, i, 1)
        self.lbl_total = QLabel("0.00")
        self.lbl_total.setObjectName("grandTotal")
        self.lbl_total.setAlignment(Qt.AlignCenter)
        tl.addWidget(self.lbl_total, 4, 0, 1, 2)
        self.lbl_promo = QLabel("")
        self.lbl_promo.setStyleSheet("color:#F9A8D4; font-weight:700;")
        self.lbl_promo.setAlignment(Qt.AlignCenter)
        self.lbl_promo.setWordWrap(True)
        tl.addWidget(self.lbl_promo, 5, 0, 1, 2)
        self.lbl_change = QLabel("")
        self.lbl_change.setObjectName("changeLabel")
        self.lbl_change.setAlignment(Qt.AlignCenter)
        self.lbl_change.setWordWrap(True)
        tl.addWidget(self.lbl_change, 6, 0, 1, 2)
        side.addWidget(totals)

        pay = button("💵  دفع  (F2)", "payBtn", self.checkout)
        pay.setMinimumHeight(56)
        side.addWidget(pay)

        grid = QGridLayout()
        grid.setSpacing(8)
        actions = [
            ("⚡ نقدي سريع  F12", self.quick_cash), ("٪ خصم  F9", self.set_discount),
            ("🔢 كمية  F8", self.change_qty), ("🏷 سعر  F10", self.change_price),
            ("📦 الوحدة  F5", self.change_unit), ("🗑 حذف سطر  Del", self.remove_selected),
            ("⏸ تعليق  F6", self.hold), ("▶ المعلّقة  F7", self.show_held),
            ("🖨 آخر فاتورة  F11", self.reprint_last), ("💰 فتح الدرج", self.open_drawer),
            ("✖ تفريغ السلة", self.clear_confirm), ("➕ منتج جديد", self.new_product),
            ("🎁 استبدال نقاط", self.redeem_points), ("🔍 فحص سعر", self.price_check),
        ]
        for i, (text, slot) in enumerate(actions):
            b = button(text, "posBtn", slot)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(40)
            grid.addWidget(b, i // 2, i % 2)
        side.addLayout(grid)
        side.addStretch()
        side.addWidget(hint("Enter إضافة • +/- الكمية • ↓ للتنقل • Esc رجوع للبحث"))
        root.addWidget(side_w)

    def setup_shortcuts(self):
        keys = {"F2": self.checkout, "F12": self.quick_cash, "F4": self.pick_customer, "F6": self.hold,
                "F7": self.show_held, "F8": self.change_qty, "F5": self.change_unit, "F9": self.set_discount, "F10": self.change_price,
                "F11": self.reprint_last, "Esc": self.focus_search, "F3": self.focus_search}
        for k, fn in keys.items():
            sc = QShortcut(QKeySequence(k), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)

    def refresh(self):
        self.load_favorites()
        self.focus_search()

    def focus_search(self):
        self.results.hide()
        self.search.setFocus()
        self.search.selectAll()

    def show_flash(self, text, kind="ok"):
        colors = {"ok": "#16A34A", "err": "#DC2626", "info": "#2563EB"}
        self.flash.setStyleSheet(f"color:{colors[kind]}; font-weight:700;")
        self.flash.setText(text)
        self._flash_timer.start(4000)
        if kind == "err":
            QApplication.beep()

    # ------------------------------------------------------------------ المفضلة
    def load_favorites(self):
        while self.fav_grid.count():
            w = self.fav_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        favs = products.get_all_products(favorites_only=True)
        self.fav_area.setVisible(bool(favs))
        cols = 6
        for i, p in enumerate(favs):
            b = button(f"{p['name']}\n{m(p['sale_price'])}", "favBtn")
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, pid=p["id"]: self.add_product(products.get_product(pid)))
            self.fav_grid.addWidget(b, i // cols, i % cols)

    # ------------------------------------------------------------------ البحث
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if obj is self.search:
                empty = not self.search.text()
                if key == Qt.Key_Down:
                    target = self.results if self.results.isVisible() and self.results.rowCount() else self.cart_table
                    if target.rowCount():
                        target.setFocus()
                        if not target.selectedItems():
                            target.selectRow(0 if target is self.results else target.rowCount() - 1)
                    return True
                if empty and key in (Qt.Key_Plus, Qt.Key_Minus):
                    self.bump_selected(1 if key == Qt.Key_Plus else -1)
                    return True
                if empty and key == Qt.Key_Delete:
                    self.remove_selected()
                    return True
            elif obj is self.results:
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    self.add_selected_result()
                    return True
                if key == Qt.Key_Up and self.results.currentRow() <= 0:
                    self.search.setFocus()
                    return True
            elif obj is self.cart_table and self.cart_table.state() != QAbstractItemView.EditingState:
                if key == Qt.Key_Delete:
                    self.remove_selected()
                    return True
                if key in (Qt.Key_Plus, Qt.Key_Minus):
                    self.bump_selected(1 if key == Qt.Key_Plus else -1)
                    return True
        return super().eventFilter(obj, event)

    def on_text(self, text):
        text = text.strip()
        if "*" in text:
            text = text.split("*", 1)[1].strip()
        if len(text) >= 2 and not text.isdigit():
            rows = products.get_all_products(search=text)[:60]
            self.results.set_rows([[r["name"], r["barcode"] or "", float(r["sale_price"]), qty_cell(r["quantity"])]
                                   for r in rows], rows,
                                  colors=["#FEE2E2" if r["quantity"] <= 0 else None for r in rows])
            self.results.setVisible(bool(rows))
            if rows:
                self.results.selectRow(0)
        else:
            self.results.hide()

    def on_enter(self):
        raw = self.search.text().strip()
        if not raw:
            if self.cart:
                self.checkout()
            return
        multiplier = None
        code = raw
        if "*" in raw:
            left, code = raw.split("*", 1)
            try:
                multiplier = float(left.replace(",", "."))
            except ValueError:
                multiplier = None
            code = code.strip()
        if not code:
            return
        product, scale_qty, unit = products.lookup_code(code)
        if product:
            self.add_product(product, scale_qty or multiplier, unit)
            self.search.clear()
            return
        if self.results.isVisible() and self.results.rowCount():
            self.add_selected_result(multiplier)
            return
        if code.isdigit():
            self.show_flash(f"الباركود {code} غير مسجّل", "err")
            if auth.has_permission("inventory") and ask(self, f"الباركود {code} غير موجود.\nهل تريد إضافته كمنتج جديد؟"):
                self.new_product(code)
            self.search.selectAll()
        else:
            self.show_flash("لا يوجد منتج بهذا الاسم", "err")

    def add_selected_result(self, multiplier=None):
        p = self.results.selected_data()
        if p:
            self.add_product(products.get_product(p["id"]), multiplier if isinstance(multiplier, float) else None)
            self.search.clear()
            self.results.hide()
            self.search.setFocus()

    # ------------------------------------------------------------------ السلة
    def _base_in_cart(self, product_id, exclude=None):
        """مجموع الكمية بالوحدة الأساسية لمنتج في السلة (الكرتونة = 24 حبة مثلاً)"""
        return sum(i["quantity"] * i.get("factor", 1) for j, i in enumerate(self.cart)
                   if i["product_id"] == product_id and j != exclude)

    def _stock_ok(self, it, extra_base):
        if settings.get_bool("allow_negative_stock"):
            return True
        if extra_base > it["stock"] + 1e-9:
            self.show_flash(f"⚠ المتوفر من {it['base_name']}: {fmt_qty(it['stock'])} {it['unit']} فقط", "err")
            return False
        return True

    def add_product(self, product, quantity=None, unit=None):
        if not product:
            return
        factor = float(unit["factor"]) if unit else 1.0
        if quantity is None and product["is_weighted"] and not unit:
            val, ok = QInputDialog.getDouble(self, "الوزن", f"أدخل وزن {product['name']} ({product['unit']}):",
                                             1.0, 0.001, 100000, 3)
            if not ok:
                return
            quantity = val
        quantity = round_qty(quantity or 1)
        if quantity <= 0:
            return
        price = unit["sale_price"] if unit else products.price_for(product, self.customer)
        line = {"product_id": product["id"], "base_name": product["name"],
                "product_name": f"{product['name']} ({unit['name']})" if unit else product["name"],
                "quantity": quantity, "unit_price": price, "list_price": price, "factor": factor,
                "unit_name": unit["name"] if unit else product["unit"], "stock": product["quantity"],
                "unit": product["unit"]}
        if not self._stock_ok(line, self._base_in_cart(product["id"]) + quantity * factor):
            return
        existing = next((i for i in self.cart if i["product_id"] == product["id"] and i.get("factor", 1) == factor
                         and money(i["unit_price"]) == money(price)), None)
        if existing:
            existing["quantity"] = round_qty(existing["quantity"] + quantity)
            idx = self.cart.index(existing)
        else:
            self.cart.append(line)
            idx = len(self.cart) - 1
        self.render_cart(select=idx)
        msg, kind = f"✓ {line['product_name']}  ×{fmt_qty(quantity)}", "ok"
        exp = products.expiry_status(product["id"])
        if exp:
            exp_date, days_left = exp
            if days_left < 0:
                msg, kind = f"⛔ انتبه: يوجد من {product['name']} دفعة منتهية الصلاحية منذ {exp_date}", "err"
            elif days_left <= settings.get_float("expiry_alert_days", 30):
                msg, kind = f"{msg}   ⏳ أقرب صلاحية: {exp_date} (بعد {days_left} يوم)", "info"
        self.show_flash(msg, kind)

    def change_unit(self):
        """تبديل وحدة السطر المحدد: حبة ↔ كرتونة..."""
        idx = self.selected_index()
        if idx is None:
            return
        it = self.cart[idx]
        choices = products.unit_choices(it["product_id"])
        if len(choices) < 2:
            self.show_flash("هذا المنتج له وحدة بيع واحدة. أضف وحدات (كرتونة...) من بطاقة المنتج", "info")
            return
        labels = [f"{c['name']}  ({fmt_qty(c['factor'])} {it['unit']})  —  {m(c['sale_price'])}" for c in choices]
        current = next((i for i, c in enumerate(choices) if c["factor"] == it.get("factor", 1)), 0)
        label, ok = QInputDialog.getItem(self, "وحدة البيع", it["base_name"], labels, current, False)
        if not ok:
            return
        c = choices[labels.index(label)]
        new_line = dict(it, factor=float(c["factor"]), unit_name=c["name"], unit_price=c["sale_price"],
                        list_price=c["sale_price"],
                        product_name=it["base_name"] if c["factor"] == 1 else f"{it['base_name']} ({c['name']})")
        if not self._stock_ok(new_line, self._base_in_cart(it["product_id"], exclude=idx) + it["quantity"] * c["factor"]):
            return
        self.cart[idx] = new_line
        self.render_cart(select=idx)
        self.focus_search()

    def render_cart(self, select=None):
        self._rendering = True
        self.cart_table.setRowCount(len(self.cart))
        for r, it in enumerate(self.cart):
            name = QTableWidgetItem(it["product_name"])
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            q = QTableWidgetItem(fmt_qty(it["quantity"]))
            q.setTextAlignment(Qt.AlignCenter)
            price = QTableWidgetItem(m(it["unit_price"]))
            price.setTextAlignment(Qt.AlignCenter)
            if money(it["unit_price"]) != money(it["list_price"]):
                price.setForeground(Qt.darkYellow)
                price.setToolTip(f"السعر الأصلي {m(it['list_price'])}")
            total = QTableWidgetItem(m(it["quantity"] * it["unit_price"]))
            total.setFlags(total.flags() & ~Qt.ItemIsEditable)
            total.setTextAlignment(Qt.AlignCenter)
            for c, item in enumerate((name, q, price, total)):
                self.cart_table.setItem(r, c, item)
        self._rendering = False
        if select is not None and 0 <= select < len(self.cart):
            self.cart_table.selectRow(select)
            self.cart_table.scrollToItem(self.cart_table.item(select, 0))
        self.update_totals()

    def _update_display(self, totals, disc):
        from ui import customer_display
        try:
            d = customer_display.get()
            if d:
                d.show_cart(self.cart, totals, disc)
        except Exception:
            pass  # شاشة الزبون لا يجب أن توقف البيع أبداً

    def update_totals(self):
        subtotal = sales.compute_totals(self.cart)["subtotal"]
        self.discount = min(self.discount, subtotal)
        if self.cart:
            disc = sales.cart_discounts(self.cart, self.discount, self.points)
        else:
            disc = {"total": 0.0, "promo_lines": [], "points_value": 0.0}
        t = sales.compute_totals(self.cart, disc["total"])
        parts = [f"🎁 {l['name']}: −{m(l['amount'])}" for l in disc["promo_lines"]]
        if disc["points_value"]:
            parts.append(f"⭐ {self.points:g} نقطة: −{m(disc['points_value'])}")
        self.lbl_promo.setText("\n".join(parts))
        self._update_display(t, disc)
        sym = settings.get("currency_symbol")
        self.lbl_items.setText(str(len(self.cart)))
        self.lbl_sub.setText(m(t["subtotal"]))
        self.lbl_disc.setText(m(t["discount"]))
        self.lbl_tax.setText(m(t["tax"]) if settings.get_bool("vat_enabled") else "—")
        self.lbl_total.setText(f"{m(t['total'])} {sym}")
        return t

    def on_cart_edit(self, item):
        if self._rendering:
            return
        r, c = item.row(), item.column()
        if r >= len(self.cart):
            return
        from core.utils import to_float
        val = to_float(item.text(), -1)
        it = self.cart[r]
        if c == COL_QTY:
            if val <= 0:
                self.show_flash("كمية غير صحيحة", "err")
            else:
                if self._stock_ok(it, self._base_in_cart(it["product_id"], exclude=r) + val * it.get("factor", 1)):
                    it["quantity"] = round_qty(val)
        elif c == COL_PRICE:
            if val < 0:
                self.show_flash("سعر غير صحيح", "err")
            elif money(val) != money(it["unit_price"]):
                if require_permission(self, "price_override"):
                    it["unit_price"] = money(val)
        QTimer.singleShot(0, lambda: self.render_cart(select=r))

    def selected_index(self):
        rows = self.cart_table.selectionModel().selectedRows()
        if rows:
            return rows[0].row()
        return len(self.cart) - 1 if self.cart else None

    def bump_selected(self, delta):
        idx = self.selected_index()
        if idx is None:
            return
        it = self.cart[idx]
        new = round_qty(it["quantity"] + delta)
        if new <= 0:
            self.remove_selected()
            return
        if delta > 0 and not self._stock_ok(it, self._base_in_cart(it["product_id"]) + delta * it.get("factor", 1)):
            return
        it["quantity"] = new
        self.render_cart(select=idx)

    def change_qty(self):
        idx = self.selected_index()
        if idx is None:
            return
        self.cart_table.setCurrentCell(idx, COL_QTY)
        self.cart_table.setFocus()
        self.cart_table.editItem(self.cart_table.item(idx, COL_QTY))

    def change_price(self):
        idx = self.selected_index()
        if idx is None:
            return
        if not require_permission(self, "price_override"):
            return
        it = self.cart[idx]
        val, ok = QInputDialog.getDouble(self, "تغيير السعر", f"السعر الجديد لـ {it['product_name']}:",
                                         it["unit_price"], 0, 10_000_000, 2)
        if ok:
            it["unit_price"] = money(val)
            self.render_cart(select=idx)

    def remove_selected(self):
        idx = self.selected_index()
        if idx is not None and idx < len(self.cart):
            name = self.cart[idx]["product_name"]
            del self.cart[idx]
            self.render_cart(select=min(idx, len(self.cart) - 1))
            self.show_flash(f"تم حذف {name}", "info")

    def clear_cart(self):
        self.cart = []
        self.discount = 0.0
        self.points = 0.0
        self.set_customer(None)
        self.render_cart()

    def clear_confirm(self):
        if self.cart and ask(self, "تفريغ السلة بالكامل؟"):
            self.clear_cart()
        self.focus_search()

    # ------------------------------------------------------------------ عميل / خصم / تعليق
    def set_customer(self, customer):
        if (customer["id"] if customer else None) != (self.customer["id"] if self.customer else None):
            self.points = 0.0
        self.customer = customer
        self._reprice_for_customer()
        if customer:
            bal = customers.balance(customer["id"])
            pts = f" • 🎁 {loyalty.balance(customer['id']):g} نقطة" if loyalty.enabled() else ""
            self.customer_btn.setText(f"👤  {customer['name']}  (رصيده {m(bal)}{pts})")
        else:
            self.customer_btn.setText("👤  زبون نقدي (F4)")
        if hasattr(self, "lbl_promo"):
            self.update_totals()

    def _reprice_for_customer(self):
        """عند اختيار عميل جملة تتحول أسعار الحبة لسعر الجملة، وتعود عند إلغائه (ما لم يُعدَّل السعر يدوياً)"""
        for it in self.cart:
            if float(it.get("factor", 1) or 1) != 1 or money(it["unit_price"]) != money(it["list_price"]):
                continue
            p = products.get_product(it["product_id"])
            if p:
                new = products.price_for(p, self.customer)
                it["unit_price"] = it["list_price"] = new
        if self.cart and hasattr(self, "lbl_promo"):
            self.render_cart()

    def redeem_points(self):
        if not loyalty.enabled():
            self.show_flash("نقاط الولاء غير مفعّلة (الإعدادات ← نقاط الولاء)", "info")
            return
        if not self.customer:
            self.show_flash("اختر العميل أولاً (F4) لاستبدال نقاطه", "err")
            return
        if not self.cart:
            return
        have = loyalty.balance(self.customer["id"])
        min_pts = settings.get_float("loyalty_min_redeem", 0)
        if have < min_pts or have <= 0:
            self.show_flash(f"رصيد العميل {have:g} نقطة؛ أقل استبدال {min_pts:g}", "info")
            return
        per_point = settings.get_float("loyalty_point_value", 0.05) or 0.05
        subtotal = sales.compute_totals(self.cart)["subtotal"]
        max_pts = float(int(min(have, (subtotal - self.discount) / per_point)))
        if max_pts < min_pts:
            self.show_flash("قيمة الفاتورة أقل من قيمة أقل استبدال للنقاط", "info")
            return
        val, ok = QInputDialog.getDouble(self, "استبدال نقاط الولاء",
                                         f"رصيد {self.customer['name']}: {have:g} نقطة (النقطة = {per_point:g})\n"
                                         f"عدد النقاط للاستبدال:", max_pts, 0, max_pts, 0)
        if ok:
            self.points = val if val >= min_pts else 0.0
            self.update_totals()
        self.focus_search()

    def price_check(self):
        """فحص سعر صنف بدون إضافته للسلة (سؤال الزبون: بكم هذا؟)"""
        code, ok = QInputDialog.getText(self, "فحص سعر", "امسح الباركود أو اكتب الاسم:")
        if not ok or not code.strip():
            self.focus_search()
            return
        p, _, unit = products.lookup_code(code.strip())
        if not p:
            found = products.get_all_products(search=code.strip())
            p = found[0] if found else None
        if not p:
            self.show_flash("الصنف غير موجود", "err")
        else:
            price = unit["sale_price"] if unit else p["sale_price"]
            name = f"{p['name']} ({unit['name']})" if unit else p["name"]
            self.show_flash(f"🔍 {name}: {m(price)} {settings.get('currency_symbol')} — المتوفر {fmt_qty(p['quantity'])}", "info")
        self.focus_search()

    def pick_customer(self):
        dlg = CustomerPicker(self)
        res = dlg.exec()
        if res == QDialog.Accepted:
            self.set_customer(dlg.selected)
        elif res == 2:
            self.set_customer(None)
        self.focus_search()

    def set_discount(self):
        if not self.cart:
            return
        subtotal = sales.compute_totals(self.cart)["subtotal"]
        dlg = DiscountDialog(self, subtotal, self.discount)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.discount()
            max_pct = settings.get_float("cashier_max_discount_percent", 10)
            if subtotal and d / subtotal * 100 > max_pct + 1e-9 and not require_permission(self, "big_discount"):
                return
            self.discount = d
            self.update_totals()
        self.focus_search()

    def hold(self):
        if not self.cart:
            return
        label, ok = QInputDialog.getText(self, "تعليق الفاتورة", "وصف مختصر (اسم الزبون مثلاً):")
        if not ok:
            return
        sales.hold_cart(self.cart, self.discount, self.customer["id"] if self.customer else None, label)
        self.clear_cart()
        self.show_flash("تم تعليق الفاتورة. استرجعها بـ F7", "info")
        self.focus_search()

    def show_held(self):
        dlg = HeldCartsDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen:
            if self.cart and not ask(self, "السلة الحالية ليست فارغة. هل تريد تعليقها واسترجاع المحددة؟"):
                sales.hold_cart(dlg.chosen["cart"], dlg.chosen.get("discount", 0), dlg.chosen.get("customer_id"))
                return
            if self.cart:
                sales.hold_cart(self.cart, self.discount, self.customer["id"] if self.customer else None, "معلّقة تلقائياً")
            self.cart = dlg.chosen["cart"]
            # تحديث المخزون المتوفر لكل سطر
            for it in self.cart:
                p = products.get_product(it["product_id"])
                it["stock"] = p["quantity"] if p else 0
                it.setdefault("base_name", p["name"] if p else it["product_name"])
                it.setdefault("unit", p["unit"] if p else "")
            self.discount = dlg.chosen.get("discount", 0)
            cid = dlg.chosen.get("customer_id")
            self.set_customer(customers.get_customer(cid) if cid else None)
            self.render_cart()
        self.focus_search()

    def new_product(self, barcode_text=""):
        if not require_permission(self, "inventory"):
            return
        dlg = ProductDialog(self, barcode_text=barcode_text if isinstance(barcode_text, str) else "")
        if dlg.exec() == QDialog.Accepted:
            p = products.get_product(dlg.saved_id)
            self.load_favorites()
            if p["quantity"] > 0 or settings.get_bool("allow_negative_stock"):
                self.add_product(p)
        self.focus_search()

    # ------------------------------------------------------------------ الدفع
    def quick_cash(self):
        if not self.cart:
            return
        t = self.update_totals()
        self.finish_sale({"cash_amount": t["total"], "card_amount": 0.0, "credit_amount": 0.0,
                          "cash_received": t["total"], "change": 0.0}, print_it=settings.get_bool("auto_print_receipt"))

    def checkout(self):
        if not self.cart:
            self.show_flash("السلة فارغة", "err")
            return
        t = self.update_totals()
        dlg = PaymentDialog(self, t["total"], self.customer)
        if dlg.exec() == QDialog.Accepted and dlg.result_data:
            self.finish_sale(dlg.result_data, print_it=dlg.print_chk.isChecked())
        else:
            self.focus_search()

    def finish_sale(self, pay, print_it=False):
        shift_id, ok = ensure_shift(self)
        if not ok:
            return
        cid = self.customer["id"] if self.customer else None
        kwargs = dict(discount=self.discount, customer_id=cid, cash_amount=pay["cash_amount"],
                      card_amount=pay["card_amount"], credit_amount=pay["credit_amount"],
                      cash_received=pay["cash_received"], shift_id=shift_id, points_redeemed=self.points)
        try:
            try:
                res = sales.create_sale(self.cart, **kwargs)
            except SaleError as e:
                if "حد الدين" in str(e) and ask(self, f"{e}\n\nهل تريد المتابعة بإذن المدير؟") \
                        and require_permission(self, "over_credit_limit"):
                    res = sales.create_sale(self.cart, allow_over_limit=True, **kwargs)
                else:
                    raise
        except SaleError as e:
            warn(self, str(e))
            return
        except Exception as e:
            error(self, f"تعذر حفظ الفاتورة:\n{e}")
            return

        self.last_invoice_id = res["invoice_id"]
        if res["cash_amount"] > 0 and settings.get_bool("drawer_on_cash_sale"):
            self.open_drawer(silent=True)
        if res["credit_amount"]:
            msg = f"✓ {res['invoice_number']}\nدين على العميل: {m(res['credit_amount'])}"
        else:
            msg = f"✓ {res['invoice_number']}\nالباقي للزبون: {m(res['change'])}"
        if res.get("points_earned"):
            msg += f"\n🎁 +{res['points_earned']:g} نقطة"
        self.lbl_change.setText(msg)
        from ui import customer_display
        try:
            d = customer_display.get()
            if d:
                d.show_paid(res["total"], res["change"], res.get("points_earned") or 0)
        except Exception:
            pass
        self.clear_cart()
        if print_it:
            try:
                printing.print_html(self, receipts.invoice_html(res["invoice_id"]))
            except Exception as e:
                warn(self, f"تم حفظ الفاتورة لكن تعذرت الطباعة:\n{e}")
        self.sale_completed.emit()
        self.focus_search()

    def open_drawer(self, silent=False, reason="فتح يدوي"):
        if not silent and not require_permission(self, "cash"):
            return
        try:
            if drawer.open_drawer():
                if not silent:
                    audit.log("فتح درج النقود", reason)
            elif not silent:
                self.show_flash("لم يُعرَّف درج نقود لهذا الجهاز (الإعدادات ← الطباعة والدرج)", "info")
        except drawer.DrawerError as e:
            self.show_flash(f"⚠ {e}", "err")

    def reprint_last(self):
        if self.last_invoice_id:
            printing.print_html(self, receipts.invoice_html(self.last_invoice_id, copy=True), preview=True)
        else:
            self.show_flash("لا توجد فاتورة سابقة في هذه الجلسة", "info")
