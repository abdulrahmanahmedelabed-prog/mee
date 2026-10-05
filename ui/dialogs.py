# -*- coding: utf-8 -*-
"""نوافذ مشتركة: الدخول، كلمة المرور، فتح الوردية، العملاء، المنتجات، عدّ النقود"""

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QLabel, QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QTextEdit,
    QGridLayout, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit
)

from core import auth, settings, customers, products, shifts
from core.barcode import internal_barcode
from core.utils import money, fmt_money, fmt_qty, to_float
from ui.widgets import MoneySpin, ok_cancel, warn, error, info, Table, title, hint, button, qty_cell, m


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("تسجيل الدخول")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(10)
        from core import branding
        pm = branding.logo_pixmap(96)
        if pm:                                     # شعار المحل أعلى شاشة الدخول
            logo = QLabel()
            logo.setPixmap(pm)
            logo.setAlignment(Qt.AlignCenter)
            lay.addWidget(logo)
        head = QLabel(settings.get('shop_name') if pm else f"🏪  {settings.get('shop_name')}")
        head.setObjectName("titleLabel")
        head.setAlignment(Qt.AlignCenter)
        lay.addWidget(head)
        lay.addWidget(hint("مرحباً بك، سجّل دخولك للبدء"), alignment=Qt.AlignCenter)
        form = QFormLayout()
        self.user = QLineEdit()
        self.user.setPlaceholderText("اسم المستخدم")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("كلمة المرور")
        self.pw.returnPressed.connect(self.try_login)
        self.user.returnPressed.connect(self.pw.setFocus)
        form.addRow("المستخدم:", self.user)
        form.addRow("كلمة المرور:", self.pw)
        lay.addLayout(form)
        self.msg = QLabel("")
        self.msg.setStyleSheet("color:#DC2626;")
        lay.addWidget(self.msg)
        btn = button("دخول", slot=self.try_login)
        btn.setMinimumHeight(42)
        lay.addWidget(btn)
        from core import remote, config, i18n
        lang = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            lang.addItem(name, code)
        lang.setCurrentIndex(max(0, lang.findData(config.get("language") or "ar")))
        lang.currentIndexChanged.connect(lambda _: self.change_language(lang.currentData()))
        lay.addWidget(lang, alignment=Qt.AlignCenter)
        forgot = button("نسيت كلمة المرور؟", "ghostBtn", self.forgot)
        lay.addWidget(forgot, alignment=Qt.AlignCenter)
        if remote.is_client():
            lay.addWidget(hint(f"نقطة بيع فرعية «{config.get('terminal_name')}» متصلة بالجهاز الرئيسي "
                               f"{config.get('server_host')}"))
        elif auth.authenticate("admin", "admin"):
            lay.addWidget(hint("أول تشغيل: المستخدم admin وكلمة المرور admin (سيُطلب تغييرها)"))
        self.user.setFocus()

    def forgot(self):
        ResetPasswordDialog(self).exec()

    def change_language(self, code):
        """تُطبَّق اللغة فوراً: تُعاد شاشة الدخول باللغة الجديدة (انظر run_login)"""
        from core import config
        from PySide6.QtWidgets import QApplication
        from ui import i18n_qt, theme
        config.save({"language": code})
        app = QApplication.instance()
        i18n_qt.apply_language(code, app)
        app.setLayoutDirection(i18n_qt.direction())
        theme.apply(app)
        self.relang = True
        self.done(QDialog.Rejected)

    @staticmethod
    def run_login():
        """شاشة الدخول؛ تُعاد فوراً عند تغيير اللغة منها. ترجع True عند نجاح الدخول"""
        while True:
            dlg = LoginDialog()
            ok = dlg.exec() == QDialog.Accepted
            if not getattr(dlg, "relang", False):
                return ok

    def try_login(self):
        if auth.login(self.user.text(), self.pw.text()):
            self.accept()
        else:
            from core import remote
            err = remote.CLIENT.last_error if remote.is_client() else None
            self.msg.setText(err or "اسم المستخدم أو كلمة المرور غير صحيحة")
            self.pw.selectAll()
            self.pw.setFocus()


class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None, user_id=None, forced=False):
        super().__init__(parent)
        self.user_id = user_id or auth.current_user_id()
        self.setWindowTitle("تغيير كلمة المرور")
        lay = QFormLayout(self)
        if forced:
            lay.addRow(QLabel("لحماية بياناتك، يرجى تعيين كلمة مرور جديدة."))
        self.p1 = QLineEdit()
        self.p2 = QLineEdit()
        for p in (self.p1, self.p2):
            p.setEchoMode(QLineEdit.Password)
        lay.addRow("كلمة المرور الجديدة:", self.p1)
        lay.addRow("تأكيد كلمة المرور:", self.p2)
        ok_cancel(self, lay)

    def accept(self):
        if self.p1.text() != self.p2.text():
            warn(self, "كلمتا المرور غير متطابقتين")
            return
        try:
            auth.change_password(self.user_id, self.p1.text())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class OpenShiftDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("فتح وردية جديدة")
        lay = QFormLayout(self)
        lay.addRow(QLabel("أدخل المبلغ الموجود في الصندوق الآن (الفكّة):"))
        self.amount = MoneySpin(big=True)
        lay.addRow("الرصيد الافتتاحي:", self.amount)
        ok_cancel(self, lay, "فتح الوردية")
        self.amount.setFocus()

    def accept(self):
        try:
            shifts.open_shift(self.amount.value())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


def ensure_shift(parent):
    """يرجع رقم الوردية المفتوحة، ويطلب فتح وردية إذا كانت مطلوبة في الإعدادات"""
    sid = shifts.current_shift_id()
    if sid or not settings.get_bool("require_shift"):
        return sid or None, True
    dlg = OpenShiftDialog(parent)
    if dlg.exec() == QDialog.Accepted:
        return shifts.current_shift_id(), True
    return None, False


class CashCountDialog(QDialog):
    """عدّ النقود بالفئات عند إغلاق الوردية"""
    DENOMS = [200, 100, 50, 20, 10, 5, 2, 1, 0.5, 0.1]

    def __init__(self, parent=None, expected=None):
        super().__init__(parent)
        self.setWindowTitle("إغلاق الوردية - عدّ النقود")
        lay = QVBoxLayout(self)
        lay.addWidget(hint("أدخل عدد كل فئة من النقود الموجودة في الصندوق، أو اكتب المجموع مباشرة."))
        grid = QGridLayout()
        self.spins = []
        for i, d in enumerate(self.DENOMS):
            s = QSpinBox()
            s.setMaximum(100000)
            s.valueChanged.connect(self.recalc)
            grid.addWidget(QLabel(f"فئة {d:g}"), i // 2, (i % 2) * 2)
            grid.addWidget(s, i // 2, (i % 2) * 2 + 1)
            self.spins.append((d, s))
        lay.addLayout(grid)
        form = QFormLayout()
        self.total = MoneySpin(big=True)
        form.addRow("المجموع المعدود:", self.total)
        self.expected = expected
        self.diff = QLabel("")
        self.diff.setObjectName("subTitle")
        form.addRow("الفرق:", self.diff)
        self.note = QLineEdit()
        form.addRow("ملاحظة:", self.note)
        lay.addLayout(form)
        self.total.valueChanged.connect(self.show_diff)
        bb = ok_cancel(self, lay, "إغلاق الوردية")
        self.show_diff()

    def recalc(self):
        self.total.setValue(sum(d * s.value() for d, s in self.spins))

    def show_diff(self):
        if self.expected is None:
            return
        d = money(self.total.value() - self.expected)
        label = "مطابق ✓" if abs(d) < 0.01 else ("زيادة" if d > 0 else "عجز")
        color = "#16A34A" if abs(d) < 0.01 else ("#D97706" if d > 0 else "#DC2626")
        self.diff.setText(f"{m(d)}  ({label})  — المتوقع {m(self.expected)}")
        self.diff.setStyleSheet(f"color:{color};")


# ---------------------------------------------------------------------------
# العملاء
# ---------------------------------------------------------------------------

class CustomerDialog(QDialog):
    def __init__(self, parent=None, customer=None):
        super().__init__(parent)
        self.customer = customer
        self.setWindowTitle("تعديل عميل" if customer else "عميل جديد")
        self.setMinimumWidth(420)
        lay = QFormLayout(self)
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("05xxxxxxxx")
        self.address = QLineEdit()
        self.limit = MoneySpin()
        self.limit.setToolTip("0 = بدون حد")
        self.opening = MoneySpin()
        self.notes = QLineEdit()
        self.level = QComboBox()
        for k, v in customers.PRICE_LEVELS.items():
            self.level.addItem(v, k)
        lay.addRow("الاسم:", self.name)
        lay.addRow("الهاتف:", self.phone)
        lay.addRow("العنوان:", self.address)
        lay.addRow("حد الدين المسموح:", self.limit)
        lay.addRow("", hint("0 = بدون حد. عند التجاوز يُطلب إذن المدير."))
        lay.addRow("مستوى السعر:", self.level)
        if not customer:
            lay.addRow("دين سابق (إن وجد):", self.opening)
        lay.addRow("ملاحظات:", self.notes)
        if customer:
            self.name.setText(customer["name"])
            self.phone.setText(customer["phone"] or "")
            self.address.setText(customer["address"] or "")
            self.limit.setValue(customer["credit_limit"] or 0)
            self.notes.setText(customer["notes"] or "")
            self.level.setCurrentIndex(max(0, self.level.findData(customer["price_level"] or "retail")))
        ok_cancel(self, lay)
        self.new_id = None

    def accept(self):
        try:
            if self.customer:
                customers.update_customer(self.customer["id"], self.name.text(), self.phone.text(), self.address.text(),
                                          self.limit.value(), self.notes.text(), self.level.currentData())
            else:
                self.new_id = customers.add_customer(self.name.text(), self.phone.text(), self.address.text(),
                                                     self.limit.value(), self.notes.text(), self.opening.value(),
                                                     self.level.currentData())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class CustomerPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("اختيار عميل")
        self.resize(560, 480)
        self.selected = None
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("ابحث بالاسم أو رقم الهاتف...")
        self.search.textChanged.connect(self.load)
        self.search.returnPressed.connect(self.choose)
        row.addWidget(self.search)
        row.addWidget(button("+ عميل جديد", "successBtn", self.add_new))
        lay.addLayout(row)
        self.table = Table(["الاسم", "الهاتف", "الرصيد المستحق"])
        self.table.doubleClicked.connect(self.choose)
        lay.addWidget(self.table)
        btns = QHBoxLayout()
        btns.addWidget(button("اختيار", slot=self.choose))
        btns.addWidget(button("بدون عميل", "secondaryBtn", self.clear))
        lay.addLayout(btns)
        self.load()
        self.search.setFocus()

    def load(self):
        rows = customers.list_customers(self.search.text().strip() or None)
        self.table.set_rows([[r["name"], r["phone"] or "", float(r["balance_due"])] for r in rows], rows)
        if rows:
            self.table.selectRow(0)

    def choose(self):
        r = self.table.selected_data()
        if r:
            self.selected = r
            self.accept()

    def clear(self):
        self.selected = None
        self.done(2)

    def add_new(self):
        dlg = CustomerDialog(self)
        dlg.name.setText(self.search.text())
        if dlg.exec() == QDialog.Accepted:
            self.selected = customers.get_customer(dlg.new_id)
            self.accept()


# ---------------------------------------------------------------------------
# المنتجات
# ---------------------------------------------------------------------------

class ProductDialog(QDialog):
    def __init__(self, parent=None, product=None, barcode_text=""):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("تعديل منتج" if product else "منتج جديد")
        self.setMinimumWidth(900)
        outer = QHBoxLayout(self)
        lay = QFormLayout()
        outer.addLayout(lay, 1)
        side = QVBoxLayout()
        outer.addLayout(side, 1)
        self.name = QLineEdit()
        self.barcode = QLineEdit(barcode_text)
        self.barcode.setPlaceholderText("امسح الباركود هنا أو اتركه فارغاً")
        bc_row = QHBoxLayout()
        bc_row.addWidget(self.barcode)
        bc_row.addWidget(button("توليد", "secondaryBtn", self.gen_barcode, "توليد باركود داخلي لطباعته كملصق"))
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems([""] + products.get_categories())
        self.unit = QComboBox()
        self.unit.setEditable(True)
        self.unit.addItems(products.UNITS)
        self.cost = MoneySpin(decimals=4)      # تكلفة الحبة بأربع خانات (الكرتونة ÷ عدد الحبات)
        self.price = MoneySpin()
        self.wholesale = MoneySpin()
        self.wholesale.setToolTip("يُطبَّق تلقائياً عند البيع لعميل مستواه «جملة». 0 = نفس سعر البيع")
        self.margin = QLabel("")
        self.margin.setObjectName("hint")
        self.qty = MoneySpin(decimals=3)
        self.min_qty = MoneySpin(decimals=3)
        self.weighted = QCheckBox("منتج يُباع بالوزن (ميزان)")
        self.plu = QLineEdit()
        self.plu.setPlaceholderText("رمز الصنف على الميزان، مثل 123")
        self.fav = QCheckBox("زر سريع في شاشة البيع (للخبز والخضار وما لا باركود له)")

        lay.addRow("اسم المنتج:", self.name)
        lay.addRow("الباركود:", bc_row)
        lay.addRow("الفئة:", self.category)
        lay.addRow("الوحدة:", self.unit)
        lay.addRow("سعر التكلفة:", self.cost)
        lay.addRow("سعر البيع:", self.price)
        lay.addRow("", self.margin)
        lay.addRow("سعر الجملة (اختياري):", self.wholesale)
        if not product:
            lay.addRow("الكمية الافتتاحية:", self.qty)
        lay.addRow("حد التنبيه (نواقص):", self.min_qty)
        lay.addRow("", self.weighted)
        lay.addRow("رمز الميزان PLU:", self.plu)
        lay.addRow("", self.fav)

        # ---- وحدات بيع إضافية (كرتونة، علبة 6...)
        side.addWidget(title("وحدات بيع إضافية", "subTitle"))
        side.addWidget(hint("مثال: كرتونة = 24 حبة بسعر 60 وباركود خاص بها. عند مسح باركود الكرتونة تُباع كاملة "
                            "ويُخصم 24 من المخزون. ويمكن تبديل وحدة أي سطر في البيع بـ F5."))
        self.units = QTableWidget(0, 4)
        self.units.setHorizontalHeaderLabels(["الوحدة", "عدد الحبات فيها", "الباركود", "سعر البيع"])
        self.units.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.units.verticalHeader().setVisible(False)
        self.units.setMinimumHeight(150)
        side.addWidget(self.units)
        urow = QHBoxLayout()
        urow.addWidget(button("+ إضافة وحدة", "secondaryBtn", lambda: self.add_unit_row()))
        urow.addWidget(button("حذف الوحدة المحددة", "secondaryBtn", self.remove_unit_row))
        urow.addStretch()
        side.addLayout(urow)
        if not product:
            side.addWidget(title("الصلاحية", "subTitle"))
            self.track_expiry = QCheckBox("للكمية الافتتاحية تاريخ صلاحية")
            self.expiry = QDateEdit(calendarPopup=True)
            self.expiry.setDisplayFormat("yyyy-MM-dd")
            self.expiry.setDate(QDate.currentDate().addMonths(6))
            self.expiry.setEnabled(False)
            self.track_expiry.toggled.connect(self.expiry.setEnabled)
            side.addWidget(self.track_expiry)
            side.addWidget(self.expiry)
            side.addWidget(hint("تواريخ صلاحية البضاعة الجديدة تُدخل مع فاتورة المشتريات أو عند إضافة كمية."))
        side.addStretch()
        if product:
            for u in products.get_units(product["id"]):
                self.add_unit_row(u)

        self.cost.valueChanged.connect(self.update_margin)
        self.price.valueChanged.connect(self.update_margin)
        self.weighted.toggled.connect(self.plu.setEnabled)
        self.plu.setEnabled(False)

        if product:
            self.name.setText(product["name"])
            self.barcode.setText(product["barcode"] or "")
            self.category.setCurrentText(product["category"] or "")
            self.unit.setCurrentText(product["unit"] or "قطعة")
            self.cost.setValue(product["cost_price"])
            self.price.setValue(product["sale_price"])
            self.wholesale.setValue(product["wholesale_price"] or 0)
            self.min_qty.setValue(product["min_quantity"])
            self.weighted.setChecked(bool(product["is_weighted"]))
            self.plu.setText(product["plu_code"] or "")
            self.fav.setChecked(bool(product["is_favorite"]))
        ok_cancel(self, side)
        self.saved_id = None
        (self.name if barcode_text or product else self.barcode).setFocus()
        self.update_margin()

    def update_margin(self):
        c, p = self.cost.value(), self.price.value()
        if p > 0:
            pct = (p - c) / p * 100
            color = "#DC2626" if p < c else "#16A34A"
            self.margin.setText(f"الربح في القطعة: {m(p - c)}  |  هامش الربح: {pct:.1f}%")
            self.margin.setStyleSheet(f"color:{color};")
        else:
            self.margin.setText("")

    def gen_barcode(self):
        self.barcode.setText(products.next_internal_barcode(self.product["id"] if self.product else None))

    def add_unit_row(self, u=None):
        r = self.units.rowCount()
        self.units.insertRow(r)
        vals = [u["name"], fmt_qty(u["factor"]), u["barcode"] or "", f"{u['sale_price']:.2f}"] if u else \
            ["كرتونة", "", "", ""]
        for c, v in enumerate(vals):
            self.units.setItem(r, c, QTableWidgetItem(v))

    def remove_unit_row(self):
        r = self.units.currentRow()
        if r >= 0:
            self.units.removeRow(r)

    def units_data(self):
        out = []
        for r in range(self.units.rowCount()):
            cell = lambda c: (self.units.item(r, c).text().strip() if self.units.item(r, c) else "")
            if not cell(0) and not cell(1):
                continue
            out.append({"name": cell(0), "factor": to_float(cell(1)), "barcode": cell(2), "sale_price": to_float(cell(3))})
        return out

    def accept(self):
        if self.price.value() < self.cost.value() and self.price.value() > 0:
            from ui.widgets import ask
            if not ask(self, "سعر البيع أقل من سعر التكلفة! هل تريد المتابعة؟"):
                return
        try:
            args = dict(name=self.name.text(), barcode=self.barcode.text(), category=self.category.currentText(),
                        cost_price=self.cost.value(), sale_price=self.price.value(), min_quantity=self.min_qty.value(),
                        unit=self.unit.currentText(), plu_code=self.plu.text() if self.weighted.isChecked() else None,
                        is_weighted=self.weighted.isChecked(), is_favorite=self.fav.isChecked(),
                        wholesale_price=self.wholesale.value())
            if self.product:
                products.update_product(self.product["id"], **args)
                self.saved_id = self.product["id"]
            else:
                expiry = self.expiry.date().toString("yyyy-MM-dd") if self.track_expiry.isChecked() else None
                self.saved_id = products.add_product(quantity=self.qty.value(), opening_expiry=expiry, **args)
                self.product = products.get_product(self.saved_id)  # حتى لا يُكرَّر المنتج إذا فشل حفظ الوحدات
            products.set_units(self.saved_id, self.units_data())
        except ValueError as e:
            warn(self, str(e))
            return
        except Exception as e:
            error(self, e)
            return
        super().accept()


class ProductPicker(QDialog):
    """اختيار منتج بالبحث (للمشتريات والتقارير)"""

    def __init__(self, parent=None, text=""):
        super().__init__(parent)
        self.setWindowTitle("اختيار منتج")
        self.resize(640, 480)
        self.selected = None
        lay = QVBoxLayout(self)
        self.search = QLineEdit(text)
        self.search.setPlaceholderText("ابحث بالاسم أو الباركود...")
        self.search.textChanged.connect(self.load)
        self.search.returnPressed.connect(self.choose)
        lay.addWidget(self.search)
        self.table = Table(["المنتج", "الباركود", "التكلفة", "البيع", "الكمية"])
        self.table.doubleClicked.connect(self.choose)
        lay.addWidget(self.table)
        lay.addWidget(button("اختيار", slot=self.choose))
        self.load()

    def load(self):
        rows = products.get_all_products(search=self.search.text().strip() or None)[:300]
        self.table.set_rows([[r["name"], r["barcode"] or "", float(r["cost_price"]), float(r["sale_price"]),
                              qty_cell(r["quantity"])] for r in rows], rows)
        if rows:
            self.table.selectRow(0)

    def choose(self):
        r = self.table.selected_data()
        if r:
            self.selected = r
            self.accept()


class TextDialog(QDialog):
    """عرض نص قابل للنسخ (مثل رسالة تذكير واتساب)"""

    def __init__(self, parent, title_text, text):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.resize(460, 280)
        lay = QVBoxLayout(self)
        self.edit = QTextEdit()
        self.edit.setPlainText(text)
        lay.addWidget(self.edit)
        row = QHBoxLayout()
        row.addWidget(button("نسخ النص", slot=self.copy))
        row.addWidget(button("إغلاق", "secondaryBtn", self.accept))
        lay.addLayout(row)

    def copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.edit.toPlainText())
        self.accept()


class NetworkDialog(QDialog):
    """إعداد هذا الجهاز: مستقل، جهاز رئيسي (خادم)، أو نقطة بيع فرعية"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from core import config
        self.setWindowTitle("الشبكة ونقاط البيع المتعددة")
        self.setMinimumWidth(560)
        cfg = config.load()
        lay = QVBoxLayout(self)
        lay.addWidget(hint("لتشغيل أكثر من كاشير: اجعل جهازاً واحداً (رئيسي) يحفظ البيانات، وبقية الأجهزة (فرعية) "
                           "تتصل به عبر شبكة المحل (نفس الراوتر). لا حاجة للإنترنت."))
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("جهاز واحد مستقل", config.MODE_STANDALONE)
        self.mode.addItem("جهاز رئيسي (يحفظ البيانات ويخدم الأجهزة الأخرى)", config.MODE_SERVER)
        self.mode.addItem("نقطة بيع فرعية (تتصل بالجهاز الرئيسي)", config.MODE_CLIENT)
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg["mode"])))
        self.terminal = QLineEdit(cfg["terminal_name"])
        self.terminal.setPlaceholderText("مثال: كاشير 1")
        form.addRow("وضع هذا الجهاز:", self.mode)
        form.addRow("اسم هذا الجهاز:", self.terminal)
        self.host = QLineEdit(cfg["server_host"])
        self.host.setPlaceholderText("عنوان IP للجهاز الرئيسي، مثل 192.168.1.10")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(cfg["server_port"]))
        self.code = QLineEdit(cfg["link_code"])
        self.code.setPlaceholderText("الرمز الظاهر في الجهاز الرئيسي")
        form.addRow("عنوان الجهاز الرئيسي:", self.host)
        form.addRow("المنفذ:", self.port)
        form.addRow("رمز الربط:", self.code)
        lay.addLayout(form)
        self.server_info = QLabel()
        self.server_info.setObjectName("chipOk")
        self.server_info.setWordWrap(True)
        lay.addWidget(self.server_info)
        row = QHBoxLayout()
        self.test_btn = button("🔌 اختبار الاتصال", "secondaryBtn", self.test)
        row.addWidget(self.test_btn)
        row.addStretch()
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addWidget(hint("بعد الحفظ أعد تشغيل البرنامج. في الجهاز الرئيسي قد يسأل جدار حماية ويندوز عن السماح "
                           "للبرنامج بالاتصال على الشبكة الخاصة: اختر (سماح)."))
        ok_cancel(self, lay, "حفظ")
        self.mode.currentIndexChanged.connect(self.update_state)
        self.update_state()

    def update_state(self):
        from core import config
        mode = self.mode.currentData()
        client = mode == config.MODE_CLIENT
        for w in (self.host, self.test_btn):
            w.setEnabled(client)
        self.code.setReadOnly(not client)
        self.server_info.setVisible(mode == config.MODE_SERVER)
        self.server_info.setText(f"أدخل في كل جهاز فرعي:   العنوان {config.local_ip()}   •   المنفذ {self.port.value()}   •   "
                                 f"رمز الربط {self.code.text()}")

    def test(self):
        from core import remote
        c = remote.Client(self.host.text().strip(), self.port.value(), self.code.text().strip(), self.terminal.text())
        try:
            info_ = c.ping()
            self.status.setText(f"✓ متصل بالجهاز الرئيسي: {info_.get('shop')}")
            self.status.setStyleSheet("color:#16A34A; font-weight:700;")
        except remote.RemoteError as e:
            self.status.setText(f"✗ {e}")
            self.status.setStyleSheet("color:#DC2626; font-weight:700;")

    def accept(self):
        from core import config
        mode = self.mode.currentData()
        if not self.terminal.text().strip():
            warn(self, "أدخل اسماً لهذا الجهاز")
            return
        if mode == config.MODE_CLIENT and (not self.host.text().strip() or not self.code.text().strip()):
            warn(self, "أدخل عنوان الجهاز الرئيسي ورمز الربط")
            return
        config.save({"mode": mode, "terminal_name": self.terminal.text().strip(), "server_host": self.host.text().strip(),
                     "server_port": self.port.value(), "link_code": self.code.text().strip().upper()})
        info(self, "تم الحفظ. أعد تشغيل البرنامج لتطبيق التغيير.")
        super().accept()


class ResetPasswordDialog(QDialog):
    """استعادة دخول المدير برمز من مزوّد البرنامج (لا تُحذف أي بيانات)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from core import license, vendor
        self.setWindowTitle("استعادة كلمة مرور المدير")
        self.setMinimumWidth(460)
        lay = QFormLayout(self)
        try:
            mid = license.machine_id()
        except Exception as e:
            mid = str(e)
        self.mid = mid
        lay.addRow(hint("أرسل رمز الجهاز لمزوّد البرنامج، ويرسل لك رمز استعادة صالحاً 3 أيام."))
        m = QLabel(mid)
        m.setStyleSheet("font-size:18px; font-weight:900; color:#1D4ED8;")
        m.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addRow("رمز الجهاز:", m)
        if vendor.VENDOR_PHONE:
            lay.addRow("", button("📱 طلب رمز عبر واتساب", "successBtn", self.request))
        self.code = QTextEdit()
        self.code.setMaximumHeight(80)
        self.code.setPlaceholderText("الصق رمز الاستعادة هنا (يبدأ بـ SR1.)")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        lay.addRow("رمز الاستعادة:", self.code)
        lay.addRow("كلمة المرور الجديدة:", self.pw)
        ok_cancel(self, lay, "استعادة")

    def request(self):
        from core import vendor, whatsapp, settings
        from ui.widgets import open_whatsapp
        msg = f"طلب رمز استعادة كلمة مرور المدير\nالمحل: {settings.get('shop_name')}\nرمز الجهاز: {self.mid}"
        open_whatsapp(self, whatsapp.link("+" + vendor.VENDOR_PHONE, msg), msg)

    def accept(self):
        from core import license
        try:
            user = license.reset_admin_password(self.code.toPlainText(), self.pw.text())
        except (license.LicenseError, ValueError) as e:
            warn(self, str(e))
            return
        info(self, f"تمت الاستعادة. ادخل باسم المستخدم «{user}» وكلمة المرور الجديدة.")
        super().accept()
