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
# الواجهة الإنجليزية تعرض أدلة إنجليزية كاملة (docs/en)، والعربية تعرض العربية ومعها الملخص الإنجليزي
GUIDES_EN = [("🧾 Cashier card", "en/Cashier_Card.md"), ("🎓 Complete training guide", "en/Training_Guide.md"),
             ("⭐ Product overview", "Product_Sheet_EN.md"), ("📚 Accounting made simple", "en/Accounting_Made_Simple.md"),
             ("⚖ How we compare", "en/Competitor_Comparison.md")]


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
        self.guides = (GUIDES_AR + [("📄 Product overview (English)", "Product_Sheet_EN.md")]) if i18n.is_rtl() \
            else GUIDES_EN
        for label, _ in self.guides:
            self.list.addItem(label)
        self.list.currentRowChanged.connect(self.show_guide)
        split.addWidget(self.list)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)       # النص والصور بعرض النافذة: تمرير عمودي فقط
        split.addWidget(self.view)
        split.setSizes([260, 900])
        lay.addWidget(split, 1)
        support = vendor.display_name() + (f" — واتساب {vendor.VENDOR_PHONE_DISPLAY}" if vendor.VENDOR_PHONE else "") + \
                  (f" — {i18n.tr(vendor.SUPPORT_HOURS)}" if vendor.VENDOR_PHONE else "")
        row = QHBoxLayout()
        row.addWidget(hint(f"الدعم الفني: {support}   •   {vendor.PRODUCT_NAME} v{vendor.VERSION}"))
        row.addStretch()
        row.addWidget(button("🎬 الفيديو التعريفي", "secondaryBtn", self.play_video, "فيديو قصير يعرّف بالبرنامج (دقيقة)"))
        if os.environ.get("SHOP_DEMO_ACTIVE") != "1":
            from ui.widgets import open_training
            row.addWidget(button("🎓 نسخة التدريب", "secondaryBtn", lambda: open_training(self),
                                 "برنامج كامل ببيانات سوبرماركت تجريبية للتعلّم، منفصل عن بيانات محلك"))
        row.addWidget(button("📲 ربط الجوال", "secondaryBtn", self.pair, "رمز تحميل تطبيق الجوال ورمز ربطه بالمحل"))
        row.addWidget(button("⬆ التحديثات", "secondaryBtn", self.check_updates, "التحقق من وجود نسخة أحدث وتثبيتها"))
        if vendor.VENDOR_PHONE:
            row.addWidget(button("📱 تواصل مع الدعم", "successBtn", self.contact))
        lay.addLayout(row)

    def check_updates(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt as _Qt
        from core import updates
        from ui.widgets import info, warn
        QApplication.setOverrideCursor(_Qt.WaitCursor)
        try:
            found = updates.check(timeout=8, raise_errors=True)
        except updates.UpdateError as e:
            return warn(self, i18n.tr(str(e)))
        finally:
            QApplication.restoreOverrideCursor()
        if not found:
            return info(self, i18n.tr("لديك أحدث نسخة ({0}).").format(vendor.VERSION))
        win = self.window()
        if hasattr(win, "_update_info"):
            win._update_info = found
        from ui.update_dialog import open_update
        open_update(self, found)

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
        self.view.setSearchPaths([docs_dir(), os.path.dirname(path)])   # صور الأدلة (docs/*.png)
        self.view.setMarkdown(text)
        self._fit_images()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.view.toPlainText():
            self._fit_images()

    def _fit_images(self):
        """الصور الأعرض من مساحة القراءة تُصغَّر لعرضها (لا تمرير أفقي)، والصغيرة تبقى بحجمها"""
        from PySide6.QtGui import QTextCursor, QImageReader
        maxw = max(200, self.view.viewport().width() - 40)
        doc = self.view.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if frag.isValid() and fmt.isImageFormat():
                    img = fmt.toImageFormat()
                    natural = getattr(self, "_img_sizes", {}).get(img.name())
                    if natural is None:
                        for base in self.view.searchPaths():
                            p = os.path.join(base, img.name())
                            if os.path.exists(p):
                                sz = QImageReader(p).size()
                                natural = (sz.width(), sz.height())
                                break
                        self.__dict__.setdefault("_img_sizes", {})[img.name()] = natural
                    if natural and natural[0] > 0:
                        w = min(natural[0], maxw)
                        img.setWidth(w)
                        img.setHeight(natural[1] * w / natural[0])
                        cur = QTextCursor(doc)
                        cur.setPosition(frag.position())
                        cur.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                        cur.setCharFormat(img)
                it += 1
            block = block.next()

    def play_video(self):
        """الفيديو الإعلاني داخل البرنامج (أو بمشغل الفيديو في الجهاز إن لم يتوفر التشغيل الداخلي)"""
        base = db.app_dir()
        import sys
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", base)
        name = "ad_horizontal.mp4"
        path = next((p for p in (os.path.join(base, "marketing", "ad", name), os.path.join(base, name))
                     if os.path.exists(p)), None)
        if not path:
            from ui.widgets import warn
            warn(self, "ملف الفيديو غير موجود في مجلد البرنامج.")
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            from PySide6.QtWidgets import QDialog
        except Exception:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(i18n.tr("الفيديو التعريفي"))
        dlg.resize(960, 560)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(0, 0, 0, 0)
        video = QVideoWidget()
        v.addWidget(video)
        player = QMediaPlayer(dlg)
        audio = QAudioOutput(dlg)
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        player.setSource(QUrl.fromLocalFile(path))
        dlg.finished.connect(player.stop)
        player.play()
        dlg.exec()

    def pair(self):
        from ui.pair_dialog import open_pairing
        open_pairing(self.window())

    def contact(self):
        from core import whatsapp, settings
        from ui.widgets import open_whatsapp
        msg = f"{settings.get('shop_name')}: "
        open_whatsapp(self, whatsapp.link("+" + vendor.VENDOR_PHONE, msg), msg)
