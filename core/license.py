# -*- coding: utf-8 -*-
"""
الترخيص والتفعيل (لبيع البرنامج):

- فترة تجربة مجانية كاملة المزايا (30 يوماً) تبدأ من أول تشغيل.
- بعدها يحتاج البرنامج "مفتاح تفعيل" خاصاً بجهاز الزبون (رمز الجهاز) يصدره المطوّر بأداة tools/license_tool.py.
- المفتاح موقّع رقمياً (RSA-SHA256): البرنامج يحمل المفتاح العام فقط، فلا يمكن توليد مفاتيح مزيفة
  بدون المفتاح الخاص الموجود عند المطوّر وحده.
- عند انتهاء التجربة أو الاشتراك: يتوقف البيع فقط. التقارير والديون والنسخ الاحتياطي تبقى متاحة؛
  لا نحتجز بيانات الزبون أبداً.

صيغة المفتاح: SA1.<بيانات base64>.<توقيع base64>
البيانات: shop (اسم المحل)، machine (رمز الجهاز)، plan، terminals (0 = غير محدود)، expires (فارغ = دائم)، issued، id
"""

import base64
import hashlib
import json
import os
import sys
import uuid
from datetime import date, timedelta

from core import db

TRIAL_DAYS = 30
TRIAL_TERMINALS = 3
PREFIX = "SA1"
PLANS = {"basic": "الأساسية (جهاز واحد)", "pro": "الاحترافية (حتى 3 أجهزة)", "enterprise": "الشاملة (أجهزة غير محدودة)",
         "subscription": "اشتراك شهري/سنوي"}

try:
    from core.license_pubkey import PUBLIC_KEY
except ImportError:  # لم يُولّد المطوّر مفاتيحه بعد
    PUBLIC_KEY = None

# DigestInfo لخوارزمية SHA-256 (معيار PKCS#1 v1.5)
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


class LicenseError(ValueError):
    pass


# ---------------------------------------------------------------------------
# رمز الجهاز
# ---------------------------------------------------------------------------

def _raw_machine_id():
    if os.environ.get("SHOP_MACHINE_ID"):
        return os.environ["SHOP_MACHINE_ID"]
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                 winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0))
            return winreg.QueryValueEx(key, "MachineGuid")[0]
        except OSError:
            pass
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p) as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            pass
    return str(uuid.getnode())


def machine_id():
    """رمز قصير يرسله الزبون للمطوّر، مثل: 4F1A-9C03-7B2E-D5A8"""
    h = hashlib.sha256(("shop-accounting|" + _raw_machine_id()).encode("utf-8")).hexdigest().upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def normalize_machine(code):
    code = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


# ---------------------------------------------------------------------------
# التوقيع والتحقق (RSA بدون مكتبات خارجية)
# ---------------------------------------------------------------------------

def _b64e(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _encoded_digest(payload: bytes, k: int) -> int:
    t = _SHA256_PREFIX + hashlib.sha256(payload).digest()
    if k < len(t) + 11:
        raise LicenseError("المفتاح قصير جداً")
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return int.from_bytes(em, "big")


def sign(payload: bytes, private_key: dict) -> bytes:
    n, d = private_key["n"], private_key["d"]
    k = (n.bit_length() + 7) // 8
    return pow(_encoded_digest(payload, k), d, n).to_bytes(k, "big")


def verify_signature(payload: bytes, signature: bytes, public_key: dict) -> bool:
    n, e = public_key["n"], public_key["e"]
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    return pow(s, e, n) == _encoded_digest(payload, k)


def make_key(data: dict, private_key: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{PREFIX}.{_b64e(payload)}.{_b64e(sign(payload, private_key))}"


def parse_key(key: str, public_key=None) -> dict:
    """يتحقق من المفتاح ويرجع بياناته، أو يرفع LicenseError"""
    public_key = public_key or PUBLIC_KEY
    if not public_key:
        raise LicenseError("لم يُجهَّز البرنامج بمفتاح الترخيص بعد.\n(للمطوّر: شغّل python tools/license_tool.py init)")
    key = "".join((key or "").split())
    parts = key.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LicenseError("صيغة مفتاح التفعيل غير صحيحة. انسخ المفتاح كاملاً كما وصلك.")
    try:
        payload, signature = _b64d(parts[1]), _b64d(parts[2])
    except (ValueError, TypeError):
        raise LicenseError("مفتاح التفعيل تالف")
    if not verify_signature(payload, signature, public_key):
        raise LicenseError("مفتاح التفعيل غير صالح")
    return json.loads(payload.decode("utf-8"))


# ---------------------------------------------------------------------------
# الحالة
# ---------------------------------------------------------------------------

def _effective_today():
    """نأخذ أحدث تاريخ شاهده البرنامج حتى لا يفيد إرجاع ساعة الجهاز للوراء"""
    today = date.today()
    last = db.get_meta("last_seen_date")
    try:
        last_d = date.fromisoformat(last) if last else None
    except ValueError:
        last_d = None
    if not last_d or today > last_d:
        try:
            db.set_meta("last_seen_date", today.isoformat())
        except Exception:
            pass
        return today
    return last_d


def _install_date():
    raw = db.get_meta("install_date") or db.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return date.today()


def status():
    """حالة الترخيص: licensed / trial / expired / license_expired"""
    today = _effective_today()
    mid = machine_id()
    out = {"machine_id": mid, "plan": None, "plan_label": None, "shop": None, "terminals": TRIAL_TERMINALS,
           "expires": None, "days_left": None, "key_error": None}
    key = db.get_meta("license_key")
    if key:
        try:
            data = parse_key(key)
            if normalize_machine(data.get("machine")) != mid:
                raise LicenseError("مفتاح التفعيل لجهاز آخر")
            out.update(plan=data.get("plan"), plan_label=PLANS.get(data.get("plan"), data.get("plan")),
                       shop=data.get("shop"), terminals=int(data.get("terminals") or 0), expires=data.get("expires") or None)
            if out["expires"]:
                left = (date.fromisoformat(out["expires"]) - today).days
                out["days_left"] = left
                if left < 0:
                    out.update(state="license_expired",
                               message=f"انتهى الاشتراك بتاريخ {out['expires']}. البيع متوقف حتى التجديد؛ بقية البرنامج تعمل.")
                    return out
            out.update(state="licensed", message=f"نسخة مفعّلة — {out['plan_label']}" +
                       (f" حتى {out['expires']}" if out["expires"] else " (دائمة)"))
            return out
        except (LicenseError, ValueError, KeyError) as e:
            out["key_error"] = str(e)
    left = TRIAL_DAYS - (today - _install_date()).days
    out["days_left"] = left
    if left > 0:
        out.update(state="trial", message=f"نسخة تجريبية — متبقٍ {left} يوماً")
    else:
        out.update(state="expired", terminals=1,
                   message="انتهت الفترة التجريبية. البيع متوقف حتى التفعيل؛ التقارير والبيانات متاحة.")
    return out


def can_sell():
    return status()["state"] in ("licensed", "trial")


def require_active():
    st = status()
    if st["state"] not in ("licensed", "trial"):
        raise LicenseError(st["message"] + "\nللتفعيل: الإعدادات ← الترخيص والتفعيل.")


def activate(key):
    data = parse_key(key)
    if normalize_machine(data.get("machine")) != machine_id():
        raise LicenseError(f"هذا المفتاح صادر لجهاز آخر ({data.get('machine')}).\nرمز هذا الجهاز: {machine_id()}")
    if data.get("expires"):
        try:
            if date.fromisoformat(data["expires"]) < date.today():
                raise LicenseError(f"هذا المفتاح منتهي الصلاحية منذ {data['expires']}")
        except ValueError:
            raise LicenseError("تاريخ انتهاء غير صالح في المفتاح")
    db.set_meta("license_key", "".join(key.split()))
    from core import audit
    audit.log("تفعيل البرنامج", f"{data.get('plan')} - {data.get('shop')} - حتى {data.get('expires') or 'دائم'}")
    return status()


def max_terminals():
    """عدد أجهزة الكاشير المسموح (بما فيها الجهاز الرئيسي). 0 = غير محدود"""
    return status()["terminals"]


def request_message():
    """رسالة جاهزة يرسلها الزبون للمطوّر عبر واتساب لطلب التفعيل"""
    from core import settings
    return (f"طلب تفعيل برنامج المحاسبة ونقاط البيع\nالمحل: {settings.get('shop_name')}\n"
            f"الهاتف: {settings.get('shop_phone') or '-'}\nرمز الجهاز: {machine_id()}")
