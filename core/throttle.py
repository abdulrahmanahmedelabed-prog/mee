# -*- coding: utf-8 -*-
"""
الحماية من تخمين كلمات المرور ورمز الربط عبر الشبكة:
بعد 5 محاولات خاطئة يُقفل الدخول من نفس الجهاز/لنفس الحساب 30 ثانية، وتتضاعف المدة مع كل خطأ إضافي
(حتى 15 دقيقة). الدخول الصحيح يصفّر العدّاد. في الذاكرة فقط: لا يمسّ قاعدة البيانات.
"""

import threading
import time

FREE_ATTEMPTS = 5
BASE_LOCK = 30
MAX_LOCK = 15 * 60

_lock = threading.Lock()
_fails = {}          # key -> [عدد الأخطاء، آخر خطأ، مقفل حتى]


def _keys(ip, username=None):
    keys = [("ip", ip or "")]
    if username:
        keys.append(("user", username.strip().lower()))
    return keys


def wait_seconds(ip, username=None):
    """كم ثانية يجب الانتظار قبل محاولة جديدة (0 = مسموح)"""
    now = time.time()
    with _lock:
        return max([int(_fails.get(k, [0, 0, 0])[2] - now + 0.999) for k in _keys(ip, username)] + [0])


def failed(ip, username=None):
    now = time.time()
    with _lock:
        if len(_fails) > 5000:           # حماية الذاكرة من سيل عناوين وهمية
            for k in [k for k, v in _fails.items() if v[2] < now and now - v[1] > 3600]:
                _fails.pop(k, None)
        for k in _keys(ip, username):
            n, last, until = _fails.get(k, [0, 0, 0])
            if now - last > 3600:
                n = 0
            n += 1
            if n >= FREE_ATTEMPTS:
                until = now + min(MAX_LOCK, BASE_LOCK * 2 ** (n - FREE_ATTEMPTS))
            _fails[k] = [n, now, until]


def succeeded(ip, username=None):
    with _lock:
        for k in _keys(ip, username):
            _fails.pop(k, None)


def message(seconds):
    from core import i18n
    if seconds >= 60:
        return i18n.tr(f"محاولات دخول خاطئة كثيرة. حاول بعد {(seconds + 59) // 60} دقيقة.")
    return i18n.tr(f"محاولات دخول خاطئة كثيرة. حاول بعد {seconds} ثانية.")


def reset():
    """للاختبارات"""
    with _lock:
        _fails.clear()
