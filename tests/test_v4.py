# -*- coding: utf-8 -*-
"""اختبارات النسخة 4: القيد المزدوج، الشيكات، العروض، نقاط الولاء، مرتجع المشتريات، الطلبيات، الترخيص، الأمان"""
from datetime import date, timedelta

import pytest

from core import (db, products, sales, suppliers, customers, expenses, shifts, reports, settings, ledger, cheques,
                  promotions, loyalty, reorder, license, remote, auth, owner_web)
from core.sales import SaleError


def d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def item(pid, q, price, name="x", **kw):
    return dict(product_id=pid, product_name=name, quantity=q, unit_price=price, **kw)


def _busy_shop():
    """يوم عمل كامل بكل أنواع العمليات"""
    settings.set_many({"vat_enabled": "1", "vat_rate": "16", "prices_include_vat": "1"})
    a = products.add_product("أرز", "100", "مواد غذائية", 8, 11.6, 50, 5)
    b = products.add_product("زيت", "200", "مواد غذائية", 20, 29, 0, 5)
    sup = suppliers.add_supplier("شركة التموين", "0599000000", opening_balance=300)
    suppliers.create_purchase(sup, [{"product_id": b, "quantity": 10, "unit_cost": 20, "expiry_date": d(90)}], paid=100,
                              payment_method=suppliers.PAY_BANK)
    cust = customers.add_customer("أبو محمد", "0599111111", credit_limit=1000, opening_balance=50)
    sid = shifts.open_shift(200)
    s1 = sales.create_sale([item(a, 5, 11.6), item(b, 2, 29)], discount=6, shift_id=sid, cash_received=200)
    s2 = sales.create_sale([item(a, 3, 11.6)], customer_id=cust, cash_amount=10, credit_amount=24.8, shift_id=sid)
    sales.create_sale([item(b, 1, 29)], card_amount=29, shift_id=sid)
    it = sales.returnable_items(s1["invoice_id"])[0]
    sales.create_return(s1["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], shift_id=sid)
    it2 = sales.returnable_items(s2["invoice_id"])[0]
    sales.create_return(s2["invoice_id"], [{"invoice_item_id": it2["id"], "quantity": 1}], refund_method=sales.REFUND_DEBT)
    customers.receive_payment(cust, 15, "نقدي", shift_id=sid)
    customers.adjust_balance(cust, -2, "مسامحة")
    suppliers.pay_supplier(sup, 50, suppliers.PAY_DRAWER, shift_id=sid)
    suppliers.pay_supplier(sup, 70, suppliers.PAY_BANK)
    expenses.add_expense("كهرباء", 40, from_drawer=True, shift_id=sid)
    expenses.add_expense("إيجار", 500, from_drawer=False)
    products.set_stock_count(a, products.get_product(a)["quantity"] - 1)   # عجز جرد قطعة
    shifts.cash_movement(-100, "سحب المالك")
    suppliers.create_purchase_return(sup, [{"product_id": b, "quantity": 2}], "تالف")
    return {"a": a, "b": b, "sup": sup, "cust": cust, "sid": sid}


def test_ledger_balances_and_matches_subledgers():
    s = _busy_shop()
    t = db.today()
    tb = ledger.trial_balance(t, t)
    assert tb["totals"]["balanced"], tb["totals"]
    bal = {r["code"]: r["closing"] for r in tb["rows"]}
    # الحسابات المساعدة تطابق دفتر الأستاذ
    assert bal[ledger.RECEIVABLES] == customers.balance(s["cust"])
    assert -bal[ledger.PAYABLES] == suppliers.balance(s["sup"])
    assert bal[ledger.CASH] == shifts.summary(s["sid"])["expected_cash"]
    # المخزون الدفتري = قيمة المخزون الفعلية (لا فروقات في هذا السيناريو)
    assert bal[ledger.INVENTORY] == pytest.approx(products.inventory_value()["cost_value"], abs=0.02)
    bs = ledger.balance_sheet(t)
    assert bs["balanced"]
    assert bs["total_assets"] == pytest.approx(bs["total_liabilities"] + bs["total_equity"], abs=0.01)
    # قائمة الدخل من الدفتر = تقرير الأرباح والخسائر (مع إيراد تسوية المرتجع للمورد = 0 هنا)
    inc = ledger.income_statement(t, t)
    pl = reports.profit_and_loss(t, t)
    assert inc["net_sales"] == pytest.approx(pl["net_revenue"], abs=0.01)
    assert inc["cogs"] == pytest.approx(pl["cogs"], abs=0.01)
    assert inc["net_income"] == pytest.approx(pl["net_profit"], abs=0.01)
    assert pl["other_adjustments"] == -2  # مسامحة العميل
    # كشف حساب الصندوق يبدأ بصفر وينتهي بالنقد المتوقع
    st = ledger.account_statement(ledger.CASH, t, t)
    assert st["closing"] == shifts.summary(s["sid"])["expected_cash"]
    exp = ledger.account_statement(ledger.EXPENSES, t, t)
    assert exp["closing"] == 540


def test_shift_close_difference_and_handover():
    pid = products.add_product("خبز", "300", "", 1, 2, 100, 0)
    sid = shifts.open_shift(100)
    sales.create_sale([item(pid, 10, 2)], shift_id=sid)
    shifts.close_shift(115)              # عجز 5
    shifts.open_shift(50)                # المالك أخذ 65 بين الورديتين
    t = db.today()
    bal = {r["code"]: r["closing"] for r in ledger.trial_balance(t, t)["rows"]}
    assert bal[ledger.CASH] == 50
    assert bal[ledger.CASH_SHORT] == 5
    assert ledger.trial_balance(t, t)["totals"]["balanced"]
    assert ledger.income_statement(t, t)["net_income"] == reports.profit_and_loss(t, t)["net_profit"]


def test_manual_entries_and_accounts():
    with pytest.raises(ValueError):
        ledger.add_manual_entry(db.today(), "غير متوازن", [{"account": ledger.BANK, "debit": 100},
                                                           {"account": ledger.CAPITAL, "credit": 90}])
    with pytest.raises(ValueError):
        ledger.add_manual_entry(db.today(), "حساب مجهول", [{"account": "9999", "debit": 1}, {"account": "1110", "credit": 1}])
    r = ledger.add_manual_entry(db.today(), "إيداع رأس مال", [{"account": ledger.BANK, "debit": 5000},
                                                              {"account": ledger.CAPITAL, "credit": 5000}])
    ledger.add_account("1520", "سيارة التوصيل", "asset")
    with pytest.raises(ValueError):
        ledger.add_account("1520", "مكرر", "asset")
    ledger.add_manual_entry(db.today(), "شراء سيارة", [{"account": "1520", "debit": 3000},
                                                      {"account": ledger.BANK, "credit": 3000}])
    bs = ledger.balance_sheet()
    assert bs["balanced"] and bs["total_assets"] == 5000
    ledger.void_entry(r["entry_id"])
    assert ledger.balance_sheet()["total_assets"] == 0
    assert ledger.balance_sheet()["balanced"]


def test_cheques_in_and_out():
    cust = customers.add_customer("تاجر", opening_balance=1000)
    sup = suppliers.add_supplier("مورد", opening_balance=800)
    c1 = cheques.receive_cheque(cust, 600, d(10), "12345", "بنك فلسطين")
    assert customers.balance(cust) == 400
    c2 = cheques.issue_cheque(sup, 500, d(3), "777", "بنك القدس")
    assert suppliers.balance(sup) == 300
    assert [c["id"] for c in cheques.due_soon(7)] == [c2]
    assert cheques.totals() == {"incoming": 600, "outgoing": 500}
    cheques.bounce_cheque(c1, "رصيد غير كافٍ")
    assert customers.balance(cust) == 1000
    with pytest.raises(ValueError):
        cheques.clear_cheque(c1)
    cheques.clear_cheque(c2)
    t = db.today()
    bal = {r["code"]: r["closing"] for r in ledger.trial_balance(t, t)["rows"]}
    assert bal.get(ledger.CHEQUES_IN, 0) == 0 and bal.get(ledger.CHEQUES_OUT, 0) == 0
    assert bal[ledger.BANK] == -500
    assert ledger.trial_balance(t, t)["totals"]["balanced"]


def test_promotions_buy_get_bundle_percent():
    tuna = products.add_product("تونة", "400", "معلبات", 3, 5, 100, 0)
    soap = products.add_product("صابون", "500", "منظفات", 2, 4, 100, 0)
    promotions.add_promotion("اشترِ 2 واحصل على 1", "buy_get", product_id=tuna, buy_qty=2, get_qty=1)
    promotions.add_promotion("15% على المنظفات", "percent", category="منظفات", percent=15)
    cart = [item(tuna, 7, 5), item(soap, 2, 4)]
    r = promotions.apply(cart)
    assert r["total"] == 2 * 5 + 1.2 and len(r["lines"]) == 2
    res = sales.create_sale(cart, discount=1)
    inv = sales.get_invoice(res["invoice_id"])
    assert inv["promo_discount"] == 11.2 and inv["discount"] == 12.2 and inv["total"] == 43 - 12.2
    assert "عروض" in inv["note"]
    # عرض منتهي لا يُطبق
    with db.tx() as conn:
        conn.execute("UPDATE promotions SET end_date=?", (d(-1),))
    assert promotions.apply(cart)["total"] == 0
    with pytest.raises(ValueError):
        promotions.add_promotion("", "percent", percent=10, category="x")
    water = products.add_product("ماء", "600", "", 0.5, 1.5, 100, 0)
    promotions.add_promotion("3 بـ 4", "bundle", product_id=water, bundle_qty=3, bundle_price=4)
    assert promotions.apply([item(water, 7, 1.5)])["total"] == 2 * (4.5 - 4)
    settings.set("promotions_enabled", "0")
    assert promotions.apply([item(water, 7, 1.5)])["total"] == 0


def test_loyalty_earn_redeem_and_return():
    settings.set_many({"loyalty_enabled": "1", "loyalty_points_per_unit": "1", "loyalty_point_value": "0.05",
                       "loyalty_min_redeem": "100"})
    pid = products.add_product("قهوة", "700", "", 20, 30, 100, 0)
    cid = customers.add_customer("زبونة دائمة")
    r1 = sales.create_sale([item(pid, 5, 30)], customer_id=cid)
    assert r1["points_earned"] == 150 and loyalty.balance(cid) == 150
    with pytest.raises(SaleError):
        sales.create_sale([item(pid, 1, 30)], customer_id=cid, points_redeemed=50)   # أقل من الحد
    with pytest.raises(SaleError):
        sales.create_sale([item(pid, 1, 30)], customer_id=cid, points_redeemed=500)  # أكثر من الرصيد
    r2 = sales.create_sale([item(pid, 1, 30)], customer_id=cid, points_redeemed=100)
    assert r2["total"] == 25 and r2["points_value"] == 5
    assert loyalty.balance(cid) == 150 - 100 + 25
    it = sales.returnable_items(r1["invoice_id"])[0]
    sales.create_return(r1["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])
    assert loyalty.balance(cid) == 75 - 30
    t = db.today()
    assert ledger.trial_balance(t, t)["totals"]["balanced"]


def test_purchase_return_and_reorder():
    pid = products.add_product("حليب", "800", "ألبان", 4, 6, 0, 10)
    products.set_units(pid, [{"name": "كرتونة", "factor": 12, "barcode": "801", "sale_price": 66}])
    sup = suppliers.add_supplier("الألبان", "0599222333")
    suppliers.create_purchase(sup, [{"product_id": pid, "quantity": 30, "unit_cost": 4}])
    for _ in range(3):
        sales.create_sale([item(pid, 5, 6)])
    r = suppliers.create_purchase_return(sup, [{"product_id": pid, "quantity": 3, "unit_cost": 3.5}], "منتهي")
    assert r["total"] == 10.5 and products.get_product(pid)["quantity"] == 12
    assert suppliers.balance(sup) == 120 - 10.5
    with pytest.raises(ValueError):
        suppliers.create_purchase_return(sup, [{"product_id": pid, "quantity": 100}])
    t = db.today()
    tb = ledger.trial_balance(t, t)
    assert tb["totals"]["balanced"]
    assert {r["code"]: r["closing"] for r in tb["rows"]}[ledger.STOCK_LOSS] == 1.5  # بيع للمورد بأقل من التكلفة
    assert ledger.income_statement(t, t)["net_income"] == reports.profit_and_loss(t, t)["net_profit"]
    sug = reorder.suggestions(days=30, cover_days=14)
    s = [x for x in sug if x["product_id"] == pid][0]
    # بيع 15 في 30 يوماً = 0.5 يومياً ← 7 للتغطية + 10 حد أدنى − 12 موجود = 5 ← كرتونة واحدة
    assert s["order_units"] == 1 and s["unit_name"] == "كرتونة" and s["supplier_name"] == "الألبان"
    msg = reorder.order_message([s], "الألبان")
    assert "حليب" in msg and "كرتونة" in msg


@pytest.fixture
def keys(monkeypatch):
    import importlib.util, os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "license_tool.py")
    spec = importlib.util.spec_from_file_location("license_tool", path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    public, private = tool.generate_keypair(768)
    monkeypatch.setattr(license, "PUBLIC_KEY", public)
    monkeypatch.setenv("SHOP_MACHINE_ID", "test-machine")
    return tool, private


def test_license_trial_activation_and_expiry(keys):
    tool, private = keys
    st = license.status()
    assert st["state"] == "trial" and st["days_left"] == license.TRIAL_DAYS
    pid = products.add_product("سكر", "900", "", 3, 4, 100, 0)
    # انتهاء التجربة يوقف البيع فقط
    db.set_meta("install_date", d(-40))
    assert license.status()["state"] == "expired"
    with pytest.raises(SaleError):
        sales.create_sale([item(pid, 1, 4)])
    assert reports.profit_and_loss(db.today(), db.today())["invoice_count"] == 0  # التقارير تعمل
    # مفتاح لجهاز آخر مرفوض
    other, _ = tool.issue(private, "AAAA-BBBB-CCCC-DDDD", "محل آخر")
    with pytest.raises(license.LicenseError):
        license.activate(other)
    # مفتاح معدّل مرفوض
    good, data = tool.issue(private, license.machine_id(), "سوبرماركت الأمل", "pro", 3)
    body = good.split(".")
    with pytest.raises(license.LicenseError):
        license.activate(body[0] + "." + body[1][:-2] + "AA." + body[2])
    st = license.activate(good)
    assert st["state"] == "licensed" and st["terminals"] == 3 and st["shop"] == "سوبرماركت الأمل"
    sales.create_sale([item(pid, 1, 4)])
    # اشتراك منتهٍ
    sub, _ = tool.issue(private, license.machine_id(), "x", "subscription", 1, d(5))
    license.activate(sub)
    assert license.status()["state"] == "licensed"
    db.set_meta("last_seen_date", d(10))   # الساعة تقدمت (أو أُرجعت للوراء بعد ذلك)
    assert license.status()["state"] == "license_expired"
    with pytest.raises(license.LicenseError):
        license.activate(tool.issue(private, license.machine_id(), "x", "subscription", 1, d(-1))[0])


def test_remote_permission_checks():
    cashier = {"id": 99, "role": "cashier"}
    admin = {"id": 1, "role": "admin"}
    with pytest.raises(PermissionError):
        remote.check_permission(("auth", "create_user"), cashier, [], {})
    with pytest.raises(PermissionError):
        remote.check_permission(("auth", "change_password"), cashier, [1, "x"], {})
    remote.check_permission(("auth", "change_password"), cashier, [99, "newpass"], {})
    with pytest.raises(PermissionError):
        remote.check_permission(("settings", "save_shared"), cashier, [{}], {})
    with pytest.raises(PermissionError):
        remote.check_permission(("ledger", "add_manual_entry"), cashier, [], {})
    remote.check_permission(("auth", "create_user"), admin, [], {})
    remote.check_permission(("sales", "create_sale"), cashier, [], {})
    # كل وظائف الوحدات الجديدة متاحة عبر الشبكة، والدوال التي تأخذ اتصالاً داخلياً ليست منها
    fns = remote.remote_functions()
    assert ("ledger", "trial_balance") in fns and ("cheques", "receive_cheque") in fns
    assert ("loyalty", "_record") not in fns


def test_owner_web_and_daily_summary():
    pid = products.add_product("شاي", "910", "", 5, 8, 3, 5)
    sales.create_sale([item(pid, 1, 8, "شاي")])
    token, err = owner_web.login(b"username=admin&password=wrong")
    assert token is None and err
    token, err = owner_web.login(b"username=admin&password=admin")
    assert token and not err
    user = owner_web.user_from_cookie(f"a=b; {owner_web.COOKIE}={token}")
    assert user["username"] == "admin"
    html = owner_web.dashboard_page()
    assert "مبيعات اليوم" in html and "شاي" in html
    txt = reports.daily_summary_text()
    assert "المبيعات: 8.00" in txt and "تحت الحد الأدنى" in txt
    owner_web.logout(f"{owner_web.COOKIE}={token}")
    assert owner_web.user_from_cookie(f"{owner_web.COOKIE}={token}") is None


def test_insights_abc_and_bulk_prices():
    from core import insights
    a = products.add_product("رابح", "i1", "مواد", 5, 10, 100, 5)
    b = products.add_product("خاسر", "i2", "مواد", 12, 10, 50, 5)
    c = products.add_product("نادر", "i3", "مواد", 1, 2, 3, 5)
    d = products.add_product("راكد", "i4", "منظفات", 20, 30, 40, 1)
    cid = customers.add_customer("زبون")
    for _ in range(5):
        sales.create_sale([item(a, 10, 10), item(b, 1, 10)])
    sales.create_sale([item(a, 2, 10), item(c, 1, 2)], customer_id=cid)
    cards = {x["key"]: x for x in insights.insights(30)}
    assert "loss_pricing" in cards and cards["loss_pricing"]["severity"] == "danger"
    assert "dead_stock" in cards and "راكد" in "".join(cards["dead_stock"]["items"])
    assert list(cards)[0] in ("loss_pricing", "stockout")        # الأخطر أولاً
    abc = insights.abc_analysis(90)
    assert abc[0]["name"] == "رابح" and abc[0]["class"] == "A"
    assert insights.bought_together(60)[0]["count"] == 5
    prev = insights.price_update_preview("margin", 20, rounding=0.5, only_below_target=True)
    names = {p["name"]: p["new"] for p in prev}
    assert names["خاسر"] == 15 and "رابح" not in names          # 12 / 0.8 = 15 ؛ الرابح هامشه 50%
    assert insights.apply_price_update(prev) == len(prev)
    assert products.get_product(b)["sale_price"] == 15
    up = insights.price_update_preview("percent", 10, category="منظفات")
    assert up == [{"id": d, "name": "راكد", "cost": 20, "old": 30, "new": 33}]


def test_input_vat_on_purchases_and_vat_report():
    settings.set_many({"vat_enabled": "1", "vat_rate": "16", "prices_include_vat": "1"})
    pid = products.add_product("عصير", "v1", "", 0, 11.6, 0, 0)
    sup = suppliers.add_supplier("مورد ضريبي")
    suppliers.create_purchase(sup, [{"product_id": pid, "quantity": 10, "unit_cost": 5.8}], tax=8)   # 58 شامل 8
    assert products.get_product(pid)["cost_price"] == 5          # التكلفة بدون ضريبة المدخلات
    assert suppliers.balance(sup) == 58
    with pytest.raises(ValueError):
        suppliers.create_purchase(sup, [{"product_id": pid, "quantity": 1, "unit_cost": 5}], tax=9)
    sales.create_sale([item(pid, 5, 11.6)])                       # 58 منها 8 ضريبة مخرجات
    t = db.today()
    v = reports.vat_report(t, t)
    assert v["output_tax"] == 8 and v["input_tax"] == 8 and v["net_due"] == 0
    tb = ledger.trial_balance(t, t)
    bal = {r["code"]: r["closing"] for r in tb["rows"]}
    assert tb["totals"]["balanced"] and bal[ledger.VAT_INPUT] == 8 and bal[ledger.VAT] == -8
    assert bal[ledger.INVENTORY] == pytest.approx(products.inventory_value()["cost_value"], abs=0.01)
    assert ledger.income_statement(t, t)["net_income"] == reports.profit_and_loss(t, t)["net_profit"] == 25


def test_online_orders_core():
    from core import orders
    pid = products.add_product("أرز", "o1", "مواد", 5, 12, 50, 0)
    order = {"name": "سامي", "phone": "0599111222", "fulfilment": "pickup",
             "items": [{"product_id": pid, "quantity": 2, "unit_price": 0.01}]}   # السعر من المتصفح يُتجاهل
    with pytest.raises(orders.OrderError):
        orders.create_order(order, "1.1.1.1")                                     # المتجر غير مفعّل
    settings.set_many({"online_store_enabled": "1", "online_store_delivery_fee": "5"})
    r = orders.create_order(order, "1.1.1.1")
    assert r["total"] == 24 and r["order_number"].startswith("WEB-")
    with pytest.raises(orders.OrderError):
        orders.create_order(dict(order, fulfilment="delivery"), "1.1.1.1")        # التوصيل بدون عنوان
    assert orders.create_order(dict(order, fulfilment="delivery", address="شارع 1"), "1.1.1.1")["total"] == 29
    for _ in range(10):
        orders.create_order(order, "2.2.2.2")
    with pytest.raises(orders.OrderError):
        orders.create_order(order, "2.2.2.2")                                     # حد 10 طلبات بالساعة
    assert orders.new_count() == 12
    o = orders.list_orders("open")[-1]
    orders.set_status(o["id"], "ready")
    assert "جاهز" in orders.status_message(orders.get_order(o["id"]))
    assert "أرز" in orders.store_page()


def test_einvoice_qr_and_updates():
    from core import einvoice, updates, receipts
    b64 = einvoice.tlv_base64("سوبرماركت", "300000000000003", "2026-09-27T10:00:00", 115, 15)
    assert einvoice.decode_tlv(b64) == {1: "سوبرماركت", 2: "300000000000003", 3: "2026-09-27T10:00:00",
                                        4: "115.00", 5: "15.00"}
    assert einvoice.qr_data_uri(b64).startswith("data:image/png;base64,")
    settings.set_many({"einvoice_qr": "1", "vat_enabled": "1", "tax_number": "300000000000003"})
    pid = products.add_product("شاي", "q1", "", 5, 11.5, 10, 0)
    r = sales.create_sale([item(pid, 1, 11.5)])
    html = receipts.invoice_html(r["invoice_id"])
    assert "data:image/png;base64," in html and "فاتورة ضريبية مبسطة" in html
    assert updates.is_newer("6.1", "6.0") and not updates.is_newer("6.0", "6.0") and updates.is_newer("10.0", "9.9")
    assert updates.check(url="") is None and updates.check(url="http://127.0.0.1:9/none.json") is None
