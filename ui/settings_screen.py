# -*- coding: utf-8 -*-
"""الإعدادات: بيانات المحل، الضريبة، الطباعة، البيع والمخزون، الميزان، المستخدمون، النسخ الاحتياطي"""

import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QFormLayout, QLineEdit, QCheckBox,
                               QComboBox, QDoubleSpinBox, QSpinBox, QLabel, QDialog, QFileDialog, QTextEdit)

from PySide6.QtCore import Qt

from core import settings, auth, backup, receipts, drawer, config, remote, shifts
from ui import printing
from ui.dialogs import ChangePasswordDialog, NetworkDialog
from ui.widgets import Table, button, page, title, hint, warn, info, ask, error, ok_cancel, card, require_permission


class UserDialog(QDialog):
    def __init__(self, parent, user=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("تعديل مستخدم" if user else "مستخدم جديد")
        lay = QFormLayout(self)
        self.username = QLineEdit()
        self.full_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.role = QComboBox()
        for k, v in auth.ROLES.items():
            self.role.addItem(v, k)
        self.active = QCheckBox("فعّال")
        self.active.setChecked(True)
        lay.addRow("اسم الدخول:", self.username)
        lay.addRow("الاسم الكامل:", self.full_name)
        if not user:
            lay.addRow("كلمة المرور:", self.password)
        lay.addRow("الدور:", self.role)
        lay.addRow("", self.active)
        perms = QLabel()
        perms.setWordWrap(True)
        perms.setObjectName("hint")
        lay.addRow("الصلاحيات:", perms)
        self.role.currentIndexChanged.connect(
            lambda: perms.setText("، ".join(auth.PERMISSIONS[p] for p in auth.PERMISSIONS
                                            if p in auth.ROLE_PERMISSIONS[self.role.currentData()])))
        if user:
            self.username.setText(user["username"])
            self.username.setEnabled(False)
            self.full_name.setText(user["full_name"] or "")
            self.role.setCurrentIndex(self.role.findData(user["role"]))
            self.active.setChecked(bool(user["is_active"]))
        else:
            self.role.setCurrentIndex(self.role.findData("cashier"))
        self.role.currentIndexChanged.emit(self.role.currentIndex())
        ok_cancel(self, lay)

    def accept(self):
        try:
            if self.user:
                auth.update_user(self.user["id"], self.full_name.text(), self.role.currentData(), self.active.isChecked())
            else:
                auth.create_user(self.username.text(), self.full_name.text(), self.password.text(), self.role.currentData())
        except Exception as e:
            warn(self, str(e))
            return
        super().accept()


def logo_for_thermal(img):
    """نسخة الطابعة الحرارية: على خلفية بيضاء (الشفاف لا يصبح أسود) ثم رمادي، بعرض 400 بكسل كحد أقصى"""
    from PySide6.QtGui import QImage, QPainter, QColor
    from PySide6.QtCore import Qt
    if img.width() > 400:
        img = img.scaledToWidth(400, Qt.SmoothTransformation)
    flat = QImage(img.size(), QImage.Format_RGB32)
    flat.fill(QColor("white"))
    p = QPainter(flat)
    p.drawImage(0, 0, img)
    p.end()
    return flat.convertToFormat(QImage.Format_Grayscale8)


class SettingsScreen(QWidget):
    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addStretch()
        self.save_btn = button("💾 حفظ الإعدادات", "successBtn", self.save)
        head.addWidget(self.save_btn)
        lay.addLayout(head)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.fields = {}

        # --- بيانات المحل
        f = self._form_tab("بيانات المحل")
        self._line(f, "shop_name", "اسم المحل:")
        self._line(f, "branch_name", "اسم الفرع (للمحلات متعددة الفروع):")
        self._line(f, "shop_address", "العنوان:")
        self._line(f, "shop_phone", "الهاتف:")
        self._line(f, "tax_number", "الرقم الضريبي / المشتغل المرخص:")
        logo_row = QHBoxLayout()
        self.logo_lbl = QLabel("")
        logo_row.addWidget(self.logo_lbl)
        logo_row.addWidget(button("🖼 اختيار شعار...", "secondaryBtn", self.choose_logo))
        logo_row.addWidget(button("إزالة", "secondaryBtn", self.clear_logo))
        logo_row.addStretch()
        f.addRow("شعار المحل:", logo_row)
        f.addRow("", hint("يظهر في القائمة الجانبية وشاشة الدخول وشاشة الزبون، وعلى الفواتير والكشوف والتقارير "
                          "وقسائم الرواتب، وفي لوحة المالك والمتجر الأونلاين."))
        lang = QComboBox()
        from core import i18n as _i18n
        for code, name in _i18n.LANGUAGES.items():
            lang.addItem(name, code)
        self.fields["language"] = lang
        f.addRow("اللغة / Language:", lang)
        f.addRow("", hint("تتغير اللغة فوراً عند الحفظ، أو من زر 🌐 أعلى الشاشة. The language changes instantly."))
        from ui import theme as _theme
        from core import config as _config
        self.theme_combo = QComboBox()
        for code in (_theme.LIGHT, _theme.DARK, _theme.AUTO):
            self.theme_combo.addItem(_theme.NAMES[code], code)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(_config.load().get("theme") or _theme.LIGHT)))
        f.addRow("مظهر البرنامج:", self.theme_combo)
        f.addRow("", hint("الداكن مريح للعين في الليل والإضاءة الخافتة، والتلقائي يتبع إعداد ويندوز. "
                          "يتغير فوراً، أو من زر 🌙 أعلى الشاشة. لكل جهاز مظهره."))

        # --- العملة والضريبة
        f = self._form_tab("العملة والضريبة")
        self._line(f, "currency_symbol", "رمز العملة:")
        self._line(f, "currency_name", "اسم العملة:")
        self._check(f, "vat_enabled", "تفعيل ضريبة القيمة المضافة")
        self._num(f, "vat_rate", "نسبة الضريبة %:", 0, 100)
        self._check(f, "prices_include_vat", "أسعار البيع شاملة للضريبة (الأشيع في المحلات)")
        f.addRow("", hint("عند التفعيل تظهر الضريبة في الفاتورة وتُطرح من الإيراد في تقرير الأرباح."))
        self._check(f, "einvoice_qr", "طباعة رمز QR للفاتورة الإلكترونية (صيغة الفوترة المبسطة المعتمدة في السعودية)")
        self._line(f, "extra_currencies", "عملات إضافية للدفع النقدي (مثل USD=3.65,JOD=5.15):")

        # --- الدفع الإلكتروني
        f = self._form_tab("الدفع الإلكتروني")
        f.addRow(hint("المحافظ الإلكترونية وتطبيقات البنوك التي يدفع بها زبائنك. لكل واحدة يظهر زر في نافذة الدفع، "
                      "يعرض للزبون رقم حسابك ورمز QR، ويسجّل رقم العملية. كل طريقة لها تقرير مطابقة في التقارير."))
        self.wallet_table = WalletsEditor()
        f.addRow(self.wallet_table)
        self._check(f, "wallet_ref_required", "إلزام الكاشير بكتابة رقم العملية من إشعار الزبون (موصى به)")

        # --- الطباعة
        f = self._form_tab("الطباعة ودرج النقود")
        f.addRow(hint("إعدادات الطابعة والدرج خاصة بهذا الجهاز (كل كاشير له طابعته)."))
        self.printer = QComboBox()
        self.printer.addItem("الطابعة الافتراضية", "")
        for p in printing.available_printers():
            self.printer.addItem(p, p)
        f.addRow("الطابعة:", self.printer)
        self.width = QComboBox()
        self.width.addItem("80 مم (حرارية)", "80")
        self.width.addItem("58 مم (حرارية صغيرة)", "58")
        self.width.addItem("A4", "210")
        f.addRow("عرض الورق:", self.width)
        self._line(f, "receipt_footer", "رسالة أسفل الفاتورة:")
        self._check(f, "auto_print_receipt", "طباعة الفاتورة تلقائياً بعد كل بيع")
        f.addRow("", button("🖨 معاينة فاتورة تجريبية", "secondaryBtn", self.test_print))
        dm = QComboBox()
        for k, v in drawer.MODES.items():
            dm.addItem(v, k)
        self.fields["drawer_mode"] = dm
        f.addRow("درج النقود:", dm)
        self._line(f, "drawer_printer", "اسم طابعة الدرج (فارغ = طابعة الفواتير):")
        self._line(f, "drawer_host", "IP طابعة الشبكة:")
        self._num(f, "drawer_port", "منفذ طابعة الشبكة:", 1, 65535, decimals=0)
        self._line(f, "drawer_serial", "منفذ COM:")
        self._check(f, "drawer_on_cash_sale", "فتح الدرج تلقائياً عند كل بيع نقدي")
        self._check(f, "customer_display", "شاشة الزبون: عرض الأصناف والإجمالي والباقي على الشاشة الثانية")
        from core import payments as _pay
        term = QComboBox()
        for k, v in _pay.MODES.items():
            term.addItem(v, k)
        self.fields["card_terminal"] = term
        f.addRow("جهاز الدفع بالبطاقة:", term)
        self._line(f, "card_terminal_url", "عنوان جسر الجهاز البنكي:")
        f.addRow("", button("💳 فحص الاتصال بجهاز الدفع", "secondaryBtn", self.test_terminal))
        f.addRow("", button("💰 تجربة فتح الدرج", "secondaryBtn", self.test_drawer))

        # --- البيع والمخزون
        f = self._form_tab("البيع والمخزون")
        self._check(f, "simple_mode", "الوضع المبسّط للدكان الصغير (إخفاء المحاسبة والشيكات والعروض والطلبات والمستشار)")
        self._check(f, "touch_mode", "شاشة لمس: أزرار أكبر ولوحة أرقام في نافذة الدفع (بعد إعادة التشغيل)")
        self._check(f, "require_shift", "إلزام فتح وردية قبل البيع (لضبط الصندوق)")
        self._check(f, "allow_negative_stock", "السماح بالبيع عند نفاد الكمية (مخزون سالب)")
        self._num(f, "cashier_max_discount_percent", "أقصى خصم للكاشير بدون إذن مدير %:", 0, 100)
        self._num(f, "expiry_alert_days", "التنبيه قبل انتهاء الصلاحية بـ (يوم):", 1, 365, decimals=0)
        self._check(f, "block_expired_sale", "منع البيع إذا وُجدت دفعة منتهية من الصنف لم تُتلف")
        self._line(f, "whatsapp_country_code", "رمز الدولة لأرقام واتساب (970 فلسطين، 972، 962 الأردن):")
        cats = QTextEdit()
        cats.setMaximumHeight(80)
        self.fields["expense_categories"] = cats
        f.addRow("أنواع المصاريف (مفصولة بفاصلة):", cats)

        # --- الميزان
        f = self._form_tab("باركود الميزان")
        f.addRow(hint("موازين الملحمة والخضار تطبع ملصقاً بباركود يحتوي رمز الصنف والوزن. عرّف رمز الميزان (PLU) "
                      "في بطاقة المنتج، وسيقرأ البرنامج الوزن تلقائياً عند المسح.\n"
                      "الصيغة: بادئة (2 رقم) + رمز الصنف + الوزن بالغرام أو السعر + رقم تحقق = 13 رقماً."))
        self._check(f, "scale_enabled", "تفعيل قراءة باركود الميزان")
        self._line(f, "scale_prefixes", "البادئات (مفصولة بفاصلة):")
        mode = QComboBox()
        mode.addItem("الوزن بالغرام", "weight")
        mode.addItem("السعر (بالأغورة/القرش)", "price")
        self.fields["scale_mode"] = mode
        f.addRow("القيمة في الباركود:", mode)
        self._num(f, "scale_code_length", "عدد خانات رمز الصنف:", 4, 6, decimals=0)

        # --- نقاط الولاء ولوحة المالك
        f = self._form_tab("نقاط الولاء ولوحة المالك")
        f.addRow(title("🎁 نقاط الولاء", "subTitle"))
        self._check(f, "loyalty_enabled", "تفعيل نقاط الولاء للعملاء المسجلين")
        self._num(f, "loyalty_points_per_unit", "النقاط المكتسبة لكل 1 من العملة:", 0, 100)
        self._num(f, "loyalty_point_value", "قيمة النقطة الواحدة عند الاستبدال:", 0, 100, decimals=3)
        self._num(f, "loyalty_min_redeem", "أقل عدد نقاط للاستبدال:", 0, 1_000_000, decimals=0)
        f.addRow("", hint("مثال: نقطة لكل شيكل، والنقطة = 0.05 ← الزبون يسترد 5% من مشترياته. "
                          "100 نقطة كحد أدنى = خصم 5 شيكل بعد 100 شيكل مشتريات."))
        self._check(f, "promotions_enabled", "تطبيق العروض التلقائية في نقطة البيع")
        f.addRow(title("📱 لوحة المالك وملخص اليوم", "subTitle"))
        self._line(f, "owner_whatsapp", "رقم واتساب المالك (لإرسال ملخص اليوم):")
        self._check(f, "owner_web", "تشغيل لوحة المالك على الجوال من هذا الجهاز")
        self.owner_url = hint("")
        self.owner_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow("", self.owner_url)
        self.pair_qr = QLabel()
        self.pair_qr.setToolTip("امسحه بتطبيق نقطة البيع على الجوال لربطه بهذا المحل")
        f.addRow("ربط تطبيق الجوال:", self.pair_qr)

        # --- المتجر الإلكتروني
        f = self._form_tab("المتجر الإلكتروني")
        f.addRow(hint("صفحة يطلب منها الزبائن من جوالاتهم (استلام أو توصيل، والدفع عند الاستلام). "
                      "الطلبات تظهر في شاشة «الطلبات الأونلاين». الرابط: http://عنوان-الجهاز:8765/shop — "
                      "يلزم تشغيل خدمة الويب (جهاز رئيسي أو «تشغيل لوحة المالك»). للوصول من الإنترنت استخدم "
                      "Cloudflare Tunnel أو Tailscale Funnel."))
        self._check(f, "online_store_enabled", "تفعيل المتجر الإلكتروني واستقبال الطلبات")
        self._check(f, "online_store_delivery", "إتاحة التوصيل")
        self._num(f, "online_store_delivery_fee", "رسوم التوصيل:", 0, 1000)
        self._num(f, "online_store_min_order", "أقل قيمة للطلب:", 0, 100000)
        self._line(f, "online_store_message", "رسالة أعلى صفحة المتجر:")

        # --- الترخيص والتفعيل
        lic = QWidget()
        ll = QVBoxLayout(lic)
        c, cl = card()
        self.lic_status = QLabel("")
        self.lic_status.setObjectName("subTitle")
        self.lic_status.setWordWrap(True)
        cl.addWidget(self.lic_status)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("رمز هذا الجهاز:"))
        self.machine_lbl = QLabel("")
        self.machine_lbl.setStyleSheet("font-size:20px; font-weight:900; letter-spacing:2px; color:#1D4ED8;")
        self.machine_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mrow.addWidget(self.machine_lbl)
        mrow.addWidget(button("📋 نسخ", "secondaryBtn", self.copy_machine))
        mrow.addWidget(button("📱 طلب التفعيل عبر واتساب", "successBtn", self.request_activation))
        mrow.addStretch()
        cl.addLayout(mrow)
        cl.addWidget(hint("1) أرسل رمز الجهاز لمزوّد البرنامج.  2) يرسل لك مفتاح التفعيل.  3) الصقه هنا واضغط «تفعيل»."))
        self.lic_key = QTextEdit()
        self.lic_key.setPlaceholderText("الصق مفتاح التفعيل هنا (يبدأ بـ SA1.)")
        self.lic_key.setMaximumHeight(110)
        cl.addWidget(self.lic_key)
        cl.addWidget(button("✓ تفعيل", "successBtn", self.activate_license), alignment=Qt.AlignRight)
        ll.addWidget(c)
        self.vendor_lbl = hint("")
        ll.addWidget(self.vendor_lbl)
        ll.addStretch()
        self.license_tab = self.tabs.addTab(lic, "الترخيص والتفعيل")

        # --- المستخدمون
        users = QWidget()
        ul = QVBoxLayout(users)
        row = QHBoxLayout()
        row.addWidget(button("+ مستخدم", "successBtn", self.add_user))
        row.addWidget(button("✏ تعديل", "secondaryBtn", self.edit_user))
        row.addWidget(button("🔑 تغيير كلمة المرور", "secondaryBtn", self.reset_pw))
        row.addStretch()
        ul.addLayout(row)
        self.users = Table(["#", "اسم الدخول", "الاسم", "الدور", "الحالة", "تاريخ الإنشاء"], stretch=2)
        self.users.doubleClicked.connect(self.edit_user)
        ul.addWidget(self.users)
        ul.addWidget(hint("الكاشير: بيع، فواتير، عملاء، صندوق. مدير المحل: كل شيء عدا الإعدادات والمستخدمين. "
                          "عند حاجة الكاشير لعملية غير مسموحة (خصم كبير، مرتجع، تغيير سعر) يُطلب إذن المدير فوراً."))
        # --- هذا الجهاز والشبكة
        net = QWidget()
        nl = QVBoxLayout(net)
        c, cl = card()
        self.net_info = QLabel()
        self.net_info.setWordWrap(True)
        self.net_info.setObjectName("subTitle")
        cl.addWidget(self.net_info)
        cl.addWidget(button("🖧 إعداد الشبكة ونقاط البيع المتعددة", None, self.network_settings), alignment=Qt.AlignRight)
        nl.addWidget(c)
        nl.addWidget(title("الورديات المفتوحة على كل الأجهزة", "subTitle"))
        self.open_shifts = Table(["#", "الجهاز", "الكاشير", "منذ", "الرصيد الافتتاحي"])
        nl.addWidget(self.open_shifts)
        self.tabs.addTab(net, "هذا الجهاز والشبكة")

        self.users_tab = self.tabs.addTab(users, "المستخدمون")

        # --- النسخ الاحتياطي
        bk = QWidget()
        bl = QVBoxLayout(bk)
        f2 = QFormLayout()
        self.backup_dir = QLineEdit()
        self.fields["backup_dir"] = self.backup_dir
        r = QHBoxLayout()
        r.addWidget(self.backup_dir)
        r.addWidget(button("اختيار...", "secondaryBtn", self.choose_backup_dir))
        f2.addRow("مجلد النسخ (يُفضّل فلاشة أو مجلد Google Drive/OneDrive):", r)
        keep = QSpinBox()
        keep.setRange(3, 365)
        self.fields["backup_keep"] = keep
        f2.addRow("عدد النسخ المحفوظة:", keep)
        self.mirror_dir = QLineEdit()
        self.mirror_dir.setPlaceholderText("مثال: C:/Users/اسمك/Google Drive/نسخ المحل")
        self.fields["backup_mirror_dir"] = self.mirror_dir
        r2 = QHBoxLayout()
        r2.addWidget(self.mirror_dir)
        r2.addWidget(button("اختيار...", "secondaryBtn", self.choose_mirror_dir))
        f2.addRow("نسخة ثانية تلقائية في مجلد سحابي:", r2)
        f2.addRow("", hint("ثبّت Google Drive أو OneDrive على الجهاز واختر مجلداً داخله: كل نسخة تُرفع للسحابة تلقائياً، "
                           "فتبقى بياناتك آمنة حتى لو تعطّل الجهاز أو سُرق."))
        bl.addLayout(f2)
        row = QHBoxLayout()
        row.addWidget(button("💾 نسخة احتياطية الآن", "successBtn", self.backup_now))
        self.restore_btn = button("♻ استعادة المحددة", "dangerBtn", self.restore)
        self.restore_file_btn = button("📂 استعادة من ملف...", "secondaryBtn", self.restore_file)
        row.addWidget(self.restore_btn)
        row.addWidget(self.restore_file_btn)
        row.addStretch()
        bl.addLayout(row)
        self.backups = Table(["الملف", "الحجم", "التاريخ"])
        bl.addWidget(self.backups)
        bl.addWidget(hint("يأخذ البرنامج نسخة تلقائية يومياً عند التشغيل، ونسخة عند الإغلاق."))
        self.tabs.addTab(bk, "النسخ الاحتياطي")

    # ---------------------------------------------------------------- مساعدات
    def _form_tab(self, name):
        from PySide6.QtWidgets import QScrollArea, QFrame
        wdg = QWidget()
        outer = QVBoxLayout(wdg)
        c, cl = card()
        form = QFormLayout()
        form.setSpacing(10)
        cl.addLayout(form)
        outer.addWidget(c)
        outer.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(wdg)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: #F1F5F9; }")
        self.tabs.addTab(scroll, name)
        return form

    def _line(self, form, key, label):
        w = QLineEdit()
        self.fields[key] = w
        form.addRow(label, w)

    def _check(self, form, key, label):
        w = QCheckBox(label)
        self.fields[key] = w
        form.addRow("", w)

    def _num(self, form, key, label, lo, hi, decimals=2):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        self.fields[key] = w
        form.addRow(label, w)

    # ---------------------------------------------------------------- تحميل وحفظ
    def refresh(self):
        settings.reload()
        for k, w in self.fields.items():
            v = settings.get(k, "")
            if isinstance(w, QCheckBox):
                w.setChecked(v == "1")
            elif isinstance(w, (QDoubleSpinBox, QSpinBox)):
                w.setValue(float(v or 0) if isinstance(w, QDoubleSpinBox) else int(float(v or 0)))
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(v)))
            elif isinstance(w, QTextEdit):
                w.setPlainText(v)
            else:
                w.setText(v)
        from core import i18n
        lang = self.fields["language"]                 # لغة هذا الجهاز (قد تكون بُدّلت من زر 🌐)
        lang.setCurrentIndex(max(0, lang.findData(i18n.language())))
        from core import config
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(config.load().get("theme") or "light")))
        self.printer.setCurrentIndex(max(0, self.printer.findData(settings.get("printer_name"))))
        self.width.setCurrentIndex(max(0, self.width.findData(settings.get("receipt_width_mm"))))
        is_admin = auth.has_permission("users")
        self.save_btn.setEnabled(auth.has_permission("settings"))
        for i in range(self.tabs.count() - 2):
            self.tabs.setTabEnabled(i, auth.has_permission("settings"))
        self.tabs.setTabEnabled(self.users_tab, is_admin)
        self.load_users()
        self.load_backups()
        self.load_network()
        self.load_license()
        self.load_logo()
        from core import wallets
        self.wallet_table.set_items(wallets.all_wallets())
        port = config.get("server_port") or 8765
        running = remote.SERVER.httpd is not None
        self.owner_url.setText(
            f"افتح من جوال المالك (على نفس شبكة المحل): http://{config.local_ip()}:{port}/owner "
            f"{'— تعمل الآن ✓' if running else '— تعمل بعد إعادة تشغيل البرنامج'}\n"
            "للمتابعة من خارج المحل ثبّت تطبيق VPN مجاني مثل Tailscale على الجهاز والجوال.")
        self.show_pair_qr(f"http://{config.local_ip()}:{port}")
        client = remote.is_client()
        for b in (self.restore_btn, self.restore_file_btn):
            b.setEnabled(not client)
            b.setToolTip("الاستعادة تتم من الجهاز الرئيسي فقط" if client else "")

    def save(self):
        values = {}
        for k, w in self.fields.items():
            if isinstance(w, QCheckBox):
                values[k] = "1" if w.isChecked() else "0"
            elif isinstance(w, QDoubleSpinBox):
                values[k] = f"{w.value():g}"
            elif isinstance(w, QSpinBox):
                values[k] = str(w.value())
            elif isinstance(w, QComboBox):
                values[k] = w.currentData()
            elif isinstance(w, QTextEdit):
                values[k] = ",".join(x.strip() for x in w.toPlainText().replace("\n", ",").split(",") if x.strip())
            else:
                values[k] = w.text().strip()
        values["printer_name"] = self.printer.currentData() or ""
        values["receipt_width_mm"] = self.width.currentData()
        if not values.get("shop_name"):
            warn(self, "اسم المحل مطلوب")
            return
        from core import wallets
        try:
            values["wallets"] = wallets.to_json(self.wallet_table.items())
        except ValueError as e:
            warn(self, str(e))
            return
        from core import i18n
        new_lang = values.get("language")
        settings.set_many(values)
        w = self.window()
        from core import config
        new_theme = self.theme_combo.currentData()
        if new_theme != (config.load().get("theme") or "light") and hasattr(w, "switch_theme"):
            if new_lang and new_lang != i18n.language():
                config.save({"language": new_lang})
                from ui import i18n_qt
                from PySide6.QtWidgets import QApplication
                i18n_qt.apply_language(new_lang, QApplication.instance())
                QApplication.instance().setLayoutDirection(i18n_qt.direction())
            w.switch_theme(new_theme)
            return
        if new_lang and new_lang != i18n.language() and hasattr(w, "switch_language"):
            w.switch_language(new_lang)               # فوراً، والنافذة الجديدة تفتح على الإعدادات
            return
        if hasattr(w, "refresh_nav"):
            w.refresh_nav()
        info(self, "تم حفظ الإعدادات")
        w = self.window()
        if hasattr(w, "update_header"):
            w.update_header()

    def test_drawer(self):
        self.save_local_drawer()
        try:
            if drawer.open_drawer():
                info(self, "تم إرسال أمر فتح الدرج ✓")
            else:
                warn(self, "اختر طريقة توصيل الدرج أولاً")
        except drawer.DrawerError as e:
            warn(self, str(e))

    def save_local_drawer(self):
        keys = ["drawer_mode", "drawer_printer", "drawer_host", "drawer_port", "drawer_serial", "drawer_on_cash_sale"]
        vals = {}
        for k in keys:
            w = self.fields[k]
            vals[k] = (w.currentData() if isinstance(w, QComboBox) else "1" if isinstance(w, QCheckBox) and w.isChecked()
                       else "0" if isinstance(w, QCheckBox) else f"{w.value():g}" if isinstance(w, QDoubleSpinBox)
                       else w.text().strip())
        config.save(vals)

    def load_network(self):
        cfg = config.load()
        if cfg["mode"] == config.MODE_SERVER:
            text = (f"🖧 هذا هو الجهاز الرئيسي «{cfg['terminal_name']}».\nأدخل في كل نقطة بيع فرعية:  العنوان "
                    f"{config.local_ip()}   •   المنفذ {cfg['server_port']}   •   رمز الربط {cfg['link_code']}")
            conns = remote.connected_terminals()
            if conns:
                text += "\nأجهزة اتصلت مؤخراً: " + "، ".join(f"{k} ({v[11:16]})" for k, v in conns.items())
        elif cfg["mode"] == config.MODE_CLIENT:
            text = (f"💻 نقطة بيع فرعية «{cfg['terminal_name']}» متصلة بالجهاز الرئيسي "
                    f"{cfg['server_host']}:{cfg['server_port']}")
        else:
            text = f"💻 جهاز مستقل «{cfg['terminal_name']}». لتشغيل أكثر من كاشير اضغط الزر بالأسفل."
        self.net_info.setText(text)
        rows = shifts.open_shifts()
        self.open_shifts.set_rows([[r["id"], r["terminal"] or "", r["full_name"] or r["username"] or "",
                                    (r["opened_at"] or "")[:16], float(r["opening_cash"])] for r in rows])

    def network_settings(self):
        if not auth.has_permission("settings") and not require_permission(self, "settings"):
            return
        NetworkDialog(self).exec()
        self.load_network()

    def choose_mirror_dir(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد النسخة السحابية")
        if d:
            self.mirror_dir.setText(d)

    def test_print(self):
        body = ("<div class='c big'><b>" + settings.get("shop_name") + "</b></div><hr>"
                "<table><tr><td>منتج تجريبي</td><td class='l'>10.00</td></tr>"
                "<tr class='tot'><td>الإجمالي</td><td class='l'>10.00 " + settings.get("currency_symbol") + "</td></tr></table>"
                "<hr><div class='c'>" + (settings.get("receipt_footer") or "") + "</div>")
        printing.print_html(self, receipts._wrap(body, int(self.width.currentData())), width_mm=int(self.width.currentData()),
                            preview=True)

    # ---------------------------------------------------------------- المستخدمون
    def load_users(self):
        rows = auth.list_users()
        self.users.set_rows([[u["id"], u["username"], u["full_name"] or "", auth.ROLES.get(u["role"], u["role"]),
                              "فعّال" if u["is_active"] else "موقوف", (u["created_at"] or "")[:10]] for u in rows], rows)

    def add_user(self):
        if UserDialog(self).exec() == QDialog.Accepted:
            self.load_users()

    def edit_user(self):
        u = self.users.selected_data()
        if u and UserDialog(self, u).exec() == QDialog.Accepted:
            self.load_users()

    def reset_pw(self):
        u = self.users.selected_data()
        if u:
            ChangePasswordDialog(self, u["id"]).exec()

    # ---------------------------------------------------------------- النسخ الاحتياطي
    def load_backups(self):
        rows = backup.list_backups()
        self.backups.set_rows([[os.path.basename(f), f"{size / 1024:.0f} KB", dt]
                               for f, size, dt in rows], [f for f, _, _ in rows])

    def choose_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد النسخ الاحتياطي")
        if d:
            self.backup_dir.setText(d)

    def backup_now(self):
        if self.backup_dir.text().strip() != (settings.get("backup_dir") or ""):
            settings.set("backup_dir", self.backup_dir.text().strip())
        try:
            path = backup.create_backup()
            info(self, f"تم حفظ النسخة:\n{path}")
        except Exception as e:
            error(self, e)
        self.load_backups()

    def _restore(self, path):
        if not ask(self, "سيتم استبدال كل البيانات الحالية بمحتوى النسخة المختارة (مع حفظ نسخة من الوضع الحالي أولاً).\n"
                         "هل أنت متأكد؟"):
            return
        try:
            backup.restore_backup(path)
            info(self, "تمت الاستعادة بنجاح. يُفضّل إعادة تشغيل البرنامج.")
        except Exception as e:
            error(self, e)
        self.load_backups()

    def restore(self):
        path = self.backups.selected_data()
        if path:
            self._restore(path)

    def restore_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف النسخة", "", "Database (*.db)")
        if path:
            self._restore(path)

    # ---------------------------------------------------------------- الترخيص
    def load_license(self):
        from core import license, vendor
        st = license.status()
        icon = {"licensed": "✅", "trial": "⏳"}.get(st["state"], "⛔")
        extra = ""
        if st["state"] == "licensed":
            extra = f"\nالمحل: {st['shop']} — الأجهزة المسموحة: {st['terminals'] or 'غير محدود'}"
        if st.get("key_error"):
            extra += f"\n⚠ المفتاح المحفوظ: {st['key_error']}"
        self.lic_status.setText(f"{icon} {st['message']}{extra}")
        self.machine_lbl.setText(st["machine_id"])
        v = [vendor.PRODUCT_NAME + f" — الإصدار {vendor.VERSION}", f"المزوّد: {vendor.VENDOR_NAME}"]
        if vendor.VENDOR_PHONE:
            v.append(f"الدعم: {vendor.VENDOR_PHONE} ({vendor.SUPPORT_HOURS})")
        if vendor.VENDOR_WEBSITE:
            v.append(vendor.VENDOR_WEBSITE)
        self.vendor_lbl.setText("  •  ".join(v))

    def show_license_tab(self):
        self.tabs.setCurrentIndex(self.license_tab)

    def copy_machine(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.machine_lbl.text())
        info(self, "تم نسخ رمز الجهاز.")

    def request_activation(self):
        from core import license, vendor, whatsapp
        from ui.widgets import open_whatsapp
        msg = license.request_message()
        url = whatsapp.link("+" + vendor.VENDOR_PHONE, msg) if vendor.VENDOR_PHONE else None
        open_whatsapp(self, url, msg)

    def activate_license(self):
        from core import license
        try:
            st = license.activate(self.lic_key.toPlainText())
        except (license.LicenseError, ValueError) as e:
            warn(self, str(e))
            return
        self.lic_key.clear()
        self.load_license()
        info(self, f"تم التفعيل بنجاح ✓\n{st['message']}")
        w = self.window()
        if hasattr(w, "update_license"):
            w.update_license()

    # ---------------------------------------------------------------- الشعار
    def show_pair_qr(self, address):
        from PySide6.QtGui import QPixmap
        import base64
        from core.einvoice import qr_data_uri
        uri = qr_data_uri(address)
        pm = QPixmap()
        if uri:
            pm.loadFromData(base64.b64decode(uri.split(",", 1)[1]))
            self.pair_qr.setPixmap(pm.scaled(160, 160, Qt.KeepAspectRatio, Qt.FastTransformation))
        else:
            self.pair_qr.setText(address)

    def load_logo(self):
        from PySide6.QtGui import QPixmap
        import base64
        data = settings.get("shop_logo_color") or settings.get("shop_logo") or ""
        if data:
            pm = QPixmap()
            pm.loadFromData(base64.b64decode(data))
            self.logo_lbl.setPixmap(pm.scaledToHeight(48))
        else:
            self.logo_lbl.setText("—")

    def choose_logo(self):
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        import base64
        path, _ = QFileDialog.getOpenFileName(self, "اختر صورة الشعار", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            warn(self, "تعذر قراءة الصورة")
            return
        from PySide6.QtCore import Qt as _Qt

        def b64(im):
            buf = QByteArray()
            io = QBuffer(buf)
            io.open(QIODevice.WriteOnly)
            im.save(io, "PNG")
            return base64.b64encode(bytes(buf)).decode("ascii")
        color = img.scaled(480, 480, _Qt.KeepAspectRatio, _Qt.SmoothTransformation) if max(img.width(), img.height()) > 480 else img
        gray = logo_for_thermal(img)
        settings.set_many({"shop_logo": b64(gray), "shop_logo_color": b64(color)})
        self.load_logo()
        w = self.window()
        if hasattr(w, "update_header"):
            w.update_header()                      # يظهر فوراً في القائمة الجانبية

    def clear_logo(self):
        settings.set_many({"shop_logo": "", "shop_logo_color": ""})
        self.load_logo()
        w = self.window()
        if hasattr(w, "update_header"):
            w.update_header()

    def test_terminal(self):
        from core import payments
        self.save()
        try:
            st = payments.status()
        except payments.TerminalError as e:
            warn(self, str(e))
            return
        (info if st.get("ok") else warn)(self, f"{'✓ متصل' if st.get('ok') else '✗'} {st.get('terminal') or st.get('message', '')}")


class WalletsEditor(QWidget):
    """جدول بسيط لطرق الدفع الإلكتروني: الاسم، الحساب، أين يصل المال، رمز QR"""

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QTableWidget, QHeaderView
        from core import wallets
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["الاسم", "رقم الحساب أو الهاتف أو الاسم المستعار", "يصل المال إلى",
                                              "نص رمز QR من التطبيق (اختياري)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(220)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("+ إضافة طريقة دفع", "secondaryBtn", lambda: self.add_row({})))
        row.addWidget(button("حذف المحددة", "secondaryBtn", self.remove_row))
        row.addWidget(button("✨ اقتراحات لبلدي", "secondaryBtn", self.suggest))
        row.addStretch()
        lay.addLayout(row)
        self._dests = wallets.DESTS

    def add_row(self, w):
        from PySide6.QtWidgets import QTableWidgetItem
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(w.get("name", "")))
        self.table.setItem(r, 1, QTableWidgetItem(w.get("account", "")))
        combo = QComboBox()
        for k, label in self._dests.items():
            combo.addItem(label, k)
        combo.setCurrentIndex(max(0, combo.findData(w.get("dest", "wallet"))))
        self.table.setCellWidget(r, 2, combo)
        self.table.setItem(r, 3, QTableWidgetItem(w.get("qr", "")))

    def remove_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def suggest(self):
        from core import wallets
        have = {w["name"] for w in self.items()}
        added = 0
        for w in wallets.presets():
            if w["name"] not in have:
                self.add_row(w)
                added += 1
        if added:
            info(self, "أُضيفت طرق الدفع الشائعة في بلدك. اكتب رقم حسابك أو هاتفك لكل واحدة، واحذف ما لا تستخدمه، ثم احفظ.")

    def set_items(self, items):
        self.table.setRowCount(0)
        for w in items:
            self.add_row(w)

    def items(self):
        out = []
        for r in range(self.table.rowCount()):
            cell = lambda c: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
            combo = self.table.cellWidget(r, 2)
            if cell(0):
                out.append({"name": cell(0), "account": cell(1), "dest": combo.currentData() if combo else "wallet",
                            "qr": cell(3)})
        return out

