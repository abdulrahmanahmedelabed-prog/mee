# -*- coding: utf-8 -*-
"""إعدادات البرنامج (تُخزّن في قاعدة البيانات)"""

from core import db, config

DEFAULTS = {
    "shop_name": "محلي",
    "shop_address": "",
    "shop_phone": "",
    "tax_number": "",
    "currency_symbol": "₪",
    "currency_name": "شيكل",
    # الضريبة
    "vat_enabled": "0",
    "vat_rate": "16",
    "prices_include_vat": "1",
    # الفواتير (الطابعة ودرج النقود من إعدادات الجهاز: core/config.py)
    "receipt_footer": "شكراً لزيارتكم",
    # المخزون والبيع
    "allow_negative_stock": "0",
    "require_shift": "1",
    "cashier_max_discount_percent": "10",
    # باركود الميزان (للمنتجات الموزونة في السوبرماركت)
    "scale_enabled": "1",
    "scale_prefixes": "20,21,22,23,24,25,26,27,28,29",
    "scale_mode": "weight",        # weight = الوزن بالغرام / price = السعر
    "scale_code_length": "5",
    # النسخ الاحتياطي
    "backup_dir": "",
    "backup_mirror_dir": "",        # نسخة ثانية تلقائية (مجلد Google Drive / OneDrive / فلاشة)
    "backup_keep": "30",
    # الصلاحية
    "expiry_alert_days": "30",
    "block_expired_sale": "0",
    # واتساب
    "whatsapp_country_code": "970",
    "owner_whatsapp": "",           # رقم المالك لإرسال ملخص اليوم
    # نقاط الولاء
    "loyalty_enabled": "0",
    "loyalty_points_per_unit": "1",   # نقاط لكل 1 شيكل من قيمة الفاتورة
    "loyalty_point_value": "0.05",    # قيمة النقطة بالعملة عند الاستبدال
    "loyalty_min_redeem": "100",      # أقل عدد نقاط يمكن استبداله
    # العروض
    "promotions_enabled": "1",
    "target_margin_percent": "15",
    # المتجر الإلكتروني والطلبات (النسخة 6)
    "online_store_enabled": "0",
    "simple_mode": "0",               # الوضع المبسّط للدكاكين الصغيرة: يخفي الشاشات المتقدمة
    "shop_logo": "",                  # شعار المحل على الفاتورة (PNG/JPG بترميز base64)
    "online_store_delivery": "1",
    "online_store_delivery_fee": "0",
    "online_store_min_order": "0",
    "online_store_message": "اطلب من محلنا واستلم أو نوصلك 🛵",
    # الفاتورة الإلكترونية (رمز QR بصيغة الفوترة السعودية المبسطة)
    "einvoice_qr": "0",
    # عملات إضافية للدفع النقدي: رمز=سعر الصرف، مثل USD=3.65,JOD=5.15
    "extra_currencies": "",
    # المحافظ الإلكترونية وتطبيقات البنوك: JSON [{name, account, dest, qr}] (انظر core/wallets.py)
    "wallets": "[]",
    "wallet_ref_required": "0",   # إلزام الكاشير بكتابة رقم العملية     # هامش الربح المستهدف (للمستشار الذكي وتحديث الأسعار)
    "expense_categories": "إيجار,كهرباء,ماء,رواتب,إنترنت واتصالات,مواصلات,صيانة,تنظيف,ضيافة,أخرى",
}

_cache = {}


def ensure_defaults():
    with db.tx() as conn:
        for k, v in DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    reload()


def all_values():
    return {r["key"]: r["value"] for r in db.query("SELECT key, value FROM settings")}


def reload():
    values = all_values()
    _cache.clear()
    _cache.update(values)


def get(key, default=None):
    if key in config.LOCAL_KEYS:
        v = config.get(key)
        return str(v) if v is not None else default
    if not _cache:
        try:
            reload()
        except Exception:
            pass
    if key in _cache:
        return _cache[key]
    return DEFAULTS.get(key, default) if default is None else default


def get_bool(key):
    return str(get(key, "0")) in ("1", "true", "True")


def get_float(key, default=0.0):
    try:
        return float(get(key, default))
    except (TypeError, ValueError):
        return default


def set_many(values: dict):
    local = {k: (("1" if v else "0") if isinstance(v, bool) else str(v)) for k, v in values.items() if k in config.LOCAL_KEYS}
    if local:
        config.save(local)
    values = {k: v for k, v in values.items() if k not in config.LOCAL_KEYS}
    if values:
        save_shared(values)
    reload()


def save_shared(values: dict):
    with db.tx() as conn:
        for k, v in values.items():
            if isinstance(v, bool):
                v = "1" if v else "0"
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, str(v)))
    reload()   # مهم على الجهاز الرئيسي عندما يأتي التغيير من جهاز فرعي


def set(key, value):
    set_many({key: value})


def expense_categories():
    return [c.strip() for c in get("expense_categories", "").split(",") if c.strip()]
