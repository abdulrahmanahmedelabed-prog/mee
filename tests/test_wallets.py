# -*- coding: utf-8 -*-
"""الدفع بالمحافظ الإلكترونية وتطبيقات البنوك: البيع، القيود، المطابقة، الوردية، التقارير الدورية"""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import db, products, sales, customers, shifts, reports, settings, ledger, wallets, receipts  # noqa: E402
from core.sales import SaleError  # noqa: E402


def item(pid, q, price):
    return {"product_id": pid, "product_name": "x", "quantity": q, "unit_price": price}


def setup_wallets():
    settings.set_many({"wallets": wallets.to_json([
        {"name": "PalPay", "account": "0599123456", "dest": "wallet"},
        {"name": "تحويل بنكي فوري", "account": "PS92PALS000000000400123456702", "dest": "bank", "qr": "IBAN:PS92"}])})


def bal(code):
    row = ledger._balances(None, db.today()).get(code, [0, 0, 0])
    return round(row[0] + row[1] - row[2], 2)


def test_wallet_sale_posts_to_right_account_and_reconciles():
    setup_wallets()
    a = products.add_product("أرز", "100", "مواد", 8, 10, 100, 5)
    sid = shifts.open_shift(100)
    s1 = sales.create_sale([item(a, 3, 10)], wallet_amount=30, wallet_name="PalPay", wallet_ref="TX-77", shift_id=sid)
    s2 = sales.create_sale([item(a, 2, 10)], cash_amount=5, wallet_amount=15, wallet_name="تحويل بنكي فوري",
                           shift_id=sid)
    inv = sales.get_invoice(s1["invoice_id"])
    assert (inv["wallet_amount"], inv["wallet_name"], inv["wallet_ref"], inv["wallet_bank"], inv["payment_method"]) == \
        (30, "PalPay", "TX-77", 0, "PalPay")
    assert sales.get_invoice(s2["invoice_id"])["wallet_bank"] == 1
    assert bal(ledger.WALLETS) == 30 and bal(ledger.BANK) == 15 and bal(ledger.CASH) == 105   # 100 رصيد الوردية الافتتاحي
    tb = ledger.trial_balance(None, db.today())
    assert tb["totals"]["balanced"] and ledger.balance_sheet()["balanced"]

    # تسديد دين عميل عبر المحفظة يذهب لحساب المحفظة ويظهر في تقرير المطابقة
    c = customers.add_customer("أبو سامي", "0599000111", opening_balance=40)
    customers.receive_payment(c, 25, "PalPay")
    assert bal(ledger.WALLETS) == 55
    t = db.today()
    s = {r["name"]: r for r in wallets.summary(t, t)}
    assert (s["PalPay"]["count"], s["PalPay"]["sales"], s["PalPay"]["debts"], s["PalPay"]["total"]) == (2, 30, 25, 55)
    assert s["تحويل بنكي فوري"]["total"] == 15 and s["تحويل بنكي فوري"]["dest"] == "حساب البنك مباشرة"
    assert [r["wallet_ref"] for r in wallets.invoices("PalPay", t, t)] == ["TX-77"]

    # تحويل رصيد المحفظة للبنك مع عمولة (عملية مالية جاهزة)
    ledger.add_manual_entry(t, "تحويل للبنك", [{"account": ledger.BANK, "debit": 54, "credit": 0},
                                               {"account": ledger.PAYMENT_FEES, "debit": 1, "credit": 0},
                                               {"account": ledger.WALLETS, "debit": 0, "credit": 55}])
    assert bal(ledger.WALLETS) == 0 and bal(ledger.BANK) == 69
    assert ledger.balance_sheet()["balanced"]

    # الوردية: الدفع الإلكتروني لا يدخل في النقد المتوقع
    d = shifts.summary(sid)
    assert d["wallet_sales"] == 45 and d["cash_sales"] == 5 and d["expected_cash"] == 105
    p = reports.profit_and_loss(t, t)
    assert p["wallet_sales"] == 45
    html = receipts.invoice_html(s1["invoice_id"])
    assert "PalPay" in html and "TX-77" in html


def test_wallet_validation():
    setup_wallets()
    a = products.add_product("سكر", "200", "مواد", 3, 5, 100, 5)
    with pytest.raises(SaleError):
        sales.create_sale([item(a, 1, 5)], wallet_amount=5)                         # بدون اسم
    with pytest.raises(SaleError):
        sales.create_sale([item(a, 1, 5)], wallet_amount=6, wallet_name="PalPay")    # أكثر من الإجمالي
    settings.set_many({"wallet_ref_required": "1"})
    with pytest.raises(SaleError):
        sales.create_sale([item(a, 1, 5)], wallet_amount=5, wallet_name="PalPay")    # رقم العملية إلزامي
    assert sales.create_sale([item(a, 1, 5)], wallet_amount=5, wallet_name="PalPay", wallet_ref="1")["total"] == 5
    with pytest.raises(ValueError):
        wallets.to_json([{"name": "A"}, {"name": "A"}])
    assert [w["name"] for w in wallets.presets("962")][0] == "CliQ"


def test_period_summary_matches_profit_report():
    setup_wallets()
    a = products.add_product("زيت", "300", "مواد", 20, 30, 500, 5)
    sid = shifts.open_shift(0)
    sales.create_sale([item(a, 2, 30)], shift_id=sid)
    sales.create_sale([item(a, 1, 30)], wallet_amount=30, wallet_name="PalPay", shift_id=sid)
    from core import expenses
    expenses.add_expense("كهرباء", 12, from_drawer=True, shift_id=sid)
    t = db.today()
    start = (date.today() - timedelta(days=400)).isoformat()
    whole = reports.profit_and_loss(start, t)
    for g in ("day", "week", "month", "year"):
        rows = reports.period_summary(start, t, g)
        assert round(sum(r["net_profit"] for r in rows), 2) == whole["net_profit"], g
        assert round(sum(r["wallet"] for r in rows), 2) == 30
        assert sum(r["count"] for r in rows) == 2
    week = reports.period_summary(t, t, "week")[0]["period"]
    assert date.fromisoformat(week).weekday() == 5          # الأسبوع يبدأ السبت


def test_payment_dialog_wallet(monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog
    QApplication.instance() or QApplication([])
    setup_wallets()
    from ui import pos_screen
    monkeypatch.setattr(pos_screen.WalletDialog, "exec", lambda self: (self.ref.setText("R-9"), QDialog.Accepted)[1])
    d = pos_screen.PaymentDialog(None, 50.0)
    d.cash.setValue(20)                     # الزبون دفع 20 نقداً والباقي بالمحفظة
    d.pay_wallet(wallets.get("PalPay"))
    data, err = d.compute()
    assert err is None
    assert (data["cash_amount"], data["wallet_amount"], data["wallet_name"], data["wallet_ref"]) == (20, 30, "PalPay", "R-9")
    d.clear_wallet()
    data, _ = d.compute()
    assert data["wallet_amount"] == 0 and data["cash_amount"] == 50


def test_fast_ledger_totals_include_wallets():
    setup_wallets()
    a = products.add_product("شاي", "400", "مواد", 4, 6, 100, 5)
    sales.create_sale([item(a, 2, 6)], wallet_amount=12, wallet_name="PalPay")
    sales.create_sale([item(a, 1, 6)], wallet_amount=6, wallet_name="تحويل بنكي فوري")
    t = db.today()
    fast = ledger._balances(None, t)
    slow = {}
    for e in ledger.entries(None, t):
        for acc, d, c in e["lines"]:
            row = slow.setdefault(acc, [0.0, 0.0, 0.0])
            row[1] += d
            row[2] += c
    for k in set(fast) | set(slow):
        f, s = fast.get(k, [0, 0, 0]), slow.get(k, [0, 0, 0])
        assert [round(x, 2) for x in f] == [round(x, 2) for x in s], (k, f, s)
    assert round(fast[ledger.WALLETS][1], 2) == 12


def test_daily_sales_entries_equal_per_invoice_entries():
    setup_wallets()
    a = products.add_product("قهوة", "500", "مواد", 10, 15, 100, 5)
    c = customers.add_customer("زبون", "0599")
    sales.create_sale([item(a, 2, 15)])
    sales.create_sale([item(a, 1, 15)], card_amount=15)
    sales.create_sale([item(a, 1, 15)], wallet_amount=15, wallet_name="PalPay")
    sales.create_sale([item(a, 1, 15)], wallet_amount=15, wallet_name="تحويل بنكي فوري")
    s = sales.create_sale([item(a, 2, 15)], customer_id=c, cash_amount=0, credit_amount=30)
    it = sales.returnable_items(s["invoice_id"])[0]
    sales.create_return(s["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], refund_method=sales.REFUND_DEBT)
    t = db.today()

    def sums(daily):
        out = {}
        for e in ledger.entries(t, t, daily_sales=daily):
            for acc, d, cr in e["lines"]:
                out[acc] = round(out.get(acc, 0) + d - cr, 2)
        return {k: v for k, v in out.items() if v}
    assert sums(True) == sums(False)
    daily = [e for e in ledger.journal(t, t, daily_sales=True) if e["source"] == "sale"]
    assert len(daily) == 1 and "5 فاتورة" in daily[0]["description"]
    st = ledger.account_statement(ledger.WALLETS, t, t, daily_sales=True)
    assert st["closing"] == 15 and len(st["rows"]) == 1
