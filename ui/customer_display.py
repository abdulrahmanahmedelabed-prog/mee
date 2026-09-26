# -*- coding: utf-8 -*-
"""
شاشة الزبون: تُعرض على الشاشة الثانية (أو شاشة صغيرة موجهة للزبون) وتُظهر الأصناف والإجمالي
وتوفير العروض، ثم «شكراً — الباقي» بعد الدفع. تزيد ثقة الزبون وتقلل الأخطاء والخلافات عند الكاشير.
التفعيل: الإعدادات ← الطباعة ودرج النقود ← «شاشة الزبون».
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame

from core import settings, config
from core.utils import fmt_qty, money

_INSTANCE = None


def enabled():
    return str(config.get("customer_display") or "0") == "1"


def get():
    """نافذة شاشة الزبون (تُنشأ عند أول استخدام) أو None إن لم تكن مفعّلة"""
    global _INSTANCE
    if not enabled():
        if _INSTANCE:
            _INSTANCE.hide()
        return None
    if _INSTANCE is None:
        _INSTANCE = CustomerDisplay()
    return _INSTANCE


def _m(v):
    return f"{money(v):,.2f}"


class CustomerDisplay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("شاشة الزبون")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("QWidget#cd { background:#0F172A; } QLabel { color:white; background:transparent; }")
        self.setObjectName("cd")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 30, 40, 30)
        self.shop = QLabel()
        self.shop.setAlignment(Qt.AlignCenter)
        self.shop.setStyleSheet("font-size:34px; font-weight:900; color:#93C5FD;")
        lay.addWidget(self.shop)
        line = QFrame()
        line.setStyleSheet("background:#1E293B; min-height:2px; max-height:2px;")
        lay.addWidget(line)
        self.items = QLabel()
        self.items.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.items.setStyleSheet("font-size:26px; line-height:150%;")
        self.items.setTextFormat(Qt.RichText)
        lay.addWidget(self.items, 1)
        self.saving = QLabel()
        self.saving.setAlignment(Qt.AlignCenter)
        self.saving.setStyleSheet("font-size:26px; font-weight:800; color:#F9A8D4;")
        lay.addWidget(self.saving)
        self.total = QLabel()
        self.total.setAlignment(Qt.AlignCenter)
        self.total.setStyleSheet("font-size:72px; font-weight:900; color:#4ADE80;")
        lay.addWidget(self.total)
        self.footer = QLabel()
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setStyleSheet("font-size:24px; color:#FACC15; font-weight:800;")
        lay.addWidget(self.footer)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.idle)
        self.place()
        self.idle()

    def place(self):
        screens = QGuiApplication.screens()
        target = screens[1] if len(screens) > 1 else screens[0]
        g = target.geometry()
        if len(screens) > 1:
            self.setGeometry(g)
            self.showFullScreen()
        else:
            self.resize(800, 600)   # شاشة واحدة: نافذة يمكن سحبها (للتجربة)
            self.show()

    def _sym(self):
        return settings.get("currency_symbol") or ""

    def idle(self):
        self.shop.setText(f"🏪 {settings.get('shop_name')}")
        self.items.setText(f"<div style='text-align:center; font-size:40px; color:#CBD5E1'><br><br>أهلاً وسهلاً بكم 🌷</div>")
        self.saving.setText("")
        self.total.setText("")
        self.footer.setText(settings.get("receipt_footer") or "")

    def show_cart(self, cart, totals, discounts=None):
        if not cart:
            if not self._timer.isActive():   # لا نمسح رسالة «شكراً — الباقي» فور تفريغ السلة
                self.idle()
            return
        self._timer.stop()
        self.shop.setText(f"🏪 {settings.get('shop_name')}")
        rows = "".join(
            f"<tr><td style='padding:4px 0'>{it['product_name']}</td>"
            f"<td style='padding:4px 20px; color:#94A3B8'>× {fmt_qty(it['quantity'])}</td>"
            f"<td style='padding:4px 0; text-align:left'>{_m(it['quantity'] * it['unit_price'])}</td></tr>"
            for it in cart[-9:])
        more = f"<div style='color:#64748B; font-size:20px'>+ {len(cart) - 9} أصناف أخرى</div>" if len(cart) > 9 else ""
        self.items.setText(f"{more}<table width='100%'>{rows}</table>")
        saved = (discounts or {}).get("total", 0) or totals.get("discount", 0)
        self.saving.setText(f"🎁 وفّرت {_m(saved)} {self._sym()}" if saved else "")
        self.total.setText(f"{_m(totals['total'])} {self._sym()}")
        self.footer.setText(f"عدد الأصناف: {len(cart)}")

    def show_paid(self, total, change, points=0):
        self.items.setText(f"<div style='text-align:center; font-size:44px'><br>شكراً لتسوقكم 🌷</div>")
        self.saving.setText(f"🎁 +{points:g} نقطة" if points else "")
        self.total.setText(f"الباقي: {_m(change)} {self._sym()}" if change else f"{_m(total)} {self._sym()} ✓")
        self.footer.setText(settings.get("receipt_footer") or "")
        self._timer.start(8000)
