# -*- coding: utf-8 -*-
"""اختبارات الواجهة بدون شاشة (offscreen): تدفق البيع الكامل من نقطة البيع"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core import products, sales, customers, settings, barcode, shifts, suppliers, db


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
    assert data == {"cash_amount": 20, "card_amount": 10, "credit_amount": 27.5, "cash_received": 20, "change": 0.0,
                    "note": "", "card_ref": "", "wallet_amount": 0.0, "wallet_name": "", "wallet_ref": ""}


def test_all_screens_open(app):
    from ui.main_window import MainWindow, PAGES
    w = MainWindow()
    w.show()
    for key, *_ in PAGES:
        w.go(key)
        app.processEvents()
        assert w.stack.currentWidget() is w.page_holders[key]
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


def test_wholesale_customer_reprices_and_customer_display(pos):
    from core import config
    pid = products.add_product("سكر كيس", "w1", "", 3, 5, 100, 0, wholesale_price=4.2)
    retail = customers.add_customer("زبون مفرق")
    whole = customers.add_customer("تاجر جملة", price_level="wholesale")
    config.save({"customer_display": "1"})
    pos.search.setText("10*w1")
    pos.on_enter()
    assert pos.update_totals()["total"] == 50
    from ui import customer_display
    d = customer_display.get()
    assert "50.00" in d.total.text()
    pos.set_customer(customers.get_customer(whole))
    assert pos.cart[0]["unit_price"] == 4.2 and pos.update_totals()["total"] == 42
    pos.set_customer(customers.get_customer(retail))
    assert pos.cart[0]["unit_price"] == 5
    pos.set_customer(customers.get_customer(whole))
    pos.finish_sale({"cash_amount": 42, "card_amount": 0, "credit_amount": 0, "cash_received": 50, "change": 8})
    assert "8.00" in d.total.text() and "شكراً" in d.items.text()
    assert sales.get_invoice(pos.last_invoice_id)["total"] == 42
    config.save({"customer_display": "0"})
    assert customer_display.get() is None


def test_pos_keeps_selling_when_network_drops(pos, monkeypatch):
    from core import offline, remote, promotions
    pid = products.add_product("حمص", "h1", "", 2, 4, 10, 0)
    promotions.add_promotion("3 بـ 10", "bundle", product_id=pid, bundle_qty=3, bundle_price=10)
    offline.refresh_cache()

    def down(*a, **k):
        raise remote.ConnectionFailed("الشبكة مقطوعة")
    monkeypatch.setattr(products, "lookup_code", down)
    monkeypatch.setattr(sales, "cart_discounts", down)
    monkeypatch.setattr(sales, "create_sale", down)
    pos.search.setText("3*h1")
    pos.on_enter()
    assert pos.offline_mode and len(pos.cart) == 1
    assert pos.update_totals()["total"] == 10                       # العرض محسوب من النسخة المحلية
    pos.finish_sale({"cash_amount": 10, "card_amount": 0, "credit_amount": 0, "cash_received": 20, "change": 10})
    assert pos.cart == [] and offline.pending_count() == 1 and "الباقي" in pos.lbl_change.text()
    from core import receipts
    assert "10.00" in receipts.offline_receipt_html(offline.queue()[0])
    monkeypatch.undo()
    assert offline.sync() == (1, 0)
    inv = sales.get_invoices(limit=1)[0]
    assert inv["total"] == 10 and inv["promo_discount"] == 2
    assert products.get_product(pid)["quantity"] == 7


def test_online_order_to_pos_sale(pos):
    from core import orders
    settings.set("online_store_enabled", "1")
    pid = products.add_product("زيت", "z1", "", 10, 15, 20, 0)
    r = orders.create_order({"name": "ليلى", "phone": "0599333444", "items": [{"product_id": pid, "quantity": 3}]}, "ip")
    pos.load_order(orders.get_order(r["id"]))
    assert len(pos.cart) == 1 and pos.cart[0]["quantity"] == 3 and pos.customer["phone"] == "0599333444"
    pos.finish_sale({"cash_amount": 45, "card_amount": 0, "credit_amount": 0, "cash_received": 50, "change": 5})
    o = orders.get_order(r["id"])
    assert o["status"] == "done" and o["invoice_id"] == pos.last_invoice_id
    from ui.orders_screen import OrdersScreen
    s = OrdersScreen()
    s.refresh()


def test_online_delivery_fee_becomes_revenue_on_invoice(pos):
    from core import orders, reports
    settings.set_many({"online_store_enabled": "1", "online_store_delivery": "1", "online_store_delivery_fee": "7"})
    pid = products.add_product("أرز", "r1", "", 10, 20, 20, 0)
    r = orders.create_order({"name": "سامي", "phone": "0599111222", "fulfilment": "delivery", "address": "الحارة",
                             "items": [{"product_id": pid, "quantity": 2}]}, "ip2")
    assert r["total"] == 47
    pos.load_order(orders.get_order(r["id"]))
    assert len(pos.cart) == 2 and pos.cart[1]["service"] and pos.cart[1]["unit_price"] == 7
    pos.finish_sale({"cash_amount": 47, "card_amount": 0, "credit_amount": 0, "cash_received": 50, "change": 3})
    inv = sales.get_invoice(pos.last_invoice_id)
    assert inv["total"] == 47                                   # الفاتورة = ما دفعه الزبون بالضبط
    assert products.get_product(pid)["quantity"] == 18          # رسوم الخدمة لا تمس المخزون
    svc = products.get_product(products.service_product("رسوم التوصيل"))
    assert svc["quantity"] == 0 and svc["is_service"] == 1
    assert svc["id"] not in [p["id"] for p in products.get_low_stock_products()]
    t = db.today()
    assert reports.profit_and_loss(t, t)["net_sales"] == 47


def test_foreign_currency_cash_payment(app):
    from ui.pos_screen import PaymentDialog, parse_currencies
    assert parse_currencies("USD=3.65, jod=5.15,bad,X=0") == [("USD", 3.65), ("JOD", 5.15)]
    settings.set("extra_currencies", "USD=3.5")
    d = PaymentDialog(None, 70, None)
    from PySide6.QtWidgets import QInputDialog
    orig = QInputDialog.getDouble
    QInputDialog.getDouble = staticmethod(lambda *a, **k: (25.0, True))
    try:
        d.pay_foreign("USD", 3.5)
    finally:
        QInputDialog.getDouble = orig
    data, err = d.compute()
    assert err is None and data["change"] == 17.5 and data["note"] == "دفع 25 USD بسعر 3.5"


def test_simple_mode_logo_and_touch_keypad(app):
    from core import config, receipts
    from ui.main_window import MainWindow, ADVANCED_PAGES
    settings.set("simple_mode", "1")
    w = MainWindow()
    assert all(w.nav_buttons[k].isHidden() for k in ADVANCED_PAGES)
    assert not w.nav_buttons["pos"].isHidden() and not w.nav_buttons["help"].isHidden()
    settings.set("simple_mode", "0")
    w.refresh_nav()
    assert not w.nav_buttons["accounting"].isHidden()
    w.show()
    w.go("help")
    assert w.pages["help"].view.toPlainText()                       # الدليل يُعرض داخل البرنامج
    w.close()
    settings.set("shop_logo", "iVBORw0KGgo=")
    pid = products.add_product("لوغو", "lg1", "", 1, 2, 5, 0)
    r = sales.create_sale([{"product_id": pid, "product_name": "لوغو", "quantity": 1, "unit_price": 2}])
    assert "data:image/png;base64,iVBORw0KGgo=" in receipts.invoice_html(r["invoice_id"])
    config.save({"touch_mode": "1"})
    from ui.pos_screen import PaymentDialog
    d = PaymentDialog(None, 12.5, None)
    for k in "20.5":
        d.key(k)
    assert d.cash.value() == 20.5 and d.compute()[0]["change"] == 8
    d.key("⌫")
    d.key("C")
    assert d.cash.value() == 0
    config.save({"touch_mode": "0"})


def test_card_terminal_simulator_and_bridge(app):
    import threading, socket, importlib.util, os
    from core import config, payments, receipts
    with pytest.raises(payments.TerminalError):
        payments.charge(10)                                          # يدوي: لا ربط
    config.save({"card_terminal": "simulator"})
    assert payments.charge(10)["approved"] and not payments.charge(10.13)["approved"]
    # الجسر المرجعي عبر HTTP حقيقي
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "terminal_bridge.py")
    spec = importlib.util.spec_from_file_location("terminal_bridge", path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    httpd = bridge.serve(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        config.save({"card_terminal": "bridge", "card_terminal_url": f"http://127.0.0.1:{port}"})
        assert payments.status()["ok"]
        r = payments.charge(25.5, "INV-TEST")
        assert r["approved"] and r["card"].startswith("****") and "AUTH" in r["reference"]
        from ui.pos_screen import PaymentDialog, TerminalDialog
        d = PaymentDialog(None, 40, None)
        t = TerminalDialog(None, 40)
        t.wait()
        assert t.result() == 1 and t.result_data["approved"]
        d.card.setValue(40); d.cash.setValue(0); d.card_ref = t.result_data["reference"]
        data, err = d.compute()
        pid = products.add_product("بطاقة", "cd1", "", 10, 40, 5, 0)
        res = sales.create_sale([{"product_id": pid, "product_name": "x", "quantity": 1, "unit_price": 40}],
                                cash_amount=0, card_amount=40, card_ref=data["card_ref"])
        assert data["card_ref"] in receipts.invoice_html(res["invoice_id"])
    finally:
        httpd.shutdown()
        httpd.server_close()
        config.save({"card_terminal": "manual"})
    with pytest.raises(payments.TerminalError):
        config.save({"card_terminal": "bridge", "card_terminal_url": f"http://127.0.0.1:{port}",
                     "card_terminal_timeout": 3})
        payments.charge(5)                                           # الجسر متوقف: رسالة واضحة
    config.save({"card_terminal": "manual"})


def test_language_switch_is_instant_and_keeps_cart(app):
    from PySide6.QtCore import Qt
    from core import auth
    auth.login("admin", "admin")
    qapp = app
    from core import config, i18n
    from ui import i18n_qt
    from ui.main_window import MainWindow
    a = products.add_product("حليب", "7001", "ألبان", 3, 5, 20, 2)
    w = MainWindow()
    w.show()
    w.go("pos")
    w.pages["pos"].add_product(products.get_product(a), 2)
    w2 = w.switch_language("en")
    assert i18n.language() == "en" and config.get("language") == "en"
    assert w2.current_key == "pos" and len(w2.pages["pos"].cart) == 1
    assert qapp.layoutDirection() == Qt.LeftToRight
    w3 = w2.switch_language("ar")
    assert i18n.language() == "ar" and qapp.layoutDirection() == Qt.RightToLeft
    assert len(w3.pages["pos"].cart) == 1 and w3.pages["pos"].cart[0]["quantity"] == 2
    w3.pages["pos"].clear_cart()
    w3.close()
    i18n_qt.apply_language("ar", qapp)


def test_window_fits_small_screens_and_pos_shortcuts_stay_visible(app):
    from core import auth
    auth.login("admin", "admin")
    qapp = app
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    hint = w.minimumSizeHint()
    assert hint.width() <= 1024 and hint.height() <= 600, (hint.width(), hint.height())
    for size in ((1366, 705), (1280, 650), (1024, 560)):
        w.resize(*size)
        w.go("pos")
        qapp.processEvents()
        pos = w.pages["pos"]
        bottom = pos.height()
        for b in pos.action_buttons + [pos.pay_btn, pos.keys_hint]:
            assert b.isVisible()
            assert b.mapTo(pos, b.rect().bottomLeft()).y() <= bottom, (size, b.text())
    assert w._rail                      # الشاشة الضيقة: القائمة أيقونات فقط
    w.resize(1600, 900)
    qapp.processEvents()
    assert not w._rail
    w.close()
