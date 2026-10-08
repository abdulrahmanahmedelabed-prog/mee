# -*- coding: utf-8 -*-
"""
الأعمال الثقيلة في الخلفية (تجهيز الطباعة الكبيرة): شريط تقدّم رفيع أسفل النافذة، والعمل يستمر عادياً.
عند الانتهاء: 📄 فتح، 🖨 طباعة، 💾 حفظ باسم.
"""

import os
import shutil
import tempfile
import threading
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy

from core import i18n
from ui.widgets import button, error, info

_BAR = None


class _Bridge(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)


class JobBar(QFrame):
    """شريط أسفل النافذة الرئيسية. عمل واحد في كل مرة، والبقية تنتظر بالترتيب"""

    def __init__(self, parent=None):
        super().__init__(parent)
        global _BAR
        _BAR = self
        self.setObjectName("jobBar")
        self.setStyleSheet("#jobBar { border-top: 1px solid palette(mid); }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(10)
        self.label = QLabel("")
        self.bar = QProgressBar()
        self.bar.setFixedHeight(10)
        self.bar.setTextVisible(False)
        self.bar.setMaximumWidth(360)
        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addStretch()
        self.open_btn = button("📄 فتح", "secondaryBtn", self.open_file)
        self.print_btn = button("🖨 طباعة", "primaryBtn", self.print_file)
        self.save_btn = button("💾 حفظ باسم", "secondaryBtn", self.save_as)
        self.cancel_btn = button("إلغاء", "ghostBtn", self.cancel)
        self.close_btn = button("✕", "ghostBtn", self.hide)
        for b in (self.open_btn, self.print_btn, self.save_btn, self.cancel_btn, self.close_btn):
            b.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            lay.addWidget(b)
        self.queue = []
        self.current = None
        self.result = None
        self.hide()

    # ---------------------------------------------------------------- تشغيل
    def submit(self, title, work, on_done=None, report=None):
        """work(progress, cancelled) يعمل في خيط خلفي ويرجع النتيجة (مسار PDF غالباً)"""
        self.queue.append((title, work, on_done, report))
        if self.current is None:
            self._next()

    def _next(self):
        if not self.queue:
            return
        title, work, on_done, report = self.queue.pop(0)
        self.current = {"title": title, "cancel": False, "on_done": on_done, "report": report, "start": time.time()}
        job = self.current
        br = _Bridge()
        job["bridge"] = br
        br.progress.connect(lambda i, n: self._progress(job, i, n))
        br.finished.connect(lambda res: self._done(job, res))
        br.failed.connect(lambda msg: self._failed(job, msg))
        self.label.setText(i18n.tr("⏳ جارٍ تجهيز {0}…").format(i18n.tr(title)))
        self.bar.setRange(0, 0)
        self.bar.show()
        self._buttons(working=True)
        self.show()

        def run():
            try:
                res = work(lambda i, n: br.progress.emit(i, n), lambda: job["cancel"])
                br.finished.emit(res)
            except Exception as e:  # noqa: BLE001
                br.failed.emit("" if e.__class__.__name__ == "Cancelled" else str(e))
        threading.Thread(target=run, daemon=True).start()

    def _buttons(self, working):
        self.cancel_btn.setVisible(working)
        for b in (self.open_btn, self.print_btn, self.save_btn):
            b.setVisible(not working)
        self.close_btn.setVisible(not working)

    def _progress(self, job, i, n):
        if job is not self.current:
            return
        self.bar.setRange(0, max(n, 1))
        self.bar.setValue(i)
        self.label.setText(i18n.tr("⏳ جارٍ تجهيز {0}… صفحة {1} من {2}").format(i18n.tr(job["title"]), i, n))

    def _done(self, job, res):
        self.current = None
        self.result = (job, res)
        if job.get("on_done"):
            job["on_done"](res)
        pages = res[1] if isinstance(res, tuple) else None
        secs = time.time() - job["start"]
        self.bar.hide()
        self.label.setText(i18n.tr("✓ جاهز: {0}").format(i18n.tr(job["title"]))
                           + (f" — {pages} " + i18n.tr("صفحة") if pages else "") + f"  ({secs:.1f} s)")
        self._buttons(working=False)
        has_file = bool(self._path())
        self.open_btn.setVisible(has_file)
        self.save_btn.setVisible(has_file)
        self.print_btn.setVisible(has_file and bool(job.get("report")))
        if not has_file:
            self.label.setText(i18n.tr("✓ أُرسل للطابعة: {0}").format(i18n.tr(job["title"]))
                               + (f" — {pages} " + i18n.tr("صفحة") if pages else ""))
        QTimer.singleShot(0, self._next)

    def _failed(self, job, msg):
        self.current = None
        self.hide()
        if msg:
            error(self.window(), i18n.tr("تعذر تجهيز {0}:").format(i18n.tr(job["title"])) + "\n" + msg)
        QTimer.singleShot(0, self._next)

    def cancel(self):
        if self.current:
            self.current["cancel"] = True
            self.label.setText(i18n.tr("جارٍ الإلغاء…"))

    # ---------------------------------------------------------------- بعد الانتهاء
    def _path(self):
        res = self.result[1] if self.result else None
        return res[0] if isinstance(res, tuple) else None

    def open_file(self):
        if self._path():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._path()))

    def save_as(self):
        src = self._path()
        if not src:
            return
        name = i18n.tr(self.result[0]["title"]) + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("حفظ PDF"), name, "PDF (*.pdf)")
        if path:
            shutil.copyfile(src, path)
            info(self.window(), i18n.tr("تم الحفظ"))

    def print_file(self):
        """اختيار الطابعة ثم الطباعة في الخلفية بنفس الرسم السريع"""
        if not self.result or not self.result[0].get("report"):
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        from ui import table_print
        rep = self.result[0]["report"]
        printer = QPrinter(QPrinter.HighResolution)
        table_print._page(printer, rep.landscape)
        if QPrintDialog(printer, self.window()).exec() != QPrintDialog.Accepted:
            return
        self.submit(self.result[0]["title"], lambda prog, canc: (None, table_print.render(rep, printer, prog, canc)))


def bar():
    return _BAR


def print_table(parent, report, title=None):
    """تجهيز جدول كبير كملف PDF في الخلفية مع شريط تقدّم (أو مباشرة إن لم توجد نافذة رئيسية)"""
    from ui import table_print
    fd, path = tempfile.mkstemp(prefix="report_", suffix=".pdf")
    os.close(fd)

    def work(progress, cancelled):
        printer = table_print.make_pdf_printer(path, report.landscape)
        return path, table_print.render(report, printer, progress, cancelled)

    b = bar()
    if b is None:                                 # بلا نافذة رئيسية (نوافذ مستقلة)
        work(None, None)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return path
    b.submit(title or report.title, work, report=report)
    return None
