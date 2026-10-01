# -*- coding: utf-8 -*-
"""
تطبيق الترجمة على واجهة Qt دون تعديل الشاشات:
- كل نص يُعرض (عنوان، زر، تسمية، تبويب، عنصر قائمة، رأس جدول، رسالة) يمر عبر i18n.tr.
- الكود يقرأ النص الأصلي (العربي) عند الحاجة، فلا يتأثر أي منطق يعتمد على النصوص (أسماء التبويبات، طرق الدفع...).
- النصوص الممرّرة في المُنشئ مباشرة تُترجم عند ظهور العنصر (QEvent.Show).
يُفعَّل فقط عند اختيار لغة غير العربية.
"""

import re

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import (QApplication, QLabel, QAbstractButton, QGroupBox, QWidget, QLineEdit, QTextEdit,
                               QTabWidget, QComboBox, QTableWidget, QMessageBox, QInputDialog, QFileDialog,
                               QPlainTextEdit)

from core import i18n

ROLE = Qt.UserRole + 77
_installed = False
_NATIVE = {}        # الدوال الأصلية قبل الترجمة (لعرض نص كما هو، مثل اسم اللغة بحروفها)
_HTML = re.compile(r"<[a-zA-Z/][^>]*>")


def trq(text):
    if not isinstance(text, str):
        return text
    if _HTML.search(text):
        return re.sub(r">([^<>]+)<", lambda m: ">" + i18n.tr(m.group(1)) + "<", text) if text.lstrip().startswith("<") \
            else re.sub(r"([^<>]+)(?=<|$)", lambda m: i18n.tr(m.group(1)), text)
    return i18n.tr(text)


def direction():
    return Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight


TOUCH_STYLE = """
* { font-size: 16px; }
QPushButton { padding: 14px 18px; min-height: 30px; }
QPushButton#posBtn { min-height: 52px; font-size: 16px; }
QPushButton#favBtn { min-height: 70px; font-size: 16px; }
QTableWidget::item { padding: 10px 6px; }
QLineEdit#bigSearch { font-size: 22px; padding: 16px; }
QScrollBar:vertical { width: 22px; }
"""


def adapt_style(sheet):
    """قلب محاذاة التصميم للغات من اليسار لليمين، وتكبير العناصر لشاشات اللمس"""
    from core import config
    if str(config.get("touch_mode") or "0") == "1":
        sheet = sheet + TOUCH_STYLE
    if i18n.is_rtl():
        return sheet
    return sheet.replace("text-align: right", "text-align: left").replace("subcontrol-position: top right",
                                                                          "subcontrol-position: top left")


def _amp(text):
    """& في الأزرار والتبويبات تعني اختصاراً في Qt؛ نعرضها كما هي"""
    return text.replace("&", "&&") if isinstance(text, str) else text


def _patch_setter(cls, setter, getter=None, escape_amp=False):
    prop = "_i18n_" + setter
    native_set = getattr(cls, setter)
    _NATIVE[(cls, setter)] = native_set

    def set_text(self, text, *args):
        if isinstance(text, str) and i18n.ARABIC.search(text):
            self.setProperty(prop, text)
            out = trq(text)
            return native_set(self, _amp(out) if escape_amp and out != text else out, *args)
        self.setProperty(prop, None)
        return native_set(self, text, *args)
    setattr(cls, setter, set_text)
    if getter:
        native_get = getattr(cls, getter)

        def get_text(self):
            v = self.property(prop)
            return v if isinstance(v, str) else native_get(self)
        setattr(cls, getter, get_text)
    return native_set


def _patch_tabs():
    native_add, native_insert = QTabWidget.addTab, QTabWidget.insertTab
    native_set, native_get = QTabWidget.setTabText, QTabWidget.tabText

    def add(self, widget, *args):
        args = list(args)
        label = args[-1]
        args[-1] = _amp(i18n.tr(label))
        idx = native_add(self, widget, *args)
        self.tabBar().setTabData(idx, label)
        return idx

    def insert(self, index, widget, *args):
        args = list(args)
        label = args[-1]
        args[-1] = _amp(i18n.tr(label))
        idx = native_insert(self, index, widget, *args)
        self.tabBar().setTabData(idx, label)
        return idx

    def set_text(self, index, label):
        self.tabBar().setTabData(index, label)
        native_set(self, index, _amp(i18n.tr(label)))

    def get_text(self, index):
        d = self.tabBar().tabData(index)
        return d if isinstance(d, str) else native_get(self, index)
    QTabWidget.addTab, QTabWidget.insertTab, QTabWidget.setTabText, QTabWidget.tabText = add, insert, set_text, get_text


def _patch_combo():
    native_add, native_insert = QComboBox.addItem, QComboBox.insertItem
    native_current, native_item = QComboBox.currentText, QComboBox.itemText
    native_find, native_set_current, native_set_item = QComboBox.findText, QComboBox.setCurrentText, QComboBox.setItemText

    def add(self, *args, **kw):
        args = list(args)
        pos = 0 if isinstance(args[0], str) else 1
        text = args[pos]
        args[pos] = i18n.tr(text)
        native_add(self, *args, **kw)
        self.setItemData(self.count() - 1, text, ROLE)

    def add_items(self, texts):
        for t in texts:
            add(self, t)

    def insert(self, index, *args, **kw):
        args = list(args)
        pos = 0 if isinstance(args[0], str) else 1
        text = args[pos]
        args[pos] = i18n.tr(text)
        native_insert(self, index, *args, **kw)
        real = min(index, self.count() - 1) if index >= 0 else self.count() - 1
        self.setItemData(real, text, ROLE)

    def item_text(self, i):
        v = self.itemData(i, ROLE)
        return v if isinstance(v, str) else native_item(self, i)

    def current(self):
        t, i = native_current(self), self.currentIndex()
        if i >= 0 and native_item(self, i) == t:
            v = self.itemData(i, ROLE)
            if isinstance(v, str):
                return v
        return t

    def find(self, text, *args):
        for i in range(self.count()):
            if self.itemData(i, ROLE) == text:
                return i
        return native_find(self, text, *args)

    def set_current(self, text):
        i = find(self, text)
        if i >= 0:
            self.setCurrentIndex(i)
        else:
            native_set_current(self, text)

    def set_item(self, i, text):
        self.setItemData(i, text, ROLE)
        native_set_item(self, i, i18n.tr(text))
    QComboBox.addItem, QComboBox.addItems, QComboBox.insertItem = add, add_items, insert
    QComboBox.itemText, QComboBox.currentText, QComboBox.findText = item_text, current, find
    QComboBox.setCurrentText, QComboBox.setItemText = set_current, set_item


def _patch_statics():
    for name in ("information", "warning", "critical", "question"):
        native = getattr(QMessageBox, name)

        def make(native):
            def f(parent, title, text, *args, **kw):
                return native(parent, i18n.tr(title), i18n.tr(text), *args, **kw)
            return staticmethod(f)
        setattr(QMessageBox, name, make(native))

    for name in ("getText", "getDouble", "getInt", "getMultiLineText"):
        native = getattr(QInputDialog, name)

        def make(native):
            def f(parent, title, label, *args, **kw):
                return native(parent, i18n.tr(title), i18n.tr(label), *args, **kw)
            return staticmethod(f)
        setattr(QInputDialog, name, make(native))

    native_item = QInputDialog.getItem

    def get_item(parent, title, label, items, *args, **kw):
        shown = [i18n.tr(x) for x in items]
        val, ok = native_item(parent, i18n.tr(title), i18n.tr(label), shown, *args, **kw)
        if ok and val in shown:
            val = list(items)[shown.index(val)]
        return val, ok
    QInputDialog.getItem = staticmethod(get_item)

    for name in ("getSaveFileName", "getOpenFileName", "getExistingDirectory"):
        native = getattr(QFileDialog, name)

        def make(native):
            def f(parent=None, caption="", directory="", *args, **kw):
                return native(parent, i18n.tr(caption), i18n.tr(directory), *args, **kw)
            return staticmethod(f)
        setattr(QFileDialog, name, make(native))

    native_headers = QTableWidget.setHorizontalHeaderLabels
    QTableWidget.setHorizontalHeaderLabels = lambda self, labels: native_headers(self, [i18n.tr(x) for x in labels])


class _ShowFilter(QObject):
    """نصوص وُضعت في المُنشئ (QLabel("...")، QCheckBox("...")، QFormLayout.addRow("...")) تُترجم عند الظهور"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            try:
                if isinstance(obj, (QLabel, QAbstractButton)):
                    t = obj.text()
                    if t and i18n.ARABIC.search(t) and obj.property("_i18n_setText") is None:
                        obj.setText(t)
                elif isinstance(obj, QGroupBox) and i18n.ARABIC.search(obj.title() or ""):
                    obj.setTitle(obj.title())
                if isinstance(obj, QMessageBox):
                    obj.setText(i18n.tr(obj.text()))
                if isinstance(obj, QWidget) and obj.isWindow():
                    wt = obj.windowTitle()
                    if wt and i18n.ARABIC.search(wt):
                        obj.setWindowTitle(wt)
                    obj.setLayoutDirection(direction())
            except RuntimeError:
                pass
        return False


def install(app=None):
    """يُستدعى مرة واحدة بعد اختيار اللغة وقبل إنشاء النوافذ"""
    global _installed, _filter
    if _installed or i18n.is_rtl():
        return
    _installed = True
    _patch_setter(QLabel, "setText", "text")
    _patch_setter(QAbstractButton, "setText", "text", escape_amp=True)
    _patch_setter(QGroupBox, "setTitle", "title")
    _patch_setter(QWidget, "setWindowTitle")
    _patch_setter(QWidget, "setToolTip")
    _patch_setter(QLineEdit, "setPlaceholderText")
    _patch_setter(QTextEdit, "setPlaceholderText")
    _patch_setter(QPlainTextEdit, "setPlaceholderText")
    _patch_tabs()
    _patch_combo()
    _patch_statics()
    app = app or QApplication.instance()
    if app:
        app.setLayoutDirection(direction())
        _filter = _ShowFilter(app)
        app.installEventFilter(_filter)


def set_raw_text(button, text):
    """نص زر يظهر كما هو بدون ترجمة"""
    native = _NATIVE.get((QAbstractButton, "setText"))
    button.setProperty("_i18n_setText", text)          # يمنع ترجمته عند الظهور
    (native or QAbstractButton.setText)(button, text)


def apply_language(lang, app=None):
    i18n.set_language(lang)
    install(app)
