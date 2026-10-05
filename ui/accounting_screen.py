# -*- coding: utf-8 -*-
"""
شاشة المحاسبة: الميزانية العمومية، قائمة الدخل، ميزان المراجعة، دفتر اليومية، كشف أي حساب، القيود اليدوية ودليل الحسابات.
كلها تُبنى تلقائياً من عمليات البرنامج؛ صاحب المحل لا يحتاج كتابة أي قيد إلا للعمليات خارج البيع والشراء.
"""

from html import escape

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox, QLabel, QGridLayout, QDialog,
                               QFormLayout, QLineEdit, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView,
                               QAbstractItemView)

from core import ledger, settings, db
from core.utils import money, to_float
from ui import printing
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


class AccountingScreen(QWidget):
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

        # 2) قائمة الدخل
        self.is_table = Table(["البند", "المبلغ"], stretch=0, sortable=False)
        self._add_tab(self.is_table, "قائمة الدخل", self.is_table)

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

    def _add_tab(self, widget, name, table):
        idx = self.tabs.addTab(widget, name)
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
            note = "✓ الميزانية متوازنة: الأصول = الالتزامات + حقوق الملكية." if bs["balanced"] else "✗ الميزانية غير متوازنة!"
            if bs["inventory_physical"] is not None and abs(bs["inventory_physical"] - bs["inventory_book"]) >= 0.01:
                note += (f"  ملاحظة: قيمة المخزون الفعلية حسب الكميات {m(bs['inventory_physical'])} والدفترية "
                         f"{m(bs['inventory_book'])} (الفرق من تعديلات التكلفة أو البيع بمخزون سالب).")
            self.bs_note.setText(note)
        elif name == "قائمة الدخل":
            s = ledger.income_statement(a, b)
            rows = [("المبيعات", s["sales"]), ("− مردودات المبيعات", s["returns"]), ("= صافي المبيعات", s["net_sales"]),
                    ("− تكلفة البضاعة المباعة", s["cogs"]), ("= مجمل الربح", s["gross_profit"]),
                    ("+ إيرادات أخرى", s["other_income"]), ("", None)]
            rows += [(f"− {e['name']}", e["amount"]) for e in s["expenses"]]
            rows += [("= مجموع المصروفات", s["total_expenses"]), ("", None), ("= صافي الربح (الدخل)", s["net_income"])]
            self.is_table.set_rows([[k, float(v) if v is not None else ""] for k, v in rows],
                                   colors=[("#EFF6FF" if k.startswith("=") else None) for k, _ in rows])
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
        t, name = self.current_table()
        if not t:
            return
        a, b = self.range.range()
        heads = "".join(f"<th>{escape(t.horizontalHeaderItem(c).text())}</th>" for c in range(t.columnCount()))
        body = ""
        for r in range(t.rowCount()):
            body += "<tr>" + "".join(f"<td>{escape(t.item(r, c).text() if t.item(r, c) else '')}</td>"
                                     for c in range(t.columnCount())) + "</tr>"
        period = f"في {b}" if name == "الميزانية العمومية" else f"من {a} إلى {b}"
        from core import branding
        html = branding.document(f"<table width='100%' border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse'>"
                                 f"<tr style='background:#eee'>{heads}</tr>{body}</table>", name, period)
        printing.print_html(self, html, width_mm=210, preview=True)
