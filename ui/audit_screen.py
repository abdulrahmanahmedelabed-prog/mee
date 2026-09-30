# -*- coding: utf-8 -*-
"""شاشة التدقيق المالي الآلي: تشغيل إجراءات التدقيق، عرض الرأي والدرجة والملاحظات، وطباعة التقرير"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSplitter, QCheckBox,
                               QApplication)

from core import financial_audit, settings
from ui import printing
from ui.widgets import Table, button, page, hint, card, KpiCard, DateRange, m

SEV_COLORS = {"critical": "#B42318", "high": "#C4320A", "medium": "#B54708", "low": "#175CD3", "ok": "#067647"}
SEV_BG = {"critical": "#FEF3F2", "high": "#FFF4ED", "medium": "#FFFAEB", "low": "#EFF8FF", "ok": None}


class AuditScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.result = None

        head = QHBoxLayout()
        self.range = DateRange("هذه السنة")
        head.addWidget(self.range)
        head.addStretch()
        self.run_btn = button("▶ ابدأ التدقيق", "successBtn", self.run)
        head.addWidget(self.run_btn)
        self.print_btn = button("🖨 تقرير التدقيق", "secondaryBtn", self.print_report)
        self.print_btn.setEnabled(False)
        head.addWidget(self.print_btn)
        lay.addLayout(head)

        g = QGridLayout()
        g.setSpacing(14)
        self.k_score = KpiCard("درجة التدقيق", "#2563EB", "🎯")
        self.k_opinion = KpiCard("رأي المدقق", "#16A34A", "⚖")
        self.k_issues = KpiCard("ملاحظات تحتاج معالجة", "#DC2626", "🚩")
        self.k_ok = KpiCard("إجراءات سليمة", "#16A34A", "✅")
        for i, k in enumerate((self.k_score, self.k_opinion, self.k_issues, self.k_ok)):
            g.addWidget(k, 0, i)
            k.set("—")
        lay.addLayout(g)
        self.opinion = hint("يفحص البرنامج كل العمليات المسجّلة كما يفعل المدقق الخارجي: توازن الدفاتر، مطابقة الديون "
                            "والمخزون، اكتمال الفواتير، عجز الصندوق ومؤشرات التلاعب، أعمار الديون، البضاعة المنتهية والراكدة، "
                            "هامش الربح، الضريبة، والنسخ الاحتياطي. اختر الفترة واضغط «ابدأ التدقيق».")
        lay.addWidget(self.opinion)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.show_ok = QCheckBox("إظهار الإجراءات السليمة")
        self.show_ok.toggled.connect(self.fill)
        ll.addWidget(self.show_ok)
        self.table = Table(["الخطورة", "المجال", "الملاحظة", "المبلغ", "العدد"], stretch=2, sortable=False)
        self.table.itemSelectionChanged.connect(self.show_detail)
        ll.addWidget(self.table, 1)
        split.addWidget(left)

        det, dl = card()
        self.d_title = QLabel("اختر ملاحظة لعرض تفاصيلها")
        self.d_title.setObjectName("subTitle")
        self.d_title.setWordWrap(True)
        dl.addWidget(self.d_title)
        self.d_sev = QLabel("")
        dl.addWidget(self.d_sev)
        self.d_text = QLabel("")
        self.d_text.setWordWrap(True)
        dl.addWidget(self.d_text)
        self.d_action = QLabel("")
        self.d_action.setWordWrap(True)
        self.d_action.setObjectName("hint")
        dl.addWidget(self.d_action)
        self.d_samples = QLabel("")
        self.d_samples.setWordWrap(True)
        self.d_samples.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dl.addWidget(self.d_samples)
        dl.addStretch()
        split.addWidget(det)
        split.setSizes([760, 360])
        lay.addWidget(split, 1)

    def refresh(self):
        pass

    def run(self):
        a, b = self.range.range()
        self.run_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.result = financial_audit.run(a, b)
        finally:
            QApplication.restoreOverrideCursor()
            self.run_btn.setEnabled(True)
        r = self.result
        c = r["counts"]
        color = "#16A34A" if r["score"] >= 90 else "#2563EB" if r["score"] >= 75 else "#D97706" if r["score"] >= 60 else "#DC2626"
        self.k_score.set(f"{r['score']} / 100", r["grade"])
        self.k_score.value.setStyleSheet(f"color:{color};")
        self.k_opinion.set(r["opinion"], f"{r['procedures']} إجراء تدقيق")
        self.k_opinion.value.setStyleSheet(
            f"color:{'#DC2626' if c['critical'] else '#D97706' if c['high'] else '#16A34A'};")
        self.k_issues.set(str(c["critical"] + c["high"] + c["medium"] + c["low"]),
                          f"حرج {c['critical']} • مرتفع {c['high']} • متوسط {c['medium']} • منخفض {c['low']}")
        self.k_ok.set(str(c["ok"]))
        self.opinion.setText(r["opinion_text"])
        self.print_btn.setEnabled(True)
        self.fill()
        if self.table.rowCount():
            self.table.setCurrentCell(0, 0)

    def fill(self):
        if not self.result:
            return
        items = [f for f in self.result["findings"] if self.show_ok.isChecked() or f["severity"] != "ok"]
        self.table.set_rows([[financial_audit.SEVERITY[f["severity"]], f["area"], f["title"],
                              f["amount"] if f["amount"] is not None else "", f["count"] or ""] for f in items],
                            items, [SEV_BG[f["severity"]] for f in items])
        for r, f in enumerate(items):
            it = self.table.item(r, 0)
            it.setForeground(QColor(SEV_COLORS[f["severity"]]))

    def show_detail(self):
        f = self.table.selected_data()
        if not f:
            return
        self.d_title.setText(f["title"])
        self.d_sev.setText(f"الخطورة: {financial_audit.SEVERITY[f['severity']]} • {f['area']}"
                           + (f" • المبلغ: {m(f['amount'])}" if f["amount"] is not None else ""))
        self.d_sev.setStyleSheet(f"color:{SEV_COLORS[f['severity']]}; font-weight:600;")
        self.d_text.setText(f["detail"])
        self.d_action.setText(f"الإجراء المقترح: {f['action']}" if f["action"] else "")
        self.d_samples.setText("\n".join("• " + s for s in f["samples"]))

    def print_report(self):
        if self.result:
            printing.print_html(self, financial_audit.report_html(self.result, settings.get("shop_name") or ""),
                                width_mm=210, preview=True)
