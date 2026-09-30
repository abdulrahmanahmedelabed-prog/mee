# -*- coding: utf-8 -*-
"""قواعد محاسبية من مراجعة المنطق: الوردية للعمليات النقدية، المرتجع النقدي لفاتورة آجلة، تعديل المخزون،
إعادة تقييم التكلفة، حذف مصروف وردية مغلقة، وقوالب الضريبة والإهلاك"""
import pytest

from core import db, products, sales, customers, suppliers, shifts, expenses, settings, ledger, reports
from core.sales import SaleError


def item(pid, q, price):
    return {"product_id": pid, "product_name": "x", "quantity": q, "unit_price": price}


def bal(code):
    row = ledger._balances(None, db.today()).get(code, [0, 0, 0])
    return round(row[0] + row[1] - row[2], 2)


def test_cash_operations_need_open_shift():
    settings.set_many({"require_shift": "1"})
    a = products.add_product("أرز", "1", "مواد", 5, 8, 50, 1)
    c = customers.add_customer("زبون", "059", opening_balance=100)
    s = suppliers.add_supplier("مورد", opening_balance=100)
    inv = sales.create_sale([item(a, 1, 8)], card_amount=8, cash_amount=0)      # غير نقدي: مسموح بلا وردية
    it = sales.returnable_items(inv["invoice_id"])[0]
    for fn in (lambda: customers.receive_payment(c, 10, "نقدي"),
               lambda: suppliers.pay_supplier(s, 10, suppliers.PAY_DRAWER),
               lambda: expenses.add_expense("كهرباء", 10, from_drawer=True)):
        with pytest.raises(ValueError):
            fn()
    with pytest.raises(SaleError):
        sales.create_return(inv["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])
    customers.receive_payment(c, 10, "تحويل")              # غير نقدي: مسموح
    suppliers.pay_supplier(s, 10, suppliers.PAY_BANK)
    sid = shifts.open_shift(100)
    customers.receive_payment(c, 10, "نقدي")               # تُربط بالوردية المفتوحة تلقائياً
    expenses.add_expense("كهرباء", 5, from_drawer=True)
    d = shifts.summary(sid)
    assert d["customer_payments_cash"] == 10 and d["expenses_cash"] == 5 and d["expected_cash"] == 105


def test_cash_refund_of_credit_invoice_limited_to_what_was_paid():
    a = products.add_product("زيت", "2", "مواد", 20, 30, 50, 1)
    c = customers.add_customer("أبو علي", "059")
    inv = sales.create_sale([item(a, 3, 30)], customer_id=c, cash_amount=30, credit_amount=60)
    it = sales.returnable_items(inv["invoice_id"])[0]
    sales.create_return(inv["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])   # 30 نقداً = ما دفعه
    with pytest.raises(SaleError):     # ما زال عليه 60: لا يُرد نقداً أكثر مما دفع
        sales.create_return(inv["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])
    sales.create_return(inv["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], refund_method=sales.REFUND_DEBT)
    assert customers.balance(c) == 30
    customers.receive_payment(c, 30, "تحويل")               # سدد دينه: الآن يُسمح بالرد النقدي
    sales.create_return(inv["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])
    assert customers.balance(c) == 0


def test_manual_stock_changes_hit_profit_not_capital():
    a = products.add_product("سكر", "3", "مواد", 4, 6, 100, 1)
    t = db.today()
    products.adjust_stock(a, -5, "تصحيح خطأ")              # نقص بلا مستند = خسارة
    products.adjust_stock(a, 2, "أخرى")                     # زيادة بلا مستند = مكسب
    products.adjust_stock(a, 10, "استلام بضاعة")            # بضاعة بلا فاتورة = أرصدة افتتاحية
    p = reports.profit_and_loss(t, t)
    assert p["stock_loss"] == 12                            # 5×4 − 2×4
    assert p["net_profit"] == ledger.income_statement(t, t)["net_income"]
    assert bal(ledger.INVENTORY) == round(products.inventory_value()["cost_value"], 2)


def test_cost_price_edit_revalues_stock_in_books():
    a = products.add_product("شاي", "4", "مواد", 10, 15, 20, 1)
    p = products.get_product(a)
    products.update_product(a, p["name"], p["barcode"], p["category"], 12, 15, 1, p["unit"])
    t = db.today()
    assert reports.profit_and_loss(t, t)["stock_loss"] == -40            # 20 × (12 − 10) مكسب إعادة تقييم
    assert bal(ledger.INVENTORY) == round(products.inventory_value()["cost_value"], 2) == 240
    assert ledger.trial_balance(None, t)["totals"]["balanced"]


def test_expense_of_closed_shift_cannot_be_deleted():
    shifts.open_shift(100)
    e = expenses.add_expense("ضيافة", 20, from_drawer=True)
    shifts.close_shift(80)
    with pytest.raises(ValueError):
        expenses.delete_expense(e)
    e2 = expenses.add_expense("إيجار", 500, from_drawer=False)
    expenses.delete_expense(e2)                              # ليس من الدرج: يُحذف


def test_vat_settlement_and_depreciation_templates():
    labels = {l: (dr, cr) for l, dr, cr in ledger.TEMPLATES}
    t = db.today()
    ledger.add_manual_entry(t, "شراء معدات", [{"account": ledger.FIXED_ASSETS, "debit": 1200},
                                             {"account": ledger.BANK, "credit": 1200}])
    for label in ("إهلاك الأصول الثابتة (الأثاث والمعدات)", "دفع ضريبة القيمة المضافة المستحقة من البنك",
                  "مقاصة ضريبة المدخلات مع الضريبة المستحقة (عند تقديم الإقرار)"):
        dr, cr = labels[label]
        ledger.add_manual_entry(t, label, [{"account": dr, "debit": 100}, {"account": cr, "credit": 100}])
    assert bal(ledger.FIXED_ASSETS) == 1100
    assert reports.profit_and_loss(t, t)["net_profit"] == -100            # الإهلاك مصروف
    assert ledger.balance_sheet()["balanced"]


def test_percent_promotions_do_not_stack():
    from core import promotions
    settings.set_many({"promotions_enabled": "1"})
    a = products.add_product("منظف", "5", "منظفات", 5, 10, 50, 1)
    b = products.add_product("صابون", "6", "منظفات", 2, 4, 50, 1)
    promotions.add_promotion("10% منظفات", "percent", category="منظفات", percent=10)
    promotions.add_promotion("20% منظف", "percent", product_id=a, percent=20)
    r = promotions.apply([item(a, 1, 10), item(b, 1, 4)])
    assert r["total"] == 2.4          # المنظف 20% فقط (2)، والصابون 10% (0.4) — وليس 30% على المنظف


def test_deleting_product_with_stock_writes_it_off():
    a = products.add_product("علبة", "7", "مواد", 3, 5, 10, 1)
    products.delete_product(a)
    t = db.today()
    assert reports.profit_and_loss(t, t)["stock_loss"] == 30
    assert bal(ledger.INVENTORY) == round(products.inventory_value()["cost_value"], 2) == 0


def test_unit_cost_keeps_four_decimals_for_cartons():
    a = products.add_product("علكة", "8", "حلويات", 0, 1, 0, 0)
    s = suppliers.add_supplier("موزع")
    suppliers.create_purchase(s, [{"product_id": a, "quantity": 1, "unit_cost": 10, "factor": 24,
                                   "unit_name": "كرتونة"}])
    assert products.get_product(a)["cost_price"] == 0.4167
    sales.create_sale([item(a, 12, 1)])
    sales.create_sale([item(a, 12, 1)])
    t = db.today()
    assert reports.profit_and_loss(t, t)["cogs"] == 10.0         # بخانتين كانت 0.42 × 24 = 10.08
    assert abs(bal(ledger.INVENTORY)) < 0.01
