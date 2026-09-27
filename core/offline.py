# -*- coding: utf-8 -*-
"""
البيع أثناء انقطاع الشبكة (لنقاط البيع الفرعية):

- بعد الدخول وكل 10 دقائق تُحفظ نسخة محلية من الأصناف والوحدات والعروض والإعدادات (offline_cache.json).
- إذا انقطع الجهاز الرئيسي: نقطة البيع تكمل البيع (نقدي وبطاقة فقط) من النسخة المحلية،
  وتحفظ كل فاتورة في طابور محلي (offline_queue.json) بمعرّف فريد.
- عند عودة الاتصال تُرحَّل الفواتير تلقائياً بأوقاتها الأصلية. الخادم يرفض تكرار نفس الفاتورة،
  فلا مشكلة إن انقطع الاتصال أثناء الترحيل.
- الآجل ونقاط الولاء والمرتجعات تحتاج الاتصال (لأنها تعتمد على أرصدة لا يعرفها الجهاز الفرعي وحده).
"""

import json
import os
import threading
import time
import uuid

from core import db, settings, context, auth
from core.barcode import parse_scale_barcode
from core.utils import money, qty

_lock = threading.Lock()
CACHE_MAX_AGE = 600  # ثانية


def _path(name):
    os.makedirs(db.DATA_DIR, exist_ok=True)
    return os.path.join(db.DATA_DIR, name)


def _write(name, data):
    tmp = _path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _path(name))   # كتابة ذرّية: لا يتلف الملف لو انقطعت الكهرباء أثناء الحفظ


def _read(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------------------
# النسخة المحلية
# ---------------------------------------------------------------------------

def refresh_cache():
    """تُستدعى والاتصال قائم: تحفظ ما يلزم للبيع بدون شبكة"""
    from core import products, promotions
    data = {
        "saved_at": time.time(),
        "products": [dict(p) for p in products.get_all_products()],
        "units": products.all_units(),
        "promotions": [dict(p) for p in promotions.active_promotions()],
        "settings": settings.all_values(),
    }
    with _lock:
        _write("offline_cache.json", data)
    return len(data["products"])


def cache():
    return _read("offline_cache.json", {"saved_at": 0, "products": [], "units": [], "promotions": [], "settings": {}})


def cache_age():
    c = cache()
    return time.time() - c["saved_at"] if c["saved_at"] else None


def _setting(c, key, default=None):
    return c["settings"].get(key, default)


def lookup_code(code):
    """مثل products.lookup_code لكن من النسخة المحلية: (المنتج، الكمية، الوحدة)"""
    code = (code or "").strip()
    c = cache()
    by_id = {p["id"]: p for p in c["products"]}
    for p in c["products"]:
        if p.get("barcode") == code:
            return p, None, None
    for u in c["units"]:
        if u.get("barcode") == code and u["product_id"] in by_id:
            return by_id[u["product_id"]], None, u
    parsed = parse_scale_barcode(code)
    if parsed:
        plu, value, mode = parsed
        for p in c["products"]:
            if p.get("plu_code") == plu:
                if mode == "weight":
                    return p, qty(value), None
                return p, qty(value / (p["sale_price"] or 1)), None
    return None, None, None


def search(text, favorites_only=False):
    c = cache()
    words = (text or "").split()
    out = []
    for p in c["products"]:
        if favorites_only and not p.get("is_favorite"):
            continue
        hay = f"{p['name']} {p.get('barcode') or ''}"
        if all(w in hay for w in words):
            out.append(p)
    return sorted(out, key=lambda p: p["name"])


def get_product(product_id):
    return next((p for p in cache()["products"] if p["id"] == product_id), None)


def discounts(cart, manual_discount=0.0):
    """خصم العروض من النسخة المحلية (بنفس منطق الجهاز الرئيسي)"""
    from core import promotions
    c = cache()
    promo = {"total": 0.0, "lines": []}
    if cart and str(_setting(c, "promotions_enabled", "1")) == "1" and c["promotions"]:
        today = db.today()
        active = [p for p in c["promotions"] if (not p.get("start_date") or p["start_date"] <= today)
                  and (not p.get("end_date") or p["end_date"] >= today)]
        cats = {p["id"]: p.get("category") for p in c["products"]}
        promo = promotions.compute(cart, active, cats)
    manual = money(max(manual_discount or 0, 0))
    return {"manual": manual, "promo": promo["total"], "promo_lines": promo["lines"], "points_value": 0.0,
            "total": money(manual + promo["total"])}


# ---------------------------------------------------------------------------
# طابور الفواتير
# ---------------------------------------------------------------------------

def queue():
    return _read("offline_queue.json", [])


def pending_count():
    return len([q for q in queue() if not q.get("error")])


def queue_sale(cart, discount, promo_discount, cash_amount, card_amount, cash_received, shift_id,
               wallet_amount=0.0, wallet_name="", wallet_ref="", card_ref=""):
    from core import sales
    if not cart:
        raise sales.SaleError("السلة فارغة")
    t = sales.compute_totals(cart, money(discount + promo_discount))
    if abs(money(cash_amount + card_amount + (wallet_amount or 0)) - t["total"]) > 0.009:
        raise sales.SaleError("مجموع المدفوع لا يساوي إجمالي الفاتورة")
    clean_cart = [{k: it[k] for k in ("product_id", "product_name", "quantity", "unit_price", "factor", "unit_name",
                                       "list_price") if k in it} for it in cart]
    payload = {"ref": f"{context.terminal()}-{uuid.uuid4().hex}", "created_at": db.now(), "cart": clean_cart,
               "discount": money(discount), "promo_discount": money(promo_discount), "cash_amount": money(cash_amount),
               "card_amount": money(card_amount), "wallet_amount": money(wallet_amount or 0),
               "wallet_name": wallet_name or "", "wallet_ref": wallet_ref or "", "card_ref": card_ref or "",
               "cash_received": money(cash_received or cash_amount),
               "shift_id": shift_id, "user": (auth.current_user() or {}).get("username"), "total": t["total"],
               "subtotal": t["subtotal"], "tax": t["tax"], "change": money((cash_received or cash_amount) - cash_amount)}
    with _lock:
        q = queue()
        q.append(payload)
        _write("offline_queue.json", q)
    return payload


def sync():
    """ترحيل الطابور للجهاز الرئيسي. يرجع (عدد المرحّل، عدد المتعذر). يتوقف عند انقطاع الاتصال"""
    from core import sales, remote
    synced = failed = 0
    with _lock:
        q = queue()
        remaining = []
        stop = False
        for item in q:
            if stop:
                remaining.append(item)
                continue
            try:
                sales.import_offline_sale(item)
                synced += 1
            except remote.ConnectionFailed:
                remaining.append(item)
                stop = True
            except (sales.SaleError, ValueError, remote.RemoteError) as e:
                item["error"] = str(e)   # تبقى ظاهرة للمدير (مثلاً انتهاء الترخيص) وتُعاد محاولتها لاحقاً
                remaining.append(item)
                failed += 1
        _write("offline_queue.json", remaining)
    return synced, failed


def retry_failed():
    with _lock:
        q = queue()
        for item in q:
            item.pop("error", None)
        _write("offline_queue.json", q)
