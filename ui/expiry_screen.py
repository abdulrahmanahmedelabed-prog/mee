# -*- coding: utf-8 -*-
"""شاشة الصلاحية: البضاعة المنتهية والقريبة من الانتهاء، مع الإتلاف وتصدير قائمة للمرتجع للمورد"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QGridLayout

from core import products, settings, db
from core.utils import fmt_qty
from ui.widgets import Table, button, page, hint, warn, ask, m, KpiCard, qty_cell, require_permission


class ExpiryScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.addWidget(QLabel("عرض ما ينتهي خلال:"))
        self.days = QSpinBox()
        self.days.setRange(0, 730)
        self.days.setSuffix(" يوم")
        self.days.valueChanged.connect(self.load)
        top.addWidget(self.days)
        top.addStretch()
        top.addWidget(button("📤 تصدير (لإرجاعها للمورد)", "secondaryBtn",
                             lambda: self.table.export_csv(self, f"الصلاحية {db.today()}.csv")))
        top.addWidget(button("🗑 إتلاف الدفعة المحددة", "dangerBtn", self.write_off))
        lay.addLayout(top)

        g = QGridLayout()
        self.k_expired = KpiCard("منتهية الصلاحية", "#DC2626", "⛔")
        self.k_week = KpiCard("تنتهي خلال 7 أيام", "#D97706", "⚠")
        self.k_period = KpiCard("قريبة الانتهاء (الفترة المختارة)", "#2563EB", "⏳")
        for i, k in enumerate((self.k_expired, self.k_week, self.k_period)):
            g.addWidget(k, 0, i)
        lay.addLayout(g)

        self.table = Table(["الصنف", "الفئة", "تاريخ الانتهاء", "الأيام المتبقية", "الكمية المتبقية", "القيمة بالتكلفة",
                            "رقم الدفعة"])
        lay.addWidget(self.table, 1)
        lay.addWidget(hint("نصيحة: ضع البضاعة الأقرب انتهاءً في مقدمة الرف، أو اعمل عليها عرضاً وخصماً قبل انتهائها. "
                           "إتلاف الدفعة يخصمها من المخزون ويسجلها خسارة في تقرير الأرباح."))

    def refresh(self):
        if not self.days.value():
            self.days.blockSignals(True)
            self.days.setValue(int(settings.get_float("expiry_alert_days", 30)))
            self.days.blockSignals(False)
        self.load()

    def load(self):
        rows = products.expiring_batches(self.days.value())
        expired = [r for r in rows if r["days_left"] < 0]
        week = [r for r in rows if 0 <= r["days_left"] <= 7]
        self.k_expired.set(str(len(expired)), f"قيمتها {m(sum(r['value'] for r in expired))}")
        self.k_week.set(str(len(week)), f"قيمتها {m(sum(r['value'] for r in week))}")
        self.k_period.set(str(len(rows)), f"قيمتها {m(sum(r['value'] for r in rows))}")

        def left(r):
            dl = r["days_left"]
            return ("منتهية منذ %d يوم" % -dl if dl < 0 else ("اليوم" if dl == 0 else f"{dl} يوم"), dl)
        colors = [("#FEE2E2" if r["days_left"] < 0 else "#FEF3C7" if r["days_left"] <= 7 else None) for r in rows]
        self.table.set_rows([[r["name"], r["category"] or "", r["expiry_date"], left(r),
                              (f"{fmt_qty(r['remaining'])} {r['unit']}", r["remaining"]), float(r["value"]),
                              r["batch_no"] or ""] for r in rows], rows, colors)

    def write_off(self):
        b = self.table.selected_data()
        if not b:
            warn(self, "اختر دفعة من الجدول")
            return
        if require_permission(self, "inventory") and \
                ask(self, f"إتلاف {fmt_qty(b['remaining'])} {b['unit']} من {b['name']} (صلاحية {b['expiry_date']})؟"):
            products.write_off_batch(b["id"])
            self.load()
