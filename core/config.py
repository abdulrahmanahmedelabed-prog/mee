# -*- coding: utf-8 -*-
"""
إعدادات هذا الجهاز فقط (تُحفظ في ملف data/terminal.json وليس في قاعدة البيانات):
وضع التشغيل (مستقل/خادم/نقطة بيع فرعية)، اسم الجهاز، الطابعة، درج النقود...
لأن كل جهاز كاشير له طابعته ودرجه الخاص.
"""

import json
import os
import secrets
import socket

MODE_STANDALONE = "standalone"   # جهاز واحد
MODE_SERVER = "server"           # الجهاز الرئيسي: يحفظ البيانات ويخدم بقية الأجهزة
MODE_CLIENT = "client"           # نقطة بيع فرعية تتصل بالجهاز الرئيسي

DEFAULTS = {
    "mode": MODE_STANDALONE,
    "terminal_name": "",
    "server_host": "",
    "server_port": 8765,
    "link_code": "",               # رمز الربط السري بين الأجهزة
    "owner_web": "0",              # تشغيل لوحة المالك على الجوال في الوضع المستقل
    # الطباعة
    "printer_name": "",
    "receipt_width_mm": "80",
    "auto_print_receipt": "0",
    # درج النقود
    "drawer_mode": "none",         # none / printer / network / serial
    "drawer_printer": "",
    "drawer_host": "",
    "drawer_port": 9100,
    "drawer_serial": "COM1",
    "drawer_on_cash_sale": "1",
}

# مفاتيح تُقرأ من إعدادات الجهاز بدل إعدادات المحل العامة
LOCAL_KEYS = {"printer_name", "receipt_width_mm", "auto_print_receipt", "drawer_mode", "drawer_printer",
              "drawer_host", "drawer_port", "drawer_serial", "drawer_on_cash_sale"}

_cache = None


def _path():
    from core import db
    return os.path.join(db.DATA_DIR, "terminal.json")


def load():
    global _cache
    data = dict(DEFAULTS)
    try:
        with open(_path(), encoding="utf-8") as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        pass
    if not data["terminal_name"]:
        data["terminal_name"] = socket.gethostname() or "الكاشير 1"
    if not data["link_code"]:
        data["link_code"] = secrets.token_hex(3).upper()
    _cache = data
    return data


def save(values: dict):
    data = load()
    data.update(values)
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    global _cache
    _cache = data
    from core import context
    context.set_terminal(data["terminal_name"])


def get(key, default=None):
    if _cache is None:
        load()
    return _cache.get(key, default)


def reset_cache():
    global _cache
    _cache = None


def is_client():
    return get("mode") == MODE_CLIENT


def local_ip():
    """عنوان هذا الجهاز على الشبكة المحلية (لإدخاله في الأجهزة الفرعية)"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
