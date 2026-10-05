# -*- coding: utf-8 -*-
"""
مدير التفعيل — نافذة للمطوّر لإصدار مفاتيح التفعيل بدون أوامر (لا تُسلَّم للزبائن أبداً).
التشغيل: انقر مرتين على license_manager.bat  (أو: python tools/license_manager.py)
"""

import csv
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QDate, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QFormLayout, QHBoxLayout,  # noqa: E402
                               QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from core import license as lic  # noqa: E402
from tools import license_tool as lt  # noqa: E402

STYLE = """
QWidget { font-size: 14px; }
QPushButton { padding: 8px 16px; border-radius: 8px; background: #E2E8F0; }
QPushButton#main { background: #16A34A; color: white; font-weight: bold; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit { padding: 6px; border: 1px solid #CBD5E1; border-radius: 6px; }
QLabel#status { padding: 12px; border-radius: 10px; font-weight: bold; }
"""


def machine_ok(code):
    return len(lic.normalize_machine(code)) == 19


class LicenseManager(QWidget):
    def __init__(self, key_dir=None):
        super().__init__()
        self.key_dir = key_dir or lt.DEFAULT_DIR
        self.setWindowTitle("مدير التفعيل — للمطوّر فقط")
        self.resize(760, 620)
        lay = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.keys_btn = QPushButton("🔐 إنشاء مفاتيحي (مرة واحدة)")
        self.keys_btn.setObjectName("main")
        self.keys_btn.clicked.connect(self.create_keys)
        row.addWidget(self.keys_btn)
        folder = QPushButton("📂 فتح مجلد المفاتيح (لأخذ نسخة احتياطية)")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.key_dir)))
        row.addWidget(folder)
        row.addStretch()
        lay.addLayout(row)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._issue_tab(), "🔑 مفتاح تفعيل لزبون")
        self.tabs.addTab(self._reset_tab(), "🔓 نسي الزبون كلمة المرور")
        self.log_table = QTableWidget()
        self.tabs.addTab(self.log_table, "📜 سجل المفاتيح")
        self.refresh()

    # ------------------------------------------------------------------ الواجهات
    def _issue_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("الزبون يرسل لك «رمز الجهاز» من شاشة: الإعدادات ← الترخيص والتفعيل (أو زر «طلب التفعيل عبر واتساب»)."))
        f = QFormLayout()
        self.machine = QLineEdit()
        self.machine.setPlaceholderText("مثل: 4F1A-9C03-7B2E-D5A8")
        f.addRow("رمز جهاز الزبون:", self.machine)
        self.shop = QLineEdit()
        f.addRow("اسم المحل:", self.shop)
        self.plan = QComboBox()
        for k, label in lic.PLANS.items():
            self.plan.addItem(label, k)
        f.addRow("الباقة:", self.plan)
        self.terminals = QSpinBox()
        self.terminals.setRange(0, 99)
        self.terminals.setSpecialValueText("غير محدود")
        from core import plans as _plans
        self.plan.currentIndexChanged.connect(
            lambda _: self.terminals.setValue(_plans.TERMINALS.get(self.plan.currentData(), 1)))
        self.plan.setCurrentIndex(1)
        self.terminals.setValue(_plans.TERMINALS["pro"])
        f.addRow("عدد أجهزة الكاشير:", self.terminals)
        exp = QHBoxLayout()
        self.has_exp = QCheckBox("اشتراك ينتهي بتاريخ:")
        self.exp = QDateEdit(QDate.currentDate().addYears(1))
        self.exp.setCalendarPopup(True)
        self.exp.setDisplayFormat("yyyy-MM-dd")
        self.exp.setEnabled(False)
        self.has_exp.toggled.connect(self.exp.setEnabled)
        exp.addWidget(self.has_exp)
        exp.addWidget(self.exp)
        exp.addStretch()
        f.addRow("المدة:", exp)
        v.addLayout(f)
        b = QPushButton("🔑 إصدار مفتاح التفعيل")
        b.setObjectName("main")
        b.clicked.connect(self.issue)
        v.addWidget(b, alignment=Qt.AlignRight)
        self.key_out = QTextEdit()
        self.key_out.setReadOnly(True)
        self.key_out.setPlaceholderText("سيظهر المفتاح هنا")
        v.addWidget(self.key_out, 1)
        r = QHBoxLayout()
        c1 = QPushButton("📋 نسخ رسالة واتساب جاهزة للزبون")
        c1.clicked.connect(lambda: self.copy(self.message()))
        c2 = QPushButton("📋 نسخ المفتاح فقط")
        c2.clicked.connect(lambda: self.copy(self.last_key))
        r.addWidget(c1)
        r.addWidget(c2)
        r.addStretch()
        v.addLayout(r)
        self.last_key = ""
        return w

    def _reset_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        info = QLabel("الزبون يضغط «نسيت كلمة المرور؟» في شاشة الدخول، ويرسل لك رمز الجهاز الظاهر.\n"
                      "تأكد أنه صاحب المحل فعلاً قبل إرسال الرمز. الرمز صالح 3 أيام ولمرة واحدة، ولا يحذف أي بيانات.")
        info.setWordWrap(True)
        v.addWidget(info)
        f = QFormLayout()
        self.reset_machine = QLineEdit()
        self.reset_machine.setPlaceholderText("مثل: 4F1A-9C03-7B2E-D5A8")
        f.addRow("رمز جهاز الزبون:", self.reset_machine)
        v.addLayout(f)
        b = QPushButton("🔓 إصدار رمز الاستعادة")
        b.setObjectName("main")
        b.clicked.connect(self.make_reset)
        v.addWidget(b, alignment=Qt.AlignRight)
        self.reset_out = QTextEdit()
        self.reset_out.setReadOnly(True)
        v.addWidget(self.reset_out, 1)
        c = QPushButton("📋 نسخ الرمز")
        c.clicked.connect(lambda: self.copy(self.reset_out.toPlainText()))
        v.addWidget(c, alignment=Qt.AlignLeft)
        return w

    # ------------------------------------------------------------------ الحالة
    def refresh(self):
        ok, state = lt.pubkey_status(self.key_dir)
        self.keys_btn.setVisible(state == "none")
        texts = {
            "none": ("#FEF3C7", "الخطوة الأولى (مرة واحدة في حياتك): اضغط «إنشاء مفاتيحي». بعدها ابنِ نسخة البرنامج "
                                "(build_exe.bat) لتقبل المفاتيح التي تصدرها من هنا."),
            "ok": ("#DCFCE7", f"✓ مفاتيحك جاهزة، والبرنامج مجهّز بها. النسخ التي تبنيها من هذا المجلد تقبل مفاتيحك.\n"
                              f"احفظ نسخة من مجلد المفاتيح على فلاشة:\n\u2066{self.key_dir}\u2069"),
            "missing": ("#FEE2E2", "⚠ البرنامج غير مجهّز بمفتاحك بعد. أغلق النافذة وافتحها من جديد، أو شغّل build_exe.bat."),
            "mismatch": ("#FEE2E2", "⚠ المفتاح العام داخل البرنامج لا يطابق مفتاحك الخاص (ربما من جهاز آخر). "
                                    "اضغط «إصلاح» ثم أعد بناء البرنامج."),
        }
        color, text = texts[state]
        self.status.setText(text)
        self.status.setStyleSheet(f"background:{color};")
        if state in ("missing", "mismatch"):
            self.keys_btn.setText("🛠 إصلاح")
            self.keys_btn.setVisible(True)
        self.load_log()
        return ok

    def create_keys(self):
        self.keys_btn.setEnabled(False)
        self.status.setText("⏳ جارٍ إنشاء المفاتيح... قد يستغرق دقيقة، لا تغلق النافذة.")
        done = {}
        t = threading.Thread(target=lambda: done.update(created=lt.init_keys(self.key_dir)), daemon=True)
        t.start()
        timer = QTimer(self)

        def check():
            if t.is_alive():
                return
            timer.stop()
            self.keys_btn.setEnabled(True)
            self.refresh()
            if done.get("created"):
                QMessageBox.information(self, "تم", "✓ أُنشئت مفاتيحك.\n\nمهم جداً: خذ نسخة من مجلد المفاتيح على فلاشة. "
                                                    "إن ضاع لن تستطيع تفعيل النسخ التي بعتها.\n\n"
                                                    "الخطوة التالية: ابنِ البرنامج (build_exe.bat) ووزّع النسخة الجديدة.")
        timer.timeout.connect(check)
        timer.start(200)
        self._timer = timer
        self._thread = t

    def _private(self):
        path = os.path.join(self.key_dir, "private_key.json")
        if not os.path.exists(path):
            QMessageBox.warning(self, "المفاتيح", "أنشئ مفاتيحك أولاً (الزر في الأعلى).")
            return None
        return lt.load_private(path)

    # ------------------------------------------------------------------ العمليات
    def issue(self):
        if not machine_ok(self.machine.text()):
            QMessageBox.warning(self, "رمز الجهاز", "رمز الجهاز غير صحيح. يجب أن يكون 16 حرفاً/رقماً مثل 4F1A-9C03-7B2E-D5A8")
            return
        if not self.shop.text().strip():
            QMessageBox.warning(self, "اسم المحل", "اكتب اسم المحل")
            return
        private = self._private()
        if not private:
            return
        expires = self.exp.date().toString("yyyy-MM-dd") if self.has_exp.isChecked() else None
        key, data = lt.issue(private, self.machine.text(), self.shop.text().strip(), self.plan.currentData(),
                             self.terminals.value(), expires)
        lt.log_issue(data, key, self.key_dir)
        self.last_key, self.last_data = key, data
        self.key_out.setPlainText(key)
        self.load_log()

    def message(self):
        if not self.last_key:
            return ""
        d = self.last_data
        until = f"حتى {d['expires']}" if d["expires"] else "دائم"
        return (f"مرحباً، هذا مفتاح تفعيل برنامج المحاسبة ونقاط البيع لـ «{d['shop']}» ({until}):\n\n{self.last_key}\n\n"
                "طريقة التفعيل: افتح البرنامج ← الإعدادات ← الترخيص والتفعيل ← الصق المفتاح في المربع ← اضغط «تفعيل».")

    def make_reset(self):
        if not machine_ok(self.reset_machine.text()):
            QMessageBox.warning(self, "رمز الجهاز", "رمز الجهاز غير صحيح")
            return
        private = self._private()
        if private:
            self.reset_out.setPlainText(lt.reset_code(private, self.reset_machine.text()))

    def copy(self, text):
        if text:
            QGuiApplication.clipboard().setText(text)
            QMessageBox.information(self, "نُسخ", "✓ نُسخ. الصقه في واتساب للزبون.")

    def load_log(self):
        path = os.path.join(self.key_dir, "licenses_log.csv")
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        head, body = (rows[0][:7], rows[1:]) if rows else (["التاريخ", "المحل", "رمز الجهاز"], [])
        self.log_table.setColumnCount(len(head))
        self.log_table.setHorizontalHeaderLabels(head)
        self.log_table.setRowCount(len(body))
        for r, row in enumerate(reversed(body)):
            for c, v in enumerate(row[:7]):
                self.log_table.setItem(r, c, QTableWidgetItem(v))
        self.log_table.resizeColumnsToContents()


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    f = QFont()
    f.setFamilies(["Segoe UI", "Tahoma", "Noto Sans Arabic"])
    app.setFont(f)
    app.setStyleSheet(STYLE)
    w = LicenseManager()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
