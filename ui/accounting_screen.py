# -*- coding: utf-8 -*-
"""
شاشة المحاسبة: الميزانية العمومية، قائمة الدخل، ميزان المراجعة، دفتر اليومية، كشف أي حساب، القيود اليدوية ودليل الحسابات.
كلها تُبنى تلقائياً من عمليات البرنامج؛ صاحب المحل لا يحتاج كتابة أي قيد إلا للعمليات خارج البيع والشراء.
"""


from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox, QLabel, QGridLayout, QDialog,
                               QFormLayout, QLineEdit, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
                               QAbstractItemView)

from core import ledger, settings, db
from core.utils import money, to_float
from ui import printing
from ui.widgets import CalcDoubleSpinBox
from ui.widgets import (Table, button, page, title, hint, m, card, DateRange, KpiCard, warn, info, ask, MoneySpin,
                        ok_cancel, require_permission)


class TemplateEntryDialog(QDialog):
    """قيد جاهز لغير المحاسب: اختر العملية واكتب المبلغ"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("عملية مالية خارج البيع والشراء")
        self.setMinimumWidth(520)
        lay = QFormLayout(self)
        lay.addRow(hint("استخدم هذه النافذة لتسجيل أموال تدخل أو تخرج من المحل بعيداً عن البيع والشراء والمصاريف "
                        "(رأس مال، إيداع في البنك، شراء معدات، قرض...). البرنامج يكتب القيد المحاسبي بنفسه."))
        self.kind = QComboBox()
        for label, dr, cr in ledger.TEMPLATES:
            self.kind.addItem(label, (dr, cr))
        self.amount = MoneySpin(big=True)
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(QDate.currentDate())
        self.desc = QLineEdit()
        self.desc.setPlaceholderText("بيان إضافي (اختياري)")
        self.preview = hint("")
        lay.addRow("العملية:", self.kind)
        lay.addRow("المبلغ:", self.amount)
        lay.addRow("التاريخ:", self.date)
        lay.addRow("البيان:", self.desc)
        lay.addRow("", self.preview)
        self.kind.currentIndexChanged.connect(self.update_preview)
        self.amount.valueChanged.connect(self.update_preview)
        ok_cancel(self, lay, "تسجيل")
        self.update_preview()

    def update_preview(self):
        dr, cr = self.kind.currentData()
        self.preview.setText(f"القيد: من حـ/ {ledger.account_name(dr)}  ←  إلى حـ/ {ledger.account_name(cr)}  "
                             f"بمبلغ {m(self.amount.value())}")

    def accept(self):
        dr, cr = self.kind.currentData()
        desc = self.kind.currentText() + (f" - {self.desc.text().strip()}" if self.desc.text().strip() else "")
        try:
            ledger.add_manual_entry(self.date.date().toString("yyyy-MM-dd"), desc,
                                    [{"account": dr, "debit": self.amount.value()},
                                     {"account": cr, "credit": self.amount.value()}])
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class JournalEntryDialog(QDialog):
    """قيد يومية حر (للمحاسب): عدة أسطر مدين/دائن"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("قيد يومية يدوي")
        self.resize(760, 460)
        self.accounts = ledger.list_accounts()
        lay = QVBoxLayout(self)
        top = QFormLayout()
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(QDate.currentDate())
        self.desc = QLineEdit()
        top.addRow("التاريخ:", self.date)
        top.addRow("البيان:", self.desc)
        lay.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["الحساب", "مدين", "دائن", "ملاحظة"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self.update_totals)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button("+ سطر", "secondaryBtn", self.add_row))
        row.addWidget(button("حذف السطر", "dangerBtn", self.remove_row))
        row.addStretch()
        self.totals = QLabel("")
        self.totals.setObjectName("subTitle")
        row.addWidget(self.totals)
        lay.addLayout(row)
        ok_cancel(self, lay, "حفظ القيد")
        self.add_row()
        self.add_row()

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        combo = QComboBox()
        for a in self.accounts:
            combo.addItem(f"{a['code']}  {a['name']}", a["code"])
        self.table.setCellWidget(r, 0, combo)
        for c in (1, 2, 3):
            self.table.setItem(r, c, QTableWidgetItem(""))

    def remove_row(self):
        r = self.table.currentRow()
        if r >= 0 and self.table.rowCount() > 2:
            self.table.removeRow(r)
            self.update_totals()

    def lines(self):
        out = []
        for r in range(self.table.rowCount()):
            out.append({"account": self.table.cellWidget(r, 0).currentData(),
                        "debit": to_float(self.table.item(r, 1).text() if self.table.item(r, 1) else "", 0),
                        "credit": to_float(self.table.item(r, 2).text() if self.table.item(r, 2) else "", 0),
                        "note": self.table.item(r, 3).text() if self.table.item(r, 3) else ""})
        return out

    def update_totals(self, *_):
        ls = self.lines() if self.table.rowCount() and self.table.item(self.table.rowCount() - 1, 3) else []
        d, c = money(sum(x["debit"] for x in ls)), money(sum(x["credit"] for x in ls))
        ok = abs(d - c) < 0.01 and d > 0
        self.totals.setText(f"مدين {m(d)}  |  دائن {m(c)}  {'✓ متوازن' if ok else '✗ غير متوازن'}")
        self.totals.setStyleSheet(f"color:{'#16A34A' if ok else '#DC2626'};")

    def accept(self):
        try:
            ledger.add_manual_entry(self.date.date().toString("yyyy-MM-dd"), self.desc.text(), self.lines())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class AccountDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("حساب جديد في دليل الحسابات")
        lay = QFormLayout(self)
        self.code = QLineEdit()
        self.code.setPlaceholderText("4 أرقام، مثل 1520")
        self.name = QLineEdit()
        self.type = QComboBox()
        for k, v in ledger.TYPES.items():
            self.type.addItem(v, k)
        lay.addRow("رقم الحساب:", self.code)
        lay.addRow("اسم الحساب:", self.name)
        lay.addRow("النوع:", self.type)
        lay.addRow("", hint("الرقم الأول: 1 أصول، 2 خصوم، 3 حقوق ملكية، 4 إيرادات، 5-9 مصروفات"))
        ok_cancel(self, lay)

    def accept(self):
        try:
            ledger.add_account(self.code.text(), self.name.text(), self.type.currentData())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class AssetDialog(QDialog):
    """إضافة أصل ثابت: يُحسب إهلاكه شهرياً وحده"""

    def __init__(self, parent):
        super().__init__(parent)
        from core import accountant
        self.setWindowTitle("أصل ثابت جديد")
        lay = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("مثل: ثلاجة عرض، جهاز كاشير، رفوف، سيارة توصيل")
        self.cost = MoneySpin()
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(QDate.currentDate())
        from PySide6.QtWidgets import QDoubleSpinBox
        self.life = CalcDoubleSpinBox()
        self.life.setRange(0.5, 50)
        self.life.setDecimals(1)
        self.life.setValue(5)
        self.life.setSuffix(" سنة")
        self.salvage = MoneySpin()
        self.paid = QComboBox()
        for code, label in accountant.PAY_SOURCES.items():
            self.paid.addItem(label, code)
        lay.addRow("الأصل:", self.name)
        lay.addRow("التكلفة:", self.cost)
        lay.addRow("تاريخ الشراء:", self.date)
        lay.addRow("العمر الإنتاجي:", self.life)
        lay.addRow("قيمته في النهاية (خردة):", self.salvage)
        lay.addRow("طريقة الدفع:", self.paid)
        lay.addRow("", hint("يُحسب الإهلاك شهرياً بالقسط الثابت ويُسجَّل في الدفاتر تلقائياً.\n"
                            "أثاث ورفوف: 5-10 سنوات • أجهزة وكمبيوتر: 3-5 • ثلاجات: 5-8 • سيارات: 5"))
        ok_cancel(self, lay)

    def accept(self):
        from core import accountant
        try:
            accountant.add_asset(self.name.text(), self.cost.value(), self.date.date().toString("yyyy-MM-dd"),
                                 self.life.value(), self.salvage.value(), self.paid.currentData())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class DisposeDialog(QDialog):
    def __init__(self, parent, asset):
        super().__init__(parent)
        self.asset = asset
        self.setWindowTitle("بيع أو استبعاد أصل")
        lay = QFormLayout(self)
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(QDate.currentDate())
        self.proceeds = MoneySpin()
        self.into = QComboBox()
        for code, label in (("1110", "نقداً في الصندوق"), ("1120", "في البنك"), ("3120", "أخذها المالك")):
            self.into.addItem(label, code)
        lay.addRow("الأصل:", QLabel(asset["name"]))
        lay.addRow("التاريخ:", self.date)
        lay.addRow("ثمن البيع (0 إن تَلِف):", self.proceeds)
        lay.addRow("استُلم الثمن:", self.into)
        lay.addRow("", hint("الفرق بين ثمن البيع وقيمته الدفترية يُسجَّل ربحاً أو خسارة تلقائياً."))
        ok_cancel(self, lay)

    def accept(self):
        from core import accountant
        try:
            accountant.dispose_asset(self.asset["id"], self.date.date().toString("yyyy-MM-dd"), self.proceeds.value(),
                                     self.into.currentData())
        except ValueError as e:
            warn(self, str(e))
            return
        super().accept()


class CloseMonthDialog(QDialog):
    """إقفال الشهر: تدقيق كامل، حزمة القوائم المالية، ثم قفل الدفاتر"""

    def __init__(self, parent):
        super().__init__(parent)
        from core import accountant
        self.setWindowTitle("إقفال الشهر")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        st = accountant.status()
        lay.addWidget(title("✅ إقفال الشهر", "subTitle"))
        lay.addWidget(hint("ما يفعله المحاسب والمدقق في نهاية كل شهر، بضغطة واحدة:\n"
                           "1) تدقيق كامل لكل عمليات الشهر  2) قائمة الدخل والميزانية والتدفقات النقدية وإقرار الضريبة "
                           "للطباعة  3) قفل الدفاتر حتى نهاية الشهر فلا يُضاف أو يُحذف شيء بتاريخ قديم."))
        row = QHBoxLayout()
        row.addWidget(QLabel("الشهر:"))
        self.month = QComboBox()
        for y, mth in reversed(st["pending"]):            # الأحدث أولاً؛ اختيار شهر يُقفل كل ما قبله أيضاً
            self.month.addItem(f"{y}-{mth:02d}", (y, mth))
        row.addWidget(self.month, 1)
        lay.addLayout(row)
        if len(st["pending"]) > 1:
            lay.addWidget(hint(f"{len(st['pending'])} شهراً بانتظار الإقفال: اختيار شهر يُقفل كل الأشهر التي قبله معه."))
        self.state = QLabel(f"الدفاتر مقفلة حتى: {st['locked_until'] or 'لم تُقفل بعد'}")
        self.state.setObjectName("hint")
        lay.addWidget(self.state)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        lay.addWidget(self.result)
        btns = QHBoxLayout()
        self.go = button("🔎 دقّق وأقفل", "successBtn", self.run)
        self.go.setEnabled(self.month.count() > 0)
        btns.addWidget(self.go)
        if st["locked_until"]:
            btns.addWidget(button("🔓 فتح آخر شهر مقفل", "secondaryBtn", self.reopen))
        btns.addStretch()
        btns.addWidget(button("إغلاق", "secondaryBtn", self.reject))
        lay.addLayout(btns)
        if not self.month.count():
            self.result.setText("لا توجد أشهر منتهية تنتظر الإقفال. 👍")

    def run(self):
        from core import accountant
        y, mth = self.month.currentData()
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = accountant.close_month(y, mth)
        except ValueError as e:
            QApplication.restoreOverrideCursor()
            warn(self, str(e))
            return
        QApplication.restoreOverrideCursor()
        r = res["audit"]
        if not res["closed"]:
            crit = [f for f in r["findings"] if f["severity"] == "critical"]
            msg = "المدقق وجد ملاحظات حرجة في هذا الشهر:\n" + "\n".join(f"• {f['title']}" for f in crit[:6]) + \
                  "\n\nالأفضل معالجتها أولاً (التدقيق المالي يشرح كل واحدة). هل تريد الإقفال رغم ذلك؟"
            if not ask(self, msg):
                return
            res = accountant.close_month(y, mth, force=True)
        a, b = res["date_from"], res["date_to"]
        self.result.setText(f"✓ أُقفلت الدفاتر حتى {b}. رأي المدقق: {r['opinion']} — الدرجة {r['score']}/100.")
        html = accountant.package_html(a, b, r, settings.get("shop_name"))
        printing.print_html(self, html, width_mm=210, preview=True)
        self.accept()

    def reopen(self):
        from core import accountant, auth
        lock = accountant.locked_until()
        if not lock or not ask(self, f"فتح الشهر المقفل الأخير (حتى {lock})؟ يُسجَّل ذلك في سجل العمليات."):
            return
        d = QDate.fromString(lock, "yyyy-MM-dd")
        prev_end = QDate(d.year(), d.month(), 1).addDays(-1).toString("yyyy-MM-dd")
        accountant.unlock_books(prev_end if prev_end >= "2000" else None)
        info(self, "فُتح الشهر. أقفله من جديد بعد التصحيح.")
        self.reject()


class AccountingScreen(QWidget):
    KEEP_ON_THEME = True          # تبديل السمة يعيد تلوينها دون إعادة الحساب
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        self.range = DateRange("هذه السنة")
        self.range.changed.connect(self.load)
        head.addWidget(self.range)
        from PySide6.QtWidgets import QCheckBox
        self.per_invoice = QCheckBox("تفصيل كل فاتورة")
        self.per_invoice.setToolTip("بدون العلامة: قيد مبيعات واحد لكل يوم (أوضح وأسرع). مع العلامة: قيد لكل فاتورة")
        self.per_invoice.toggled.connect(self.load)
        head.addWidget(self.per_invoice)
        head.addStretch()
        head.addWidget(button("➕ عملية مالية", "successBtn", self.template_entry,
                              "رأس مال، إيداع وسحب من البنك، قرض، شراء معدات، تسوية الضريبة..."))
        head.addWidget(button("📤 تصدير", "secondaryBtn", self.export_current))
        head.addWidget(button("🖨 طباعة", "secondaryBtn", self.print_current))
        lay.addLayout(head)
        row2 = QHBoxLayout()
        self.lock_lbl = QLabel("")
        self.lock_lbl.setObjectName("hint")
        row2.addWidget(self.lock_lbl)
        row2.addStretch()
        row2.addWidget(button("✅ إقفال الشهر", "secondaryBtn", self.close_month,
                              "تدقيق الشهر كاملاً، طباعة القوائم المالية، وقفل الدفاتر حتى نهايته"))
        lay.addLayout(row2)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(lambda _: self.load())
        lay.addWidget(self.tabs, 1)
        self.tables = {}

        # 1) الميزانية العمومية
        bs = QWidget()
        bl = QVBoxLayout(bs)
        bl.setContentsMargins(0, 10, 0, 0)
        g = QGridLayout()
        self.k_assets = KpiCard("ما يملكه المحل (الأصول)", "#2563EB", "🏦")
        self.k_liab = KpiCard("ما على المحل (الالتزامات)", "#DC2626", "📕")
        self.k_worth = KpiCard("صافي حق المالك", "#16A34A", "💎")
        for i, k in enumerate((self.k_assets, self.k_liab, self.k_worth)):
            g.addWidget(k, 0, i)
        bl.addLayout(g)
        self.bs_table = Table(["البند", "رقم الحساب", "المبلغ"], stretch=0, sortable=False)
        bl.addWidget(self.bs_table, 1)
        self.bs_note = hint("")
        bl.addWidget(self.bs_note)
        self._add_tab(bs, "الميزانية العمومية", self.bs_table)

        # 2) قائمة الدخل (مع المقارنة بالفترة السابقة)
        self.is_table = Table(["البند", "المبلغ", "الفترة السابقة", "التغير"], stretch=0, sortable=False)
        self._add_tab(self.is_table, "قائمة الدخل", self.is_table)

        # 2.2) المؤشرات المالية
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setContentsMargins(0, 10, 0, 0)
        self.ratio_sum = QLabel("")
        self.ratio_sum.setObjectName("subTitle")
        rl.addWidget(self.ratio_sum)
        self.ratio_table = Table(["", "المؤشر", "القيمة", "ماذا يعني"], stretch=3, sortable=False)
        self.ratio_table.setWordWrap(True)
        rl.addWidget(self.ratio_table, 1)
        rl.addWidget(hint("المؤشرات تُحسب للفترة المختارة أعلاه من الدفاتر نفسها. 🟢 جيد • 🟡 انتبه • 🔴 يحتاج معالجة."))
        self._add_tab(rw, "المؤشرات المالية", self.ratio_table)

        # 2.5) قائمة التدفقات النقدية
        cfw = QWidget()
        cfl = QVBoxLayout(cfw)
        cfl.setContentsMargins(0, 10, 0, 0)
        self.cf_table = Table(["البند", "المبلغ"], stretch=0, sortable=False)
        cfl.addWidget(self.cf_table, 1)
        self.cf_note = hint("")
        cfl.addWidget(self.cf_note)
        self._add_tab(cfw, "التدفقات النقدية", self.cf_table)

        # 3) ميزان المراجعة
        tb = QWidget()
        tl = QVBoxLayout(tb)
        tl.setContentsMargins(0, 10, 0, 0)
        self.tb_table = Table(["رقم الحساب", "اسم الحساب", "رصيد أول الفترة", "مدين الفترة", "دائن الفترة",
                               "رصيد مدين", "رصيد دائن"], stretch=1, sortable=False)
        self.tb_table.doubleClicked.connect(self.open_account_from_tb)
        tl.addWidget(self.tb_table, 1)
        self.tb_status = QLabel("")
        self.tb_status.setObjectName("subTitle")
        tl.addWidget(self.tb_status)
        tl.addWidget(hint("انقر مرتين على أي حساب لفتح كشفه التفصيلي."))
        self._add_tab(tb, "ميزان المراجعة", self.tb_table)

        # 4) دفتر اليومية
        self.jr_table = Table(["التاريخ", "المرجع", "البيان", "الحساب", "مدين", "دائن"], stretch=2, sortable=False)
        self._add_tab(self.jr_table, "دفتر اليومية", self.jr_table)

        # 5) كشف حساب
        st = QWidget()
        sl = QVBoxLayout(st)
        sl.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("الحساب:"))
        self.acc_combo = QComboBox()
        self.acc_combo.setMinimumWidth(320)
        self.acc_combo.currentIndexChanged.connect(self.load)
        row.addWidget(self.acc_combo)
        row.addStretch()
        self.st_summary = QLabel("")
        self.st_summary.setObjectName("subTitle")
        row.addWidget(self.st_summary)
        sl.addLayout(row)
        self.st_table = Table(["التاريخ", "المرجع", "البيان", "مدين", "دائن", "الرصيد"], stretch=2, sortable=False)
        sl.addWidget(self.st_table, 1)
        self._add_tab(st, "كشف حساب", self.st_table)

        # 6) القيود اليدوية
        mj = QWidget()
        ml = QVBoxLayout(mj)
        ml.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(button("➕ عملية جاهزة", "successBtn", self.template_entry))
        row.addWidget(button("📝 قيد يومية حر (للمحاسب)", "secondaryBtn", self.free_entry))
        row.addWidget(button("🚫 إلغاء القيد المحدد", "dangerBtn", self.void_entry))
        row.addStretch()
        ml.addLayout(row)
        self.mj_table = Table(["الرقم", "التاريخ", "البيان", "المبلغ", "الحالة", "المستخدم"], stretch=2)
        ml.addWidget(self.mj_table, 1)
        self._add_tab(mj, "القيود اليدوية", self.mj_table)

        # 6.2) مطابقة البنك
        bw = QWidget()
        bl2 = QVBoxLayout(bw)
        bl2.setContentsMargins(0, 10, 0, 0)
        bl2.addWidget(hint("اكتب رصيد البنك كما في كشف البنك أو تطبيقه في تاريخ معيّن. يقارنه البرنامج برصيد البنك في الدفاتر، "
                           "ويطرح مبالغ البطاقات والمحافظ التي لم تصل للبنك بعد (تُسوّى عادة في اليوم التالي)، ويبيّن الفرق."))
        frm = QHBoxLayout()
        frm.addWidget(QLabel("التاريخ:"))
        self.rec_date = QDateEdit(calendarPopup=True)
        self.rec_date.setDisplayFormat("yyyy-MM-dd")
        self.rec_date.setDate(QDate.currentDate())
        frm.addWidget(self.rec_date)
        frm.addWidget(QLabel("رصيد كشف البنك:"))
        self.rec_amount = MoneySpin()
        self.rec_amount.setRange(-99999999, 99999999)
        frm.addWidget(self.rec_amount)
        frm.addWidget(button("⚖ طابق", "primaryBtn", self.reconcile))
        frm.addStretch()
        bl2.addLayout(frm)
        self.rec_result = QLabel("")
        self.rec_result.setWordWrap(True)
        self.rec_result.setObjectName("subTitle")
        bl2.addWidget(self.rec_result)
        rb = QHBoxLayout()
        self.rec_save = button("💾 حفظ المطابقة", "secondaryBtn", lambda: self.save_reconcile(False))
        self.rec_fees = button("🏦 تسجيل الفرق عمولات بنكية وحفظ", "secondaryBtn", lambda: self.save_reconcile(True))
        rb.addWidget(self.rec_save)
        rb.addWidget(self.rec_fees)
        rb.addStretch()
        bl2.addLayout(rb)
        self.rec_table = Table(["التاريخ", "الكشف", "الدفاتر", "في الطريق", "الفرق", "حُفظت في"], stretch=0)
        bl2.addWidget(self.rec_table, 1)
        self._add_tab(bw, "مطابقة البنك", self.rec_table)

        # 6.5) الأصول الثابتة والإهلاك التلقائي
        fa = QWidget()
        fl = QVBoxLayout(fa)
        fl.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(button("+ أصل ثابت", "successBtn", self.add_asset))
        row.addWidget(button("💲 بيع/استبعاد الأصل المحدد", "secondaryBtn", self.dispose_asset))
        row.addStretch()
        fl.addLayout(row)
        self.fa_table = Table(["الأصل", "تاريخ الشراء", "التكلفة", "العمر (شهر)", "القسط الشهري", "مجمع الإهلاك",
                               "القيمة الدفترية", "الحالة"], stretch=0)
        fl.addWidget(self.fa_table, 1)
        fl.addWidget(hint("الإهلاك يُحسب ويُسجَّل في الدفاتر تلقائياً آخر كل شهر — لا تحتاج قيداً يدوياً."))
        self._add_tab(fa, "الأصول الثابتة", self.fa_table)

        # 7) دليل الحسابات
        ca = QWidget()
        cl = QVBoxLayout(ca)
        cl.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(button("+ حساب جديد", "successBtn", self.add_account))
        row.addStretch()
        cl.addLayout(row)
        self.ca_table = Table(["رقم الحساب", "اسم الحساب", "النوع", "طبيعة الرصيد"], stretch=1)
        cl.addWidget(self.ca_table, 1)
        cl.addWidget(hint("الحسابات المولّدة تلقائياً: كل مبيعاتك ومشترياتك وديونك ومصاريفك تتحول إلى قيود في هذه "
                          "الحسابات بدون تدخل منك. المصاريف لها حساب فرعي لكل نوع (كهرباء، إيجار...)."))
        self._add_tab(ca, "دليل الحسابات", self.ca_table)

    def open_section(self, name):
        from ui.widgets import select_tab
        select_tab(self.tabs, name)

    def _add_tab(self, widget, name, table):
        self.tabs.blockSignals(True)          # لا تحميل أثناء البناء: refresh() عند فتح الشاشة يحمّل مرة واحدة
        idx = self.tabs.addTab(widget, name)
        self.tabs.blockSignals(False)
        self.tables[idx] = (table, name)

    def refresh(self):
        cur = self.acc_combo.currentData()
        self.acc_combo.blockSignals(True)
        self.acc_combo.clear()
        self.acc_combo.addItem(f"{ledger.EXPENSES}  كل المصاريف التشغيلية", ledger.EXPENSES)
        for a in ledger.list_accounts():
            self.acc_combo.addItem(f"{a['code']}  {a['name']}", a["code"])
        self.acc_combo.setCurrentIndex(max(0, self.acc_combo.findData(cur or ledger.CASH)))
        self.acc_combo.blockSignals(False)
        self.load()

    def load(self):
        a, b = self.range.range()
        name = self.tabs.tabText(self.tabs.currentIndex())
        from core import accountant
        try:
            st = accountant.status()
            lock = st["locked_until"]
            self.lock_lbl.setText(("🔒 " + f"مقفلة حتى {lock}" if lock else "🔓 الدفاتر مفتوحة") +
                                  (f" • {len(st['pending'])} شهر بانتظار الإقفال" if st["pending"] else ""))
        except Exception:
            self.lock_lbl.setText("")
        if name == "الميزانية العمومية":
            bs = ledger.balance_sheet(b)
            self.k_assets.set(m(bs["total_assets"]), f"في {b}")
            self.k_liab.set(m(bs["total_liabilities"]))
            self.k_worth.set(m(bs["net_worth"]), "الأصول − الالتزامات")
            rows, colors = [], []

            def section(label, items, total_label, total):
                rows.append([label, "", ""])
                colors.append("#E2E8F0")
                for x in items:
                    rows.append([f"    {x['name']}", x["code"], float(x["amount"])])
                    colors.append(None)
                rows.append([total_label, "", float(total)])
                colors.append("#EFF6FF")
            section("الأصول (ما يملكه المحل)", bs["assets"], "= مجموع الأصول", bs["total_assets"])
            section("الالتزامات (ما على المحل للغير)", bs["liabilities"], "= مجموع الالتزامات", bs["total_liabilities"])
            section("حقوق الملكية (حق المالك)", bs["equity"], "= مجموع حقوق الملكية", bs["total_equity"])
            rows.append(["= الالتزامات + حقوق الملكية", "", float(money(bs["total_liabilities"] + bs["total_equity"]))])
            colors.append("#DCFCE7" if bs["balanced"] else "#FEE2E2")
            self.bs_table.set_rows(rows, colors=colors)
            from core.i18n import tr
            note = tr("✓ الميزانية متوازنة: الأصول = الالتزامات + حقوق الملكية." if bs["balanced"]
                      else "✗ الميزانية غير متوازنة!")
            if bs["inventory_physical"] is not None and abs(bs["inventory_physical"] - bs["inventory_book"]) >= 0.01:
                note += "  " + tr(f"ملاحظة: قيمة المخزون الفعلية حسب الكميات {m(bs['inventory_physical'])} والدفترية "
                                  f"{m(bs['inventory_book'])} (الفرق من تعديلات التكلفة أو البيع بمخزون سالب).")
            self.bs_note.setText(note)
        elif name == "قائمة الدخل":
            from core import accountant
            cmp_ = accountant.comparative_income(a, b)
            s, p = cmp_["current"], cmp_["previous"]
            pexp = {e["code"]: e["amount"] for e in p["expenses"]}
            rows = [("المبيعات", s["sales"], p["sales"]), ("− مردودات المبيعات", s["returns"], p["returns"]),
                    ("= صافي المبيعات", s["net_sales"], p["net_sales"]), ("− تكلفة البضاعة المباعة", s["cogs"], p["cogs"]),
                    ("= مجمل الربح", s["gross_profit"], p["gross_profit"]),
                    ("+ إيرادات أخرى", s["other_income"], p["other_income"]), ("", None, None)]
            rows += [(f"− {e['name']}", e["amount"], pexp.get(e["code"], 0.0)) for e in s["expenses"]]
            rows += [("= مجموع المصروفات", s["total_expenses"], p["total_expenses"]), ("", None, None),
                     ("= صافي الربح (الدخل)", s["net_income"], p["net_income"])]

            def change(c, v):
                if c is None or v is None or not v:
                    return ""
                return f"{(c / v - 1) * 100:+.1f}%" if v > 0 else ""
            self.is_table.set_rows([[k, float(c) if c is not None else "", float(v) if v is not None else "", change(c, v)]
                                    for k, c, v in rows],
                                   colors=[("#EFF6FF" if k.startswith("=") else None) for k, _, _ in rows])
            self.is_table.setHorizontalHeaderItem(2, QTableWidgetItem(f"{cmp_['prev_from']} → {cmp_['prev_to']}"))
        elif name == "المؤشرات المالية":
            from core import accountant
            r = accountant.ratios(a, b)
            icon = {"good": "🟢", "watch": "🟡", "bad": "🔴"}
            self.ratio_table.set_rows([[icon[x["verdict"]], x["name"], x["display"], x["explain"]] for x in r["items"]],
                                      r["items"])
            self.ratio_table.resizeRowsToContents()
            sm = r["summary"]
            self.ratio_sum.setText(f"🟢 {sm['good']} جيد   🟡 {sm['watch']} انتبه   🔴 {sm['bad']} يحتاج معالجة   — "
                                   f"الفترة {r['days']} يوماً")
        elif name == "مطابقة البنك":
            from core import accountant
            self.rec_table.set_rows([[x["as_of"], float(x["statement"]), float(x["adjusted_book"]), float(x["in_transit"]),
                                      float(x["difference"]), x.get("saved_at", "")[:16]]
                                     for x in accountant.bank_reconciliations()])
        elif name == "التدفقات النقدية":
            from core import accountant
            cf = accountant.cash_flow(a, b)
            rows, colors = [], []
            for key, label, total_label in (
                    ("operating", "التدفقات من التشغيل (البيع والشراء والمصاريف)", "= صافي التدفق من التشغيل"),
                    ("investing", "التدفقات من الاستثمار (شراء وبيع الأصول)", "= صافي التدفق من الاستثمار"),
                    ("financing", "التدفقات من التمويل (المالك والقروض)", "= صافي التدفق من التمويل")):
                rows.append([label, ""])
                colors.append("#E2E8F0")
                for x in cf["sections"][key]:
                    rows.append([f"    {x['name']}", float(x["amount"])])
                    colors.append(None)
                rows.append([total_label, float(cf["totals"][key])])
                colors.append("#EFF6FF")
            rows += [["النقد أول الفترة (الصندوق والبنك والمحافظ)", float(cf["cash_open"])],
                     ["= صافي التغير في النقد", float(cf["net_change"])],
                     ["النقد آخر الفترة", float(cf["cash_close"])]]
            colors += [None, "#EFF6FF", "#DCFCE7" if cf["reconciled"] else "#FEE2E2"]
            self.cf_table.set_rows(rows, colors=colors)
            self.cf_note.setText("✓ التدفقات تطابق رصيد النقد الفعلي." if cf["reconciled"] else
                                 "✗ التدفقات لا تطابق رصيد النقد — شغّل التدقيق المالي.")
        elif name == "الأصول الثابتة":
            from core import accountant
            rows = accountant.list_assets()
            self.fa_table.set_rows([[r["name"], r["purchase_date"], float(r["cost"]), r["life_months"],
                                     float(r["monthly"]), float(r["accumulated"]), float(r["book_value"]),
                                     (f"بيع في {r['disposed_at']}" if r["disposed_at"] else "قيد الاستخدام")]
                                    for r in rows], rows)
        elif name == "ميزان المراجعة":
            tb = ledger.trial_balance(a, b)
            self.tb_table.set_rows([[r["code"], r["name"], float(r["opening"]), float(r["debit"]), float(r["credit"]),
                                     float(r["closing_debit"]), float(r["closing_credit"])] for r in tb["rows"]], tb["rows"])
            t = tb["totals"]
            self.tb_status.setText(f"المجاميع: مدين {m(t['debit'])} | دائن {m(t['credit'])} — أرصدة: مدين "
                                   f"{m(t['closing_debit'])} | دائن {m(t['closing_credit'])}   "
                                   f"{'✓ متوازن' if t['balanced'] else '✗ غير متوازن'}")
        elif name == "دفتر اليومية":
            rows, colors, shade = [], [], False
            for e in ledger.journal(a, b, daily_sales=not self.per_invoice.isChecked())[-3000:]:
                shade = not shade
                for i, ln in enumerate(e["lines"]):
                    rows.append([e["date"][:16] if i == 0 else "", e["ref"] if i == 0 else "",
                                 e["description"] if i == 0 else "",
                                 ("    " if ln["credit"] else "") + ln["name"],
                                 float(ln["debit"]) if ln["debit"] else "", float(ln["credit"]) if ln["credit"] else ""])
                    colors.append("#F8FAFC" if shade else None)
            self.jr_table.set_rows(rows, colors=colors)
        elif name == "كشف حساب":
            code = self.acc_combo.currentData()
            if not code:
                return
            st = ledger.account_statement(code, a, b, daily_sales=not self.per_invoice.isChecked())
            rows = [["", "", "رصيد أول الفترة", "", "", float(st["opening"])]]
            rows += [[r["date"][:16], r["ref"], r["description"], float(r["debit"]) if r["debit"] else "",
                      float(r["credit"]) if r["credit"] else "", float(r["balance"])] for r in st["rows"]]
            self.st_table.set_rows(rows)
            self.st_summary.setText(f"الرصيد الختامي: {m(st['closing'])} ({st['normal']})")
        elif name == "القيود اليدوية":
            rows = ledger.list_manual_entries(a, b)
            self.mj_table.set_rows([[r["entry_number"], r["entry_date"], r["description"], float(r["amount"] or 0),
                                     "ملغى" if r["is_void"] else "فعّال", r["username"] or ""] for r in rows], rows,
                                   colors=[("#FEE2E2" if r["is_void"] else None) for r in rows])
        elif name == "دليل الحسابات":
            rows = ledger.list_accounts()
            self.ca_table.set_rows([[r["code"], r["name"], ledger.TYPES.get(r["type"], r["type"]),
                                     "مدين" if ledger.is_debit_normal(r["code"]) else "دائن"] for r in rows], rows)

    # ------------------------------------------------------------------
    def open_account_from_tb(self):
        r = self.tb_table.selected_data()
        if not r:
            return
        idx = self.acc_combo.findData(r["code"])
        if idx < 0:
            self.acc_combo.addItem(f"{r['code']}  {r['name']}", r["code"])
            idx = self.acc_combo.count() - 1
        self.acc_combo.setCurrentIndex(idx)
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "كشف حساب":
                self.tabs.setCurrentIndex(i)

    def reconcile(self):
        from core import accountant
        r = accountant.bank_reconciliation(self.rec_date.date().toString("yyyy-MM-dd"), self.rec_amount.value())
        self._rec = r
        if r["matched"]:
            msg = f"✓ مطابق: رصيد البنك في الدفاتر {m(r['adjusted_book'])} يساوي الكشف."
        else:
            kind = ("على الأغلب عمولات أو رسوم بنكية لم تُسجَّل" if r["difference"] < 0 else
                    "إيداع أو تحويل وصل للبنك ولم يُسجَّل في البرنامج")
            msg = (f"الدفاتر: {m(r['book'])} − مبالغ في الطريق {m(r['in_transit'])} = {m(r['adjusted_book'])} • "
                   f"الكشف: {m(r['statement'])} • الفرق: {m(r['difference'])} — {kind}.")
        self.rec_result.setText(msg)
        self.rec_fees.setEnabled(r["difference"] < -0.009)

    def save_reconcile(self, fees):
        from core import accountant
        if not require_permission(self, "accounting"):
            return
        try:
            accountant.save_bank_reconciliation(self.rec_date.date().toString("yyyy-MM-dd"), self.rec_amount.value(),
                                                record_fees=fees)
        except ValueError as e:
            warn(self, str(e))
            return
        self.reconcile()
        self.load()

    def close_month(self):
        if require_permission(self, "accounting"):
            CloseMonthDialog(self).exec()
            self.load()

    def add_asset(self):
        if require_permission(self, "accounting") and AssetDialog(self).exec() == QDialog.Accepted:
            info(self, "أُضيف الأصل، وسيُحسب إهلاكه شهرياً تلقائياً.")
            self.load()

    def dispose_asset(self):
        r = self.fa_table.selected_data()
        if r and not r["disposed_at"] and require_permission(self, "accounting") and \
                DisposeDialog(self, r).exec() == QDialog.Accepted:
            self.load()

    def template_entry(self):
        if require_permission(self, "accounting") and TemplateEntryDialog(self).exec() == QDialog.Accepted:
            info(self, "تم تسجيل العملية وأُضيف القيد المحاسبي.")
            self.load()

    def free_entry(self):
        if require_permission(self, "accounting") and JournalEntryDialog(self).exec() == QDialog.Accepted:
            self.load()

    def void_entry(self):
        r = self.mj_table.selected_data()
        if not r or r["is_void"]:
            return
        if require_permission(self, "accounting") and ask(self, f"إلغاء القيد {r['entry_number']}؟ (يبقى ظاهراً كملغى)"):
            ledger.void_entry(r["id"])
            self.load()

    def add_account(self):
        if require_permission(self, "accounting") and AccountDialog(self).exec() == QDialog.Accepted:
            self.refresh()

    def current_table(self):
        return self.tables.get(self.tabs.currentIndex(), (None, ""))

    def export_current(self):
        t, name = self.current_table()
        if t:
            a, b = self.range.range()
            t.export_csv(self, f"{name} {a} - {b}.csv")

    def print_current(self):
        """الطباعة تُجهَّز في الخلفية بشريط تقدّم أسفل النافذة؛ دفتر اليومية يُطبع كاملاً للفترة"""
        t, name = self.current_table()
        if not t:
            return
        from ui import jobs
        from ui.table_print import TableReport
        a, b = self.range.range()
        period = f"في {b}" if name == "الميزانية العمومية" else f"من {a} إلى {b}"
        if name == "دفتر اليومية":
            jobs.print_table(self, _JournalReport(a, b, not self.per_invoice.isChecked(), period))
            return
        jobs.print_table(self, TableReport.from_table(t, name, period))


class _JournalReport:
    """دفتر اليومية كاملاً للفترة: الأسطر تُجهَّز داخل الخيط الخلفي نفسه (لا تجميد مهما كبر الدفتر)"""

    def __init__(self, a, b, daily, period):
        from core import i18n
        self.a, self.b, self.daily = a, b, daily
        self.title, self.subtitle = i18n.tr("دفتر اليومية"), i18n.tr(period)
        self.headers = [i18n.tr(h) for h in ("التاريخ", "المرجع", "البيان", "الحساب", "مدين", "دائن")]
        self.numeric = {4, 5}
        self.landscape = False
        self._rows = self._shade = None

    def _load(self):
        from core import i18n
        rows, shade, sh = [], [], False
        for e in ledger.journal(self.a, self.b, daily_sales=self.daily):
            sh = not sh
            for i, ln in enumerate(e["lines"]):
                rows.append([e["date"][:16] if i == 0 else "", e["ref"] if i == 0 else "",
                             i18n.tr(e["description"]) if i == 0 else "",
                             ("    " if ln["credit"] else "") + i18n.tr(ln["name"]),
                             f"{ln['debit']:,.2f}" if ln["debit"] else "", f"{ln['credit']:,.2f}" if ln["credit"] else ""])
                shade.append(sh)
        self._rows, self._shade = rows, shade

    @property
    def rows(self):
        if self._rows is None:
            self._load()
        return self._rows

    @property
    def shade(self):
        if self._rows is None:
            self._load()
        return self._shade
