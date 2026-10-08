# -*- coding: utf-8 -*-
"""
التحديث: التحقق من نسخة جديدة، ثم «تحديث الآن» بضغطة واحدة.

1. يقرأ صفحة آخر إصدار في GitHub (core/vendor.py: UPDATE_URL) أو ملف JSON بسيط:
       {"version": "6.1", "url": "https://example.com/download", "notes": "...", "setup_url": "https://.../Setup.exe",
        "sha256": "..."}
2. ينزّل ملف التثبيت عبر HTTPS ويتحقق من حجمه وبصمته SHA-256 (التي ينشرها GitHub مع كل ملف).
3. نسخة احتياطية من البيانات، ثم تثبيت صامت يحافظ على مجلد البيانات، وإعادة فتح البرنامج تلقائياً.
لا يُرسل أي بيانات عن الزبون.
"""

import hashlib
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request

SETUP_ASSET = "ShopAccounting-Setup.exe"
TRUSTED_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
                 "api.github.com")
MAX_SETUP_BYTES = 600 * 1024 * 1024


class UpdateError(Exception):
    pass


class Cancelled(Exception):
    pass


def parse_version(v):
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def _from_github(data):
    """صفحة الإصدار في GitHub (releases/latest) ← نفس صيغة ملف JSON البسيط"""
    out = {"version": str(data["tag_name"]).lstrip("vV"), "url": data.get("html_url", ""),
           "notes": data.get("name", ""), "body": (data.get("body") or "")[:4000]}
    for a in data.get("assets") or []:
        if a.get("name") == SETUP_ASSET:
            out["setup_url"] = a.get("browser_download_url", "")
            out["setup_size"] = int(a.get("size") or 0)
            digest = str(a.get("digest") or "")
            if digest.startswith("sha256:"):
                out["sha256"] = digest.split(":", 1)[1].lower()
    return out


def check(url=None, current=None, timeout=4, raise_errors=False):
    """يرجع dict النسخة الجديدة إن وُجدت، وإلا None. raise_errors: UpdateError عند تعذر الاتصال (للفحص اليدوي)"""
    from core import vendor
    url = url if url is not None else getattr(vendor, "UPDATE_URL", "")
    current = current or vendor.VERSION
    if not url:
        return None
    try:
        if not url.startswith("https://"):
            return None
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ShopAccounting"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(500_000).decode("utf-8"))
        return newer_than(data, current)
    except Exception as e:
        if raise_errors:
            raise UpdateError("تعذر الاتصال بخادم التحديثات. تأكد من الإنترنت وحاول لاحقاً") from e
        return None


def newer_than(data, current):
    if "tag_name" in data:
        data = _from_github(data)
    for key in ("url", "setup_url"):
        if not str(data.get(key, "")).startswith("https://"):
            data[key] = ""              # لا نفتح ولا ننزّل إلا روابط آمنة
    if is_newer(str(data.get("version", "0")), current):
        return data
    return None


# ---------------------------------------------------------------------------
# التحديث بضغطة واحدة
# ---------------------------------------------------------------------------

def app_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""


def can_self_update(info=None):
    """ويندوز + نسخة مثبّتة (وليست المحمولة أو تشغيلاً من الكود) + ملف تثبيت في الإصدار"""
    if info is not None and not info.get("setup_url"):
        return False
    d = app_dir()
    return sys.platform == "win32" and bool(d) and os.path.exists(os.path.join(d, "unins000.exe"))


def _trusted(url):
    p = urllib.parse.urlparse(url)
    return p.scheme == "https" and (p.hostname or "") in TRUSTED_HOSTS


def download(info, dest_dir=None, progress=None, cancelled=None, timeout=30, opener=None):
    """ينزّل ملف التثبيت ويتحقق منه. progress(done, total). يرجع مسار الملف"""
    url = info.get("setup_url") or ""
    if not url.startswith("https://"):
        raise UpdateError("لا يوجد رابط تنزيل آمن لهذه النسخة")
    if opener is None and not _trusted(url):
        raise UpdateError("رابط التنزيل ليس من مصدر موثوق")
    dest_dir = dest_dir or tempfile.gettempdir()
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"ShopAccounting-Setup-{info.get('version', 'new')}.exe")
    part = path + ".part"
    expected = int(info.get("setup_size") or 0)
    h = hashlib.sha256()
    done = 0
    req = urllib.request.Request(url, headers={"User-Agent": "ShopAccounting"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r, open(part, "wb") as f:
            final = r.geturl() if hasattr(r, "geturl") else url
            if opener is None and not _trusted(final):
                raise UpdateError("تحويل التنزيل إلى مصدر غير موثوق")
            total = int(r.headers.get("Content-Length") or expected or 0)
            if total > MAX_SETUP_BYTES:
                raise UpdateError("حجم ملف التحديث غير منطقي")
            while True:
                if cancelled and cancelled():
                    raise Cancelled()
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_SETUP_BYTES:
                    raise UpdateError("حجم ملف التحديث غير منطقي")
                h.update(chunk)
                f.write(chunk)
                if progress:
                    progress(done, total)
        if expected and done != expected:
            raise UpdateError("لم يكتمل التنزيل، حاول مرة أخرى")
        want = (info.get("sha256") or "").lower()
        if want and h.hexdigest() != want:
            raise UpdateError("ملف التحديث لا يطابق البصمة المنشورة (قد يكون تالفاً). لم يُثبَّت شيء")
        if os.path.exists(path):
            os.remove(path)
        os.replace(part, path)
        return path
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise


def installer_args(lang="ar"):
    """تثبيت صامت بنافذة تقدم صغيرة؛ يغلق البرنامج إن بقي مفتوحاً، ويعيد فتحه بعد الانتهاء (installer/*.iss)"""
    log = os.path.join(tempfile.gettempdir(), "ShopAccounting-update.log")
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS",
            "/LANG=" + ("arabic" if lang == "ar" else "english"), "/RELAUNCH=1", f'/LOG="{log}"']


def launch_installer(path, lang="ar"):
    """يشغّل المثبّت بصلاحية المدير (نافذة ويندوز للموافقة)؛ على البرنامج أن يُغلق نفسه بعدها مباشرة"""
    if sys.platform != "win32":
        raise UpdateError("التحديث التلقائي متاح على ويندوز فقط")
    os.startfile(path, "runas", " ".join(installer_args(lang)))   # noqa: S606 — مثبّتنا الذي تحققنا من بصمته
