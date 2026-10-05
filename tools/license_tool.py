# -*- coding: utf-8 -*-
"""
أداة المطوّر لإصدار مفاتيح التفعيل (لا تُسلَّم للزبائن أبداً).

الخطوة الأولى مرة واحدة فقط:
    python tools/license_tool.py init
    - تولّد زوج مفاتيح RSA-2048.
    - المفتاح الخاص يُحفظ في مجلدك الشخصي (~/.shop_license/private_key.json): احتفظ بنسخة منه في مكان آمن؛
      إذا فقدته لن تستطيع إصدار مفاتيح للنسخ التي وزّعتها.
    - المفتاح العام يُكتب في core/license_pubkey.py ويُبنى مع البرنامج.

إصدار مفتاح لزبون (يرسل لك رمز الجهاز من شاشة التفعيل):
    python tools/license_tool.py issue --machine 4F1A-9C03-7B2E-D5A8 --shop "سوبرماركت الأمل" --plan pro
    python tools/license_tool.py issue --machine ... --shop ... --plan max --expires 2027-01-31   (اشتراك سنوي)

التحقق من مفتاح:
    python tools/license_tool.py verify "SA1...."
"""

import argparse
import csv
import json
import os
import secrets
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import license as lic  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".shop_license")
PUBKEY_FILE = os.path.join(ROOT, "core", "license_pubkey.py")

_SMALL_PRIMES = [p for p in range(3, 2000) if all(p % q for q in range(2, int(p ** 0.5) + 1))]


def _is_probable_prime(n, rounds=40):
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _random_prime(bits):
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _is_probable_prime(c):
            return c


def generate_keypair(bits=2048, e=65537):
    while True:
        p, q = _random_prime(bits // 2), _random_prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        d = pow(e, -1, phi)
        return {"n": n, "e": e}, {"n": n, "e": e, "d": d}


def cmd_init(args):
    key_dir = args.dir or DEFAULT_DIR
    priv_path = os.path.join(key_dir, "private_key.json")
    if os.path.exists(priv_path) and not args.force:
        print(f"يوجد مفتاح خاص مسبقاً: {priv_path}\n(استخدم --force لتوليد مفتاح جديد؛ المفاتيح القديمة ستتوقف عن العمل)")
        pub = json.load(open(priv_path))
        write_pubkey({"n": pub["n"], "e": pub["e"]})
        print(f"تم تحديث المفتاح العام في {PUBKEY_FILE}")
        return
    print("جارٍ توليد مفتاح RSA-2048 (قد يستغرق دقيقة)...")
    public, private = generate_keypair(args.bits)
    os.makedirs(key_dir, exist_ok=True)
    with open(priv_path, "w") as f:
        json.dump(private, f)
    try:
        os.chmod(priv_path, 0o600)
    except OSError:
        pass
    write_pubkey(public)
    print(f"✓ المفتاح الخاص: {priv_path}\n  احفظ نسخة منه في مكان آمن (فلاشة/خزنة). لا ترفعه على GitHub ولا ترسله لأحد.")
    print(f"✓ المفتاح العام: {PUBKEY_FILE}  (يُبنى مع البرنامج)")


def write_pubkey(public):
    with open(PUBKEY_FILE, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n# المفتاح العام للتحقق من مفاتيح التفعيل (مولّد بـ tools/license_tool.py init)\n")
        f.write(f"PUBLIC_KEY = {{'n': {public['n']}, 'e': {public['e']}}}\n")


def load_private(path=None):
    path = path or os.path.join(DEFAULT_DIR, "private_key.json")
    if not os.path.exists(path):
        sys.exit(f"لم يُعثر على المفتاح الخاص: {path}\nشغّل أولاً: python tools/license_tool.py init")
    return json.load(open(path))


def issue(private, machine, shop, plan="pro", terminals=3, expires=None):
    data = {"machine": lic.normalize_machine(machine), "shop": shop, "plan": plan, "terminals": int(terminals),
            "expires": expires or "", "issued": date.today().isoformat(), "id": secrets.token_hex(4).upper()}
    return lic.make_key(data, private), data


def log_issue(data, key, log_dir=None):
    """سجل المفاتيح المُصدرة (ملف CSV يفتح في Excel)"""
    log = os.path.join(log_dir or DEFAULT_DIR, "licenses_log.csv")
    new = not os.path.exists(log)
    with open(log, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["التاريخ", "المعرف", "المحل", "رمز الجهاز", "الخطة", "الأجهزة", "ينتهي", "المفتاح"])
        w.writerow([data["issued"], data["id"], data["shop"], data["machine"], data["plan"], data["terminals"],
                    data["expires"] or "دائم", key])
    return log


def reset_code(private, machine):
    data = {"type": "reset", "machine": lic.normalize_machine(machine), "date": date.today().isoformat(),
            "id": secrets.token_hex(4).upper()}
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{lic.RESET_PREFIX}.{lic._b64e(payload)}.{lic._b64e(lic.sign(payload, private))}"


def pubkey_status(key_dir=None):
    """هل المفتاح العام داخل البرنامج يطابق مفتاحك الخاص؟ يرجع (ok, message)"""
    priv_path = os.path.join(key_dir or DEFAULT_DIR, "private_key.json")
    if not os.path.exists(priv_path):
        return False, "none"
    private = json.load(open(priv_path))
    try:
        text = open(PUBKEY_FILE, encoding="utf-8").read()
    except OSError:
        return False, "missing"
    ok = f"'n': {private['n']}," in text
    return ok, "ok" if ok else "mismatch"


def init_keys(key_dir=None, bits=2048):
    """ينشئ زوج المفاتيح إن لم يوجد، ويكتب المفتاح العام داخل البرنامج. يرجع True إن أنشأ مفتاحاً جديداً"""
    key_dir = key_dir or DEFAULT_DIR
    priv_path = os.path.join(key_dir, "private_key.json")
    created = False
    if not os.path.exists(priv_path):
        public, private = generate_keypair(bits)
        os.makedirs(key_dir, exist_ok=True)
        with open(priv_path, "w") as f:
            json.dump(private, f)
        try:
            os.chmod(priv_path, 0o600)
        except OSError:
            pass
        created = True
    private = json.load(open(priv_path))
    write_pubkey({"n": private["n"], "e": private["e"]})
    return created


def cmd_issue(args):
    if args.plan not in lic.PLANS:
        sys.exit(f"الخطة يجب أن تكون واحدة من: {', '.join(lic.PLANS)}")
    if args.terminals is None:
        from core import plans
        args.terminals = plans.TERMINALS[args.plan]
    if args.expires:
        date.fromisoformat(args.expires)
    private = load_private(args.key)
    key, data = issue(private, args.machine, args.shop, args.plan, args.terminals, args.expires)
    log = log_issue(data, key, os.path.dirname(args.key) if args.key else None)
    print("\nمفتاح التفعيل (أرسله للزبون كما هو):\n")
    print(key)
    print(f"\n(سُجّل في {log})")


def cmd_reset(args):
    code = reset_code(load_private(args.key), args.machine)
    print("\nرمز استعادة كلمة مرور المدير (صالح 3 أيام ولمرة واحدة):\n")
    print(code)


def cmd_verify(args):
    pub = None
    if not lic.PUBLIC_KEY:
        p = load_private(args.key)
        pub = {"n": p["n"], "e": p["e"]}
    try:
        print(json.dumps(lic.parse_key(args.license, pub), ensure_ascii=False, indent=2))
    except lic.LicenseError as e:
        sys.exit(f"✗ {e}")


def main():
    ap = argparse.ArgumentParser(description="أداة مفاتيح التفعيل")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init", help="توليد زوج المفاتيح (مرة واحدة)")
    a.add_argument("--dir")
    a.add_argument("--bits", type=int, default=2048)
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=cmd_init)
    b = sub.add_parser("issue", help="إصدار مفتاح لزبون")
    b.add_argument("--machine", required=True)
    b.add_argument("--shop", required=True)
    b.add_argument("--plan", default="pro", help="plus / pro / max")
    b.add_argument("--terminals", type=int, default=None, help="0 = غير محدود (الافتراضي حسب الباقة: بلس 2، برو 5، ماكس غير محدود)")
    b.add_argument("--expires", help="YYYY-MM-DD للاشتراكات؛ اتركه فارغاً للترخيص الدائم")
    b.add_argument("--key", help="مسار المفتاح الخاص")
    b.set_defaults(fn=cmd_issue)
    r = sub.add_parser("reset", help="رمز استعادة كلمة مرور المدير لجهاز زبون")
    r.add_argument("--machine", required=True)
    r.add_argument("--key")
    r.set_defaults(fn=cmd_reset)
    c = sub.add_parser("verify", help="فحص مفتاح")
    c.add_argument("license")
    c.add_argument("--key")
    c.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
