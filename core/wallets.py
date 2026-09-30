# -*- coding: utf-8 -*-
"""
الدفع بالمحافظ الإلكترونية وتطبيقات البنوك (تحويل فوري، محافظ الجوال، الدفع برمز QR):

صاحب المحل يعرّف طرق الدفع التي يقبلها مرة واحدة (الإعدادات ← الدفع الإلكتروني):
  الاسم، رقم الحساب أو الهاتف أو الاسم المستعار الذي يحوّل إليه الزبون، أين يصل المال
  (رصيد المحفظة أو حساب البنك مباشرة)، ونص رمز QR الخاص بالمحل إن وُجد.

عند الدفع: زر لكل طريقة يعرض للكاشير (ولشاشة الزبون) رقم الحساب ورمز QR، ويسجّل رقم العملية من إشعار الزبون.
محاسبياً: ما يصل للمحفظة يُقيَّد في حساب «المحافظ الإلكترونية» وما يصل للبنك في «البنك»، وتحويل رصيد المحفظة
للبنك وعمولاتها عمليات مالية جاهزة. وتقرير «الدفع الإلكتروني» يطابق مجموع كل طريقة مع كشفها.

التأكيد الآلي للدفع (بدون رقم عملية يكتبه الكاشير) يحتاج حساب تاجر وواجهة برمجية من كل مزوّد.
"""

import json

from core import db, settings
from core.utils import money

DEST_WALLET, DEST_BANK = "wallet", "bank"
DESTS = {DEST_WALLET: "رصيد المحفظة", DEST_BANK: "حساب البنك مباشرة"}

# طرق شائعة حسب رمز الدولة (اقتراحات فقط؛ صاحب المحل يعدّلها ويضيف رقم حسابه)
PRESETS = {
    "970": [("PalPay", DEST_WALLET), ("Jawwal Pay", DEST_WALLET), ("تحويل بنكي فوري", DEST_BANK)],
    "972": [("Bit", DEST_BANK), ("PayBox", DEST_BANK), ("تحويل بنكي", DEST_BANK)],
    "962": [("CliQ", DEST_BANK), ("Zain Cash", DEST_WALLET), ("Orange Money", DEST_WALLET)],
    "966": [("STC Pay", DEST_WALLET), ("تحويل سريع (سريع)", DEST_BANK)],
    "971": [("Aani", DEST_BANK), ("تحويل بنكي", DEST_BANK)],
    "20": [("InstaPay", DEST_BANK), ("Vodafone Cash", DEST_WALLET)],
    "212": [("تحويل فوري", DEST_BANK)],
    "964": [("Zain Cash", DEST_WALLET), ("FastPay", DEST_WALLET)],
}


def all_wallets():
    """قائمة طرق الدفع المعرّفة: [{name, account, dest, qr}]"""
    try:
        items = json.loads(settings.get("wallets") or "[]")
    except ValueError:
        return []
    out = []
    for w in items if isinstance(items, list) else []:
        name = str(w.get("name") or "").strip()
        if name:
            out.append({"name": name, "account": str(w.get("account") or "").strip(),
                        "dest": w.get("dest") if w.get("dest") in DESTS else DEST_WALLET,
                        "qr": str(w.get("qr") or "").strip()})
    return out


def get(name):
    return next((w for w in all_wallets() if w["name"] == name), None)


def names():
    return [w["name"] for w in all_wallets()]


def to_json(items):
    """للحفظ في الإعدادات (مع التحقق من الأسماء المكررة)"""
    seen, clean = set(), []
    for w in items:
        name = str(w.get("name") or "").strip()
        if not name:
            continue
        if name in seen:
            raise ValueError(f"اسم طريقة الدفع مكرر: {name}")
        seen.add(name)
        clean.append({"name": name, "account": str(w.get("account") or "").strip(),
                      "dest": w.get("dest") if w.get("dest") in DESTS else DEST_WALLET,
                      "qr": str(w.get("qr") or "").strip()})
    return json.dumps(clean, ensure_ascii=False)


def presets(country_code=None):
    code = str(country_code or settings.get("whatsapp_country_code") or "970").lstrip("+")
    return [{"name": n, "account": "", "dest": d, "qr": ""} for n, d in PRESETS.get(code, PRESETS["970"])]


def qr_text(w):
    """نص رمز QR: رمز المحل الرسمي من التطبيق إن وُضع، وإلا رقم الحساب نفسه (يُمسح وينسخه الزبون)"""
    return w.get("qr") or w.get("account") or ""


def summary(date_from, date_to):
    """تقرير المطابقة: لكل طريقة دفع إلكتروني عدد العمليات ومجموعها (مبيعات + تسديد ديون − مبالغ أُعيدت للزبائن) في الفترة"""
    rows = db.query("""SELECT wallet_name AS name, COUNT(*) AS count, COALESCE(SUM(wallet_amount),0) AS sales
                       FROM invoices WHERE wallet_amount > 0 AND date(created_at) BETWEEN date(?) AND date(?)
                       GROUP BY wallet_name""", (date_from, date_to))
    out = {r["name"]: {"name": r["name"], "count": r["count"], "sales": money(r["sales"]), "debts": 0.0}
           for r in rows}
    known = set(names())
    if known:
        marks = ",".join("?" * len(known))
        for r in db.query(f"""SELECT method AS name, COUNT(*) AS count, COALESCE(SUM(-amount),0) AS paid
                              FROM customer_transactions WHERE type='payment' AND method IN ({marks})
                              AND date(created_at) BETWEEN date(?) AND date(?) GROUP BY method""",
                          (*known, date_from, date_to)):
            row = out.setdefault(r["name"], {"name": r["name"], "count": 0, "sales": 0.0, "debts": 0.0})
            row["count"] += r["count"]
            row["debts"] = money(r["paid"])
    for r in db.query("""SELECT r.refund_method AS name, COALESCE(SUM(r.total),0) AS t FROM returns r
                         JOIN invoices i ON i.id=r.invoice_id
                         WHERE r.refund_method = i.wallet_name AND date(r.created_at) BETWEEN date(?) AND date(?)
                         GROUP BY r.refund_method""", (date_from, date_to)):
        row = out.setdefault(r["name"], {"name": r["name"], "count": 0, "sales": 0.0, "debts": 0.0})
        row["refunds"] = money(r["t"])
    dests = {w["name"]: w["dest"] for w in all_wallets()}
    result = []
    for row in out.values():
        row.setdefault("refunds", 0.0)
        row["total"] = money(row["sales"] + row["debts"] - row["refunds"])
        row["dest"] = DESTS.get(dests.get(row["name"]), "—")
        result.append(row)
    return sorted(result, key=lambda r: -r["total"])


def invoices(name, date_from, date_to):
    """عمليات طريقة دفع معيّنة (لمطابقتها مع كشف المحفظة أو البنك سطراً بسطر)"""
    return db.query("""SELECT invoice_number, created_at, wallet_amount, wallet_ref FROM invoices
                       WHERE wallet_name=? AND wallet_amount > 0 AND date(created_at) BETWEEN date(?) AND date(?)
                       ORDER BY created_at""", (name, date_from, date_to))
