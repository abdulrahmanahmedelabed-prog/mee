# -*- coding: utf-8 -*-
"""قواعد محاسبية: مرتجع البطاقة والمحفظة، ضريبة مرتجع المشتريات، نقاط الولاء كالتزام"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import db, products, sales, customers, suppliers, shifts, reports, settings, ledger, wallets, loyalty  # noqa: E402
from core.sales import SaleError  # noqa: E402


def item(pid, q, price):
    return {"product_id": pid, "product_name": "x", "quantity": q, "unit_price": price}


def bal(code):
    row = ledger._balances(None, db.today()).get(code, [0, 0, 0])
    return round(row[0] + row[1] - row[2], 2)


def books_ok():
    t = db.today()
    assert ledger.trial_balance(None, t)["totals"]["balanced"]
    assert ledger.balance_sheet()["balanced"]
    assert round(ledger.income_statement(None, t)["net_income"], 2) == \
        reports.profit_and_loss("2000-01-01", t)["net_profit"]


def test_card_and_wallet_refunds_go_back_to_their_accounts():
    settings.set_many({"wallets": wallets.to_json([{"name": "PalPay", "account": "0599", "dest": "wallet"}])})
    a = products.add_product("أرز", "100", "مواد", 8, 10, 100, 5)
    sid = shifts.open_shift(50)
    card = sales.create_sale([item(a, 3, 10)], card_amount=30, shift_id=sid)
    wal = sales.create_sale([item(a, 2, 10)], wallet_amount=20, wallet_name="PalPay", wallet_ref="T1", shift_id=sid)
    inv = sales.get_invoice(card["invoice_id"])
    assert sales.refund_methods(inv) == [sales.REFUND_CASH, sales.REFUND_CARD]
    assert sales.refund_methods(sales.get_invoice(wal["invoice_id"])) == [sales.REFUND_CASH, "PalPay"]

    it = sales.returnable_items(card["invoice_id"])[0]
    sales.create_return(card["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], refund_method=sales.REFUND_CARD)
    it2 = sales.returnable_items(wal["invoice_id"])[0]
    sales.create_return(wal["invoice_id"], [{"invoice_item_id": it2["id"], "quantity": 1}], refund_method="PalPay")
    # طريقة لم تُستخدم في الفاتورة غير مسموحة
    with pytest.raises(SaleError):
        sales.create_return(card["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], refund_method="PalPay")

    assert bal(ledger.BANK) == 20 and bal(ledger.WALLETS) == 10 and bal(ledger.CASH) == 50   # النقد لم يتأثر
    d = shifts.summary(sid)
    assert d["cash_refunds"] == 0 and d["electronic_refunds"] == 20 and d["expected_cash"] == 50
    t = db.today()
    s = {r["name"]: r for r in wallets.summary(t, t)}
    assert (s["PalPay"]["sales"], s["PalPay"]["refunds"], s["PalPay"]["total"]) == (20, 10, 10)
    daily = {}
    for e in ledger.entries(t, t, daily_sales=True):
        for acc, dr, cr in e["lines"]:
            daily[acc] = round(daily.get(acc, 0) + dr - cr, 2)
    assert daily[ledger.BANK] == 20 and daily[ledger.WALLETS] == 10
    books_ok()


def test_card_refund_limited_to_amount_paid_by_card():
    a = products.add_product("زيت", "200", "مواد", 20, 30, 100, 5)
    s = sales.create_sale([item(a, 2, 30)], cash_amount=40, card_amount=20)
    it = sales.returnable_items(s["invoice_id"])[0]
    with pytest.raises(SaleError):
        sales.create_return(s["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 2}], refund_method=sales.REFUND_CARD)
    sales.create_return(s["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], refund_method=sales.REFUND_CASH)
    with pytest.raises(SaleError):   # 30 أكبر من المدفوع بالبطاقة (20)
        sales.create_return(s["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}],
                            refund_method=sales.REFUND_CARD)


def test_purchase_return_reverses_input_vat():
    settings.set_many({"vat_enabled": "1", "vat_rate": "16"})
    sup = suppliers.add_supplier("مورد", "0599")
    a = products.add_product("حليب", "300", "ألبان", 0, 5, 0, 5)
    suppliers.create_purchase(sup, [{"product_id": a, "quantity": 10, "unit_cost": 11.6}], paid=0, tax=16)
    assert bal(ledger.VAT_INPUT) == 16 and products.get_product(a)["cost_price"] == 10
    r = suppliers.create_purchase_return(sup, [{"product_id": a, "quantity": 5}], "منتهي", tax=8)
    assert r["total"] == 58                       # 50 + 8 ضريبة
    assert bal(ledger.VAT_INPUT) == 8 and bal(ledger.INVENTORY) == 50 and bal(ledger.PAYABLES) == -58
    t = db.today()
    v = reports.vat_report(t, t)
    assert v["input_tax"] == 8 and v["purchases_total"] == 58
    assert reports.profit_and_loss(t, t)["other_adjustments"] == 0
    books_ok()


def test_loyalty_points_are_a_liability_until_redeemed():
    settings.set_many({"loyalty_enabled": "1", "loyalty_points_per_unit": "1", "loyalty_point_value": "0.05"})
    a = products.add_product("شاي", "400", "مواد", 50, 100, 100, 5)
    c = customers.add_customer("أبو علي", "0599111")
    sales.create_sale([item(a, 2, 100)], customer_id=c)          # يكسب 200 نقطة = 10
    assert loyalty.balance(c) == 200 and loyalty.liability() == 10
    assert bal(ledger.LOYALTY) == -10 and bal(ledger.LOYALTY_COST) == 10
    t = db.today()
    assert reports.profit_and_loss(t, t)["loyalty_cost"] == 10
    books_ok()

    s2 = sales.create_sale([item(a, 1, 100)], customer_id=c, points_redeemed=100)   # يستبدل 100 نقطة = 5
    inv = sales.get_invoice(s2["invoice_id"])
    assert inv["points_value"] == 5 and inv["total"] == 95
    # الاستبدال يعكس الالتزام: 200 − 100 + 95 نقطة جديدة = 195 نقطة = 9.75
    assert loyalty.balance(c) == 195 and loyalty.liability() == 9.75 and bal(ledger.LOYALTY) == -9.75
    it = sales.returnable_items(s2["invoice_id"])[0]
    sales.create_return(s2["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])
    assert loyalty.balance(c) == 100 and bal(ledger.LOYALTY) == -5
    books_ok()
    for g in ("day", "month"):
        assert round(sum(r["net_profit"] for r in reports.period_summary("2000-01-01", t, g)), 2) == \
            reports.profit_and_loss("2000-01-01", t)["net_profit"]
