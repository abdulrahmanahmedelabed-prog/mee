# -*- coding: utf-8 -*-
"""اختبارات الواجهة بدون شاشة (offscreen): تدفق البيع الكامل من نقطة البيع"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core import products, sales, customers, settings, barcode, shifts, suppliers


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def pos(app):
    settings.set("require_shift", "0")
    from ui.pos_screen import POSScreen
    return POSScreen()


def test_scan_multiplier_and_scale(pos):
    pid = products.add_product("ماء", "123", "", 1, 2, 50, 5)
    meat = products.add_product("لحمة", None, "", 40, 60, 10, 1, "كغم", plu_code="77", is_weighted=True)
    pos.search.setText("123")
    pos.on_enter()
    pos.search.setText("3*123")
    pos.on_enter()
    assert len(pos.cart) == 1 and pos.cart[0]["quantity"] == 4
    body = "21" + "00077" + "00500"
    pos.search.setText(body + barcode.ean13_check_digit(body))
    pos.on_enter()
    assert pos.cart[1]["product_id"] == meat and pos.cart[1]["quantity"] == 0.5
    pos.bump_selected(1)  # يضيف 1 على السطر المحدد (اللحمة)
    assert pos.cart[1]["quantity"] == 1.5
    t = pos.update_totals()
    assert t["total"] == 4 * 2 + 1.5 * 60


def test_stock_guard_in_cart(pos):
    products.add_product("نادر", "999", "", 1, 2, 1, 0)
    pos.search.setText("999")
    pos.on_enter()
    pos.search.setText("999")
    pos.on_enter()
    assert pos.cart[0]["quantity"] == 1  # لم تُضف القطعة الثانية


def test_full_sale_through_pos(pos):
    products.add_product("شاي", "555", "", 5, 10, 20, 2)
    cid = customers.add_customer("زبون")
    pos.search.setText("555")
    pos.on_enter()
    pos.bump_selected(1)
    pos.set_customer(customers.get_customer(cid))
    pos.discount = 2
    pos.finish_sale({"cash_amount": 8, "card_amount": 0, "credit_amount": 10, "cash_received": 8, "change": 0})
    assert pos.cart == [] and pos.customer is None
    inv = sales.get_invoice(pos.last_invoice_id)
    assert inv["total"] == 18 and inv["credit_amount"] == 10
    assert customers.balance(cid) == 10


def test_payment_dialog_logic(app):
    from ui.pos_screen import PaymentDialog
    d = PaymentDialog(None, 57.5, None)
    d.cash.setValue(100)
    data, err = d.compute()
    assert err is None and data["change"] == 42.5
    d.cash.setValue(50)
    data, err = d.compute()
    assert data is None and "ناقص" in err
    assert not d.credit_chk.isEnabled()
    cid = customers.add_customer("س")
    d2 = PaymentDialog(None, 57.5, customers.get_customer(cid))
    d2.cash.setValue(20)
    d2.card.setValue(10)
    d2.credit_chk.setChecked(True)
    data, err = d2.compute()
    assert data == {"cash_amount": 20, "card_amount": 10, "credit_amount": 27.5, "cash_received": 20, "change": 0.0}


def test_all_screens_open(app):
    from ui.main_window import MainWindow, PAGES
    w = MainWindow()
    for key, *_ in PAGES:
        w.go(key)
        app.processEvents()
    rep = w.pages["reports"]
    for i in range(rep.tabs.count()):
        rep.tabs.setCurrentIndex(i)
    w.pages["pos"].clear_cart()
    w.close()


def test_purchase_dialog(app):
    from ui.suppliers_screen import PurchaseDialog
    pid = products.add_product("أرز", "777", "", 10, 14, 0, 2)
    sid = suppliers.add_supplier("مورد")
    d = PurchaseDialog(None, sid)
    d.scan.setText("777")
    d.on_scan()
    d.lines[0]["quantity"] = 10
    d.lines[0]["unit_cost"] = 11
    d.lines[0]["expiry"] = "2030-01-01"
    d.render()
    d.pay_all.setChecked(False)
    d.paid.setValue(50)
    import ui.suppliers_screen as ss
    ss.info = lambda *a, **k: None
    d.accept()
    assert products.get_product(pid)["quantity"] == 10
    assert suppliers.balance(sid) == 60


def test_pos_carton_and_stock_in_base_units(pos):
    pid = products.add_product("كولا", "c1", "", 2, 3, 30, 1)
    products.set_units(pid, [{"name": "كرتونة", "factor": 12, "barcode": "c12", "sale_price": 33}])
    pos.search.setText("c12")
    pos.on_enter()
    pos.search.setText("2*c12")
    pos.on_enter()   # 36 > 30 مرفوض
    assert len(pos.cart) == 1 and pos.cart[0]["quantity"] == 1 and pos.cart[0]["factor"] == 12
    pos.search.setText("c1")
    pos.on_enter()
    assert pos.update_totals()["total"] == 36
    pos.finish_sale({"cash_amount": 36, "card_amount": 0, "credit_amount": 0, "cash_received": 50, "change": 14})
    assert products.get_product(pid)["quantity"] == 30 - 13


def test_pos_promotions_and_loyalty(pos):
    from core import promotions, loyalty
    settings.set_many({"loyalty_enabled": "1", "loyalty_min_redeem": "10", "loyalty_point_value": "0.1"})
    pid = products.add_product("بسكويت", "b1", "حلويات", 1, 3, 50, 0)
    promotions.add_promotion("اشترِ 2 واحصل على 1", "buy_get", product_id=pid, buy_qty=2, get_qty=1)
    cid = customers.add_customer("زبون الولاء")
    pos.search.setText("6*b1")
    pos.on_enter()
    t = pos.update_totals()
    assert t["discount"] == 6 and t["total"] == 12 and "اشترِ 2" in pos.lbl_promo.text()
    pos.set_customer(customers.get_customer(cid))
    pos.finish_sale({"cash_amount": 12, "card_amount": 0, "credit_amount": 0, "cash_received": 12, "change": 0})
    assert loyalty.balance(cid) == 12 and "نقطة" in pos.lbl_change.text()
    inv = sales.get_invoice(pos.last_invoice_id)
    assert inv["promo_discount"] == 6
    from core import receipts
    html = receipts.invoice_html(pos.last_invoice_id)
    assert "خصم العروض" in html and "رصيد نقاطك" in html
    # استبدال النقاط في الفاتورة التالية
    pos.search.setText("b1")
    pos.on_enter()
    pos.set_customer(customers.get_customer(cid))
    pos.points = 10
    assert pos.update_totals()["total"] == 2
    pos.finish_sale({"cash_amount": 2, "card_amount": 0, "credit_amount": 0, "cash_received": 2, "change": 0})
    assert loyalty.balance(cid) == 12 - 10 + 2


def test_new_screens_actions(app):
    from core import ledger, cheques
    from ui.accounting_screen import AccountingScreen, TemplateEntryDialog
    from ui.cheques_screen import ChequesScreen, ChequeDialog
    from ui.reorder_screen import ReorderScreen
    d = TemplateEntryDialog(None)
    d.amount.setValue(1000)
    d.accept()
    assert ledger.balance_sheet()["total_assets"] == 1000
    scr = AccountingScreen()
    scr.refresh()
    for i in range(scr.tabs.count()):
        scr.tabs.setCurrentIndex(i)
    assert scr.bs_table.rowCount() > 3
    cid = customers.add_customer("صاحب شيك", opening_balance=500)
    cd = ChequeDialog(None, "in", cid)
    cd.amount.setValue(200)
    cd.number.setText("123")
    cd.accept()
    assert customers.balance(cid) == 300 and len(cheques.list_cheques()) == 1
    cs = ChequesScreen()
    cs.refresh()
    assert cs.table.rowCount() == 1
    rs = ReorderScreen()
    rs.refresh()
