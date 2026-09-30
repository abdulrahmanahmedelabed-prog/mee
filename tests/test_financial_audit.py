# -*- coding: utf-8 -*-
"""التدقيق المالي الآلي: يكتشف التلاعب والأخطاء الشائعة، ويعطي رأياً نظيفاً للدفاتر السليمة"""
import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import db, products, sales, customers, settings, wallets, financial_audit as fa  # noqa: E402


def item(pid, q, price):
    return {"product_id": pid, "product_name": "x", "quantity": q, "unit_price": price}


def titles(r, sev=None):
    return {f["title"] for f in r["findings"] if sev is None or f["severity"] == sev}


def audit():
    t = db.today()
    return fa.run("2000-01-01", t)


def shop():
    settings.set_many({"wallets": wallets.to_json([{"name": "PalPay", "account": "0599", "dest": "wallet"}])})
    a = products.add_product("أرز", "100", "مواد", 8, 10, 500, 5)
    for _ in range(5):
        sales.create_sale([item(a, 2, 10)])
    return a


def test_clean_books_get_clean_opinion():
    shop()
    r = audit()
    assert r["counts"]["critical"] == 0
    ok = titles(r, "ok")
    assert {"توازن الدفاتر", "مطابقة ديون العملاء", "مطابقة مستحقات الموردين", "مطابقة قيمة المخزون",
            "تسلسل المستندات", "سلامة الفواتير"} <= ok
    # لا ملاحظة مرتفعة إلا غياب النسخ الاحتياطي في بيئة الاختبار
    assert titles(r, "high") <= {"لا توجد نسخ احتياطية"}
    assert r["procedures"] == len(fa.CHECKS) and 0 <= r["score"] <= 100
    html = fa.report_html(r, "محل")
    assert r["opinion"] in html and "تقرير التدقيق المالي" in html


def test_detects_cash_refund_for_card_sale_and_duplicate_wallet_ref():
    a = shop()
    s = sales.create_sale([item(a, 3, 10)], card_amount=30)
    it = sales.returnable_items(s["invoice_id"])[0]
    sales.create_return(s["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 3}], refund_method=sales.REFUND_CASH)
    sales.create_sale([item(a, 1, 10)], wallet_amount=10, wallet_name="PalPay", wallet_ref="555")
    sales.create_sale([item(a, 1, 10)], wallet_amount=10, wallet_name="PalPay", wallet_ref="555")
    r = audit()
    high = titles(r, "high")
    assert "مرتجع نقدي لفاتورة دُفعت ببطاقة أو محفظة أو آجلاً" in high
    assert "رقم عملية محفظة مستخدم لأكثر من فاتورة" in high
    assert r["opinion"] == "رأي متحفظ"


def test_detects_deleted_and_tampered_invoices():
    shop()
    with db.tx() as conn:
        victim = conn.execute("SELECT id FROM invoices ORDER BY id LIMIT 1 OFFSET 2").fetchone()[0]
        conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (victim,))
        conn.execute("DELETE FROM invoices WHERE id=?", (victim,))
        conn.execute("UPDATE invoices SET cash_amount = cash_amount - 5 WHERE id=(SELECT MAX(id) FROM invoices)")
    r = audit()
    f = next(x for x in r["findings"] if x["title"].startswith("أرقام مفقودة في تسلسل فواتير البيع"))
    assert f["severity"] == "high" and f["samples"] == ["INV-000003"]
    assert "فواتير لا يساوي مجموع دفعاتها إجماليها" in titles(r, "high")


def test_unbalanced_books_give_adverse_opinion():
    shop()
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO journal_entries(entry_number, entry_date, description, is_void, created_at) "
                           "VALUES ('JV-X', ?, 'قيد مكسور', 0, ?)", (db.today(), db.now()))
        conn.execute("INSERT INTO journal_lines(entry_id, account_code, debit, credit) VALUES (?, '1110', 100, 0)",
                     (cur.lastrowid,))
    r = audit()
    assert "الدفاتر غير متوازنة" in titles(r, "critical")
    assert r["opinion"] == "رأي سلبي"


def test_old_debts_are_aged_first_in_first_out():
    a = shop()
    c = customers.add_customer("أبو سالم", "0599")
    sales.create_sale([item(a, 10, 10)], customer_id=c, cash_amount=0, credit_amount=100)
    sales.create_sale([item(a, 5, 10)], customer_id=c, cash_amount=0, credit_amount=50)
    with db.tx() as conn:   # الدين الأول عمره 120 يوماً
        conn.execute("""UPDATE customer_transactions SET created_at=datetime('now','localtime','-120 days')
                        WHERE id=(SELECT MIN(id) FROM customer_transactions WHERE customer_id=?)""", (c,))
    customers.receive_payment(c, 30, "نقدي")      # يُطفئ من الأقدم
    ag = {x["name"]: x for x in fa.aging(db.today())}["أبو سالم"]
    assert ag["balance"] == 120 and ag["buckets"] == [50, 0, 0, 70]
    assert "ديون متأخرة أكثر من 90 يوماً" in titles(audit())


def test_benford():
    rnd = random.Random(1)
    natural = [10 ** rnd.uniform(1, 5) for _ in range(2000)]      # يتبع بنفورد
    uniform = [rnd.uniform(100, 999) for _ in range(2000)]        # أرقام مختلقة بالتساوي
    assert fa.benford(natural)[0] < 0.012
    assert fa.benford(uniform)[0] > 0.015
    assert fa.benford([100] * 50)[0] is None                      # بيانات قليلة
