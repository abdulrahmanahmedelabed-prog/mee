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

        # 8) الديون
        self.debts_table = Table(["النوع", "الاسم", "الهاتف", "الرصيد"], stretch=1)
        self._add_tab(self.debts_table, "الديون والمستحقات", self.debts_table)

        # 9) المخزون
        self.stock_table = Table(["الصنف", "الفئة", "الكمية", "الحد الأدنى", "التكلفة", "قيمة المخزون", "الحالة"])
        self._add_tab(self.stock_table, "تقييم المخزون", self.stock_table)

        # 10) سجل العمليات
        self.audit_table = Table(["الوقت", "المستخدم", "العملية", "التفاصيل"], stretch=3)
        self._add_tab(self.audit_table, "سجل العمليات", self.audit_table)

    def _add_tab(self, widget, name, table):
        idx = self.tabs.addTab(widget, name)
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
                ("± عجز/زيادة الصندوق والتسويات", p["other_adjustments"]), ("= صافي الربح", p["net_profit"]),
                ("", None),
                ("مبيعات نقدية", p["cash_sales"]), ("مبيعات بطاقة", p["card_sales"]), ("مبيعات آجلة (ديون جديدة)", p["credit_sales"]),
                ("ديون محصّلة من العملاء", p["debt_collected"]), ("مشتريات بضاعة في الفترة", p["purchases"]),
            ]
            self.pl_table.set_rows([[k, float(v) if v is not None else ""] for k, v in rows],
                                   colors=[("#EFF6FF" if k.startswith("=") else None) for k, _ in rows])
        elif name == "المبيعات اليومية":
            d = reports.daily_sales(a, b)
            self.daily_chart.set_data([x["date"][5:] for x in d], [x["total"] for x in d])
            self.daily_table.set_rows([[x["date"], x["count"], float(x["total"]), float(x["profit"])] for x in reversed(d)])
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
        elif name == "سجل العمليات":
            rows = audit.recent(1000, a, b)
            self.audit_table.set_rows([[r["created_at"], r["username"] or "", r["action"], r["details"] or ""] for r in rows])

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
        html = (f"<html><body dir='rtl' style='font-family:Tahoma;font-size:10pt'>"
                f"<h2 style='text-align:center'>{escape(settings.get('shop_name'))}</h2>"
                f"<h3 style='text-align:center'>{escape(name)}</h3><p style='text-align:center'>من {a} إلى {b}</p>"
                f"<table width='100%' border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse'>"
                f"<tr style='background:#eee'>{heads}</tr>{body}</table></body></html>")
        printing.print_html(self, html, width_mm=210, preview=True)
