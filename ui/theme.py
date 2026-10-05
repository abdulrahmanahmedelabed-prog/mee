# -*- coding: utf-8 -*-
"""
السمة: فاتح / داكن / تلقائي (حسب إعداد ويندوز).
- التصميم مكتوب بألوان الوضع الفاتح، والوضع الداكن يُشتق منه بخريطة ألوان مدروسة التباين
  (نص أساسي على الخلفيات ≥ 12:1، النص الثانوي ≥ 4.5:1 حسب WCAG AA).
- لوحة ألوان Qt تُضبط صراحةً في الوضعين، فلا يكسر الوضع الداكن في ويندوز وضوحَ البرنامج الفاتح (والعكس).
- الألوان المكتوبة داخل الشاشات (أحمر للدين، أخضر للربح...) تُحوَّل تلقائياً لدرجات أفتح تُقرأ على الخلفية الداكنة.
- الطباعة (فواتير، تقارير) تبقى دائماً على ورق أبيض بحبر داكن.
"""

import re

LIGHT, DARK, AUTO = "light", "dark", "auto"
NAMES = {LIGHT: "☀ فاتح", DARK: "🌙 داكن", AUTO: "🖥 تلقائي (حسب النظام)"}

_mode = LIGHT          # السمة الفعلية المطبّقة الآن (فاتح أو داكن)

# ---------------------------------------------------------------------------
# خريطة الوضع الداكن (فاتح ← داكن). الخلفيات تصبح كحلية متدرجة، والنصوص فاتحة، والألوان الدلالية أسطع.
# ---------------------------------------------------------------------------
BG, SURFACE, SURFACE2, LINE, LINE2 = "#0E1525", "#172133", "#1D293D", "#28354C", "#3A4863"
TEXT, TEXT2, MUTED, FAINT = "#E8EDF5", "#C3CCDA", "#9AA6BA", "#8391A7"

SHEET_MAP = {
    # خلفيات
    "#F4F6FB": BG, "#FFFFFF": SURFACE, "#F8FAFC": SURFACE2, "#F9FAFB": SURFACE2, "#FAFBFD": "#1A2437",
    "#EEF1F6": LINE, "#E9EDF5": LINE, "#E4E7EC": LINE2, "#E2E8F0": LINE2, "#D0D5DD": "#46556F",
    "#CBD5E1": "#46556F", "#F2F4F7": "#222D42", "#EAEEF5": "#24304A", "#F1F5F9": "#1E2939",
    # نصوص
    "#101828": TEXT, "#0F172A": TEXT, "#1E293B": TEXT, "#344054": TEXT2, "#334155": TEXT2, "#475467": TEXT2,
    "#475569": TEXT2, "#667085": MUTED, "#64748B": MUTED, "#98A2B3": FAINT, "#94A3B8": FAINT,
    # أزرق (خلفيات ناعمة ونص عليها)
    "#EEF4FF": "#1C2B4B", "#EFF6FF": "#1C2B4B", "#EFF8FF": "#1C2B4B", "#F5F8FF": "#1C2B4B", "#DCE7FF": "#253A64",
    "#DBEAFE": "#253A64", "#1D4ED8": "#8AB4FF", "#175CD3": "#7CB4FF", "#93B4FF": "#4F7BD6",
    # أخضر
    "#ECFDF3": "#11301F", "#F6FEF9": "#11301F", "#F0FDF4": "#11301F", "#DCFCE7": "#14391F", "#D1FADF": "#1E5A38",
    "#ABEFC6": "#1E5A38", "#027A48": "#4ADE80", "#067647": "#4ADE80", "#6CE9A6": "#2F8F5B",
    # برتقالي / أصفر
    "#FFFAEB": "#33280F", "#FEF3C7": "#3A2E10", "#FFFBEB": "#33280F", "#FEDF89": "#6B5414", "#FDE68A": "#6B5414",
    "#B54708": "#FBBF24", "#92400E": "#FCD34D", "#FFF4ED": "#3A2412", "#C4320A": "#FB923C",
    # أحمر
    "#FEF3F2": "#3A1A1D", "#FEE2E2": "#3F1C20", "#FEF2F2": "#3A1A1D", "#FECDCA": "#7A2E2E", "#B42318": "#F87171",
    "#B91C1C": "#F87171",
}
# ألوان تُستخدم نصاً داخل الشاشات: أسطع في الداكن (لا تُطبَّق على الأزرار في ورقة التصميم)
INLINE_MAP = dict(SHEET_MAP, **{
    "#2563EB": "#60A5FA", "#16A34A": "#4ADE80", "#DC2626": "#F87171", "#D97706": "#FBBF24", "#7C3AED": "#A78BFA",
    "#9333EA": "#C084FC", "#0F766E": "#2DD4BF", "#0369A1": "#38BDF8",
})

# قواعد تُضاف بعد التحويل لما يختلف معناه في الداكن (أزرار وتلميحات وبطاقة الإجمالي)
DARK_EXTRA = f"""
QPushButton:hover {{ background-color: #1D4ED8; }}
QToolTip {{ background: #E8EDF5; color: #0E1525; }}
QFrame#totalsCard {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0A1020, stop:1 #1A2540);
                     border: 1px solid {LINE}; }}
QLabel#totalsValue {{ color: #FFFFFF; }}
QPushButton#ghostBtn {{ color: {TEXT2}; }}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit {{ color: {TEXT}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus,
QPlainTextEdit:focus {{ background-color: {SURFACE2}; }}
QCheckBox::indicator {{ border-color: #5B6B88; }}
QCalendarWidget QWidget {{ alternate-background-color: {SURFACE2}; }}
QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background: #1C2B4B; }}
QTextBrowser {{ background: {SURFACE}; color: {TEXT}; }}
"""

_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_WHITE_BG = re.compile(r"(background(?:-color)?\s*:\s*)white\b")


def is_dark():
    return _mode == DARK


def _sub(css, table):
    css = _WHITE_BG.sub(lambda m: m.group(1) + table["#FFFFFF"], css)
    return _HEX.sub(lambda m: table.get(m.group(0).upper(), m.group(0)), css)


def style(sheet):
    """ورقة التصميم حسب السمة الحالية"""
    if _mode != DARK:
        return sheet
    return _sub(sheet, SHEET_MAP) + DARK_EXTRA


def css(text):
    """تصميم مكتوب داخل شاشة: يُحوَّل للداكن عند الحاجة. ما يبدأ بـ /*fixed*/ يبقى كما هو (شاشة الزبون)"""
    if _mode != DARK or not text or text.startswith("/*fixed*/"):
        return text
    return _sub(text, INLINE_MAP)


def c(color):
    """لون واحد (لخلفيات صفوف الجداول والرسوم البيانية)"""
    if _mode != DARK or not color or not isinstance(color, str):
        return color
    if color.lower() == "white":
        return SURFACE
    return INLINE_MAP.get(color.upper(), color)


def html(text):
    """نص HTML معروض داخل البرنامج (بطاقات المستشار) — ليس للطباعة"""
    return css(text) if _mode == DARK else text


def system_is_dark():
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def resolve(choice):
    if choice == DARK or (choice == AUTO and system_is_dark()):
        return DARK
    return LIGHT


def palette(mode):
    from PySide6.QtGui import QPalette, QColor
    p = QPalette()
    if mode == DARK:
        vals = {QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: SURFACE, QPalette.AlternateBase: SURFACE2,
                QPalette.Text: TEXT, QPalette.Button: SURFACE2, QPalette.ButtonText: TEXT, QPalette.ToolTipBase: TEXT,
                QPalette.ToolTipText: BG, QPalette.PlaceholderText: FAINT, QPalette.Highlight: "#2563EB",
                QPalette.HighlightedText: "#FFFFFF", QPalette.Link: "#60A5FA", QPalette.BrightText: "#FFFFFF",
                QPalette.Light: LINE2, QPalette.Midlight: LINE, QPalette.Mid: LINE2, QPalette.Dark: "#0A0F1A",
                QPalette.Shadow: "#000000"}
    else:
        vals = {QPalette.Window: "#F4F6FB", QPalette.WindowText: "#101828", QPalette.Base: "#FFFFFF",
                QPalette.AlternateBase: "#FAFBFD", QPalette.Text: "#101828", QPalette.Button: "#FFFFFF",
                QPalette.ButtonText: "#101828", QPalette.ToolTipBase: "#101828", QPalette.ToolTipText: "#FFFFFF",
                QPalette.PlaceholderText: "#98A2B3", QPalette.Highlight: "#2563EB", QPalette.HighlightedText: "#FFFFFF",
                QPalette.Link: "#2563EB", QPalette.BrightText: "#FFFFFF", QPalette.Light: "#FFFFFF",
                QPalette.Midlight: "#EEF1F6", QPalette.Mid: "#D0D5DD", QPalette.Dark: "#98A2B3",
                QPalette.Shadow: "#101828"}
    for role, col in vals.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(FAINT if mode == DARK else "#98A2B3"))
    return p


_patched = False
_native = None


def _patch():
    """كل setStyleSheet داخل الشاشات يمر عبر css() فيتحول للداكن تلقائياً، ويُحفظ الأصل لإعادة التلوين لاحقاً"""
    global _patched, _native
    if _patched:
        return
    from PySide6.QtWidgets import QWidget
    _native = QWidget.setStyleSheet

    def setStyleSheet(self, text):
        if text or self.property("_theme_css"):
            self.setProperty("_theme_css", text)
        _native(self, css(text))
    QWidget.setStyleSheet = setStyleSheet
    _patched = True


def restyle(app):
    """تبديل السمة على النوافذ المفتوحة نفسها (بلا إعادة بناء ولا إعادة تحميل للبيانات):
    يعيد تلوين تصميم كل عنصر من أصله، ثم يستدعي retheme() لما يرسم ألوانه بنفسه (الجداول، الرسوم، بطاقات HTML)"""
    widgets = app.allWidgets()
    for w in widgets:
        orig = w.property("_theme_css")
        if orig:
            _native(w, css(orig))
    for w in widgets:
        fn = getattr(w, "retheme", None)
        if callable(fn):
            try:
                fn()
            except RuntimeError:          # عنصر داخلي حُذف (شاشة مقفلة أو مستبدلة) — لا شيء لإعادة تلوينه
                pass


def apply(app, choice=None):
    """تطبيق السمة على البرنامج كله. choice: light/dark/auto (الافتراضي من إعدادات الجهاز)"""
    global _mode
    from core import config
    from ui.style import STYLE_SHEET
    from ui.i18n_qt import adapt_style
    choice = choice or config.load().get("theme") or LIGHT
    _mode = resolve(choice)
    _patch()
    if not app.property("_fusion"):
        app.setStyle("Fusion")             # مظهر موحد لا يتأثر بإعداد ويندوز الداكن/الفاتح (مرة واحدة)
        app.setProperty("_fusion", True)
    app.setPalette(palette(_mode))
    sheet = adapt_style(style(STYLE_SHEET))
    if app.styleSheet() != sheet:
        app.setStyleSheet(sheet)
    return _mode
