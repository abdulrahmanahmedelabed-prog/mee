# -*- coding: utf-8 -*-
"""ربط تطبيق الجوال: رمز لتحميل التطبيق، ورمز الربط بهذا المحل، والخطوات — في نافذة واحدة واضحة"""

import base64

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from core import config, remote, settings
from ui.widgets import button, card, hint, title, warn

APK_URL = "https://github.com/abdulrahmanahmedelabed-prog/mee/releases/latest/download/ShopPOS-android.apk"


def _qr_pixmap(text, size):
    from core.einvoice import qr_data_uri
    uri = qr_data_uri(text)
    pm = QPixmap()
    if uri:
        pm.loadFromData(base64.b64decode(uri.split(",", 1)[1]))
        return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation)
    return None


def address():
    port = config.get("server_port") or 8765
    return f"http://{config.local_ip()}:{port}"


class PairDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 ربط تطبيق الجوال")
        self.resize(860, 600)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(title("📱 ربط الجوال بالمحل", "pageTitle"))
        lay.addWidget(hint("تطبيق الموظفين وصاحب المحل: أرقام اليوم، الأسعار والجرد بالكاميرا، النواقص، الديون وتذكير واتساب، "
                           "تجهيز الطلبات الأونلاين، واسأل محلك. يعمل على واي فاي المحل بلا إنترنت."))
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("subTitle")
        lay.addWidget(self.status)
        self.start_btn = button("▶ تشغيل خدمة الجوال على هذا الجهاز", "successBtn", self.start_service)
        lay.addWidget(self.start_btn, 0, Qt.AlignLeading)

        row = QHBoxLayout()
        row.setSpacing(14)
        for step, head, text, data in (
                ("1", "حمّل التطبيق", "امسح هذا الرمز بكاميرا الجوال (أندرويد) وثبّت التطبيق. لا يطلب أي صلاحيات.", APK_URL),
                ("2", "اربطه بهذا المحل", "افتح التطبيق والجوال على واي فاي المحل: يجد المحل وحده. إن لم يجده اضغط "
                                       "«📷 مسح رمز الربط» في التطبيق وامسح هذا الرمز.", None)):
            c, cl = card()
            cl.addWidget(title(f"{step}. {head}", "subTitle"))
            q = QLabel()
            q.setAlignment(Qt.AlignCenter)
            q.setMinimumSize(250, 250)
            cl.addWidget(q, 1)
            t = hint(text)
            t.setWordWrap(True)
            cl.addWidget(t)
            if data:
                pm = _qr_pixmap(data, 240)
                q.setPixmap(pm) if pm else q.setText(data)
            else:
                self.pair_qr = q
                self.addr = QLabel("")
                self.addr.setAlignment(Qt.AlignCenter)
                self.addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.addr.setObjectName("subTitle")
                cl.addWidget(self.addr)
            row.addWidget(c, 1)
        lay.addLayout(row, 1)
        lay.addWidget(hint("3. سجّل الدخول مرة واحدة باسم المستخدم وكلمة المرور نفسها التي في البرنامج — يبقى الدخول محفوظاً. "
                           "كل موظف يرى ما تسمح به صلاحياته. آيفون: افتح العنوان أعلاه من سفاري ثم «إضافة إلى الشاشة الرئيسية»."))
        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(button("إغلاق", "secondaryBtn", self.accept))
        lay.addLayout(foot)
        self.refresh()

    def refresh(self):
        running = remote.SERVER.httpd is not None
        client = remote.is_client()
        addr = address()
        self.addr.setText(addr + "/m")
        pm = _qr_pixmap(addr, 240)
        self.pair_qr.setPixmap(pm) if pm else self.pair_qr.setText(addr)
        if client:
            self.status.setText("ℹ هذا جهاز كاشير فرعي: اربط الجوال بالجهاز الرئيسي للمحل (افتح هذه النافذة هناك).")
            self.start_btn.hide()
        elif running:
            self.status.setText("🟢 خدمة الجوال تعمل على هذا الجهاز — الجوال يجده تلقائياً على نفس الشبكة.")
            self.start_btn.hide()
        else:
            self.status.setText("🔴 خدمة الجوال متوقفة على هذا الجهاز. شغّلها ليتمكن الجوال من الاتصال.")
            self.start_btn.show()

    def start_service(self):
        try:
            settings.set("owner_web", "1")            # تبقى تعمل في كل تشغيل قادم
            remote.start_server()
        except OSError as e:
            warn(self, f"تعذر تشغيل خدمة الشبكة على المنفذ {config.get('server_port') or 8765}:\n{e}")
        self.refresh()


def open_pairing(parent):
    PairDialog(parent).exec()
