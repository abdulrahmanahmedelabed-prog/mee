# -*- coding: utf-8 -*-
"""معالج الإعداد الأول: بيانات المحل والعملة والضريبة ونقاط الولاء في شاشة واحدة (يظهر مرة واحدة)"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QComboBox, QCheckBox, QDoubleSpinBox

from core import settings, db, remote
from ui.widgets import ok_cancel, hint, title, warn

CURRENCIES = [("₪", "شيكل"), ("د.أ", "دينار"), ("$", "دولار"), ("ج.م", "جنيه"), ("ر.س", "ريال"), ("د.إ", "درهم"),
              ("€", "Euro"), ("£", "Pound"), ("₺", "Lira"), ("₹", "Rupee"), ("KWD", "Dinar"), ("QAR", "Riyal"),
              ("MAD", "Dirham"), ("TND", "Dinar"), ("DZD", "Dinar"), ("IQD", "Dinar")]
COUNTRY_CODES = [("970", "فلسطين"), ("972", "الداخل"), ("962", "الأردن"), ("20", "مصر"), ("966", "السعودية"),
                 ("971", "الإمارات"), ("961", "لبنان"), ("963", "سوريا"), ("964", "العراق"), ("965", "Kuwait"),
                 ("974", "Qatar"), ("973", "Bahrain"), ("968", "Oman"), ("967", "Yemen"), ("212", "Morocco"),
                 ("213", "Algeria"), ("216", "Tunisia"), ("218", "Libya"), ("249", "Sudan"), ("90", "Türkiye"),
                 ("1", "USA / Canada"), ("44", "United Kingdom"), ("49", "Germany"), ("33", "France"), ("91", "India"),
                 ("92", "Pakistan"), ("62", "Indonesia"), ("60", "Malaysia"), ("234", "Nigeria"), ("254", "Kenya")]
EN_DEFAULTS = {"receipt_footer": "Thank you for your visit",
               "expense_categories": "Rent,Electricity,Water,Salaries,Internet & phone,Transport,Maintenance,Cleaning,"
                                     "Hospitality,Other"}


def needs_setup():
    if remote.is_client():
        return False
    try:
        return db.get_meta("setup_done") != "1"
    except Exception:
        return False


class SetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("مرحباً بك — الإعداد الأول")
        self.setMinimumWidth(520)
        lay = QFormLayout(self)
        lay.addRow(title("🏪 لنجهّز برنامجك خلال دقيقة"))
        lay.addRow(hint("يمكنك تعديل كل شيء لاحقاً من شاشة الإعدادات."))
        from core import i18n, config
        self.lang = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(config.get("language") or "ar")))
        lay.addRow("اللغة / Language:", self.lang)
        self.name = QLineEdit(settings.get("shop_name") if settings.get("shop_name") != "محلي" else "")
        self.name.setPlaceholderText("مثل: سوبرماركت الأمل")
        self.phone = QLineEdit(settings.get("shop_phone"))
        self.address = QLineEdit(settings.get("shop_address"))
        self.currency = QComboBox()
        for sym, name in CURRENCIES:
            self.currency.addItem(f"{name} ({sym})", (sym, name))
        self.country = QComboBox()
        for code, name in COUNTRY_CODES:
            self.country.addItem(f"{name} (+{code})", code)
        self.vat = QCheckBox("المحل مسجّل في ضريبة القيمة المضافة")
        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0, 50)
        self.vat_rate.setValue(settings.get_float("vat_rate", 16))
        self.vat_rate.setEnabled(False)
        self.vat.toggled.connect(self.vat_rate.setEnabled)
        self.loyalty = QCheckBox("تفعيل نقاط الولاء للزبائن الدائمين (نقطة لكل 1، النقطة = 0.05)")
        self.owner = QLineEdit(settings.get("owner_whatsapp"))
        self.owner.setPlaceholderText("0599xxxxxx")
        self.require_shift = QCheckBox("إلزام الكاشير بفتح وردية وعدّ الصندوق (موصى به)")
        self.require_shift.setChecked(settings.get_bool("require_shift"))
        lay.addRow("اسم المحل:", self.name)
        lay.addRow("الهاتف:", self.phone)
        lay.addRow("العنوان:", self.address)
        lay.addRow("العملة:", self.currency)
        lay.addRow("الدولة (لأرقام واتساب):", self.country)
        lay.addRow("", self.vat)
        lay.addRow("نسبة الضريبة %:", self.vat_rate)
        lay.addRow("", self.loyalty)
        lay.addRow("واتساب المالك (لملخص اليوم):", self.owner)
        lay.addRow("", self.require_shift)
        self.shop_type = QComboBox()
        self.shop_type.addItem("دكان أو محل صغير (وضع مبسّط — يمكن تغييره لاحقاً)", "simple")
        self.shop_type.addItem("سوبرماركت أو محل كبير (كل الميزات)", "full")
        lay.addRow("نوع المحل:", self.shop_type)
        self.touch = QCheckBox("الجهاز بشاشة لمس (أزرار أكبر ولوحة أرقام)")
        lay.addRow("", self.touch)
        bb = ok_cancel(self, lay, "ابدأ ✓")
        bb.button(QDialogButtonBox.Cancel).setText("لاحقاً")

    def accept(self):
        name = self.name.text().strip()
        if not name:
            warn(self, "اكتب اسم المحل")
            return
        sym, cname = self.currency.currentData()
        settings.set_many({"shop_name": name, "shop_phone": self.phone.text().strip(),
                           "shop_address": self.address.text().strip(), "currency_symbol": sym, "currency_name": cname,
                           "whatsapp_country_code": self.country.currentData(), "vat_enabled": self.vat.isChecked(),
                           "vat_rate": f"{self.vat_rate.value():g}", "loyalty_enabled": self.loyalty.isChecked(),
                           "owner_whatsapp": self.owner.text().strip(), "require_shift": self.require_shift.isChecked()})
        from core import config
        lang = self.lang.currentData()
        config.save({"language": lang, "touch_mode": "1" if self.touch.isChecked() else "0"})
        settings.set("simple_mode", "1" if self.shop_type.currentData() == "simple" else "0")
        if lang != "ar":
            settings.set_many(EN_DEFAULTS)
        db.set_meta("setup_done", "1")
        super().accept()
