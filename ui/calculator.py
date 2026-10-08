# -*- coding: utf-8 -*-
"""
الآلة الحاسبة وحاسبة التسعير، من أي شاشة (🧮 أعلى النافذة أو Ctrl+=).
- الحاسبة: أزرار وكتابة مباشرة، سجل للعمليات، «إدراج» النتيجة في آخر خانة كنت فيها، ونسخ.
- التسعير: من التكلفة والربح المطلوب إلى سعر البيع شاملاً الضريبة، أو العكس: كم أربح بهذا السعر؟
الحساب نفسه في core/calc.py (بلا eval).
"""

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from core import calc, i18n, settings
from ui.widgets import MoneySpin, button, card, hint, m

_WINDOW = None
_TARGET = [None]                 # آخر خانة رقم أو نص كان المستخدم فيها (خارج الحاسبة)

KEYS = [["C", "⌫", "%", "÷"],
        ["7", "8", "9", "×"],
        ["4", "5", "6", "−"],
        ["1", "2", "3", "+"],
        ["0", ".", "(", ")"]]


def _track(_old, new):
    w = new
    if isinstance(w, QLineEdit) and isinstance(w.parent(), QAbstractSpinBox):
        w = w.parent()
    if not isinstance(w, (QAbstractSpinBox, QLineEdit)):
        return
    win = w.window()
    if isinstance(win, CalculatorWindow) or getattr(win, "_is_pricing", False):
        return
    if isinstance(w, QLineEdit) and w.objectName() == "askBox":
        return
    _TARGET[0] = w


def track_focus():
    app = QApplication.instance()
    if app is not None and not getattr(app, "_calc_tracking", False):
        app.focusChanged.connect(_track)
        app._calc_tracking = True


def target():
    w = _TARGET[0]
    if w is None or not shiboken6.isValid(w) or not w.isVisible() or not w.isEnabled():
        return None
    if isinstance(w, QLineEdit) and w.isReadOnly():
        return None
    return w


def insert_value(widget, value):
    """يضع الرقم في الخانة: خانات الأرقام بقيمتها، وخانات النص (البحث، الكمية...) نصاً"""
    if isinstance(widget, QDoubleSpinBox):
        widget.setValue(round(value, widget.decimals()))
    elif isinstance(widget, QSpinBox):
        widget.setValue(int(round(value)))
    elif isinstance(widget, QLineEdit):
        widget.setText(fmt(value).replace(",", ""))
    else:
        return False
    widget.window().activateWindow()
    widget.setFocus()
    return True


def fmt(v):
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.6f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
class CalcPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        self.display = QLineEdit()
        self.display.setObjectName("bigSearch")
        self.display.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.display.setLayoutDirection(Qt.LeftToRight)
        self.display.setMinimumHeight(48)
        self.display.setStyleSheet("font-size: 22px; font-weight: 600;")
        self.display.setPlaceholderText("0")
        self.display.textChanged.connect(self.preview)
        self.display.returnPressed.connect(self.equals)
        lay.addWidget(self.display)
        self.result = QLabel("")
        self.result.setObjectName("hint")
        self.result.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.result.setLayoutDirection(Qt.LeftToRight)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.result)

        grid = QGridLayout()
        grid.setSpacing(6)
        for r, row in enumerate(KEYS):
            for c, k in enumerate(row):
                b = QPushButton(k)
                b.setObjectName("primaryBtn" if k in "÷×−+%" else "dangerBtn" if k == "C" else "secondaryBtn")
                b.setMinimumHeight(44)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, k=k: self.press(k))
                grid.addWidget(b, r, c)
        eq = QPushButton("=")
        eq.setObjectName("successBtn")
        eq.setMinimumHeight(44)
        eq.setFocusPolicy(Qt.NoFocus)
        eq.clicked.connect(self.equals)
        grid.addWidget(eq, len(KEYS), 0, 1, 4)
        grid.itemAtPosition(0, 0).widget().setToolTip("مسح (Esc)")
        wrap = QWidget()
        wrap.setLayoutDirection(Qt.LeftToRight)       # ترتيب الأزرار كحاسبة المحل في الواجهتين
        wrap.setLayout(grid)
        lay.addWidget(wrap)

        acts = QHBoxLayout()
        self.insert_btn = button("⤵ إدراج في الخانة", "primaryBtn", self.insert,
                                 "يضع النتيجة في آخر خانة كنت تكتب فيها (سعر، مبلغ، كمية...)")
        acts.addWidget(self.insert_btn, 1)
        acts.addWidget(button("📋 نسخ", "secondaryBtn", self.copy))
        lay.addLayout(acts)
        lay.addWidget(QLabel(i18n.tr("السجل")))
        self.history = QListWidget()
        self.history.setLayoutDirection(Qt.LeftToRight)
        self.history.setMinimumHeight(90)
        self.history.itemDoubleClicked.connect(lambda it: self.display.setText(it.data(Qt.UserRole)))
        self.history.setToolTip("انقر مرتين لاستخدام النتيجة")
        lay.addWidget(self.history, 1)
        lay.addWidget(hint("اكتب مباشرة: 12*3.5+4 أو 100+16% (يضيف 16%) أو 250-10% (خصم 10%). "
                           "وتعمل العمليات نفسها داخل خانات المبالغ في كل البرنامج."))
        self.value = None

    def press(self, k):
        t = self.display.text()
        if k == "C":
            self.display.clear()
            self.value = None
        elif k == "⌫":
            self.display.setText(t[:-1])
        else:
            if self.value is not None and t == fmt(self.value) and k[0].isdigit():
                t = ""                                 # رقم جديد بعد = يبدأ عملية جديدة
            self.display.setText(t + {"−": "-"}.get(k, k))
        self.display.setFocus()
        self.display.end(False)

    def preview(self, text):
        if not text.strip():
            self.result.setText("")
            return
        try:
            v = calc.evaluate(text)
            self.result.setText("= " + fmt(v) if calc.is_expression(text) else "")
        except ValueError:
            self.result.setText("")

    def equals(self):
        text = self.display.text().strip()
        if not text:
            return None
        try:
            v = calc.evaluate(text)
        except ValueError as e:
            self.result.setText("⚠ " + i18n.tr(str(e)))
            return None
        self.value = v
        if calc.is_expression(text):
            self.history.insertItem(0, f"{text} = {fmt(v)}")
            self.history.item(0).setData(Qt.UserRole, fmt(v).replace(",", ""))
            while self.history.count() > 30:
                self.history.takeItem(self.history.count() - 1)
        self.display.setText(fmt(v).replace(",", ""))
        self.result.setText("")
        return v

    def current(self):
        if not self.display.text().strip():
            return self.value
        try:
            return calc.evaluate(self.display.text())
        except ValueError:
            return None

    def insert(self):
        v = self.current()
        w = target()
        if v is None:
            self.result.setText("⚠ " + i18n.tr("لا توجد نتيجة بعد"))
            return False
        if w is None:
            self.result.setText("⚠ " + i18n.tr("انقر أولاً على الخانة التي تريد الإدراج فيها"))
            return False
        self.equals()
        return insert_value(w, v)

    def copy(self):
        v = self.current()
        if v is not None:
            QApplication.clipboard().setText(fmt(v).replace(",", ""))
            self.result.setText("✓ " + i18n.tr("تم النسخ"))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.press("C")
            return
        super().keyPressEvent(e)


# ---------------------------------------------------------------------------
ROUNDING = [("بلا تقريب", 0.0), ("لأقرب 0.05 للأعلى", 0.05), ("لأقرب 0.10 للأعلى", 0.10),
            ("لأقرب 0.25 للأعلى", 0.25), ("لأقرب 0.50 للأعلى", 0.50), ("لأقرب 1 للأعلى", 1.0)]


class PricingPanel(QWidget):
    """من التكلفة إلى السعر، أو من السعر إلى الربح. on_apply(price): زر «اعتماد السعر» (من نافذة المنتج)"""

    def __init__(self, parent=None, cost=0.0, price=0.0, on_apply=None):
        super().__init__(parent)
        self.on_apply = on_apply
        self._busy = False
        lay = QVBoxLayout(self)
        box, box_lay = card()
        form = QFormLayout()
        form.setSpacing(8)
        box_lay.addLayout(form)
        self.carton = MoneySpin(decimals=3)
        self.pieces = QSpinBox()
        self.pieces.setRange(1, 100000)
        self.pieces.setValue(1)
        self.pieces.setButtonSymbols(QSpinBox.NoButtons)
        self.pieces.setAlignment(Qt.AlignCenter)
        self.pieces.setToolTip("عدد الحبات في الكرتونة")
        self.cost = MoneySpin(decimals=4)
        self.vat = MoneySpin(maximum=100)
        vat_on = settings.get_bool("vat_enabled")
        self.vat.setValue(settings.get_float("vat_rate", 0) if vat_on else 0)
        self.mode = QComboBox()
        self.mode.addItems([i18n.tr("ربح % على التكلفة"), i18n.tr("هامش % من سعر البيع")])
        self.pct = MoneySpin(maximum=10000)
        self.pct.setValue(25)
        self.rounding = QComboBox()
        for label, _ in ROUNDING:
            self.rounding.addItem(i18n.tr(label))
        self.price = MoneySpin()
        self.price.setObjectName("bigMoney")
        self.price.setToolTip("اكتب سعراً لترى ربحك به، أو يُحسب من التكلفة والربح")
        row = QHBoxLayout()
        row.addWidget(self.carton, 2)
        row.addWidget(QLabel("÷"))
        row.addWidget(self.pieces, 1)
        form.addRow(i18n.tr("تكلفة الكرتونة ÷ عدد الحبات (اختياري):"), row)
        form.addRow(i18n.tr("تكلفة الحبة:"), self.cost)
        form.addRow(i18n.tr("الضريبة %:"), self.vat)
        prow = QHBoxLayout()
        prow.addWidget(self.mode, 2)
        prow.addWidget(self.pct, 1)
        form.addRow(i18n.tr("الربح المطلوب:"), prow)
        form.addRow(i18n.tr("تقريب السعر:"), self.rounding)
        form.addRow(i18n.tr("سعر البيع للمستهلك:"), self.price)
        lay.addWidget(box)
        self.summary = QLabel("")
        self.summary.setObjectName("card")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setMargin(12)
        lay.addWidget(self.summary)
        lay.addWidget(hint("السعر شامل الضريبة إذا كانت مفعّلة. غيّر الربح لترى السعر، أو اكتب السعر لترى ربحك وهامشك."))
        if on_apply:
            lay.addWidget(button("✓ اعتماد هذا السعر", "successBtn", self.apply))
        lay.addStretch()

        self.cost.setValue(cost or 0)
        self.carton.valueChanged.connect(self._from_carton)
        self.pieces.valueChanged.connect(self._from_carton)
        for w in (self.cost, self.vat, self.pct):
            w.valueChanged.connect(self.from_cost)
        self.mode.currentIndexChanged.connect(self.from_cost)
        self.rounding.currentIndexChanged.connect(self.from_cost)
        self.price.valueChanged.connect(self.from_price)
        if price:
            self.price.setValue(price)
            self.from_price()
        else:
            self.from_cost()

    def _from_carton(self):
        if self.carton.value() > 0:
            self.cost.setValue(self.carton.value() / max(self.pieces.value(), 1))

    def from_cost(self):
        if self._busy:
            return
        kw = {"markup": self.pct.value()} if self.mode.currentIndex() == 0 else {"margin": min(self.pct.value(), 99.9)}
        r = calc.pricing(self.cost.value(), self.vat.value(), round_to=ROUNDING[self.rounding.currentIndex()][1], **kw)
        self._busy = True
        self.price.setValue(r["gross"])
        self._busy = False
        self._show(r)

    def from_price(self):
        if self._busy:
            return
        r = calc.pricing(self.cost.value(), self.vat.value(), price=self.price.value())
        self._busy = True
        self.pct.setValue(max(r["markup"] if self.mode.currentIndex() == 0 else r["margin"], 0))
        self._busy = False
        self._show(r)

    def _show(self, r):
        self.result = r
        color = "#DC2626" if r["profit"] < 0 else "#16A34A"
        t = i18n.tr
        self.summary.setText(
            f"<b>{t('السعر قبل الضريبة')}:</b> {m(r['net'])} &nbsp; • &nbsp; <b>{t('الضريبة')}:</b> {m(r['vat'])}"
            f"<br><b>{t('السعر شامل الضريبة')}:</b> <span style='font-size:18px'><b>{m(r['gross'])}</b></span>"
            f"<br><span style='color:{color}'><b>{t('ربح الحبة')}:</b> {m(r['profit'])} &nbsp; • &nbsp; "
            f"{t('على التكلفة')} {r['markup']:.1f}% &nbsp; • &nbsp; {t('هامش من البيع')} {r['margin']:.1f}%</span>")

    def shelf_price(self):
        """السعر الذي يُكتب في المنتج: شامل الضريبة إذا كانت الأسعار تشملها، وإلا قبلها"""
        r = self.result
        if settings.get_bool("vat_enabled") and not settings.get_bool("prices_include_vat"):
            return r["net"]
        return r["gross"]

    def apply(self):
        if self.on_apply:
            self.on_apply(round(self.shelf_price(), 2))


# ---------------------------------------------------------------------------
class CalculatorWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧮 الآلة الحاسبة")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(400, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        self.calc = CalcPanel()
        self.pricing = PricingPanel()
        self.tabs.addTab(self.calc, i18n.tr("🧮 حاسبة"))
        self.tabs.addTab(self.pricing, i18n.tr("🏷 تسعير"))
        lay.addWidget(self.tabs)

    def showEvent(self, e):
        super().showEvent(e)
        if self.tabs.currentIndex() == 0:
            self.calc.display.setFocus()


def open_calculator(parent=None, tab=0):
    global _WINDOW
    track_focus()
    if _WINDOW is None or not shiboken6.isValid(_WINDOW):
        _WINDOW = CalculatorWindow(parent)
    _WINDOW.tabs.setCurrentIndex(tab)
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    return _WINDOW


def pricing_dialog(parent, cost=0.0, price=0.0):
    """حاسبة التسعير من نافذة المنتج أو المشتريات. يرجع السعر المعتمد أو None"""
    dlg = QDialog(parent)
    dlg._is_pricing = True
    dlg.setWindowTitle("🏷 حاسبة التسعير")
    dlg.resize(520, 520)
    out = []
    lay = QVBoxLayout(dlg)
    panel = PricingPanel(dlg, cost, price, on_apply=lambda p: (out.append(p), dlg.accept()))
    lay.addWidget(panel)
    dlg.panel = panel
    dlg.exec()
    return out[0] if out else None
