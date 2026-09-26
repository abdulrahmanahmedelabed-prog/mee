# -*- coding: utf-8 -*-
"""المستشار الذكي: توصيات عملية، تحليل ABC، أصناف تُشترى معاً، وتحديث الأسعار الجماعي"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QFrame, QComboBox,
                               QDoubleSpinBox, QCheckBox)

from core import insights, products, settings
from ui.widgets import Table, button, page, hint, info, ask, m, qty_cell, require_permission, KpiCard

COLORS = {"danger": ("#FEF2F2", "#DC2626", "⛔"), "warning": ("#FFFBEB", "#D97706", "⚠"),
          "info": ("#EFF6FF", "#2563EB", "💡"), "success": ("#F0FDF4", "#16A34A", "✅")}


def cards_html(cards):
    """التوصيات كصفحة واحدة منسّقة (أثبت من عناصر كثيرة داخل منطقة تمرير)"""
    from html import escape
    from core.i18n import tr, is_rtl
    side = "right" if is_rtl() else "left"
    out = []
    for c in cards:
        bg, fg, icon = COLORS[c["severity"]]
        items = "<br>".join(f"• {escape(tr(x))}" for x in c["items"])
        link = (f"&nbsp;&nbsp;<a href='act:{c['action']}' style='color:{fg}; font-weight:bold'>{escape(tr(c['action_label']))} ←</a>"
                if c.get("action") else "")
        out.append(
            f"<table width='100%' cellspacing='0' cellpadding='10' style='background-color:{bg}; margin-bottom:12px'>"
            f"<tr><td width='6' style='background-color:{fg}'></td><td align='{side}'>"
            f"<span style='font-size:14pt; font-weight:bold; color:{fg}'>{icon} {escape(tr(c['title']))}</span>{link}"
            f"<br><span style='color:#334155'>{escape(tr(c['detail']))}</span>"
            + (f"<br><span style='color:#475569; font-size:10pt'>{items}</span>" if items else "")
            + "</td></tr></table>")
    return f"<div dir='{'rtl' if is_rtl() else 'ltr'}'>{''.join(out)}</div>"


class InsightsScreen(QWidget):
    navigate = Signal(str)

    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # --- التوصيات
        rec = QWidget()
        rl = QVBoxLayout(rec)
        rl.setContentsMargins(0, 8, 0, 0)
        row = QHBoxLayout()
        row.addWidget(hint("المستشار يحلل مبيعاتك ومخزونك وديونك وورديات الكاشير ويقترح ما يزيد ربحك. "
                           "راجعه مرة يومياً مع قهوة الصباح ☕"))
        row.addStretch()
        row.addWidget(button("🔄 تحليل الآن", "successBtn", self.load_cards))
        rl.addLayout(row)
        from PySide6.QtWidgets import QTextBrowser
        self.cards = QTextBrowser()
        self.cards.setOpenLinks(False)
        self.cards.setFrameShape(QFrame.NoFrame)
        self.cards.setStyleSheet("QTextBrowser { background: transparent; font-size: 11pt; }")
        self.cards.anchorClicked.connect(lambda url: self.on_action(url.toString()[4:]))
        rl.addWidget(self.cards, 1)
        self.tabs.addTab(rec, "🤖 التوصيات")

        # --- ABC
        abc = QWidget()
        al = QVBoxLayout(abc)
        al.setContentsMargins(0, 8, 0, 0)
        kr = QHBoxLayout()
        self.k_a = KpiCard("أصناف A (تصنع 80% من مبيعاتك)", "#16A34A", "🥇")
        self.k_b = KpiCard("أصناف B (15%)", "#2563EB", "🥈")
        self.k_c = KpiCard("أصناف C (5%)", "#64748B", "🥉")
        for k in (self.k_a, self.k_b, self.k_c):
            kr.addWidget(k)
        al.addLayout(kr)
        self.abc_table = Table(["الفئة ABC", "الصنف", "التصنيف", "الكمية المباعة", "المبيعات", "الربح", "الحصة %",
                                "التراكمي %", "المخزون"], stretch=1)
        al.addWidget(self.abc_table, 1)
        al.addWidget(hint("أصناف A: لا تسمح بنفادها أبداً وراقب أسعارها. أصناف C: قلّل كمياتها ولا تحجز لها مساحة كبيرة. "
                          "(آخر 90 يوماً)"))
        self.tabs.addTab(abc, "تحليل ABC")

        # --- تُشترى معاً
        self.pairs = Table(["الصنف الأول", "الصنف الثاني", "عدد الفواتير المشتركة"], stretch=0)
        self.tabs.addTab(self.pairs, "تُشترى معاً")

        # --- تحديث الأسعار الجماعي
        pr = QWidget()
        pl = QVBoxLayout(pr)
        pl.setContentsMargins(0, 8, 0, 0)
        f = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("هامش ربح مستهدف من التكلفة %", "margin")
        self.mode.addItem("رفع/خفض سعر البيع بنسبة %", "percent")
        self.value = QDoubleSpinBox()
        self.value.setRange(-90, 95)
        self.value.setValue(settings.get_float("target_margin_percent", 15))
        self.category = QComboBox()
        self.rounding = QComboBox()
        for label, v in [("بدون تقريب", 0.0), ("لأقرب 0.10", 0.1), ("لأقرب 0.50", 0.5), ("لأقرب 1", 1.0)]:
            self.rounding.addItem(label, v)
        self.rounding.setCurrentIndex(2)
        self.only_below = QCheckBox("فقط الأصناف التي هامشها أقل من المستهدف")
        self.only_below.setChecked(True)
        for wdg in (QLabel("الطريقة:"), self.mode, QLabel("القيمة:"), self.value, QLabel("الفئة:"), self.category,
                    QLabel("التقريب:"), self.rounding, self.only_below):
            f.addWidget(wdg)
        f.addStretch()
        pl.addLayout(f)
        r2 = QHBoxLayout()
        r2.addWidget(button("👁 معاينة", "secondaryBtn", self.preview))
        r2.addWidget(button("✓ تطبيق الأسعار الجديدة", "successBtn", self.apply_prices))
        r2.addStretch()
        self.prev_lbl = QLabel("")
        r2.addWidget(self.prev_lbl)
        pl.addLayout(r2)
        self.prev_table = Table(["الصنف", "التكلفة", "السعر الحالي", "السعر الجديد", "الهامش الجديد"], stretch=0)
        pl.addWidget(self.prev_table, 1)
        pl.addWidget(hint("مثال: هامش مستهدف 20% وتقريب لأقرب 0.50: صنف تكلفته 8 يصبح سعره 10. "
                          "المعاينة لا تغيّر شيئاً حتى تضغط «تطبيق». كل تغيير يُسجَّل في سجل العمليات."))
        self.tabs.addTab(pr, "تحديث الأسعار الجماعي")
        self.changes = []
        self.tabs.currentChanged.connect(lambda _: self.load())

    def refresh(self):
        cur = self.category.currentData()
        self.category.clear()
        self.category.addItem("كل الفئات", None)
        for c in products.get_categories():
            self.category.addItem(c, c)
        self.category.setCurrentIndex(max(0, self.category.findData(cur)))
        self.load()

    def load(self):
        i = self.tabs.currentIndex()
        if i == 0:
            self.load_cards()
        elif i == 1:
            rows = insights.abc_analysis(90)
            for k, cls in ((self.k_a, "A"), (self.k_b, "B"), (self.k_c, "C")):
                part = [r for r in rows if r["class"] == cls]
                k.set(str(len(part)), f"مبيعات {m(sum(r['revenue'] for r in part))}")
            colors = {"A": "#DCFCE7", "B": "#DBEAFE", "C": None}
            self.abc_table.set_rows([[r["class"], r["name"], r["category"] or "", qty_cell(r["qty"]), float(r["revenue"]),
                                      float(r["profit"]), (f"{r['share']:.2f}", r["share"]),
                                      (f"{r['cumulative']:.1f}", r["cumulative"]), qty_cell(r["stock"])] for r in rows],
                                    rows, [colors[r["class"]] for r in rows])
        elif i == 2:
            rows = insights.bought_together(60, 50)
            self.pairs.set_rows([[r["a"], r["b"], r["count"]] for r in rows])

    def load_cards(self):
        self.cards.setHtml(cards_html(insights.insights(30)))

    def on_action(self, action):
        if action == "insights:prices":
            self.only_below.setChecked(True)
            self.mode.setCurrentIndex(0)
            self.tabs.setCurrentIndex(3)
            self.preview()
        else:
            self.navigate.emit(action)

    def preview(self):
        self.changes = insights.price_update_preview(self.mode.currentData(), self.value.value(),
                                                     self.category.currentData(), rounding=self.rounding.currentData(),
                                                     only_below_target=self.only_below.isChecked())
        self.prev_table.set_rows([[c["name"], float(c["cost"]), float(c["old"]), float(c["new"]),
                                   (f"{(c['new'] - c['cost']) / c['new'] * 100:.1f}%" if c["new"] else "-", 0)]
                                  for c in self.changes], self.changes)
        self.prev_lbl.setText(f"{len(self.changes)} صنف سيتغير سعره")

    def apply_prices(self):
        if not self.changes:
            self.preview()
        if not self.changes:
            info(self, "لا توجد أسعار تحتاج تغييراً حسب هذه الشروط.")
            return
        if not require_permission(self, "inventory"):
            return
        if ask(self, f"تغيير سعر بيع {len(self.changes)} صنف؟\nتذكّر طباعة ملصقات الأسعار الجديدة من شاشة المخزون."):
            n = insights.apply_price_update(self.changes)
            self.changes = []
            self.preview()
            info(self, f"تم تحديث {n} سعر.")
