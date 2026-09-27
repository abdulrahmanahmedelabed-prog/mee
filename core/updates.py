# -*- coding: utf-8 -*-
"""
التحقق من وجود نسخة جديدة: يقرأ ملف JSON صغيراً تنشره أنت (المطوّر) على موقعك أو على GitHub، مثل:
    {"version": "6.1", "url": "https://example.com/download", "notes": "إصلاحات وتحسينات"}
ويُضبط رابطه في core/vendor.py (UPDATE_URL). لا يُرسل أي بيانات عن الزبون.
"""

import json
import urllib.request


def parse_version(v):
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def check(url=None, current=None, timeout=4):
    """يرجع dict النسخة الجديدة إن وُجدت، وإلا None (ولا يرفع أي خطأ)"""
    from core import vendor
    url = url if url is not None else getattr(vendor, "UPDATE_URL", "")
    current = current or vendor.VERSION
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if is_newer(data.get("version", "0"), current):
            return data
    except Exception:
        return None
    return None
