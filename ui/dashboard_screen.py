# -*- coding: utf-8 -*-
"""لوحة التحكم: نظرة سريعة على اليوم"""

from datetime import datetime

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea, QFrame

from core import reports, products, auth, db
from ui.widgets import Table, page, title, hint, m, card, KpiCard, BarChart, qty_cell, button


class DashboardScreen(QWidget):
    navigate = Signal(str)

    def __init__(self):
        super().__init__()
        w, lay = page()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(w)
        QVBoxLayout(self).addWidget(scroll)
        self.layout().setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        self.greet = title("")
        head.addWidget(self.greet)
        head.addStretch()
        for text, key, obj in [("🧾 بيع جديد", "pos", "successBtn"), ("📦 إضافة بضاعة", "suppliers", "secondaryBtn"),
                               ("💸 مصروف", "expenses", "secondaryBtn"), ("📊 التقارير", "reports", "secondaryBtn")]:
            head.addWidget(button(text, obj, lambda _=False, k=key: self.navigate.emit(k)))
        lay.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.k_sales = KpiCard("مبيعات اليوم", "#2563EB", "🧾")
        self.k_profit = KpiCard("ربح اليوم (مجمل)", "#16A34A", "📈")
        self.k_count = KpiCard("عدد الفواتير", "#7C3AED", "🛒")
        self.k_cash = KpiCard("النقد في الصندوق", "#0F766E", "💵")
        self.k_debts = KpiCard("ديون العملاء", "#D97706", "📒")
        self.k_dues = KpiCard("مستحقات الموردين", "#B91C1C", "🚚")
        self.k_low = KpiCard("أصناف ناقصة", "#DC2626", "⚠")
        self.k_stock = KpiCard("قيمة المخزون", "#334155", "📦")
        self.k_expiry = KpiCard("صلاحية قريبة/منتهية", "#9333EA", "⏳")
        self.k_expiry.setCursor(Qt.PointingHandCursor)
        self.k_expiry.mousePressEvent = lambda e: self.navigate.emit("expiry")
        self.k_low.setCursor(Qt.PointingHandCursor)
        self.k_low.mousePressEvent = lambda e: self.navigate.emit("inventory")
        cards = (self.k_sales, self.k_profit, self.k_count, self.k_cash, self.k_debts,
                 self.k_dues, self.k_low, self.k_expiry, self.k_stock)
        for i, k in enumerate(cards):
            grid.addWidget(k, i // 5, i % 5)
        lay.addLayout(grid)

        c, cl = card()
        cl.addWidget(title("المبيعات آخر 14 يوماً", "subTitle"))
        self.chart = BarChart()
        cl.addWidget(self.chart)
        lay.addWidget(c)

        bottom = QHBoxLayout()
        c1, l1 = card()
        l1.addWidget(title("الأكثر مبيعاً اليوم", "subTitle"))
        self.top = Table(["الصنف", "الكمية", "المبيعات"], sortable=False)
        self.top.setMinimumHeight(260)
        l1.addWidget(self.top)
        bottom.addWidget(c1)
        c2, l2 = card()
        l2.addWidget(title("نواقص تحتاج طلبية", "subTitle"))
        self.low = Table(["الصنف", "المتوفر", "الحد الأدنى"], sortable=False)
        self.low.setMinimumHeight(260)
        l2.addWidget(self.low)
        bottom.addWidget(c2)
        lay.addLayout(bottom, 1)

    def refresh(self):
        u = auth.current_user() or {}
        h = datetime.now().hour
        salute = "صباح الخير" if h < 12 else "مساء الخير"
        self.greet.setText(f"{salute}، {u.get('full_name') or u.get('username', '')} 👋")
        d = reports.dashboard()
        t = d["today"]
        self.k_sales.set(m(t["net_sales"]), f"نقدي {m(t['cash_sales'])} • آجل {m(t['credit_sales'])}")
        self.k_profit.set(m(t["gross_profit"]), f"هامش {t['gross_margin']}%")
        self.k_count.set(str(t["invoice_count"]), f"متوسط الفاتورة {m(t['avg_basket'])}")
        self.k_cash.set(m(d["drawer_cash"]) if d["drawer_cash"] is not None else "—",
                        "الوردية مفتوحة" if d["shift"] else "لا توجد وردية مفتوحة")
        self.k_debts.set(m(d["customer_debts"]))
        self.k_dues.set(m(d["supplier_dues"]))
        self.k_low.set(str(d["low_stock"]), "اضغط للعرض")
        self.k_expiry.set(str(d["expiring"]), "اضغط للعرض")
        self.k_stock.set(m(d["inventory"]["cost_value"]), f"{d['inventory']['items']} صنف")
        days = reports.last_n_days(14)
        self.chart.set_data([x["date"][5:] for x in days], [x["total"] for x in days])
        today = db.today()
        top = reports.top_products(today, today, 10, "total")
        self.top.set_rows([[r["product_name"], qty_cell(r["qty"]), float(r["total"] or 0)] for r in top])
        low = products.get_low_stock_products()[:30]
        self.low.set_rows([[p["name"], qty_cell(p["quantity"]), qty_cell(p["min_quantity"])] for p in low],
                          colors=[("#FEE2E2" if p["quantity"] <= 0 else None) for p in low])
