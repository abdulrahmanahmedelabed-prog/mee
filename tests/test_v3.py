# -*- coding: utf-8 -*-
"""اختبارات ميزات النسخة 3: الوحدات، الصلاحية، الخسائر، الورديات لكل جهاز"""
from datetime import date, timedelta

import pytest

from core import db, products, sales, suppliers, reports, shifts, context, settings
from core.sales import SaleError


def d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def test_units_sale_return_and_reports():
    pid = products.add_product("كولا علبة", "111", "مشروبات", 2, 3, 100, 10)
    products.set_units(pid, [{"name": "كرتونة", "factor": 24, "barcode": "222", "sale_price": 60}])
    p, q, unit = products.lookup_code("222")
    assert p["id"] == pid and unit["factor"] == 24
    with pytest.raises(ValueError):
        products.add_product("آخر", "222")  # باركود الكرتونة محجوز
    cart = [{"product_id": pid, "product_name": "كولا علبة (كرتونة)", "quantity": 2, "unit_price": 60,
             "factor": 24, "unit_name": "كرتونة"},
            {"product_id": pid, "product_name": "كولا علبة", "quantity": 3, "unit_price": 3}]
    r = sales.create_sale(cart)
    assert products.get_product(pid)["quantity"] == 100 - 48 - 3
    t = db.today()
    pl = reports.profit_and_loss(t, t)
    assert pl["cogs"] == 51 * 2 and pl["gross_profit"] == 129 - 102
    assert reports.top_products(t, t)[0]["qty"] == 51
    item = [i for i in sales.returnable_items(r["invoice_id"]) if i["factor"] == 24][0]
    sales.create_return(r["invoice_id"], [{"invoice_item_id": item["id"], "quantity": 1}])
    assert products.get_product(pid)["quantity"] == 100 - 24 - 3
    with pytest.raises(SaleError):
        sales.create_sale([{"product_id": pid, "product_name": "x", "quantity": 4, "unit_price": 60, "factor": 24}])


def test_purchase_by_carton_with_expiry_and_fefo():
    pid = products.add_product("لبن", "333", "ألبان", 4, 6, 0, 5)
    sid = suppliers.add_supplier("مورد")
    suppliers.create_purchase(sid, [{"product_id": pid, "quantity": 2, "unit_cost": 48, "factor": 12,
                                     "unit_name": "كرتونة", "expiry_date": d(40)}], paid=96)
    suppliers.create_purchase(sid, [{"product_id": pid, "quantity": 6, "unit_cost": 4, "expiry_date": d(5)}], paid=24)
    p = products.get_product(pid)
    assert p["quantity"] == 30 and p["cost_price"] == 4
    # البيع يستهلك الأقرب انتهاءً أولاً
    sales.create_sale([{"product_id": pid, "product_name": "لبن", "quantity": 8, "unit_price": 6}])
    b = products.get_batches(pid)
    assert [(x["expiry_date"], x["remaining"]) for x in b] == [(d(40), 22)]
    assert products.expiry_status(pid) == (d(40), 40)
    assert products.expiring_batches(30) == []
    assert len(products.expiring_batches(45)) == 1


def test_expired_writeoff_counts_as_loss_and_blocks_sale():
    pid = products.add_product("جبنة", "444", "", 10, 15, 0, 1)
    products.adjust_stock(pid, 5, "استلام بضاعة", expiry_date=d(-2))
    products.adjust_stock(pid, 5, "استلام بضاعة", expiry_date=d(20))
    exp = products.expiring_batches(0)
    assert len(exp) == 1 and exp[0]["days_left"] == -2
    settings.set("block_expired_sale", "1")
    with pytest.raises(SaleError):
        sales.create_sale([{"product_id": pid, "product_name": "جبنة", "quantity": 1, "unit_price": 15}])
    products.write_off_batch(exp[0]["id"])
    assert products.get_product(pid)["quantity"] == 5
    sales.create_sale([{"product_id": pid, "product_name": "جبنة", "quantity": 1, "unit_price": 15}])
    pl = reports.profit_and_loss(db.today(), db.today())
    assert pl["stock_loss"] == 50
    assert pl["net_profit"] == 5 - 50


def test_stock_count_loss_and_gain():
    pid = products.add_product("سكر", "555", "", 3, 5, 10, 1)
    products.set_stock_count(pid, 8)   # عجز 2 × 3 = 6 خسارة
    products.set_stock_count(pid, 9)   # زيادة 1 × 3 = 3 ربح
    products.adjust_stock(pid, -1, "تصحيح خطأ")  # ليست خسارة
    assert reports.profit_and_loss(db.today(), db.today())["stock_loss"] == 3


def test_shift_per_terminal():
    context.set_terminal("كاشير 1")
    s1 = shifts.open_shift(100)
    context.set_terminal("كاشير 2")
    assert shifts.current_shift() is None
    s2 = shifts.open_shift(50)
    assert s1 != s2 and len(shifts.open_shifts()) == 2
    pid = products.add_product("ماء", "666", "", 1, 2, 10, 1)
    sales.create_sale([{"product_id": pid, "product_name": "ماء", "quantity": 1, "unit_price": 2}], shift_id=s2)
    assert shifts.summary(s2)["expected_cash"] == 52 and shifts.summary(s1)["expected_cash"] == 100
    t = db.today()
    assert reports.sales_by_terminal(t, t)[0]["terminal"] == "كاشير 2"
    context.set_terminal("كاشير 1")
    assert shifts.current_shift()["id"] == s1


def test_units_validation():
    pid = products.add_product("شيبس", "777", "", 1, 2, 10, 1)
    with pytest.raises(ValueError):
        products.set_units(pid, [{"name": "كرتونة", "factor": 1, "barcode": "", "sale_price": 10}])
    with pytest.raises(ValueError):
        products.set_units(pid, [{"name": "كرتونة", "factor": 12, "barcode": "777", "sale_price": 10}])
    products.set_units(pid, [{"name": "كرتونة", "factor": 12, "barcode": "888", "sale_price": 20}])
    assert [u["name"] for u in products.unit_choices(pid)] == ["قطعة", "كرتونة"]
    assert products.get_all_products(search="888")[0]["id"] == pid


def test_whatsapp_links_and_backup_mirror(tmp_path):
    from core import whatsapp, backup, customers
    assert whatsapp.normalize_phone("0599 123 456") == "970599123456"
    assert whatsapp.normalize_phone("+972 52-1234567") == "972521234567"
    assert whatsapp.normalize_phone("00962791234567") == "962791234567"
    cid = customers.add_customer("أبو علي", "0599123456", opening_balance=25)
    url = whatsapp.reminder_link(cid)
    assert url.startswith("https://wa.me/970599123456?text=")
    pid = products.add_product("ماء", "1", "", 1, 2, 5, 1)
    r = sales.create_sale([{"product_id": pid, "product_name": "ماء", "quantity": 2, "unit_price": 2}], customer_id=cid,
                          cash_amount=0, credit_amount=4)
    assert "الإجمالي" in whatsapp.invoice_text(r["invoice_id"])
    settings.set_many({"backup_dir": str(tmp_path / "b"), "backup_mirror_dir": str(tmp_path / "cloud")})
    path = backup.create_backup()
    import os
    assert os.path.exists(tmp_path / "cloud" / os.path.basename(path))
