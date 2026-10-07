# -*- coding: utf-8 -*-
"""
التصميم: مظهر تطبيقات الجوال الحديثة على ويندوز —
خلفية هادئة، بطاقات بيضاء بزوايا دائرية وظلال ناعمة، أزرار مريحة للّمس، شريط تنقل أبيض بعلامة اختيار مستديرة،
وخط عربي حديث مضمَّن مع البرنامج (IBM Plex Sans Arabic، ترخيص مفتوح OFL).
"""

import os
import sys

COLORS = {
    "primary": "#2563EB",
    "primary_dark": "#1D4ED8",
    "primary_soft": "#EEF4FF",
    "success": "#12B76A",
    "danger": "#F04438",
    "warning": "#F79009",
    "bg": "#F4F6FB",
    "card": "#FFFFFF",
    "border": "#E9EDF5",
    "text": "#101828",
    "muted": "#667085",
}

FONT_FAMILY = "IBM Plex Sans Arabic"


def fonts_dir():
    base = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        base = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "ui")
    return os.path.join(base, "fonts")


def load_fonts():
    """تحميل الخط المضمَّن. يرجع اسم العائلة، أو None إن تعذر (فيُستخدم خط النظام)"""
    from PySide6.QtGui import QFontDatabase
    family = None
    d = fonts_dir()
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(d, f))
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                family = family or (fams[0] if fams else None)
    return family


def elevate(widget, blur=28, dy=6, alpha=22):
    """ظل ناعم تحت البطاقة (مثل تطبيقات الجوال)"""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(16, 24, 40, alpha))
    widget.setGraphicsEffect(fx)
    return widget


STYLE_SHEET = """
* {
    font-family: 'IBM Plex Sans Arabic', 'Segoe UI', 'Tahoma', 'Noto Sans Arabic', sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog { background-color: #F4F6FB; }
QWidget { color: #101828; }
QWidget#page { background-color: #F4F6FB; }
QToolTip { background: #101828; color: white; border: none; padding: 8px 10px; border-radius: 8px; }
QMessageBox { background: white; }
QMessageBox QLabel { font-size: 15px; }

/* ---------- الشريط الجانبي (قائمة التنقل) ---------- */
QFrame#sidebar { background-color: #FFFFFF; border-left: 1px solid #E9EDF5; }
QLabel#logoTile {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3B82F6, stop:1 #6366F1);
    color: white; border-radius: 14px; font-size: 22px; qproperty-alignment: AlignCenter;
}
QLabel#brand { color: #101828; font-size: 16px; font-weight: 700; padding: 0; }
QLabel#brandSub { color: #98A2B3; font-size: 12px; padding: 0; }
QLabel#navSection { color: #98A2B3; font-size: 11px; font-weight: 600; padding: 12px 22px 4px 22px; }
QPushButton#navBtn {
    background: transparent; color: #475467; text-align: right; padding: 10px 16px;
    border: none; border-radius: 12px; font-size: 14px; font-weight: 500; margin: 1px 12px;
}
QPushButton#navBtn:hover { background: #F4F6FB; color: #101828; }
QPushButton#navBtn:checked { background: #EEF4FF; color: #1D4ED8; font-weight: 700; }
QFrame#userCard { background: #F8FAFC; border: 1px solid #EEF1F6; border-radius: 16px; }
QLabel#avatar {
    background: #EEF4FF; color: #1D4ED8; border-radius: 18px; font-size: 15px; font-weight: 700;
    qproperty-alignment: AlignCenter;
}
QLabel#userName { font-size: 13px; font-weight: 600; color: #101828; }
QLabel#userRole { font-size: 11px; color: #98A2B3; }
QPushButton#iconBtn {
    background: transparent; color: #667085; border: none; border-radius: 10px; padding: 4px 6px; font-size: 15px;
}
QPushButton#iconBtn:hover { background: #EEF1F6; color: #101828; }

/* ---------- الشريط العلوي ---------- */
QFrame#topbar { background: #F4F6FB; border: none; }
QLabel#topTitle { font-size: 24px; font-weight: 700; color: #101828; }
QLabel#topSub { font-size: 12px; color: #98A2B3; }
QLabel#chip { background: white; color: #344054; border: 1px solid #E9EDF5; border-radius: 16px; padding: 6px 14px; font-weight: 500; }
QLabel#chipWarn { background: #FFFAEB; color: #B54708; border: 1px solid #FEDF89; border-radius: 16px; padding: 6px 14px; font-weight: 600; }
QLabel#chipOk { background: #ECFDF3; color: #027A48; border: 1px solid #ABEFC6; border-radius: 16px; padding: 6px 14px; font-weight: 600; }
QFrame#licenseBar { background: #FFFAEB; border: 1px solid #FEDF89; border-radius: 16px; }
QLabel#licenseText { color: #B54708; font-weight: 600; }

/* ---------- الأزرار ---------- */
QPushButton {
    background-color: #2563EB; color: white; border: none; border-radius: 12px;
    padding: 10px 18px; font-weight: 600; min-height: 22px;
}
QPushButton:hover { background-color: #1D4ED8; }
QPushButton:pressed { background-color: #1E40AF; }
QPushButton:disabled, QPushButton#successBtn:disabled, QPushButton#dangerBtn:disabled, QPushButton#warnBtn:disabled,
QPushButton#secondaryBtn:disabled, QPushButton#payBtn:disabled, QPushButton#ghostBtn:disabled, QPushButton#billBtn:disabled {
    background-color: #F2F4F7; color: #98A2B3; border: none;
}
QPushButton#successBtn { background-color: #12B76A; }
QPushButton#successBtn:hover { background-color: #039855; }
QPushButton#dangerBtn { background-color: #F04438; }
QPushButton#dangerBtn:hover { background-color: #D92D20; }
QPushButton#warnBtn { background-color: #F79009; }
QPushButton#warnBtn:hover { background-color: #DC6803; }
QPushButton#secondaryBtn { background-color: #EEF4FF; color: #1D4ED8; }
QPushButton#secondaryBtn:hover { background-color: #DCE7FF; }
QPushButton#ghostBtn { background: white; color: #344054; border: 1px solid #E4E7EC; }
QPushButton#ghostBtn:hover { background: #F9FAFB; }
QPushButton#payBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #12B76A, stop:1 #0E9F6E);
    font-size: 21px; font-weight: 700; padding: 18px; border-radius: 18px;
}
QPushButton#payBtn:hover { background: #039855; }
QPushButton#posBtn {
    background: white; color: #344054; border: 1px solid #EEF1F6; border-radius: 14px;
    padding: 10px 6px; font-weight: 600; font-size: 13px;
}
QPushButton#posBtn:hover { border-color: #93B4FF; background: #F5F8FF; color: #1D4ED8; }
QPushButton#favBtn {
    background: white; color: #101828; border: 1px solid #EEF1F6; border-radius: 16px;
    padding: 8px 4px; font-weight: 600; font-size: 13px; min-height: 52px;
}
QPushButton#favBtn:hover { border-color: #6CE9A6; background: #F6FEF9; }
QPushButton#billBtn {
    background: #F6FEF9; color: #027A48; border: 1px solid #D1FADF; font-size: 16px; padding: 10px; border-radius: 14px;
}
QPushButton#billBtn:hover { background: #ECFDF3; }

/* ---------- الإدخال (حقول ممتلئة بزوايا دائرية) ---------- */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background-color: #F4F6FB; border: 1.5px solid #F4F6FB; border-radius: 12px; padding: 8px 12px;
    selection-background-color: #2563EB; selection-color: white;
}
QLineEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover, QComboBox:hover, QDateEdit:hover { border-color: #E4E7EC; }
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus,
QPlainTextEdit:focus {
    border: 1.5px solid #2563EB; background-color: white;
}
QFrame#card QLineEdit, QFrame#card QDoubleSpinBox, QFrame#card QSpinBox, QFrame#card QComboBox,
QFrame#card QDateEdit, QFrame#card QTextEdit { background-color: #F4F6FB; }
QLineEdit#bigSearch {
    font-size: 18px; padding: 14px 18px; border-radius: 18px; border: 1.5px solid #E4E7EC; background: white;
}
QLineEdit#bigSearch:focus { border: 2px solid #2563EB; }
QLineEdit#askBox {
    background: white; border: 1.5px solid #DCE7FF; border-radius: 18px; padding: 8px 16px; color: #101828;
}
QLineEdit#askBox:focus { border: 2px solid #7C3AED; }
QDoubleSpinBox#bigMoney { font-size: 28px; font-weight: 700; padding: 10px; border-radius: 16px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: white; border: 1px solid #E9EDF5; border-radius: 12px; padding: 6px;
    selection-background-color: #EEF4FF; selection-color: #1D4ED8; outline: none;
}
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 20px; height: 20px; border-radius: 6px; border: 1.5px solid #D0D5DD; background: white; }
QCheckBox::indicator:checked { background: #2563EB; border-color: #2563EB; }
QRadioButton::indicator { width: 18px; height: 18px; }

/* ---------- الجداول (صفوف واسعة بلا خطوط شبكة) ---------- */
QTableWidget, QTableView {
    background-color: white; border: 1px solid #EEF1F6; border-radius: 16px;
    gridline-color: transparent; selection-background-color: #EEF4FF; selection-color: #101828;
    alternate-background-color: #FAFBFD; outline: none;
}
QHeaderView { background: transparent; }
QHeaderView::section {
    background-color: white; color: #667085; padding: 12px 10px; border: none;
    border-bottom: 1px solid #EEF1F6; font-weight: 600; font-size: 13px;
}
QTableWidget::item { padding: 6px 10px; border-bottom: 1px solid #F4F6FB; }
QTableWidget::item:selected { background: #EEF4FF; color: #101828; }
QTableWidget#cart { font-size: 15px; }
QTableCornerButton::section { background: white; border: none; }
/* حقول التعديل داخل الجداول (تعديل السعر/الكمية): بلا حشو كبير حتى لا تضيق وتختفي أرقامها */
QTableView QLineEdit, QTableView QAbstractSpinBox, QTableView QComboBox, QTableView QDateEdit {
    padding: 0px 6px; margin: 2px; border-radius: 6px; border: 1.5px solid #2563EB; background-color: white;
    min-height: 0px;
}

/* ---------- التبويبات (أزرار مقسّمة مثل تطبيقات الجوال) ---------- */
QTabWidget::pane { border: none; background: transparent; top: 6px; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent; color: #667085; padding: 9px 18px; margin: 2px 3px;
    border: none; border-radius: 12px; font-weight: 600;
}
QTabBar::tab:selected { background: white; color: #1D4ED8; border: 1px solid #E9EDF5; }
QTabBar::tab:hover:!selected { background: #EAEEF5; color: #101828; }

/* ---------- البطاقات ---------- */
QFrame#card { background-color: white; border-radius: 20px; border: 1px solid #EEF1F6; }
QFrame#totalsCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #101828, stop:1 #1D2939);
    border-radius: 22px;
}
QLabel#totalsLabel { color: #98A2B3; font-size: 14px; }
QLabel#totalsValue { color: white; font-size: 15px; font-weight: 600; }
QLabel#grandTotal { color: #32D583; font-size: 38px; font-weight: 700; }
QLabel#changeLabel { color: #FDB022; font-size: 16px; font-weight: 700; }

QLabel#titleLabel { font-size: 22px; font-weight: 700; color: #101828; }
QLabel#subTitle { font-size: 16px; font-weight: 700; color: #101828; }
QLabel#muted { color: #667085; }
QLabel#kpiIcon { border-radius: 14px; font-size: 18px; qproperty-alignment: AlignCenter; }
QLabel#kpiValue { font-size: 26px; font-weight: 700; }
QLabel#kpiTitle { font-size: 13px; color: #667085; font-weight: 500; }
QLabel#bigNumber { font-size: 30px; font-weight: 700; color: #101828; }
QLabel#hint { color: #667085; font-size: 12px; }

QGroupBox {
    background: white; border: 1px solid #EEF1F6; border-radius: 18px; margin-top: 16px;
    padding: 16px 12px 12px 12px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 12px; color: #344054; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #D0D5DD; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: #98A2B3; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px 4px; }
QScrollBar::handle:horizontal { background: #D0D5DD; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QSplitter::handle { background: transparent; }
QStatusBar { background: white; color: #475467; }
QProgressDialog { background: white; }
QProgressBar { background: #EEF1F6; border: none; border-radius: 6px; height: 12px; text-align: center; }
QProgressBar::chunk { background: #2563EB; border-radius: 6px; }
"""
