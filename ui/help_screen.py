# -*- coding: utf-8 -*-
"""المساعدة داخل البرنامج: بطاقة الكاشير ودليل التدريب والمحاسبة ببساطة، مع بيانات الدعم"""

import os

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QTextBrowser, QSplitter, QLabel
from PySide6.QtCore import Qt

from core import db, vendor, i18n
from ui.widgets import page, hint, button

GUIDES_AR = [("🧾 بطاقة الكاشير", "04_بطاقة_الكاشير.md"), ("🎓 دليل التدريب الشامل", "03_دليل_التدريب.md"),
             ("⭐ مزايا البرنامج", "00_مزايا_البرنامج.md"), ("📚 المحاسبة ببساطة", "02_المحاسبة_ببساطة.md"),
             ("⚖ المقارنة مع المنافسين", "08_المقارنة_مع_المنافسين.md")]
GUIDES_EN = [("📄 Product overview", "Product_Sheet_EN.md")]


def docs_dir():
    base = db.app_dir()
    import sys
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", base)
    return os.path.join(base, "docs")


class HelpScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.guides = (GUIDES_AR + GUIDES_EN) if i18n.is_rtl() else (GUIDES_EN + GUIDES_AR)
        for label, _ in self.guides:
            self.list.addItem(label)
        self.list.currentRowChanged.connect(self.show_guide)
        split.addWidget(self.list)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        split.addWidget(self.view)
        split.setSizes([260, 900])
        lay.addWidget(split, 1)
        support = f"{vendor.VENDOR_NAME}" + (f" — واتساب {vendor.VENDOR_PHONE}" if vendor.VENDOR_PHONE else "") + \
                  (f" — {vendor.SUPPORT_HOURS}" if vendor.VENDOR_PHONE else "")
        row = QHBoxLayout()
        row.addWidget(hint(f"الدعم الفني: {support}   •   {vendor.PRODUCT_NAME} v{vendor.VERSION}"))
        row.addStretch()
        if vendor.VENDOR_PHONE:
            row.addWidget(button("📱 تواصل مع الدعم", "successBtn", self.contact))
        lay.addLayout(row)

    def refresh(self):
        if self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        if not self.view.toPlainText():
            self.show_guide(self.list.currentRow())

    def show_guide(self, row):
        if row < 0:
            return
        path = os.path.join(docs_dir(), self.guides[row][1])
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            text = i18n.tr("الدليل غير موجود في مجلد البرنامج")
        self.view.setSearchPaths([docs_dir()])   # صور الأدلة (docs/*.png)
        self.view.setMarkdown(text)

    def contact(self):
        from core import whatsapp, settings
        from ui.widgets import open_whatsapp
        msg = f"{settings.get('shop_name')}: "
        open_whatsapp(self, whatsapp.link("+" + vendor.VENDOR_PHONE, msg), msg)
