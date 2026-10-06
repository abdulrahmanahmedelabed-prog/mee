# -*- coding: utf-8 -*-
"""مقارنة الباقات والترقية + لوحة «ميزة مقفلة» تظهر مكان الشاشة غير المشمولة في الباقة"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QGridLayout)

from core import plans, license, vendor
from ui.widgets import button, hint
from ui.style import elevate


def request_upgrade(parent, feature=None, tier=None):
    from core import whatsapp
    from ui.widgets import open_whatsapp
    msg = plans.upgrade_message(feature, tier)
    url = whatsapp.link("+" + vendor.VENDOR_PHONE, msg) if vendor.VENDOR_PHONE else None
    open_whatsapp(parent, url, msg)


def _status_line():
    st = license.status()
    if st["state"] == "trial":
        return f"🎁 أنت تجرّب باقة ماكس كاملة مجاناً — متبقٍ {st['days_left']} يوماً. بعدها ينتقل البرنامج للباقة " \
               f"المجانية تلقائياً: البيع لا يتوقف وكل بياناتك تبقى."
    return st["message"]


class PlanCard(QFrame):
    def __init__(self, tier, current, highlight=None, on_choose=None):
        super().__init__()
        self.setObjectName("card")
        elevate(self, 24, 4, 18)
        color = plans.COLORS[tier]
        is_current = tier == current
        border = color if (is_current or tier == highlight) else "#EEF1F6"
        self.setStyleSheet(f"QFrame#card {{ border: 2px solid {border}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)
        badge = "باقتك الحالية" if is_current else ("الأنسب لك" if tier == highlight else
                                                     ("الأكثر طلباً" if tier == plans.PRO else ""))
        top = QLabel(badge)
        top.setStyleSheet(f"color:{color}; font-weight:700; font-size:12px;")
        top.setVisible(bool(badge))
        lay.addWidget(top)
        name = QLabel(plans.label(tier))
        name.setStyleSheet(f"font-size:22px; font-weight:800; color:{color};")
        lay.addWidget(name)
        tag = QLabel(plans.TAGLINES[tier])
        tag.setObjectName("hint")
        tag.setWordWrap(True)
        lay.addWidget(tag)
        price, period = plans.prices()[tier]
        p = QLabel(price)
        p.setStyleSheet("font-size:26px; font-weight:800;")
        lay.addWidget(p)
        per = QLabel(period)
        per.setObjectName("hint")
        lay.addWidget(per)
        eq = plans.GLOBAL_EQUIVALENT.get(tier)
        if eq:
            cap = QLabel("بدل سعر مثيله العالمي:")
            cap.setObjectName("hint")
            lay.addWidget(cap)
            vs = QLabel(f"{eq[0]}  {eq[1]}")
            vs.setObjectName("hint")
            vs.setLayoutDirection(Qt.LeftToRight)
            vs.setAlignment((Qt.AlignRight if self.layoutDirection() == Qt.RightToLeft else Qt.AlignLeft) | Qt.AlignVCenter)
            vs.setStyleSheet("text-decoration: line-through;")
            vs.setToolTip("أقل من نصف سعر المنتج العالمي المماثل في القوة")
            lay.addWidget(vs)
        n = plans.TERMINALS[tier]
        dev = QLabel("🖥 " + ("أجهزة غير محدودة" if n == 0 else "جهاز واحد" if n == 1 else f"حتى {n} أجهزة"))
        dev.setStyleSheet("font-weight:600;")
        lay.addWidget(dev)
        line = QFrame()
        line.setStyleSheet("background:#EEF1F6; min-height:1px; max-height:1px;")
        lay.addWidget(line)
        prev = plans.TIERS[plans.rank(tier) - 1] if plans.rank(tier) else None
        if prev:
            inc = QLabel(f"كل ما في {plans.NAMES[prev]}، وأيضاً:")
            inc.setObjectName("hint")
            lay.addWidget(inc)
        for key, title, desc in plans.features_of(tier, only_new=True):
            row = QLabel(f"✓ {title}")
            row.setToolTip(desc)
            row.setWordWrap(True)
            row.setStyleSheet("font-weight:600;" if key in ("ask", "forecast", "seasons", "audit", "insights") else "")
            lay.addWidget(row)
        lay.addStretch()
        if tier != plans.FREE and not is_current and on_choose:
            b = button(f"اطلب {plans.NAMES[tier]}", "primaryBtn", lambda: on_choose(tier))
            b.setStyleSheet(f"background:{color}; color:white;")
            lay.addWidget(b)


class PlansDialog(QDialog):
    def __init__(self, parent=None, feature=None):
        super().__init__(parent)
        self.setWindowTitle("الباقات")
        self.resize(1180, 760)
        self.feature = feature
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        head = QLabel("💎 اختر الباقة المناسبة لمحلك")
        head.setObjectName("titleLabel")
        outer.addWidget(head)
        if feature in plans.FEATURES:
            tier, title, desc = plans.FEATURES[feature]
            msg = QLabel(f"🔒 «{title}» متاحة في باقة {plans.NAMES[tier]} وما فوقها — {desc}.")
            msg.setWordWrap(True)
            msg.setStyleSheet("background:#FFFAEB; color:#B54708; border:1px solid #FEDF89; border-radius:12px;"
                              " padding:10px 14px; font-weight:600;")
            outer.addWidget(msg)
        st = QLabel(_status_line())
        st.setWordWrap(True)
        st.setObjectName("hint")
        outer.addWidget(st)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(14)
        current = license.status().get("tier") or plans.FREE
        highlight = plans.required(feature) if feature in plans.FEATURES else None
        for i, tier in enumerate(plans.TIERS):
            grid.addWidget(PlanCard(tier, current, highlight, self.choose), 0, i)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)
        outer.addWidget(hint("كل الباقات تعمل بدون إنترنت على جهازك، وبياناتك ملكك دائماً. الترقية فورية بمفتاح تفعيل "
                             "لهذا الجهاز، وعند انتهاء الاشتراك يعود البرنامج للمجانية دون أن يتوقف البيع."))
        row = QHBoxLayout()
        row.addWidget(button("🔑 لديّ مفتاح تفعيل", "secondaryBtn", self.enter_key))
        row.addStretch()
        row.addWidget(button("إغلاق", "ghostBtn", self.reject))
        outer.addLayout(row)

    def choose(self, tier):
        request_upgrade(self, self.feature, tier)

    def enter_key(self):
        w = self.parent().window() if self.parent() else None
        self.accept()
        if w is not None and hasattr(w, "open_license"):
            w.open_license()


class LockedPanel(QWidget):
    """تظهر مكان الشاشة المقفلة: ماذا تقدم الميزة، وفي أي باقة، وزر الترقية"""
    upgrade = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.addStretch()
        box = QFrame()
        box.setObjectName("card")
        elevate(box)
        box.setMaximumWidth(640)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(34, 30, 34, 30)
        bl.setSpacing(10)
        self.icon = QLabel("🔒")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet("font-size:46px;")
        bl.addWidget(self.icon)
        self.title = QLabel()
        self.title.setObjectName("titleLabel")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        bl.addWidget(self.title)
        self.desc = QLabel()
        self.desc.setAlignment(Qt.AlignCenter)
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("font-size:15px;")
        bl.addWidget(self.desc)
        self.tier = QLabel()
        self.tier.setAlignment(Qt.AlignCenter)
        self.tier.setStyleSheet("font-weight:700;")
        bl.addWidget(self.tier)
        row = QHBoxLayout()
        row.addStretch()
        self.btn = button("💎 قارن الباقات وترقَّ", "primaryBtn", lambda: self.upgrade.emit(self.feature))
        row.addWidget(self.btn)
        row.addStretch()
        bl.addLayout(row)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(box)
        h.addStretch()
        lay.addLayout(h)
        lay.addStretch()
        self.feature = None

    def show_feature(self, feature):
        self.feature = feature
        tier, title, desc = plans.FEATURES[feature]
        self.title.setText(title)
        self.desc.setText(desc)
        self.tier.setText(f"متاحة في باقة {plans.label(tier)} وما فوقها")
        self.tier.setStyleSheet(f"font-weight:700; color:{plans.COLORS[tier]};")


def require(parent, feature):
    """للأزرار داخل الشاشات: True إن كانت الميزة متاحة، وإلا تُعرض مقارنة الباقات"""
    if plans.has(feature):
        return True
    PlansDialog(parent, feature).exec()
    return False
