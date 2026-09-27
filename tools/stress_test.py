# -*- coding: utf-8 -*-
"""
اختبار التحمّل: جهاز رئيسي حقيقي + عدة أجهزة كاشير تبيع في نفس الوقت عبر الشبكة + مدير يشغّل تقارير ثقيلة.

    python tools/stress_test.py مجلد_بيانات_للتجربة --terminals 8 --seconds 60 [--copy-from demo_data]

يعمل على نسخة من البيانات (لا تستخدم بيانات محل حقيقي). في النهاية يطبع السرعة وزمن الاستجابة والأخطاء،
ويفحص سلامة البيانات: أرقام الفواتير، المخزون، توازن القيود، الصندوق.
"""

import argparse
import json
import os
import random
import shutil
import socket
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run_server(data, port):
    """الجهاز الرئيسي (بدون حد لعدد الأجهزة أثناء الاختبار فقط)"""
    os.environ["SHOP_DATA_DIR"] = data
    from core import license, remote, db, config
    license.max_terminals = lambda: 0
    license.require_active = lambda: None
    db.init_db()
    remote.start_server(port=port)
    print("READY", flush=True)
    while True:
        time.sleep(3600)


def run_cashier(port, name, seconds, seed, pace=0.0):
    from core import remote, auth, products, sales, shifts, customers, wallets
    rnd = random.Random(seed)
    remote.install_client("127.0.0.1", port, "STRESS", name)
    auth.login("admin", "admin")
    catalog = [p for p in products.get_all_products() if p["sale_price"] > 0]
    custs = [c["id"] for c in customers.list_customers()][:20]
    wl = wallets.names()
    shift = shifts.open_shift(300)
    import uuid
    lat, errors, ok, retries, t_end = [], {}, 0, 0, time.time() + seconds

    def create(cart, **kw):
        """مثل نقطة البيع: معرّف فريد لكل فاتورة، وعند انقطاع الاتصال تُعاد المحاولة بنفس المعرّف"""
        nonlocal retries
        ref = f"{name}-{uuid.uuid4().hex}"
        while True:
            try:
                return sales.create_sale(cart, sale_ref=ref, **kw)
            except remote.ConnectionFailed:
                retries += 1
                if time.time() > t_end + 60:
                    raise
                time.sleep(0.5)
    while time.time() < t_end:
        t0 = time.time()
        try:
            p = rnd.choice(catalog)
            if p["barcode"] and rnd.random() < 0.5:
                products.lookup_code(p["barcode"])            # مسح باركود
            cart = [{"product_id": x["id"], "product_name": x["name"], "quantity": rnd.choice([1, 1, 2, 3]),
                     "unit_price": x["sale_price"]} for x in rnd.sample(catalog, rnd.randint(1, 6))]
            total = sales.compute_totals(cart, sales.cart_discounts(cart, 0, 0)["total"])["total"]   # مع العروض
            r = rnd.random()
            if r < 0.3 and wl:
                create(cart, wallet_amount=total, wallet_name=rnd.choice(wl), wallet_ref=str(rnd.randint(1, 10**8)),
                                  cash_amount=0, shift_id=shift)
            elif r < 0.45:
                create(cart, card_amount=total, cash_amount=0, shift_id=shift)
            elif r < 0.52 and custs:
                cid = rnd.choice(custs)
                customers.balance(cid)
                create(cart, customer_id=cid, credit_amount=total, cash_amount=0, shift_id=shift,
                                  allow_over_limit=True)
            else:
                create(cart, shift_id=shift, cash_received=total + 5)
            ok += 1
            lat.append(time.time() - t0)
            if pace:
                time.sleep(rnd.uniform(pace * 0.5, pace * 1.5))   # وقت مسح البضاعة وخدمة الزبون
        except remote.ConnectionFailed:              # الجهاز الرئيسي متوقف: الكاشير ينتظر ثم يكمل
            retries += 1
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            k = f"{type(e).__name__}: {str(e)[:80]}"
            errors[k] = errors.get(k, 0) + 1
    for _ in range(120):
        try:
            shifts.close_shift(shifts.summary(shift)["expected_cash"])
            break
        except remote.ConnectionFailed:
            time.sleep(0.5)
    print(json.dumps({"name": name, "ok": ok, "errors": errors, "lat": lat, "retries": retries}), flush=True)


def run_manager(port, seconds):
    from core import remote, auth, reports, ledger, wallets, insights
    remote.install_client("127.0.0.1", port, "STRESS", "المدير")
    auth.login("admin", "admin")
    first = "2000-01-01"
    lat, errors, t_end = [], {}, time.time() + seconds
    today = time.strftime("%Y-%m-%d")
    jobs = [lambda: reports.profit_and_loss(first, today), lambda: reports.period_summary(first, today, "month"),
            lambda: ledger.trial_balance(None, today), lambda: ledger.balance_sheet(),
            lambda: wallets.summary(first, today), lambda: reports.top_products(first, today, 50, "profit")]
    i = 0
    while time.time() < t_end:
        t0 = time.time()
        try:
            jobs[i % len(jobs)]()
            lat.append(time.time() - t0)
        except remote.ConnectionFailed:
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            k = f"{type(e).__name__}: {str(e)[:80]}"
            errors[k] = errors.get(k, 0) + 1
        i += 1
    print(json.dumps({"name": "manager", "ok": len(lat), "errors": errors, "lat": lat}), flush=True)


def pct(values, p):
    return sorted(values)[min(len(values) - 1, int(len(values) * p))] if values else 0


def integrity(data, before):
    os.environ["SHOP_DATA_DIR"] = data
    from core import db, ledger, shifts
    db.init_db()
    out = {}
    nums = [r[0] for r in db.query("SELECT invoice_number FROM invoices")]
    out["invoices_added"] = len(nums) - before
    out["duplicate_invoice_numbers"] = len(nums) - len(set(nums))
    out["stock_mismatch_products"] = db.scalar("""SELECT COUNT(*) FROM products p WHERE ABS(p.quantity -
        (SELECT COALESCE(SUM(change_qty),0) FROM stock_movements m WHERE m.product_id=p.id)) > 0.001""")
    out["invoices_without_items"] = db.scalar("""SELECT COUNT(*) FROM invoices i WHERE NOT EXISTS
        (SELECT 1 FROM invoice_items t WHERE t.invoice_id=i.id)""")
    out["unbalanced_invoices"] = db.scalar("""SELECT COUNT(*) FROM invoices
        WHERE ABS(cash_amount + card_amount + credit_amount + wallet_amount - total) > 0.01""")
    out["trial_balance_balanced"] = ledger.trial_balance(None, db.today())["totals"]["balanced"]
    out["balance_sheet_balanced"] = ledger.balance_sheet()["balanced"]
    out["open_shifts_left_by_cashiers"] = len([s for s in shifts.open_shifts() if str(s["terminal"] or "").startswith("كاشير")])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--terminals", type=int, default=8)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--copy-from")
    ap.add_argument("--role")
    ap.add_argument("--port", type=int)
    ap.add_argument("--name")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--crash", action="store_true", help="إيقاف الجهاز الرئيسي فجأة في منتصف الاختبار ثم إعادة تشغيله")
    ap.add_argument("--pace", type=float, default=0.0, help="متوسط الثواني بين فاتورتين لكل كاشير (0 = بأقصى سرعة)")
    a = ap.parse_args()
    if a.role == "server":
        return run_server(a.data, a.port)
    if a.role == "cashier":
        return run_cashier(a.port, a.name, a.seconds, a.seed, a.pace)
    if a.role == "manager":
        return run_manager(a.port, a.seconds)

    if a.copy_from:
        shutil.rmtree(a.data, ignore_errors=True)
        shutil.copytree(a.copy_from, a.data)
    os.makedirs(a.data, exist_ok=True)
    with open(os.path.join(a.data, "terminal.json"), "w", encoding="utf-8") as f:
        json.dump({"mode": "server", "link_code": "STRESS", "terminal_name": "الجهاز الرئيسي"}, f)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", SHOP_DATA_DIR=a.data)
    import sqlite3
    c = sqlite3.connect(os.path.join(a.data, "accounting.db"))
    before = c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] if c.execute(
        "SELECT name FROM sqlite_master WHERE name='invoices'").fetchone() else 0
    c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('allow_negative_stock', '1')") if before else None
    c.commit()
    c.close()
    port = free_port()
    me = os.path.abspath(__file__)
    srv = subprocess.Popen([sys.executable, me, a.data, "--role", "server", "--port", str(port)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    assert srv.stdout.readline().startswith("READY"), srv.stderr.read()
    print(f"الجهاز الرئيسي جاهز ({before:,} فاتورة سابقة). {a.terminals} كاشير + مدير تقارير لمدة {a.seconds} ثانية...")
    procs = [subprocess.Popen([sys.executable, me, a.data, "--role", "cashier", "--port", str(port),
                               "--name", f"كاشير {i + 1}", "--seconds", str(a.seconds), "--seed", str(i),
                               "--pace", str(a.pace)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
             for i in range(a.terminals)]
    procs.append(subprocess.Popen([sys.executable, me, a.data, "--role", "manager", "--port", str(port),
                                   "--seconds", str(a.seconds)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=env))
    crash_note = None
    if a.crash:
        time.sleep(a.seconds / 2)
        srv.kill()                                   # مثل انقطاع الكهرباء عن الجهاز الرئيسي
        srv.wait()
        time.sleep(3)
        srv = subprocess.Popen([sys.executable, me, a.data, "--role", "server", "--port", str(port)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        assert srv.stdout.readline().startswith("READY"), srv.stderr.read()
        crash_note = f"أُوقف الجهاز الرئيسي فجأة عند الثانية {a.seconds // 2} وأعيد تشغيله بعد 3 ثوانٍ"
    results = []
    for p in procs:
        out, err = p.communicate(timeout=a.seconds + 300)
        line = [x for x in out.splitlines() if x.startswith("{")]
        results.append(json.loads(line[-1]) if line else {"name": "?", "ok": 0, "errors": {err[-300:]: 1}, "lat": []})
    srv.terminate()
    srv.wait(timeout=20)
    cashiers = [r for r in results if r["name"] != "manager"]
    lat = [x for r in cashiers for x in r["lat"]]
    sales_ok = sum(r["ok"] for r in cashiers)
    errs = {}
    for r in results:
        for k, v in r["errors"].items():
            errs[k] = errs.get(k, 0) + v
    mgr = next(r for r in results if r["name"] == "manager")
    summary = {
        "terminals": a.terminals, "seconds": a.seconds, "sales": sales_ok,
        "sales_per_minute": round(sales_ok / a.seconds * 60),
        "sale_latency_ms": {"median": round(statistics.median(lat) * 1000) if lat else None,
                            "p95": round(pct(lat, 0.95) * 1000), "max": round(max(lat) * 1000) if lat else None},
        "manager_reports": mgr["ok"], "report_latency_ms_median": round(statistics.median(mgr["lat"]) * 1000)
        if mgr["lat"] else None,
        "errors": errs, "crash": crash_note, "retries_after_disconnect": sum(r.get("retries", 0) for r in cashiers),
        "integrity": integrity(a.data, before)}
    summary["integrity"]["all_sales_recorded"] = summary["integrity"]["invoices_added"] == sales_ok
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
