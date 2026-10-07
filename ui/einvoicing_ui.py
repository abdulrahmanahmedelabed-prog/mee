# -*- coding: utf-8 -*-
"""واجهة الفوترة الإلكترونية المرتبطة: تبويب الإعدادات، ربط الجهاز، وسجل الفواتير المرسلة"""

import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QVBoxLayout, QApplication)

from core import einvoicing, settings
from ui.widgets import Table, button, hint, info, warn, error


def build_tab(screen, form):
    """يضيف حقول الفوترة الإلكترونية إلى نموذج الإعدادات (تُحفظ مع باقي الإعدادات)"""
    f = screen.fields
    form.addRow(hint("اختياري: اربط فواتيرك بمنصة الضريبة في بلدك. كل بيع ومرتجع يتحول تلقائياً لفاتورة إلكترونية رسمية "
                     "(UBL 2.1) تُختم وتُرسل في الخلفية، ويُطبع رمز QR الرسمي على الإيصال. "
                     "البيع لا يتوقف أبداً إن انقطع الإنترنت: الفواتير تنتظر وتُرسل عند عودته."))
    sysc = QComboBox()
    for code, name in einvoicing.SYSTEMS.items():
        sysc.addItem(name, code)
    f["einv_system"] = sysc
    form.addRow("المنصة:", sysc)
    env = QComboBox()
    for code, (name, _u, _t) in einvoicing.ZATCA_ENVS.items():
        env.addItem(name, code)
    f["einv_env"] = env
    form.addRow("بيئة «فاتورة»:", env)
    for key, label in (("einv_legal_name", "الاسم القانوني للمنشأة (كما في السجل):"),
                       ("einv_crn", "رقم السجل التجاري (السعودية):"),
                       ("einv_street", "الشارع:"), ("einv_building", "رقم المبنى (4 أرقام):"),
                       ("einv_district", "الحي:"), ("einv_city", "المدينة:"), ("einv_postal", "الرمز البريدي (5 أرقام):"),
                       ("jof_client_id", "JoFotara — معرّف العميل (Client ID):"),
                       ("jof_source_id", "JoFotara — رقم تسلسل مصدر الدخل:")):
        w = QLineEdit()
        f[key] = w
        form.addRow(label, w)
    screen.jof_secret = QLineEdit()
    screen.jof_secret.setEchoMode(QLineEdit.Password)
    screen.jof_secret.setPlaceholderText("اتركه فارغاً للإبقاء على المحفوظ")
    form.addRow("JoFotara — الرمز السري (Secret Key):", screen.jof_secret)
    kind = QComboBox()
    for code, name in einvoicing.JO_KINDS.items():
        kind.addItem(name, code)
    f["jof_kind"] = kind
    form.addRow("JoFotara — نوع الفاتورة:", kind)
    form.addRow("", hint("الرقم الضريبي واسم المحل من تبويب «بيانات المحل»، ونسبة الضريبة من «العملة والضريبة»."))
    ksa = [env] + [f[k] for k in ("einv_crn", "einv_street", "einv_building", "einv_district", "einv_city", "einv_postal")]
    jo = [f["jof_client_id"], f["jof_source_id"], screen.jof_secret, kind]
    common = [f["einv_legal_name"]]

    def show_rows(*_):
        code = sysc.currentData() or ""
        for w in ksa:
            form.setRowVisible(w, code == einvoicing.ZATCA)
        for w in jo:
            form.setRowVisible(w, code == einvoicing.JOFOTARA)
        for w in common:
            form.setRowVisible(w, bool(code))
    sysc.currentIndexChanged.connect(show_rows)
    screen._einv_rows = show_rows
    screen.einv_status = QLabel("")
    screen.einv_status.setWordWrap(True)
    screen.einv_status.setObjectName("subTitle")
    form.addRow(screen.einv_status)
    row = QHBoxLayout()
    screen.einv_link = button("🔗 ربط هذا الجهاز مع «فاتورة»", "primaryBtn", lambda: onboard(screen))
    row.addWidget(screen.einv_link)
    row.addWidget(button("📤 أرسل المعلّق الآن", "secondaryBtn", lambda: send_now(screen)))
    row.addWidget(button("📋 سجل الفواتير الإلكترونية", "secondaryBtn", lambda: EInvoiceLog(screen).exec()))
    row.addStretch()
    form.addRow(row)
    form.addRow(hint("السعودية: من بوابة «فاتورة» (fatoora.zatca.gov.sa) أنشئ رمز OTP ثم اضغط «ربط». يولّد البرنامج مفتاح التوقيع "
                     "على هذا الجهاز، ويجتاز فحوص الامتثال لدى الهيئة، ثم يستلم شهادة الإنتاج تلقائياً. "
                     "ابدأ ببيئة المطورين للتجربة (رمزها 123345) ثم انتقل للإنتاج.\n"
                     "الأردن: سجّل في نظام الفوترة الوطني (portal.jofotara.gov.jo) واحصل من «ربط أنظمة الفوترة» على "
                     "معرّف العميل والرمز السري ورقم تسلسل مصدر الدخل."))


def load(screen):
    screen._einv_rows()
    from core import remote
    if remote.is_client():
        screen.einv_status.setText("الفوترة الإلكترونية تُدار وتُرسل من الجهاز الرئيسي للمحل.")
        screen.einv_link.setVisible(False)
        return
    sys_ = einvoicing.system()
    if not sys_:
        screen.einv_status.setText("الفوترة المرتبطة معطّلة.")
        screen.einv_link.setVisible(settings.get("einv_system") == "zatca")
        return
    s = einvoicing.summary()
    miss = einvoicing.check_setup()
    txt = (f"✅ مُبلَّغ: {s['reported'] + s['warning']}   ⏳ بانتظار الإرسال: {s['pending']}   "
           f"⛔ مرفوض: {s['rejected']}   ⚠ أخطاء: {s['error']}")
    if s["late"]:
        txt += f"\n🔴 {s['late']} فاتورة تجاوزت مهلة 24 ساعة."
    if sys_ == einvoicing.ZATCA:
        stage = einvoicing.zatca_stage()
        txt += "\nحالة الربط: " + {"ready": "🟢 الجهاز مربوط والفواتير تُوقَّع وتُرسل",
                                   "compliance": "🟡 بدأ الربط ولم يكتمل — أعد «ربط»",
                                   "none": "⚪ لم يُربط بعد — الفواتير تُجهَّز وتنتظر الربط"}[stage]
    if miss:
        txt += "\nبيانات ناقصة: " + "، ".join(miss)
    screen.einv_status.setText(txt)
    screen.einv_link.setVisible(sys_ == einvoicing.ZATCA)


def save(screen):
    if screen.jof_secret.text().strip():
        einvoicing.set_jofotara_secret(screen.jof_secret.text())
        screen.jof_secret.clear()


def _run(screen, fn, done):
    """تنفيذ عملية شبكة دون تجميد الشاشة"""
    box = {}

    def work():
        try:
            box["ok"] = fn()
        except Exception as e:  # noqa: BLE001
            box["err"] = e
    t = threading.Thread(target=work, daemon=True)
    t.start()
    QApplication.setOverrideCursor(Qt.WaitCursor)

    def poll():
        if t.is_alive():
            QTimer.singleShot(150, poll)
            return
        QApplication.restoreOverrideCursor()
        done(box)
    poll()


def onboard(screen):
    if settings.get("einv_system") != einvoicing.ZATCA:
        warn(screen, "اختر المنصة «السعودية» واحفظ الإعدادات أولاً")
        return
    miss = einvoicing.check_setup(einvoicing.ZATCA)
    if miss:
        warn(screen, "أكمل البيانات واحفظها أولاً:\n• " + "\n• ".join(miss))
        return
    otp, ok = QInputDialog.getText(screen, "ربط الجهاز مع «فاتورة»",
                                   "رمز OTP من بوابة فاتورة (صالح ساعة واحدة):\n(بيئة المطورين: 123345)")
    if not ok or not otp.strip():
        return

    def done(box):
        if "err" in box:
            error(screen, str(box["err"]))
        else:
            info(screen, box["ok"])
        load(screen)
    _run(screen, lambda: einvoicing.zatca_onboard(otp), done)


def send_now(screen):
    if not einvoicing.enabled():
        warn(screen, "فعّل الفوترة الإلكترونية أولاً")
        return

    def done(box):
        if "err" in box:
            error(screen, str(box["err"]))
        else:
            s = einvoicing.summary()
            info(screen, f"أُرسل {box['ok']} مستند. المتبقي بانتظار الإرسال: {s['pending']}")
        load(screen)
    _run(screen, lambda: einvoicing.send_pending(200), done)


class EInvoiceLog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("سجل الفواتير الإلكترونية")
        self.resize(980, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("الكل", None)
        for k, v in einvoicing.STATUS.items():
            self.filter.addItem(v, k)
        self.filter.currentIndexChanged.connect(self.load)
        top.addWidget(QLabel("الحالة:"))
        top.addWidget(self.filter)
        top.addStretch()
        top.addWidget(button("💾 حفظ XML", "secondaryBtn", self.save_xml))
        top.addWidget(button("🔁 أعد الإرسال", "secondaryBtn", self.retry))
        lay.addLayout(top)
        self.table = Table(["المستند", "النوع", "العدّاد", "الحالة", "الرسالة", "أُنشئ", "أُرسل"], stretch=4)
        lay.addWidget(self.table, 1)
        lay.addWidget(hint("المرفوض: اقرأ رسالة المنصة، صحّح السبب (غالباً بيانات المنشأة)، ثم «أعد الإرسال»."))
        self.load()

    def load(self):
        rows = einvoicing.recent(500, self.filter.currentData())
        self.table.set_rows([[r["number"], "فاتورة" if r["doc_type"] == "invoice" else "إشعار دائن", r["icv"] or "",
                              einvoicing.STATUS.get(r["status"], r["status"]), (r["message"] or "")[:160],
                              (r["created_at"] or "")[:16], (r["sent_at"] or "")[:16]] for r in rows], rows)

    def save_xml(self):
        r = self.table.selected_data()
        if not r:
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ XML", f"{r['number']}.xml", "XML (*.xml)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(einvoicing.xml_of(r["id"]))

    def retry(self):
        r = self.table.selected_data()
        if r:
            einvoicing.retry(r["id"])
            self.load()
