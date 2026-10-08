# -*- coding: utf-8 -*-
"""نافذة «نسخة جديدة»: ما الجديد، ثم «تحديث الآن» (تنزيل ← تحقق ← نسخة احتياطية ← تثبيت وإعادة فتح)"""

import threading

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QTextBrowser, QVBoxLayout

from core import i18n, remote, updates, vendor
from ui.widgets import button, hint, title, warn


class _Bridge(QObject):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)


class UpdateDialog(QDialog):
    def __init__(self, parent, info):
        super().__init__(parent)
        self.info = info
        self.cancel_flag = False
        self.path = None
        self.setWindowTitle("⬆ تحديث البرنامج")
        self.resize(560, 440)
        lay = QVBoxLayout(self)
        lay.addWidget(title(i18n.tr("⬆ نسخة جديدة {0} متاحة").format(info.get("version", "")), "pageTitle"))
        lay.addWidget(hint(i18n.tr("نسختك الحالية: {0}. بياناتك ومبيعاتك تبقى كما هي، ويُؤخذ لها نسخة احتياطية "
                                   "قبل التحديث.").format(vendor.VERSION)))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        body = info.get("body") or info.get("notes") or ""
        notes.setMarkdown(body) if body else notes.setPlainText(i18n.tr("تحسينات وإصلاحات."))
        lay.addWidget(notes, 1)
        self.step = QLabel("")
        self.step.setObjectName("subTitle")
        lay.addWidget(self.step)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.hide()
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.auto = updates.can_self_update(info)
        self.go_btn = button("⬆ تحديث الآن" if self.auto else "⬇ صفحة التحميل", "successBtn", self.start)
        row.addWidget(self.go_btn)
        self.later_btn = button("لاحقاً", "secondaryBtn", self.later)
        row.addWidget(self.later_btn)
        row.addStretch()
        lay.addLayout(row)
        if not self.auto:
            lay.addWidget(hint("هذه نسخة محمولة أو بلا ملف تثبيت: نزّل النسخة الجديدة من صفحة التحميل وشغّلها "
                               "(بياناتك في مجلد data تبقى كما هي)."))

    def later(self):
        self.cancel_flag = True
        self.reject()

    def start(self):
        if not self.auto:
            QDesktopServices.openUrl(QUrl(self.info.get("url", "")))
            return self.accept()
        win = self.parent().window() if self.parent() else None
        pos = getattr(win, "pages", {}).get("pos") if win is not None else None
        if pos is not None and getattr(pos, "cart", None):
            return warn(self, "أكمل البيع الحالي في نقطة البيع أو علّقه أولاً، ثم حدّث البرنامج.")
        self.go_btn.setEnabled(False)
        self.later_btn.setText(i18n.tr("إلغاء"))
        self.bar.show()
        self.bar.setRange(0, 0)
        self.step.setText(i18n.tr("1/3 — جارٍ تنزيل النسخة الجديدة…"))
        br = self._bridge = _Bridge()
        br.progress.connect(self._progress)
        br.done.connect(self._downloaded)
        br.failed.connect(self._failed)

        def run():
            try:
                path = updates.download(self.info, progress=lambda d, t: br.progress.emit(d, t),
                                        cancelled=lambda: self.cancel_flag)
                br.done.emit(path)
            except updates.Cancelled:
                pass
            except Exception as e:  # noqa: BLE001
                br.failed.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def _progress(self, done, total):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            self.bar.setFormat(f"{done / 1048576:.1f} / {total / 1048576:.1f} MB")
        else:
            self.bar.setFormat(f"{done / 1048576:.1f} MB")

    def _failed(self, msg):
        self.step.setText("⚠ " + i18n.tr(msg))
        self.bar.hide()
        self.go_btn.setEnabled(True)
        self.go_btn.setText(i18n.tr("↻ حاول مرة أخرى"))
        self.later_btn.setText(i18n.tr("لاحقاً"))

    def _downloaded(self, path):
        self.path = path
        self.bar.setRange(0, 0)
        self.step.setText(i18n.tr("2/3 — نسخة احتياطية من البيانات…"))
        QApplication.processEvents()
        if not remote.is_client():                     # الجهاز الرئيسي فقط يحمل البيانات
            try:
                from core import backup
                backup.create_backup(tag="before_update")
            except Exception as e:  # noqa: BLE001
                return self._failed(i18n.tr("تعذرت النسخة الاحتياطية، لم يُثبَّت شيء:") + f" {e}")
        self.step.setText(i18n.tr("3/3 — التثبيت… سيُغلق البرنامج ويُفتح من جديد خلال دقيقة"))
        QApplication.processEvents()
        try:
            updates.launch_installer(path, i18n.language())
        except Exception as e:  # noqa: BLE001  (رفض نافذة صلاحية المدير مثلاً)
            return self._failed(i18n.tr("لم يبدأ التثبيت:") + f" {e}")
        self.accept()
        win = self.parent().window() if self.parent() else None
        if win is not None and hasattr(win, "quit_for_update"):
            win.quit_for_update()
        else:
            QApplication.quit()


def open_update(parent, info):
    UpdateDialog(parent, info).exec()
