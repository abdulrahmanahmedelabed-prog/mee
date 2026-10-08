# -*- coding: utf-8 -*-
"""
الطباعة الثقيلة دون تعطيل العمل: شريط تقدّم رفيع أسفل النافذة، والبيع وكل الشاشات تعمل عادياً.

كل عمل له مرحلتان:
1. تجهيز البيانات (استعلامات وحسابات بايثون) في خيط خلفي.
2. رسم الصفحات على خيط الواجهة صفحةً صفحة بين أحداث النافذة (نحو 30 ملّي ثانية في كل دورة)،
   فلا يعمل Qt في خيط خلفي أبداً (الأكثر أماناً مع خطوط ويندوز وطابعاتها).
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
SLICE_SECONDS = 0.03


class _Bridge(QObject):
    ready = Signal()
    failed = Signal(str)


class _Job:
    def __init__(self, title, prepare, pages, path, report):
        self.title, self.prepare, self.pages, self.path, self.report = title, prepare, pages, path, report
        self.cancel = False
        self.start = time.time()
        self.it = None
        self.count = 0


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
        self.last = None
        self.hide()

    # ---------------------------------------------------------------- تشغيل
    def submit(self, title, pages, prepare=None, path=None, report=None):
        """pages(): مولّد يرسم صفحة في كل خطوة ويُرجع (i, n). prepare(): تجهيز بيانات في خيط خلفي (اختياري)"""
        self.queue.append(_Job(title, prepare, pages, path, report))
        if self.current is None:
            self._next()

    def _next(self):
        if self.current is not None or not self.queue:
            return
        job = self.current = self.queue.pop(0)
        self.label.setText(i18n.tr("⏳ جارٍ تجهيز {0}…").format(i18n.tr(job.title)))
        self.bar.setRange(0, 0)
        self.bar.show()
        self._buttons(working=True)
        self.show()
        if job.prepare is None:
            QTimer.singleShot(0, lambda: self._begin(job))
            return
        br = _Bridge()
        job.bridge = br
        br.ready.connect(lambda: self._begin(job))
        br.failed.connect(lambda msg: self._fail(job, msg))

        def run():
            try:
                job.prepare()
                br.ready.emit()
            except Exception as e:  # noqa: BLE001
                br.failed.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def _begin(self, job):
        if job.cancel:
            return self._cancelled(job)
        try:
            job.it = job.pages()
        except Exception as e:  # noqa: BLE001
            return self._fail(job, str(e))
        QTimer.singleShot(0, lambda: self._step(job))

    def _step(self, job):
        """يرسم صفحات لمدة قصيرة ثم يعيد التحكم للنافذة"""
        if job.cancel:
            job.it.close()
            return self._cancelled(job)
        t = time.perf_counter()
        i = n = 0
        try:
            while time.perf_counter() - t < SLICE_SECONDS:
                i, n = next(job.it)
                job.count = n
        except StopIteration:
            return self._done(job)
        except Exception as e:  # noqa: BLE001
            job.it.close()
            return self._fail(job, str(e))
        self.bar.setRange(0, max(n, 1))
        self.bar.setValue(i)
        self.label.setText(i18n.tr("⏳ جارٍ تجهيز {0}… صفحة {1} من {2}").format(i18n.tr(job.title), i, n))
        QTimer.singleShot(0, lambda: self._step(job))

    def _buttons(self, working):
        self.cancel_btn.setVisible(working)
        for b in (self.open_btn, self.print_btn, self.save_btn):
            b.setVisible(not working)
        self.close_btn.setVisible(not working)

    def _done(self, job):
        self.current, self.last = None, job
        secs = time.time() - job.start
        pages = f" — {job.count} " + i18n.tr("صفحة") if job.count else ""
        self.bar.hide()
        self._buttons(working=False)
        has_file = bool(job.path)
        self.open_btn.setVisible(has_file)
        self.save_btn.setVisible(has_file)
        self.print_btn.setVisible(has_file and job.report is not None)
        if has_file:
            self.label.setText(i18n.tr("✓ جاهز: {0}").format(i18n.tr(job.title)) + pages + f"  ({secs:.1f} s)")
        else:
            self.label.setText(i18n.tr("✓ أُرسل للطابعة: {0}").format(i18n.tr(job.title)) + pages)
        QTimer.singleShot(0, self._next)

    def _cancelled(self, job):
        self.current = None
        self.hide()
        QTimer.singleShot(0, self._next)

    def _fail(self, job, msg):
        self.current = None
        self.hide()
        error(self.window(), i18n.tr("تعذر تجهيز {0}:").format(i18n.tr(job.title)) + "\n" + msg)
        QTimer.singleShot(0, self._next)

    def cancel(self):
        if self.current:
            self.current.cancel = True
            self.label.setText(i18n.tr("جارٍ الإلغاء…"))

    # ---------------------------------------------------------------- بعد الانتهاء
    def _path(self):
        return self.last.path if self.last else None

    def open_file(self):
        if self._path():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._path()))

    def save_as(self):
        src = self._path()
        if not src:
            return
        name = i18n.tr(self.last.title) + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, i18n.tr("حفظ PDF"), name, "PDF (*.pdf)")
        if path:
            shutil.copyfile(src, path)
            info(self.window(), i18n.tr("تم الحفظ"))

    def print_file(self):
        """اختيار الطابعة ثم الطباعة بنفس الرسم السريع، والعمل مستمر"""
        if not self.last or self.last.report is None:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        from ui import table_print
        rep = self.last.report
        printer = QPrinter(QPrinter.HighResolution)
        table_print._page(printer, rep.landscape)
        if QPrintDialog(printer, self.window()).exec() != QPrintDialog.Accepted:
            return
        self.submit(self.last.title, lambda: table_print.render_iter(rep, printer))


def bar():
    """شريط النافذة الرئيسية الحالية (أو None إن أُغلقت، مثلاً بعد تبديل اللغة)"""
    import shiboken6
    return _BAR if _BAR is not None and shiboken6.isValid(_BAR) else None


def print_table(parent, report, title=None):
    """تجهيز جدول كبير كملف PDF دون تعطيل العمل (أو مباشرة إن لم توجد نافذة رئيسية)"""
    from ui import table_print
    fd, path = tempfile.mkstemp(prefix="report_", suffix=".pdf")
    os.close(fd)

    def pages():
        return table_print.render_iter(report, table_print.make_pdf_printer(path, report.landscape))

    b = bar()
    if b is None:                                 # بلا نافذة رئيسية (نوافذ مستقلة)
        report.rows
        for _ in pages():
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return path
    b.submit(title or report.title, pages, prepare=lambda: report.rows, path=path, report=report)
    return None
