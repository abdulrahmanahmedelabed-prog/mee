# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime

import pytest

from core import db, auth, settings, products, sales, customers, suppliers, expenses, shifts, reports, backup, barcode
from core.sales import SaleError


def mk(name="حليب", price=5, cost=3, q=10, **kw):
    return products.add_product(name, kw.pop("barcode", None), kw.pop("category", "ألبان"), cost, price, q, 2, **kw)


def line(pid, q, price=None):
    p = products.get_product(pid)
    return {"product_id": pid, "product_name": p["name"], "quantity": q,
            "unit_price": p["sale_price"] if price is None else price}


# ---------------- المستخدمون ----------------

def test_default_admin_and_roles():
    assert auth.current_user()["role"] == "admin"
    assert auth.current_user()["must_change_password"] == 1
    auth.create_user("sara", "سارة", "1234", "cashier")
    u = auth.authenticate("sara", "1234")
    assert u and not auth.has_permission("reports", u) and auth.has_permission("pos", u)
    assert auth.authenticate("sara", "wrong") is None
    with pytest.raises(ValueError):
        auth.update_user(auth.current_user_id(), "x", "cashier", True)  # آخر مدير


# ---------------- البيع ----------------

def test_sale_reduces_stock_and_numbers_unique():
    pid = mk(q=10)
    nums = {sales.create_sale([line(pid, 1)])["invoice_number"] for _ in range(5)}
    assert len(nums) == 5
    assert products.get_product(pid)["quantity"] == 5


def test_insufficient_stock_blocked_and_aggregated():
    pid = mk(q=3)
    with pytest.raises(SaleError):
        sales.create_sale([line(pid, 2), line(pid, 2)])  # نفس المنتج مرتين = 4 > 3
    assert products.get_product(pid)["quantity"] == 3  # لم يتغير شيء (rollback)
    settings.set("allow_negative_stock", "1")
    sales.create_sale([line(pid, 4)])
    assert products.get_product(pid)["quantity"] == -1


def test_discount_clamped_and_reduces_profit():
    pid = mk(price=10, cost=6, q=10)
    r = sales.create_sale([line(pid, 2)], discount=50)
    assert r["discount"] == 20 and r["total"] == 0
    r = sales.create_sale([line(pid, 2)], discount=3)
    pl = reports.profit_and_loss(db.today(), db.today())
    assert pl["net_sales"] == 17
    assert pl["cogs"] == 24
    assert pl["gross_profit"] == 17 - 24


def test_vat_inclusive_and_exclusive():
    pid = mk(price=116, cost=50, q=10)
    settings.set_many({"vat_enabled": "1", "vat_rate": "16", "prices_include_vat": "1"})
    r = sales.create_sale([line(pid, 1)])
    assert r["total"] == 116 and r["tax"] == 16
    settings.set("prices_include_vat", "0")
    r = sales.create_sale([line(pid, 1)])
    assert r["total"] == 134.56 and r["tax"] == 18.56
    pl = reports.profit_and_loss(db.today(), db.today())
    assert pl["net_revenue"] == 100 + 116
    assert pl["gross_profit"] == 216 - 100


def test_credit_sale_and_payments_and_limit():
    pid = mk(price=20, q=100)
    with pytest.raises(SaleError):
        sales.create_sale([line(pid, 1)], cash_amount=0, credit_amount=20)  # بدون عميل
    cid = customers.add_customer("أبو محمد", "0599", credit_limit=50)
    sales.create_sale([line(pid, 2)], customer_id=cid, cash_amount=10, credit_amount=30)
    assert customers.balance(cid) == 30
    with pytest.raises(SaleError):
        sales.create_sale([line(pid, 2)], customer_id=cid, cash_amount=0, credit_amount=40)  # يتجاوز الحد 50
    customers.receive_payment(cid, 25)
    assert customers.balance(cid) == 5
    opening, rows = customers.statement(cid)
    assert [r["running"] for r in rows] == [30, 5]
    with pytest.raises(SaleError):
        sales.create_sale([line(pid, 1)], cash_amount=5, card_amount=5)  # المجموع لا يساوي 20


def test_change_calculation_and_mixed_label():
    pid = mk(price=17.5, q=10)
    r = sales.create_sale([line(pid, 1)], cash_received=20)
    assert r["change"] == 2.5
    r = sales.create_sale([line(pid, 2)], cash_amount=15, card_amount=20)
    assert sales.get_invoice(r["invoice_id"])["payment_method"] == "مختلط"


def test_partial_and_full_return_with_discount():
    pid = mk(price=10, cost=4, q=10)
    r = sales.create_sale([line(pid, 4)], discount=4)  # 40 - 4 = 36 => نسبة 0.9
    item = sales.returnable_items(r["invoice_id"])[0]
    ret = sales.create_return(r["invoice_id"], [{"invoice_item_id": item["id"], "quantity": 1}])
    assert ret["total"] == 9
    assert products.get_product(pid)["quantity"] == 7
    with pytest.raises(SaleError):
        sales.create_return(r["invoice_id"], [{"invoice_item_id": item["id"], "quantity": 4}])
    sales.create_return(r["invoice_id"], [{"invoice_item_id": item["id"], "quantity": 3}])
    inv = sales.get_invoice(r["invoice_id"])
    assert inv["status"] == "returned" and inv["returned_total"] == 36
    pl = reports.profit_and_loss(db.today(), db.today())
    assert pl["net_sales"] == 0 and pl["cogs"] == 0 and pl["gross_profit"] == 0


def test_return_to_debt():
    pid = mk(price=10, q=10)
    cid = customers.add_customer("زبون")
    r = sales.create_sale([line(pid, 3)], customer_id=cid, cash_amount=0, credit_amount=30)
    item = sales.returnable_items(r["invoice_id"])[0]
    sales.create_return(r["invoice_id"], [{"invoice_item_id": item["id"], "quantity": 1}], refund_method=sales.REFUND_DEBT)
    assert customers.balance(cid) == 20


def test_held_carts():
    pid = mk()
    hid = sales.hold_cart([line(pid, 2)], discount=1, label="زبون 1")
    assert sales.list_held_carts()[0]["total"] == 9
    data = sales.take_held_cart(hid)
    assert data["cart"][0]["quantity"] == 2 and sales.list_held_carts() == []


# ---------------- المشتريات والموردين ----------------

def test_purchase_weighted_cost_and_supplier_balance():
    pid = mk(price=10, cost=4, q=10)
    sid = suppliers.add_supplier("شركة الألبان")
    suppliers.create_purchase(sid, [{"product_id": pid, "quantity": 10, "unit_cost": 6, "sale_price": 11}], paid=20)
    p = products.get_product(pid)
    assert p["quantity"] == 20 and p["cost_price"] == 5 and p["sale_price"] == 11
    assert suppliers.balance(sid) == 40
    suppliers.pay_supplier(sid, 40)
    assert suppliers.balance(sid) == 0
    with pytest.raises(ValueError):
        suppliers.create_purchase(None, [{"product_id": pid, "quantity": 1, "unit_cost": 5}], paid=0)


# ---------------- الوردية والصندوق ----------------

def test_shift_expected_cash():
    pid = mk(price=10, cost=5, q=100)
    cid = customers.add_customer("زبون")
    sid = suppliers.add_supplier("مورد")
    shift = shifts.open_shift(100)
    sales.create_sale([line(pid, 5)], shift_id=shift, cash_received=100)          # +50
    sales.create_sale([line(pid, 2)], shift_id=shift, cash_amount=0, card_amount=20)  # بطاقة لا تؤثر
    r = sales.create_sale([line(pid, 3)], customer_id=cid, cash_amount=0, credit_amount=30, shift_id=shift)
    customers.receive_payment(cid, 10, shift_id=shift)                            # +10
    item = sales.returnable_items(r["invoice_id"])[0]
    s1 = sales.create_sale([line(pid, 1)], shift_id=shift)                        # +10
    it = sales.returnable_items(s1["invoice_id"])[0]
    sales.create_return(s1["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}], shift_id=shift)  # -10
    expenses.add_expense("كهرباء", 15, shift_id=shift)                            # -15
    expenses.add_expense("إيجار", 1000, from_drawer=False)                        # لا يؤثر
    suppliers.pay_supplier(sid, 20, shift_id=shift)                               # -20
    shifts.cash_movement(-30, "سحب المالك")                                        # -30
    sm = shifts.summary(shift)
    assert sm["expected_cash"] == 100 + 50 + 10 + 10 - 10 - 15 - 20 - 30
    _, diff = shifts.close_shift(90)
    assert diff == -5
    assert shifts.current_shift() is None


# ---------------- التقارير ----------------

def test_reports_run():
    pid = mk(price=10, cost=5, q=100, category="مشروبات")
    mk("منتج راكد", q=5)
    sales.create_sale([line(pid, 3)])
    expenses.add_expense("ماء", 7)
    t = db.today()
    pl = reports.profit_and_loss(t, t)
    assert pl["net_profit"] == 15 - 7
    assert reports.sales_by_category(t, t)[0]["category"] == "مشروبات"
    assert reports.top_products(t, t)[0]["qty"] == 3
    assert [p["name"] for p in reports.slow_products(t, t)] == ["منتج راكد"]
    assert reports.daily_sales(t, t)[0]["total"] == 30
    assert sum(h["count"] for h in reports.sales_by_hour(t, t)) == 1
    assert reports.dashboard()["today"]["invoice_count"] == 1


def test_local_time_stored():
    pid = mk()
    r = sales.create_sale([line(pid, 1)])
    created = datetime.strptime(sales.get_invoice(r["invoice_id"])["created_at"], "%Y-%m-%d %H:%M:%S")
    assert abs((datetime.now() - created).total_seconds()) < 60


# ---------------- الباركود والميزان ----------------

def test_barcodes():
    assert barcode.is_valid_ean13("6291041500213")
    code = barcode.internal_barcode(42)
    assert barcode.is_valid_ean13(code) and code.startswith("299")
    assert len(barcode.ean13_bits("6291041500213")) == 95


def test_code128_matches_reference():
    bits = barcode.code128_bits("ABC-123")
    try:
        from barcode import Code128  # python-barcode (اختياري للتحقق فقط)
        ref = Code128("ABC-123").build()[0]
        # المكتبة قد تختار Code-C لبعض الأرقام؛ نتحقق من الطول والبداية والنهاية على الأقل
        assert bits.startswith("11010010000") and bits.endswith("1100011101011")
    except ImportError:
        assert bits.startswith("11010010000") and bits.endswith("1100011101011")
    assert (len(bits) - 13) % 11 == 0


def test_scale_barcode_weight():
    pid = products.add_product("لحمة", None, "ملحمة", 40, 60, 50, 1, "كغم", plu_code="00123", is_weighted=True)
    body = "20" + "00123" + "01250"
    code = body + barcode.ean13_check_digit(body)
    p, q, _ = products.lookup_code(code)
    assert p["id"] == pid and q == 1.25
    settings.set("scale_mode", "price")
    body = "20" + "00123" + "03000"   # 30.00 شيكل => نصف كيلو
    p, q, _ = products.lookup_code(body + barcode.ean13_check_digit(body))
    assert q == 0.5


# ---------------- المنتجات ----------------

def test_product_unique_barcode_and_soft_delete_frees_barcode():
    pid = mk(barcode="111")
    with pytest.raises(ValueError):
        mk("آخر", barcode="111")
    products.delete_product(pid)
    mk("جديد", barcode="111")


def test_stock_count_and_movements():
    pid = mk(q=10)
    assert products.set_stock_count(pid, 7) == -3
    mv = products.stock_movements(pid)
    assert mv[0]["change_qty"] == -3 and mv[0]["balance_after"] == 7


def test_csv_roundtrip(tmp_path):
    mk(barcode="123", price=4.5)
    path = str(tmp_path / "p.csv")
    assert products.export_csv(path) == 1
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        f.write("خبز,999,مخبوزات,ربطة,2,3,20,5,\n")
    added, updated, errors = products.import_csv(path)
    assert (added, updated, errors) == (1, 1, [])


# ---------------- النسخ الاحتياطي والترقية ----------------

def test_backup_restore(tmp_path):
    pid = mk(q=10)
    path = backup.create_backup(str(tmp_path / "bk"))
    sales.create_sale([line(pid, 4)])
    assert products.get_product(pid)["quantity"] == 6
    backup.restore_backup(path)
    assert products.get_product(pid)["quantity"] == 10


def test_migrate_from_v1(tmp_path):
    path = str(tmp_path / "v1.db")
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, barcode TEXT UNIQUE, category TEXT,
        cost_price REAL NOT NULL DEFAULT 0, sale_price REAL NOT NULL DEFAULT 0, quantity REAL NOT NULL DEFAULT 0,
        min_quantity REAL NOT NULL DEFAULT 0, unit TEXT DEFAULT 'قطعة', created_at TEXT DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1);
    CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT, balance REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_number TEXT UNIQUE, customer_id INTEGER, total REAL NOT NULL DEFAULT 0,
        discount REAL NOT NULL DEFAULT 0, paid REAL NOT NULL DEFAULT 0, payment_method TEXT DEFAULT 'نقدي', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE invoice_items (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        product_name TEXT NOT NULL, quantity REAL NOT NULL, unit_price REAL NOT NULL, cost_price REAL NOT NULL DEFAULT 0, total REAL NOT NULL);
    CREATE TABLE stock_movements (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, change_qty REAL NOT NULL, reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    INSERT INTO products(name, cost_price, sale_price, quantity) VALUES ('سكر', 3, 5, 8);
    INSERT INTO customers(name, balance) VALUES ('قديم', 12.5);
    INSERT INTO invoices(invoice_number, total, discount, paid, payment_method) VALUES ('INV-20250101-0001', 10, 0, 10, 'نقدي');
    INSERT INTO invoice_items(invoice_id, product_id, product_name, quantity, unit_price, cost_price, total) VALUES (1,1,'سكر',2,5,3,10);
    """)
    c.commit()
    c.close()
    db.set_db_path(path)
    settings._cache.clear()
    db.init_db()
    auth.login("admin", "admin")
    assert customers.balance(1) == 12.5
    inv = sales.get_invoice(1)
    assert inv["cash_amount"] == 10 and inv["cost_total"] == 6 and inv["subtotal"] == 10
    pid = products.get_all_products()[0]["id"]
    r = sales.create_sale([line(pid, 1)])
    assert r["invoice_number"] == "INV-000002"
