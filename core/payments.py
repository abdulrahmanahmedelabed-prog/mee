# -*- coding: utf-8 -*-
"""
الربط مع أجهزة الدفع بالبطاقة (نقاط البيع البنكية):

كل بنك/مزوّد جهاز له بروتوكول خاص، لذلك البرنامج يتعامل مع الجهاز عبر «سائق» (driver):
- manual    : يدوي — الكاشير يُدخل المبلغ في الجهاز البنكي بنفسه ثم يكتبه في البرنامج (الوضع الافتراضي).
- simulator : محاكي للعرض والتدريب (يرفض أي مبلغ ينتهي بـ .13 لتجربة الرفض).
- bridge    : جسر مفتوح عبر HTTP/JSON على جهاز الكاشير. برنامج صغير خاص بكل بنك (يستخدم مكتبة/بروتوكول البنك)
              يطبّق هذا البروتوكول، والبرنامج لا يحتاج أي تعديل. مثال مرجعي كامل: tools/terminal_bridge.py

بروتوكول الجسر (ShopPOS Terminal Bridge v1):
  POST /sale   {"amount": 12.50, "currency": "ILS", "reference": "POS-..."}
       ←        {"approved": true, "auth_code": "123456", "rrn": "...", "card": "****1234", "message": "..."}
  GET  /status  ← {"ok": true, "terminal": "اسم الجهاز"}
"""

import json
import secrets
import time
import urllib.error
import urllib.request

from core import config, settings
from core.utils import money

MODES = {"manual": "يدوي (بدون ربط)", "simulator": "محاكي (للتجربة والتدريب)", "bridge": "جسر الجهاز البنكي (HTTP)"}


class TerminalError(Exception):
    pass


def mode():
    m = str(config.get("card_terminal") or "manual")
    return m if m in MODES else "manual"


def is_connected():
    return mode() != "manual"


def _result(approved, message="", auth_code="", rrn="", card=""):
    return {"approved": bool(approved), "message": message, "auth_code": auth_code, "rrn": rrn, "card": card,
            "reference": " ".join(x for x in (card, f"AUTH {auth_code}" if auth_code else "",
                                               f"RRN {rrn}" if rrn else "") if x)}


def simulate(amount):
    time.sleep(0.3)
    if f"{money(amount):.2f}".endswith(".13"):
        return _result(False, "مرفوضة: رصيد غير كافٍ")
    return _result(True, "موافقة", auth_code=f"{secrets.randbelow(10**6):06d}", rrn=secrets.token_hex(6).upper(),
                   card="****" + f"{secrets.randbelow(10**4):04d}")


def _bridge(path, payload=None, timeout=None):
    base = str(config.get("card_terminal_url") or "http://127.0.0.1:9900").rstrip("/")
    timeout = timeout or float(config.get("card_terminal_timeout") or 120)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise TerminalError(f"تعذر الاتصال بجهاز الدفع ({base}): {getattr(e, 'reason', e)}")


def status():
    m = mode()
    if m == "manual":
        return {"ok": False, "message": "لا يوجد ربط مع جهاز دفع"}
    if m == "simulator":
        return {"ok": True, "terminal": "محاكي"}
    return _bridge("/status", timeout=5)


def charge(amount, reference=""):
    """طلب دفع بالبطاقة على الجهاز. يرجع dict: approved, message, auth_code, rrn, card, reference"""
    amount = money(amount)
    if amount <= 0:
        raise TerminalError("المبلغ غير صحيح")
    m = mode()
    if m == "simulator":
        return simulate(amount)
    if m == "bridge":
        r = _bridge("/sale", {"amount": amount, "currency": settings.get("currency_name") or "",
                              "reference": reference or f"POS-{secrets.token_hex(4).upper()}"})
        return _result(r.get("approved"), r.get("message", ""), r.get("auth_code", ""), r.get("rrn", ""),
                       r.get("card", ""))
    raise TerminalError("لا يوجد ربط مع جهاز دفع (الإعدادات ← الطباعة ودرج النقود)")
