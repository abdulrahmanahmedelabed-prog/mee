# -*- coding: utf-8 -*-
"""عناصر واجهة مشتركة: جداول، بطاقات أرقام، فترات زمنية، رسائل، صلاحيات..."""

import csv
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal, QDate, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QPen
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QDateEdit, QComboBox, QMessageBox, QDoubleSpinBox, QFileDialog, QDialog, QFormLayout, QLineEdit,
    QDialogButtonBox, QPushButton, QToolTip
)

from core import auth
from core.utils import money, fmt_qty


# ---------------------------------------------------------------------------
# رسائل
# ---------------------------------------------------------------------------

def info(parent, text, title="تم"):
    QMessageBox.information(parent, title, text)


def warn(parent, text, title="تنبيه"):
    QMessageBox.warning(parent, title, text)


def error(parent, text, title="خطأ"):
    QMessageBox.critical(parent, title, str(text))


def ask(parent, text, title="تأكيد"):
    box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No, parent)
    box.button(QMessageBox.Yes).setText("نعم")
    box.button(QMessageBox.No).setText("لا")
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


def m(v):
    return f"{money(v):,.2f}"


# ---------------------------------------------------------------------------
# الجداول
# ---------------------------------------------------------------------------

class SortItem(QTableWidgetItem):
    """خلية تُرتَّب رقمياً عند الضغط على رأس العمود"""

    def __init__(self, text, sort_value=None):
        super().__init__(text)
        self._sort = sort_value

    def __lt__(self, other):
        a, b = self._sort, getattr(other, "_sort", None)
        if a is not None and b is not None:
            return a < b
        # ملاحظة: استدعاء super().__lt__ يسبب تكراراً لا نهائياً في PySide6، لذا نقارن النص مباشرة
        return self.text() < other.text()


class Table(QTableWidget):
    """جدول للعرض فقط مع دعم الترتيب وتخزين بيانات كل صف"""

    def __init__(self, headers, stretch=0, sortable=True, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        if stretch is not None:
            hh.setSectionResizeMode(stretch, QHeaderView.Stretch)
        hh.setHighlightSections(False)
        # بدون ترتيب افتراضي: نحافظ على الترتيب القادم من قاعدة البيانات حتى يضغط المستخدم على رأس عمود
        hh.setSortIndicator(-1, Qt.AscendingOrder)
        self._sortable = sortable
        self._data = []

    def set_rows(self, rows, data=None, colors=None):
        """rows: قائمة قوائم. الأرقام تُنسّق تلقائياً. data: كائن لكل صف. colors: لون خلفية لكل صف أو None"""
        self.setSortingEnabled(False)
        self.setRowCount(0)
        self.setRowCount(len(rows))
        self._data = list(data) if data is not None else [None] * len(rows)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                if isinstance(val, float):
                    item = SortItem(m(val), val)
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                elif isinstance(val, int) and not isinstance(val, bool):
                    item = SortItem(str(val), val)
                    item.setTextAlignment(Qt.AlignCenter)
                elif isinstance(val, tuple):  # (نص, قيمة ترتيب)
                    item = SortItem(val[0], val[1])
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item = SortItem("" if val is None else str(val))
                item.setData(Qt.UserRole, r)
                if colors and colors[r]:
                    item.setBackground(QColor(colors[r]))
                self.setItem(r, c, item)
        self.setSortingEnabled(self._sortable)

    def selected_data(self):
        items = self.selectedItems()
        if not items:
            return None
        idx = items[0].data(Qt.UserRole)
        return self._data[idx] if idx is not None and idx < len(self._data) else None

    def export_csv(self, parent, default_name="تقرير.csv"):
        path, _ = QFileDialog.getSaveFileName(parent, "تصدير إلى Excel (CSV)", default_name, "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([self.horizontalHeaderItem(c).text() for c in range(self.columnCount())])
            for r in range(self.rowCount()):
                w.writerow([(self.item(r, c).text() if self.item(r, c) else "") for c in range(self.columnCount())])
        info(parent, f"تم التصدير إلى:\n{path}")


def qty_cell(v):
    return (fmt_qty(v), float(v or 0))


# ---------------------------------------------------------------------------
# بطاقات وعناوين
# ---------------------------------------------------------------------------

def card(layout_cls=QVBoxLayout, margins=14, spacing=8):
    f = QFrame()
    f.setObjectName("card")
    lay = layout_cls(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return f, lay


def title(text, obj="titleLabel"):
    lbl = QLabel(text)
    lbl.setObjectName(obj)
    return lbl


def hint(text):
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


def button(text, obj=None, slot=None, tooltip=None, shortcut=None):
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if slot:
        b.clicked.connect(slot)
    if shortcut:
        b.setShortcut(shortcut)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class KpiCard(QFrame):
    def __init__(self, label, color="#2563EB", icon=""):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        self.title = QLabel(f"{icon}  {label}" if icon else label)
        self.title.setObjectName("kpiTitle")
        self.value = QLabel("0")
        self.value.setObjectName("kpiValue")
        self.value.setStyleSheet(f"color: {color};")
        self.sub = QLabel("")
        self.sub.setObjectName("hint")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value, sub=""):
        self.value.setText(value)
        self.sub.setText(sub)


def page():
    w = QWidget()
    w.setObjectName("page")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    return w, lay


# ---------------------------------------------------------------------------
# إدخال المبالغ
# ---------------------------------------------------------------------------

class MoneySpin(QDoubleSpinBox):
    def __init__(self, maximum=100_000_000, decimals=2, big=False, allow_negative=False):
        super().__init__()
        self.setDecimals(decimals)
        self.setMaximum(maximum)
        self.setMinimum(-maximum if allow_negative else 0)
        self.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.setGroupSeparatorShown(True)
        self.setAlignment(Qt.AlignCenter)
        if big:
            self.setObjectName("bigMoney")
            self.setMinimumHeight(56)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)


# ---------------------------------------------------------------------------
# اختيار فترة زمنية مع اختصارات
# ---------------------------------------------------------------------------

class DateRange(QWidget):
    changed = Signal()

    PRESETS = ["اليوم", "أمس", "آخر 7 أيام", "هذا الشهر", "الشهر الماضي", "هذه السنة", "مخصص"]

    def __init__(self, default="اليوم"):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.preset = QComboBox()
        self.preset.addItems(self.PRESETS)
        self.d_from = QDateEdit(calendarPopup=True)
        self.d_to = QDateEdit(calendarPopup=True)
        for d in (self.d_from, self.d_to):
            d.setDisplayFormat("yyyy-MM-dd")
            d.setDate(QDate.currentDate())
            d.dateChanged.connect(self._manual)
        lay.addWidget(QLabel("الفترة:"))
        lay.addWidget(self.preset)
        lay.addWidget(QLabel("من"))
        lay.addWidget(self.d_from)
        lay.addWidget(QLabel("إلى"))
        lay.addWidget(self.d_to)
        self._busy = False
        self.preset.currentTextChanged.connect(self._apply_preset)
        self.preset.setCurrentText(default)
        self._apply_preset(default)

    def _apply_preset(self, name):
        t = date.today()
        ranges = {
            "اليوم": (t, t),
            "أمس": (t - timedelta(days=1), t - timedelta(days=1)),
            "آخر 7 أيام": (t - timedelta(days=6), t),
            "هذا الشهر": (t.replace(day=1), t),
            "الشهر الماضي": ((t.replace(day=1) - timedelta(days=1)).replace(day=1), t.replace(day=1) - timedelta(days=1)),
            "هذه السنة": (t.replace(month=1, day=1), t),
        }
        if name in ranges:
            a, b = ranges[name]
            self._busy = True
            self.d_from.setDate(QDate(a.year, a.month, a.day))
            self.d_to.setDate(QDate(b.year, b.month, b.day))
            self._busy = False
            self.changed.emit()

    def _manual(self):
        if not self._busy:
            self.preset.blockSignals(True)
            self.preset.setCurrentText("مخصص")
            self.preset.blockSignals(False)
            self.changed.emit()

    def range(self):
        a = self.d_from.date().toString("yyyy-MM-dd")
        b = self.d_to.date().toString("yyyy-MM-dd")
        return (a, b) if a <= b else (b, a)


# ---------------------------------------------------------------------------
# الصلاحيات: إذا لم يملك المستخدم الصلاحية يُطلب إذن مدير فوراً
# ---------------------------------------------------------------------------

class ManagerOverrideDialog(QDialog):
    def __init__(self, parent, perm_label):
        super().__init__(parent)
        self.setWindowTitle("مطلوب إذن المدير")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"هذه العملية ({perm_label}) تحتاج موافقة مدير."))
        self.user = QLineEdit()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        lay.addRow("اسم المدير:", self.user)
        lay.addRow("كلمة المرور:", self.pw)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("موافقة")
        bb.button(QDialogButtonBox.Cancel).setText("إلغاء")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)


def require_permission(parent, perm):
    if auth.has_permission(perm):
        return True
    dlg = ManagerOverrideDialog(parent, auth.PERMISSIONS.get(perm, perm))
    if dlg.exec() == QDialog.Accepted:
        u = auth.authenticate(dlg.user.text(), dlg.pw.text())
        if u and auth.has_permission(perm, u):
            from core import audit
            audit.log("موافقة مدير", f"{u['username']} وافق على: {auth.PERMISSIONS.get(perm, perm)}")
            return True
        warn(parent, "بيانات المدير غير صحيحة أو لا يملك هذه الصلاحية.")
    return False


def ok_cancel(dialog, layout, ok_text="حفظ"):
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(ok_text)
    bb.button(QDialogButtonBox.Cancel).setText("إلغاء")
    bb.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
    bb.accepted.connect(dialog.accept)
    bb.rejected.connect(dialog.reject)
    layout.addRow(bb) if isinstance(layout, QFormLayout) else layout.addWidget(bb)
    return bb


# ---------------------------------------------------------------------------
# رسم بياني بسيط بالأعمدة (بدون مكتبات إضافية)
# ---------------------------------------------------------------------------

class BarChart(QWidget):
    def __init__(self, color="#2563EB", height=220):
        super().__init__()
        self.setMinimumHeight(height)
        self.color = QColor(color)
        self.labels, self.values, self.tips = [], [], []
        self.setMouseTracking(True)
        self._bars = []

    def set_data(self, labels, values, tips=None):
        self.labels, self.values = list(labels), [float(v or 0) for v in values]
        self.tips = tips or [m(v) for v in self.values]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top, bottom, side = 24, 28, 10
        p.fillRect(self.rect(), QColor("white"))
        n = len(self.values)
        self._bars = []
        if not n:
            return
        mx = max(max(self.values), 1)
        slot = (w - 2 * side) / n
        bw = max(4, slot * 0.62)
        f = QFont(self.font())
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QPen(QColor("#E2E8F0")))
        p.drawLine(side, h - bottom, w - side, h - bottom)
        step = max(1, n // 14)
        for i, v in enumerate(self.values):
            # الترتيب من اليسار لليمين زمنياً
            x = side + i * slot + (slot - bw) / 2
            bh = (h - top - bottom) * (v / mx) if v > 0 else 0
            rect = QRectF(x, h - bottom - bh, bw, bh)
            self._bars.append((QRectF(x, top, bw, h - top - bottom), i))
            p.setPen(Qt.NoPen)
            p.setBrush(self.color if v > 0 else QColor("#CBD5E1"))
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(QColor("#64748B"))
            if i % step == 0 or i == n - 1:
                p.drawText(QRectF(x - slot / 2, h - bottom + 4, bw + slot, 18), Qt.AlignCenter, self.labels[i])
            if v > 0 and n <= 16:
                p.setPen(QColor("#0F172A"))
                p.drawText(QRectF(x - slot / 2, h - bottom - bh - 18, bw + slot, 16), Qt.AlignCenter, f"{v:,.0f}")
        p.end()

    def mouseMoveEvent(self, e):
        for rect, i in self._bars:
            if rect.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(), f"{self.labels[i]}: {self.tips[i]}", self)
                return
        QToolTip.hideText()


def open_whatsapp(parent, url, fallback_text=None):
    """يفتح واتساب والرسالة جاهزة. إذا لم يوجد رقم هاتف تُعرض الرسالة للنسخ."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    if url:
        QDesktopServices.openUrl(QUrl(url))
        return True
    if fallback_text is not None:
        from ui.dialogs import TextDialog
        TextDialog(parent, "لا يوجد رقم هاتف صالح - انسخ الرسالة", fallback_text).exec()
    return False
