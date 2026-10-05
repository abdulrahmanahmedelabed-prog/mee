# -*- coding: utf-8 -*-
"""التقارير: الأرباح والخسائر، يومي، فئات، أصناف، راكدة، ساعات الذروة، الكاشير، الديون، المخزون، سجل العمليات"""

from html import escape

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox, QLabel, QGridLayout

from core import reports, customers, suppliers, products, audit, settings, receipts
from ui import printing
from ui.widgets import Table, button, page, title, m, card, DateRange, KpiCard, BarChart, qty_cell


class ReportsScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        self.range = DateRange("هذا الشهر")
        self.range.changed.connect(self.load)
        head.addWidget(self.range)
        head.addStretch()
        head.addWidget(button("📤 تصدير الجدول", "secondaryBtn", self.export_current))
        head.addWidget(button("🖨 طباعة", "secondaryBtn", self.print_current))
        lay.addLayout(head)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(lambda _: self.load())
        lay.addWidget(self.tabs, 1)
        self.tables = {}

        # 1) الأرباح والخسائر
        pl = QWidget()
        pll = QVBoxLayout(pl)
        pll.setContentsMargins(0, 10, 0, 0)
        g = QGridLayout()
        self.k_sales = KpiCard("صافي المبيعات", "#2563EB", "🧾")
        self.k_gp = KpiCard("مجمل الربح", "#16A34A", "📈")
        self.k_exp = KpiCard("المصاريف", "#DC2626", "💸")
        self.k_np = KpiCard("صافي الربح", "#0F172A", "💰")
        for i, k in enumerate((self.k_sales, self.k_gp, self.k_exp, self.k_np)):
            g.addWidget(k, 0, i)
        pll.addLayout(g)
        self.pl_table = Table(["البند", "المبلغ"], stretch=0, sortable=False)
        pll.addWidget(self.pl_table, 1)
        self._add_tab(pl, "الأرباح والخسائر", self.pl_table)

        # 2) يومي
        daily = QWidget()
        dl = QVBoxLayout(daily)
        dl.setContentsMargins(0, 10, 0, 0)
        c, cl = card()
        self.daily_chart = BarChart()
        cl.addWidget(self.daily_chart)
        dl.addWidget(c)
        self.daily_table = Table(["التاريخ", "عدد الفواتير", "صافي المبيعات", "الربح"])
        dl.addWidget(self.daily_table, 1)
        self._add_tab(daily, "المبيعات اليومية", self.daily_table)

        # 2ب) ملخص الفترات: يومي / أسبوعي / شهري / سنوي
        per = QWidget()
        pl2 = QVBoxLayout(per)
        pl2.setContentsMargins(0, 10, 0, 0)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("التجميع:"))
        self.period_group = QComboBox()
        for k, label in reports.PERIODS.items():
            self.period_group.addItem(label, k)
        self.period_group.setCurrentIndex(2)
        self.period_group.currentIndexChanged.connect(self.load)
        prow.addWidget(self.period_group)
        prow.addStretch()
        pl2.addLayout(prow)
        c3, cl3 = card()
        self.period_chart = BarChart("#16A34A")
        cl3.addWidget(self.period_chart)
        pl2.addWidget(c3)
        self.period_table = Table(["الفترة", "الفواتير", "صافي المبيعات", "مجمل الربح", "الهامش", "المصاريف",
                                   "صافي الربح", "نقدي", "بطاقة", "إلكتروني", "آجل"], stretch=0)
        pl2.addWidget(self.period_table, 1)
        self._add_tab(per, "ملخص الفترات", self.period_table)

        # 3) فئات
        self.cat_table = Table(["الفئة", "الكمية", "المبيعات", "الربح", "هامش الربح"])
        self._add_tab(self.cat_table, "حسب الفئة", self.cat_table)

        # 4) الأصناف الأكثر مبيعاً
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("ترتيب حسب:"))
        self.top_order = QComboBox()
        self.top_order.addItem("قيمة المبيعات", "total")
        self.top_order.addItem("الكمية", "qty")
        self.top_order.addItem("الربح", "profit")
        self.top_order.currentIndexChanged.connect(self.load)
        row.addWidget(self.top_order)
        row.addStretch()
        tl.addLayout(row)
        self.top_table = Table(["#", "الصنف", "الكمية", "المبيعات", "الربح"], stretch=1)
        tl.addWidget(self.top_table)
        self._add_tab(top, "الأصناف الأكثر مبيعاً", self.top_table)

        # 5) راكدة
        self.slow_table = Table(["الصنف", "الفئة", "الكمية", "قيمة المخزون (تكلفة)", "آخر بيع"])
        self._add_tab(self.slow_table, "أصناف راكدة", self.slow_table)

        # 6) ساعات الذروة
        hours = QWidget()
        hl = QVBoxLayout(hours)
        hl.setContentsMargins(0, 10, 0, 0)
        c2, cl2 = card()
        self.hour_chart = BarChart("#7C3AED")
        cl2.addWidget(self.hour_chart)
        hl.addWidget(c2)
        self.hour_table = Table(["الساعة", "عدد الفواتير", "المبيعات"])
        hl.addWidget(self.hour_table, 1)
        self._add_tab(hours, "ساعات الذروة", self.hour_table)

        # 7) الكاشير
        self.cashier_table = Table(["الكاشير", "عدد الفواتير", "المبيعات", "الخصومات"])
        self._add_tab(self.cashier_table, "حسب الكاشير", self.cashier_table)

        # 7ب) حسب نقطة البيع
        self.terminal_table = Table(["نقطة البيع (الجهاز)", "عدد الفواتير", "المبيعات"])
        self._add_tab(self.terminal_table, "حسب الجهاز", self.terminal_table)

        # 7ج) الدفع الإلكتروني: مطابقة كل محفظة/تطبيق بنكي مع كشفه
        wal = QWidget()
        wl = QVBoxLayout(wal)
        wl.setContentsMargins(0, 10, 0, 0)
        self.wallet_table = Table(["طريقة الدفع", "يصل المال إلى", "عدد العمليات", "مبيعات", "تسديد ديون", "مرتجعات",
                                   "الإجمالي"])
        self.wallet_table.itemSelectionChanged.connect(self.load_wallet_ops)
        wl.addWidget(self.wallet_table, 1)
        wl.addWidget(QLabel("عمليات الطريقة المحددة (للمطابقة سطراً بسطر مع كشف المحفظة أو البنك):"))
        self.wallet_ops = Table(["الفاتورة", "الوقت", "المبلغ", "رقم العملية"])
        wl.addWidget(self.wallet_ops, 1)
        self._add_tab(wal, "الدفع الإلكتروني", self.wallet_table)

        # 8) الديون
        self.debts_table = Table(["النوع", "الاسم", "الهاتف", "الرصيد"], stretch=1)
        self._add_tab(self.debts_table, "الديون والمستحقات", self.debts_table)

        # 9) المخزون
        self.stock_table = Table(["الصنف", "الفئة", "الكمية", "الحد الأدنى", "التكلفة", "قيمة المخزون", "الحالة"])
        self._add_tab(self.stock_table, "تقييم المخزون", self.stock_table)

        # 9ب) ضريبة القيمة المضافة
        self.vat_table = Table(["البند", "المبلغ"], stretch=0, sortable=False)
        self._add_tab(self.vat_table, "ضريبة القيمة المضافة", self.vat_table)

        # 9ج) الفروع: تقرير مجمّع لكل فروع المحل من نسخها الاحتياطية في مجلد مشترك
        br = QWidget()
        bl = QVBoxLayout(br)
        bl.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(button("📁 مجلد نسخ الفروع", "secondaryBtn", self.choose_branches_dir))
        row.addWidget(button("📥 إضافة ملف فرع", "secondaryBtn", self.add_branch_file))
        self.branches_dir_lbl = QLabel("")
        self.branches_dir_lbl.setObjectName("hint")
        row.addWidget(self.branches_dir_lbl, 1)
        bl.addLayout(row)
        self.branch_table = Table(["الفرع", "آخر تحديث", "الفواتير", "صافي المبيعات", "مجمل الربح", "المصاريف",
                                   "صافي الربح", "قيمة المخزون", "ديون العملاء", "مستحقات الموردين"], stretch=0,
                                  sortable=False)
        bl.addWidget(self.branch_table, 1)
        from ui.widgets import hint as _hint
        bl.addWidget(_hint("في كل فرع: الإعدادات ← بيانات المحل ← «اسم الفرع»، والإعدادات ← النسخ الاحتياطي ← «نسخة ثانية» "
                           "إلى مجلد مشترك (Google Drive مثلاً). هنا اختر نفس المجلد، فيقرأ البرنامج أحدث نسخة لكل فرع."))
        self._add_tab(br, "الفروع", self.branch_table)

        # 10) سجل العمليات
        self.audit_table = Table(["الوقت", "المستخدم", "العملية", "التفاصيل"], stretch=3)
        self._add_tab(self.audit_table, "سجل العمليات", self.audit_table)

    def choose_branches_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "مجلد نسخ الفروع", settings.get("branches_dir") or "")
        if d:
            settings.set_many({"branches_dir": d})
            self.load()

    def add_branch_file(self):
        from PySide6.QtWidgets import QFileDialog
        from core import branches
        from ui.widgets import warn, info
        path, _ = QFileDialog.getOpenFileName(self, "ملف نسخة احتياطية من فرع", "", "Database (*.db)")
        if not path:
            return
        try:
            name = branches.add_branch_file(path)
        except ValueError as e:
            warn(self, str(e))
            return
        info(self, f"أُضيف الفرع: {name}")
        self.load()

    def _add_tab(self, widget, name, table):
        self.tabs.blockSignals(True)          # لا تحميل أثناء البناء: refresh() عند فتح الشاشة يحمّل مرة واحدة
        idx = self.tabs.addTab(widget, name)
        self.tabs.blockSignals(False)
        self.tables[idx] = (table, name)

    def refresh(self):
        self.load()

    def load(self):
        a, b = self.range.range()
        i = self.tabs.currentIndex()
        name = self.tabs.tabText(i)
        if name == "الأرباح والخسائر":
            p = reports.profit_and_loss(a, b)
            self.k_sales.set(m(p["net_sales"]), f"{p['invoice_count']} فاتورة • متوسط السلة {m(p['avg_basket'])}")
            self.k_gp.set(m(p["gross_profit"]), f"هامش {p['gross_margin']}%")
            self.k_exp.set(m(p["expenses"]))
            self.k_np.set(m(p["net_profit"]))
            self.k_np.value.setStyleSheet(f"color:{'#16A34A' if p['net_profit'] >= 0 else '#DC2626'};")
            rows = [
                ("إجمالي المبيعات (قبل الخصم)", p["gross_sales"]), ("− الخصومات", p["discounts"]),
                ("− المرتجعات", p["returns"]), ("= صافي المبيعات", p["net_sales"]),
                ("− ضريبة القيمة المضافة المستحقة", p["tax"]), ("= صافي الإيراد", p["net_revenue"]),
                ("− تكلفة البضاعة المباعة", p["cogs"]), ("= مجمل الربح", p["gross_profit"]),
                ("− المصاريف التشغيلية", p["expenses"]),
                ("− خسائر المخزون (تالف، منتهي، عجز جرد)", p["stock_loss"]),
                ("− تكلفة نقاط الولاء (المكتسبة − المستبدلة)", p["loyalty_cost"]),
                ("± عجز/زيادة الصندوق والتسويات", p["other_adjustments"]),
                ("± عمليات مالية (عمولات، إيرادات أخرى)", p["manual_entries"]), ("= صافي الربح", p["net_profit"]),
                ("", None),
                ("مبيعات نقدية", p["cash_sales"]), ("مبيعات بطاقة", p["card_sales"]),
                ("مبيعات دفع إلكتروني (محافظ وتطبيقات)", p["wallet_sales"]), ("مبيعات آجلة (ديون جديدة)", p["credit_sales"]),
                ("ديون محصّلة من العملاء", p["debt_collected"]), ("مشتريات بضاعة في الفترة", p["purchases"]),
            ]
            self.pl_table.set_rows([[k, float(v) if v is not None else ""] for k, v in rows],
                                   colors=[("#EFF6FF" if k.startswith("=") else None) for k, _ in rows])
        elif name == "الفروع":
            from core import branches, plans
            import os
            if not plans.has("branches"):            # باقة ماكس
                self.branches_dir_lbl.setText("🔒 تقرير الفروع الموحّد متاح في باقة 👑 ماكس — اضغط «الباقات والترقية» أعلى الشاشة")
                self.branch_table.set_rows([])
                return
            d = settings.get("branches_dir")
            self.branches_dir_lbl.setText(("📁 " + os.path.basename(d.rstrip("/\\"))) if d else "لم يُحدَّد مجلد مشترك")
            self.branches_dir_lbl.setToolTip(d or "")
            rows = branches.consolidated(a, b)
            self.branch_table.set_rows([[r["branch"], r["updated"] or (r.get("error") and "تعذرت القراءة") or "",
                                         r["invoice_count"]] + [float(r[k]) for k in branches.FIELDS[1:]] for r in rows],
                                       rows, colors=[("#EFF6FF" if r["branch"] == "المجموع" else
                                                      "#FEF3F2" if r.get("error") else None) for r in rows])
            for i, r in enumerate(rows):
                if r.get("error"):
                    self.branch_table.item(i, 1).setToolTip(r["error"])
        elif name == "المبيعات اليومية":
            d = reports.daily_sales(a, b)
            self.daily_chart.set_data([x["date"][5:] for x in d], [x["total"] for x in d])
            self.daily_table.set_rows([[x["date"], x["count"], float(x["total"]), float(x["profit"])] for x in reversed(d)])
        elif name == "ملخص الفترات":
            d = reports.period_summary(a, b, self.period_group.currentData())
            self.period_chart.set_data([x["period"][-5:] if len(x["period"]) == 10 else x["period"] for x in d[-24:]],
                                       [x["net_profit"] for x in d[-24:]])
            self.period_table.set_rows([[x["period"], x["count"], float(x["net_sales"]), float(x["gross_profit"]),
                                         (f"{x['margin']}%", x["margin"]), float(x["expenses"]),
                                         float(x["net_profit"]), float(x["cash"]), float(x["card"]),
                                         float(x["wallet"]), float(x["credit"])] for x in reversed(d)])
        elif name == "الدفع الإلكتروني":
            from core import wallets
            rows = wallets.summary(a, b)
            self.wallet_table.set_rows([[r["name"], r["dest"], r["count"], float(r["sales"]), float(r["debts"]),
                                         float(r["refunds"]), float(r["total"])] for r in rows], rows)
            self.wallet_ops.set_rows([])
        elif name == "حسب الفئة":
            rows = reports.sales_by_category(a, b)
            self.cat_table.set_rows([[r["category"], qty_cell(r["qty"]), float(r["total"] or 0), float(r["profit"] or 0),
                                      (f"{(r['profit'] or 0) / r['total'] * 100:.1f}%" if r["total"] else "-", 0)]
                                     for r in rows])
        elif name == "الأصناف الأكثر مبيعاً":
            rows = reports.top_products(a, b, 100, self.top_order.currentData())
            self.top_table.set_rows([[i + 1, r["product_name"], qty_cell(r["qty"]), float(r["total"] or 0),
                                      float(r["profit"] or 0)] for i, r in enumerate(rows)])
        elif name == "أصناف راكدة":
            rows = reports.slow_products(a, b)
            self.slow_table.set_rows([[r["name"], r["category"] or "", qty_cell(r["quantity"]), float(r["stock_value"]),
                                       (r["last_sold"] or "لم يُبع أبداً")[:10]] for r in rows])
        elif name == "ساعات الذروة":
            rows = [h for h in reports.sales_by_hour(a, b)]
            self.hour_chart.set_data([f"{h['hour']:02d}" for h in rows], [h["total"] for h in rows])
            self.hour_table.set_rows([[f"{h['hour']:02d}:00", h["count"], float(h["total"])] for h in rows if h["count"]])
        elif name == "حسب الكاشير":
            rows = reports.sales_by_cashier(a, b)
            self.cashier_table.set_rows([[r["cashier"], r["cnt"], float(r["total"]), float(r["discount"])] for r in rows])
        elif name == "حسب الجهاز":
            rows = reports.sales_by_terminal(a, b)
            self.terminal_table.set_rows([[r["terminal"], r["cnt"], float(r["total"])] for r in rows])
        elif name == "الديون والمستحقات":
            rows = [["عميل (له علينا دين)", c["name"], c["phone"] or "", float(c["balance_due"])]
                    for c in customers.list_customers(debtors_only=True)]
            rows += [["مورد (مستحق له)", s["name"], s["phone"] or "", float(s["balance_due"])]
                     for s in suppliers.list_suppliers() if s["balance_due"] > 0.009]
            self.debts_table.set_rows(rows)
        elif name == "تقييم المخزون":
            rows = products.get_all_products()
            data = []
            for p in rows:
                st = "نفد" if p["quantity"] <= 0 else ("منخفض" if p["quantity"] <= p["min_quantity"] else "جيد")
                data.append([p["name"], p["category"] or "", qty_cell(p["quantity"]), qty_cell(p["min_quantity"]),
                             float(p["cost_price"]), float(max(p["quantity"], 0) * p["cost_price"]), st])
            self.stock_table.set_rows(data, colors=[("#FEE2E2" if d[6] == "نفد" else "#FEF3C7" if d[6] == "منخفض" else None)
                                                    for d in data])
        elif name == "ضريبة القيمة المضافة":
            v = reports.vat_report(a, b)
            rows = [("المبيعات شاملة الضريبة (بعد المرتجعات)", v["sales_total"]),
                    ("المبيعات الخاضعة بدون ضريبة", v["taxable_sales"]),
                    ("ضريبة المخرجات (على المبيعات)", v["output_tax"]), ("", None),
                    ("المشتريات شاملة الضريبة", v["purchases_total"]),
                    ("المشتريات بدون ضريبة", v["taxable_purchases"]),
                    ("ضريبة المدخلات (على المشتريات)", v["input_tax"]), ("", None),
                    ("= صافي الضريبة المستحقة للدفع (مخرجات − مدخلات)", v["net_due"])]
            self.vat_table.set_rows([[k, float(x) if x is not None else ""] for k, x in rows],
                                    colors=[("#EFF6FF" if k.startswith("=") else None) for k, _ in rows])
        elif name == "سجل العمليات":
            rows = audit.recent(1000, a, b)
            self.audit_table.set_rows([[r["created_at"], r["username"] or "", r["action"], r["details"] or ""] for r in rows])

    def current_table(self):
        return self.tables.get(self.tabs.currentIndex(), (None, ""))

    def load_wallet_ops(self):
        from core import wallets
        r = self.wallet_table.selected_data()
        if not r:
            return
        a, b = self.range.range()
        self.wallet_ops.set_rows([[x["invoice_number"], x["created_at"][:16], float(x["wallet_amount"]),
                                   x["wallet_ref"] or ""] for x in wallets.invoices(r["name"], a, b)])

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
        from core import branding
        html = branding.document(f"<table width='100%' border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse'>"
                                 f"<tr style='background:#eee'>{heads}</tr>{body}</table>", name, f"من {a} إلى {b}")
        printing.print_html(self, html, width_mm=210, preview=True)
