# -*- coding: utf-8 -*-
"""المحاسب الآلي، الختم ضد العبث، أسماء الأصناف بالإنجليزية، والأسعار السنوية"""

from datetime import date, timedelta

import pytest

from core import (accountant, db, ledger, expenses, financial_audit, integrity, products, sales, plans, i18n,
                  product_names)


def item(pid, qty, price, name="صنف"):
    return {"product_id": pid, "product_name": name, "quantity": qty, "unit_price": price, "cost_price": 0}


def _months_ago(n):
    d = date.today().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


def test_depreciation_schedule_and_books():
    bought = _months_ago(6).replace(day=3).isoformat()
    aid = accountant.add_asset("ثلاجة عرض", 1200, bought, 1, salvage=0, paid_from="1110")
    a = accountant.list_assets()[0]
    assert a["monthly"] == 100 and a["months_done"] == 6 and a["accumulated"] == 600 and a["book_value"] == 600
    bs = ledger.balance_sheet()
    assert bs["balanced"]
    codes = {x["code"]: x["amount"] for x in bs["assets"]}
    assert codes[ledger.FIXED_ASSETS] == 1200 and codes[accountant.ACC_DEPRECIATION] == -600
    # الإهلاك مصروف في قائمة الدخل
    pl = ledger.income_statement(bought, db.today())
    assert any(e["code"] == ledger.DEPRECIATION and e["amount"] == 600 for e in pl["expenses"])
    # البيع بربح: القيمة الدفترية 600 وثمن البيع 700 ← ربح 100
    accountant.dispose_asset(aid, db.today(), 700, "1110")
    assert ledger.balance_sheet()["balanced"]
    assert accountant.list_assets()[0]["book_value"] == 0
    full = accountant.schedule({"cost": 1000, "salvage": 100, "life_months": 7, "purchase_date": "2020-01-01",
                                "disposed_at": None}, "2030-01-01")
    assert len(full) == 7 and round(sum(x[1] for x in full), 2) == 900


def test_cash_flow_reconciles():
    pid = products.add_product("تمر", "cf1", "", 5, 9, 10, 0)
    sales.create_sale([item(pid, 2, 9, "تمر")])
    expenses.add_expense("كهرباء", 4, from_drawer=False)
    accountant.add_asset("رفوف", 300, db.today(), 5, paid_from="1120")
    cf = accountant.cash_flow("2000-01-01", db.today())
    assert cf["reconciled"]
    assert cf["totals"]["investing"] == -300


def test_period_lock_blocks_backdated_changes():
    accountant.lock_books("2020-01-31")
    with pytest.raises(ValueError):
        ledger.add_manual_entry("2020-01-15", "قيد قديم", [{"account": ledger.CASH, "debit": 5},
                                                           {"account": ledger.CAPITAL, "credit": 5}])
    with pytest.raises(ValueError):
        expenses.add_expense("إيجار", 10, from_drawer=False, expense_date="2020-01-10")
    expenses.add_expense("إيجار", 10, from_drawer=False)                    # بتاريخ اليوم مسموح
    with pytest.raises(ValueError):
        accountant.lock_books(db.today())                                    # لا قفل لفترة لم تنتهِ
    accountant.unlock_books()
    assert accountant.locked_until() == ""


def test_close_month_audits_locks_and_builds_package():
    first = _months_ago(1)
    st = accountant.status()
    assert st["locked_until"] == ""
    res = accountant.close_month(first.year, first.month, force=True)
    assert res["closed"] and accountant.locked_until() == res["date_to"]
    html = accountant.package_html(res["date_from"], res["date_to"], res["audit"])
    for title in ("قائمة الدخل", "الميزانية العمومية", "قائمة التدفقات النقدية", "إقرار ضريبة القيمة المضافة"):
        assert title in html
    with pytest.raises(ValueError):
        accountant.close_month(first.year, first.month)                        # مقفل من قبل


def test_tamper_seals_detect_direct_edits():
    pid = products.add_product("سكر", "tm1", "", 3, 5, 100, 0)
    ids = [sales.create_sale([item(pid, 1, 5, "سكر")])["invoice_id"] for _ in range(3)]
    n, bad = integrity.verify_invoices()
    assert n >= 3 and not bad
    r = financial_audit.check_tamper(None)
    assert r[0]["severity"] == "ok"
    with db.tx() as c:                       # عبث مباشر في الملف: تخفيض مبلغ فاتورة
        c.execute("UPDATE invoices SET total = total - 1 WHERE id=?", (ids[1],))
    assert integrity.verify_invoices()[1]
    with db.tx() as c:
        c.execute("UPDATE invoices SET total = total + 1 WHERE id=?", (ids[1],))
        c.execute("DELETE FROM invoice_items WHERE invoice_id=?", (ids[1],))
        c.execute("DELETE FROM invoices WHERE id=?", (ids[1],))              # حذف فاتورة من المنتصف
    assert any("حُذفت" in why for _, why in integrity.verify_invoices()[1])
    # سجل العمليات
    assert not integrity.verify_audit_log()[1]
    with db.tx() as c:
        c.execute("UPDATE audit_log SET details='لا شيء' WHERE id=(SELECT MIN(id) FROM audit_log WHERE chain IS NOT NULL)")
    assert integrity.verify_audit_log()[1]
    sev = {f["severity"] for f in financial_audit.check_tamper(None)}
    assert "critical" in sev


def test_daily_audit_runs_once_a_day():
    r1 = accountant.daily_audit()
    assert r1["date"] == db.today() and "score" in r1
    assert accountant.daily_audit() == r1


def test_english_product_names():
    pid = products.add_product("حليب طازج 1 لتر", "en1", "ألبان", 3, 5, 10, 0)
    i18n.set_language("en")
    try:
        product_names.invalidate()
        assert i18n.tr("حليب طازج 1 لتر") == "Fresh Milk 1 L"
        assert i18n.tr("ألبان") == "Dairy"
        assert i18n.tr("نقطة البيع") == "Point of sale"                    # نصوص الواجهة كما هي
        p = products.get_product(pid)
        products.update_product(pid, p["name"], p["barcode"], p["category"], p["cost_price"], p["sale_price"],
                                p["min_quantity"], p["unit"], name_en="Farm Milk 1L")
        product_names.invalidate()
        assert i18n.tr("حليب طازج 1 لتر") == "Farm Milk 1L"
        assert products.get_all_products(search="Farm")[0]["id"] == pid      # البحث بالاسم الإنجليزي
    finally:
        i18n.set_language("ar")
    assert products.fill_english_names() >= 0


def test_yearly_prices_are_under_half_of_global_equivalent():
    def usd(s):
        return float(s.replace("$", "").replace(",", ""))
    for tier, (name, price) in plans.GLOBAL_EQUIVALENT.items():
        ours = usd(plans.prices()[tier][0])
        assert 0 < ours <= usd(price) / 2, (tier, ours, price)
        assert "سنوياً" in plans.prices()[tier][1]
