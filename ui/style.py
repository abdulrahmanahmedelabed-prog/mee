# -*- coding: utf-8 -*-
"""التصميم: ألوان هادئة، خطوط واضحة، أزرار كبيرة مناسبة لشاشات اللمس"""

COLORS = {
    "primary": "#2563EB",
    "primary_dark": "#1D4ED8",
    "success": "#16A34A",
    "danger": "#DC2626",
    "warning": "#D97706",
    "sidebar": "#0F172A",
    "sidebar_hover": "#1E293B",
    "bg": "#F1F5F9",
    "card": "#FFFFFF",
    "border": "#E2E8F0",
    "text": "#0F172A",
    "muted": "#64748B",
}

STYLE_SHEET = """
* {
    font-family: 'Segoe UI', 'Tahoma', 'Noto Sans Arabic', 'Noto Naskh Arabic', sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog { background-color: #F1F5F9; }
QWidget { color: #0F172A; }
QWidget#page { background-color: #F1F5F9; }
QToolTip { background: #0F172A; color: white; border: none; padding: 6px; }

/* ---------- الشريط الجانبي ---------- */
QFrame#sidebar { background-color: #0F172A; }
QLabel#brand { color: white; font-size: 18px; font-weight: 800; padding: 14px 12px 4px 12px; }
QLabel#brandSub { color: #94A3B8; font-size: 12px; padding: 0 12px 8px 12px; }
QPushButton#navBtn {
    background: transparent; color: #CBD5E1; text-align: right; padding: 8px 16px;
    border: none; border-radius: 10px; font-size: 14px; font-weight: 600; margin: 1px 8px;
}
QPushButton#navBtn:hover { background: #1E293B; color: white; }
QPushButton#navBtn:checked { background: #2563EB; color: white; }

/* ---------- الشريط العلوي ---------- */
QFrame#topbar { background: white; border-bottom: 1px solid #E2E8F0; }
QLabel#topTitle { font-size: 18px; font-weight: 800; }
QLabel#chip { background: #EFF6FF; color: #1D4ED8; border-radius: 12px; padding: 4px 12px; font-weight: 600; }
QLabel#chipWarn { background: #FEF3C7; color: #92400E; border-radius: 12px; padding: 4px 12px; font-weight: 600; }
QLabel#chipOk { background: #DCFCE7; color: #166534; border-radius: 12px; padding: 4px 12px; font-weight: 600; }

/* ---------- الأزرار ---------- */
QPushButton {
    background-color: #2563EB; color: white; border: none; border-radius: 8px;
    padding: 9px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #1D4ED8; }
QPushButton:pressed { background-color: #1E40AF; }
QPushButton:disabled, QPushButton#successBtn:disabled, QPushButton#dangerBtn:disabled, QPushButton#warnBtn:disabled,
QPushButton#secondaryBtn:disabled, QPushButton#payBtn:disabled, QPushButton#ghostBtn:disabled, QPushButton#billBtn:disabled {
    background-color: #E2E8F0; color: #94A3B8; border: none;
}
QPushButton#successBtn { background-color: #16A34A; }
QPushButton#successBtn:hover { background-color: #15803D; }
QPushButton#dangerBtn { background-color: #DC2626; }
QPushButton#dangerBtn:hover { background-color: #B91C1C; }
QPushButton#warnBtn { background-color: #D97706; }
QPushButton#warnBtn:hover { background-color: #B45309; }
QPushButton#secondaryBtn { background-color: #E2E8F0; color: #0F172A; }
QPushButton#secondaryBtn:hover { background-color: #CBD5E1; }
QPushButton#ghostBtn { background: transparent; color: #2563EB; border: 1px solid #BFDBFE; }
QPushButton#ghostBtn:hover { background: #EFF6FF; }
QPushButton#payBtn { background-color: #16A34A; font-size: 20px; font-weight: 800; padding: 16px; border-radius: 12px; }
QPushButton#payBtn:hover { background-color: #15803D; }
QPushButton#posBtn {
    background: white; color: #0F172A; border: 1px solid #E2E8F0; border-radius: 10px;
    padding: 10px 6px; font-weight: 700; font-size: 13px;
}
QPushButton#posBtn:hover { border-color: #2563EB; background: #EFF6FF; }
QPushButton#favBtn {
    background: white; color: #0F172A; border: 1px solid #E2E8F0; border-radius: 10px;
    padding: 8px 4px; font-weight: 700; font-size: 13px; min-height: 48px;
}
QPushButton#favBtn:hover { border-color: #16A34A; background: #F0FDF4; }
QPushButton#billBtn { background: #F0FDF4; color: #166534; border: 1px solid #BBF7D0; font-size: 16px; padding: 10px; }
QPushButton#billBtn:hover { background: #DCFCE7; }

/* ---------- الإدخال ---------- */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background-color: white; border: 1.5px solid #E2E8F0; border-radius: 8px; padding: 7px 10px;
    selection-background-color: #2563EB; selection-color: white;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {
    border: 1.5px solid #2563EB;
}
QLineEdit#bigSearch { font-size: 18px; padding: 12px 14px; border-radius: 12px; border: 2px solid #CBD5E1; }
QLineEdit#bigSearch:focus { border: 2px solid #2563EB; }
QDoubleSpinBox#bigMoney { font-size: 26px; font-weight: 800; padding: 8px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #DBEAFE; selection-color: #0F172A; }
QCheckBox { spacing: 8px; }

/* ---------- الجداول ---------- */
QTableWidget {
    background-color: white; border: 1px solid #E2E8F0; border-radius: 10px;
    gridline-color: #F1F5F9; selection-background-color: #DBEAFE; selection-color: #0F172A;
    alternate-background-color: #F8FAFC;
}
QHeaderView::section {
    background-color: #F8FAFC; color: #475569; padding: 9px 8px; border: none;
    border-bottom: 1px solid #E2E8F0; font-weight: 700;
}
QTableWidget::item { padding: 4px 6px; }
QTableWidget#cart { font-size: 15px; }

/* ---------- التبويبات ---------- */
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent; color: #64748B; padding: 10px 18px; margin-left: 2px;
    border-bottom: 3px solid transparent; font-weight: 700;
}
QTabBar::tab:selected { color: #2563EB; border-bottom: 3px solid #2563EB; }
QTabBar::tab:hover { color: #0F172A; }

/* ---------- البطاقات ---------- */
QFrame#card { background-color: white; border-radius: 14px; border: 1px solid #E2E8F0; }
QFrame#totalsCard { background-color: #0F172A; border-radius: 14px; }
QLabel#totalsLabel { color: #94A3B8; font-size: 14px; }
QLabel#totalsValue { color: white; font-size: 15px; font-weight: 700; }
QLabel#grandTotal { color: #4ADE80; font-size: 36px; font-weight: 900; }
QLabel#changeLabel { color: #FACC15; font-size: 16px; font-weight: 800; }

QLabel#titleLabel { font-size: 22px; font-weight: 800; color: #0F172A; }
QLabel#subTitle { font-size: 16px; font-weight: 800; color: #0F172A; }
QLabel#muted { color: #64748B; }
QLabel#kpiValue { font-size: 24px; font-weight: 800; }
QLabel#kpiTitle { font-size: 13px; color: #64748B; font-weight: 600; }
QLabel#bigNumber { font-size: 30px; font-weight: 900; color: #0F172A; }
QLabel#hint { color: #64748B; font-size: 12px; }

QGroupBox { background: white; border: 1px solid #E2E8F0; border-radius: 12px; margin-top: 14px; padding: 14px 10px 10px 10px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 10px; color: #334155; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QStatusBar { background: white; color: #475569; }
"""
