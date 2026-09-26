# -*- coding: utf-8 -*-
"""
بيانات تجريبية لتجربة البرنامج (منتجات سوبرماركت، عملاء، موردون، مبيعات 30 يوماً).
الاستخدام:  python tools/demo_data.py  [مجلد البيانات]
لا يعمل إذا كانت قاعدة البيانات تحتوي فواتير حقيقية.
"""

import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if len(sys.argv) > 1:
    os.environ["SHOP_DATA_DIR"] = sys.argv[1]

from core import (db, auth, products, customers, suppliers, sales, expenses, shifts, settings, context,  # noqa: E402
                  promotions, cheques, ledger)

PRODUCTS = [
    # الاسم، الفئة، الوحدة، التكلفة، البيع، الكمية، الحد، باركود، مفضلة
    ("حليب طازج 1 لتر", "ألبان", "قطعة", 4.2, 5.5, 60, 15, "7290000001011", False),
    ("لبنة 500 غم", "ألبان", "علبة", 9, 12, 30, 8, "7290000001028", False),
    ("جبنة بيضاء 250 غم", "ألبان", "علبة", 8, 11, 25, 6, "7290000001035", False),
    ("لبن رائب 1 كغم", "ألبان", "علبة", 6, 8, 3, 6, "7290000001042", False),
    ("خبز عربي", "مخبوزات", "ربطة", 3, 4, 40, 10, None, True),
    ("كعك بالسمسم", "مخبوزات", "قطعة", 1.5, 2.5, 50, 10, None, True),
    ("أرز بسمتي 5 كغم", "مواد تموينية", "كيس", 32, 42, 20, 5, "6281007031113", False),
    ("سكر 1 كغم", "مواد تموينية", "كيس", 3.8, 5, 45, 10, "6281007031120", False),
    ("طحين 5 كغم", "مواد تموينية", "كيس", 17, 22, 14, 4, "6281007031137", False),
    ("زيت زيتون 1 لتر", "مواد تموينية", "قطعة", 28, 38, 18, 5, "6281007031144", False),
    ("زيت ذرة 1.8 لتر", "مواد تموينية", "قطعة", 14, 19, 22, 6, "6281007031151", False),
    ("عدس أحمر 1 كغم", "مواد تموينية", "كيس", 6, 8.5, 2, 5, "6281007031168", False),
    ("شاي 100 كيس", "مشروبات ساخنة", "علبة", 11, 15, 20, 5, "6281007031175", False),
    ("قهوة عربية 200 غم", "مشروبات ساخنة", "علبة", 14, 20, 16, 5, "6281007031182", False),
    ("نسكافيه 3×1 (علبة 30)", "مشروبات ساخنة", "علبة", 25, 33, 12, 4, "6281007031199", False),
    ("كولا 1.5 لتر", "مشروبات باردة", "قطعة", 5, 7, 48, 12, "5449000000439", False),
    ("مياه معدنية 1.5 لتر", "مشروبات باردة", "قطعة", 1.5, 2.5, 90, 24, "5449000000446", False),
    ("عصير برتقال 1 لتر", "مشروبات باردة", "قطعة", 5.5, 8, 24, 6, "5449000000453", False),
    ("بسكويت شاي", "حلويات وسناكات", "قطعة", 2, 3, 70, 15, "6223000000011", False),
    ("شيبس كبير", "حلويات وسناكات", "قطعة", 3.5, 5, 40, 10, "6223000000028", False),
    ("شوكولاتة بار", "حلويات وسناكات", "قطعة", 2.2, 3.5, 80, 20, "6223000000035", False),
    ("مسحوق غسيل 3 كغم", "منظفات", "قطعة", 24, 32, 10, 3, "8690000000017", False),
    ("سائل جلي 1 لتر", "منظفات", "قطعة", 5, 7.5, 25, 6, "8690000000024", False),
    ("محارم ورقية 10 رول", "منظفات", "قطعة", 15, 20, 15, 4, "8690000000031", False),
    ("بندورة", "خضار وفواكه", "كغم", 3, 5, 35, 8, None, True),
    ("خيار", "خضار وفواكه", "كغم", 2.5, 4, 30, 8, None, True),
    ("بطاطا", "خضار وفواكه", "كغم", 2, 3.5, 50, 10, None, True),
    ("موز", "خضار وفواكه", "كغم", 5, 8, 20, 5, None, True),
    ("لحمة عجل", "ملحمة", "كغم", 55, 75, 25, 5, None, False),
    ("دجاج كامل", "ملحمة", "كغم", 13, 18, 30, 8, None, False),
]

CUSTOMERS = [("أبو أحمد", "0599123456", 500), ("أم محمد", "0598765432", 300), ("محمود السائق", "0569112233", 0),
             ("أبو خليل", "0597001122", 1000), ("سارة", "0592334455", 200)]


def main():
    db.init_db()
    if db.scalar("SELECT COUNT(*) FROM invoices"):
        print("قاعدة البيانات تحتوي فواتير. لن تُضاف بيانات تجريبية.")
        return
    auth.set_current_user(auth.authenticate("admin", "admin") or dict(db.query_one("SELECT * FROM users LIMIT 1")))
    settings.set_many({"shop_name": "سوبرماركت النور", "shop_address": "الخليل - شارع السلام",
                       "shop_phone": "02-2220000", "loyalty_enabled": "1"})
    db.set_meta("setup_done", "1")
    random.seed(7)
    pids = []
    for name, cat, unit, cost, price, q, mn, bc, fav in PRODUCTS:
        weighted = unit == "كغم" and not fav
        plu = str(100 + len(pids)) if weighted else None
        pids.append(products.add_product(name, bc, cat, cost, price, q * 25, mn, unit, plu_code=plu,
                                         is_weighted=weighted or fav and unit == "كغم", is_favorite=fav))
    cids = [customers.add_customer(n, p, credit_limit=l) for n, p, l in CUSTOMERS]
    s1 = suppliers.add_supplier("شركة الجنيدي للألبان", "02-2221111")
    s2 = suppliers.add_supplier("مخابز الأمل", "02-2223333")
    suppliers.add_supplier("موزع المواد التموينية", "059-4445556", opening_balance=850)
    auth.create_user("cashier", "أحمد الكاشير", "1234", "cashier")

    # 30 يوماً من المبيعات
    start = datetime.now() - timedelta(days=29)
    for day in range(30):
        d = start + timedelta(days=day)
        with db.tx() as conn:
            conn.execute("INSERT INTO shifts(user_id, opened_at, opening_cash, status, terminal) VALUES (1, ?, 200, 'open', ?)",
                         (d.replace(hour=7, minute=30).strftime("%Y-%m-%d %H:%M:%S"), context.terminal()))
        sid = shifts.current_shift_id()
        for _ in range(random.randint(25, 55)):
            cart = []
            for pid in random.sample(pids, random.randint(1, 6)):
                p = products.get_product(pid)
                qn = round(random.uniform(0.5, 2.5), 3) if p["unit"] == "كغم" else random.randint(1, 3)
                if p["quantity"] >= qn:
                    cart.append({"product_id": pid, "product_name": p["name"], "quantity": qn, "unit_price": p["sale_price"]})
            if not cart:
                continue
            t = sales.compute_totals(cart)["total"]
            if random.random() < 0.12:
                cid = random.choice(cids)
                try:
                    r = sales.create_sale(cart, customer_id=cid, cash_amount=0, credit_amount=t, shift_id=sid)
                except Exception:
                    continue
            elif random.random() < 0.15:
                r = sales.create_sale(cart, cash_amount=0, card_amount=t, shift_id=sid)
            else:
                r = sales.create_sale(cart, shift_id=sid, cash_received=t + random.choice([0, 0, 1, 5, 10]))
            ts = d.replace(hour=random.choice([8, 9, 10, 11, 12, 13, 17, 18, 19, 20, 21]), minute=random.randint(0, 59))
            with db.tx() as conn:
                conn.execute("UPDATE invoices SET created_at=? WHERE id=?", (ts.strftime("%Y-%m-%d %H:%M:%S"), r["invoice_id"]))
                conn.execute("UPDATE customer_transactions SET created_at=? WHERE invoice_id=?",
                             (ts.strftime("%Y-%m-%d %H:%M:%S"), r["invoice_id"]))
        if day % 3 == 0:
            expenses.add_expense(random.choice(["كهرباء", "مواصلات", "ضيافة", "تنظيف"]), random.randint(20, 150),
                                 shift_id=sid, expense_date=d.strftime("%Y-%m-%d"))
        if day % 7 == 0:
            for cid in cids[:3]:
                bal = customers.balance(cid)
                if bal > 20:
                    customers.receive_payment(cid, round(bal * 0.6), shift_id=sid)
            suppliers.create_purchase(s1, [{"product_id": pids[0], "quantity": 60, "unit_cost": 4.3},
                                           {"product_id": pids[1], "quantity": 20, "unit_cost": 9}], paid=300, shift_id=sid)
        if day < 29:
            summary = shifts.summary(sid)
            shifts.close_shift(summary["expected_cash"] + random.choice([0, 0, 0, -5, 2]))
            with db.tx() as conn:
                conn.execute("UPDATE shifts SET closed_at=? WHERE id=?",
                             (d.replace(hour=22).strftime("%Y-%m-%d %H:%M:%S"), sid))
    suppliers.create_purchase(s2, [{"product_id": pids[4], "quantity": 100, "unit_cost": 3}], paid=0)

    # وحدات متعددة: كرتونة/شرنك بباركود خاص
    products.set_units(pids[15], [{"name": "كرتونة", "factor": 6, "barcode": "5449000000996", "sale_price": 39}])
    products.set_units(pids[16], [{"name": "شرنك", "factor": 6, "barcode": "5449000000989", "sale_price": 13}])
    products.set_units(pids[20], [{"name": "علبة", "factor": 24, "barcode": "6223000000998", "sale_price": 75}])

    # بضاعة بتواريخ صلاحية (بعضها منتهٍ وبعضها قريب)
    today = datetime.now().date()
    exp = lambda days: (today + timedelta(days=days)).isoformat()
    suppliers.create_purchase(s1, [
        {"product_id": pids[0], "quantity": 2, "unit_cost": 50, "factor": 12, "unit_name": "كرتونة", "expiry_date": exp(4)},
        {"product_id": pids[1], "quantity": 10, "unit_cost": 9, "expiry_date": exp(-3)},
        {"product_id": pids[2], "quantity": 12, "unit_cost": 8, "expiry_date": exp(12)},
        {"product_id": pids[3], "quantity": 20, "unit_cost": 6, "expiry_date": exp(25)},
    ], paid=0)
    suppliers.create_purchase(None, [{"product_id": pids[17], "quantity": 24, "unit_cost": 5.5, "expiry_date": exp(90)}],
                              paid=132)
    expenses.add_expense("إيجار", 2500, "إيجار الشهر", from_drawer=False, expense_date=start.strftime("%Y-%m-%d"))
    expenses.add_expense("رواتب", 3000, "راتب العامل", from_drawer=False, expense_date=start.strftime("%Y-%m-%d"))

    # النسخة 4: رأس مال وبنك، عروض، شيكات، مرتجع لمورد
    ledger.add_manual_entry(start.strftime("%Y-%m-%d"), "رأس مال المحل عند بدء استخدام البرنامج",
                            [{"account": ledger.BANK, "debit": 20000}, {"account": ledger.CAPITAL, "credit": 20000}])
    promotions.add_promotion("اشترِ 2 واحصل على 1 — بسكويت شاي", "buy_get", product_id=pids[18], buy_qty=2, get_qty=1)
    promotions.add_promotion("3 مياه بـ 6 شيكل", "bundle", product_id=pids[16], bundle_qty=3, bundle_price=6)
    promotions.add_promotion("خصم 10% على المنظفات", "percent", category="منظفات", percent=10,
                             end_date=(today + timedelta(days=10)).isoformat())
    cheques.receive_cheque(cids[3], 400, exp(5), "100245", "بنك فلسطين")
    cheques.receive_cheque(cids[0], 150, exp(20), "558812", "بنك القدس")
    s3 = db.scalar("SELECT id FROM suppliers WHERE name LIKE 'موزع%'")
    cheques.issue_cheque(s3, 600, exp(3), "000731", "البنك العربي")
    suppliers.create_purchase_return(s1, [{"product_id": pids[1], "quantity": 4}], "منتهي الصلاحية")
    # النسخة 5: أسعار جملة وعميل جملة
    for i in (6, 7, 8, 9, 10, 15, 16):
        p = products.get_product(pids[i])
        products.update_product(p["id"], p["name"], p["barcode"], p["category"], p["cost_price"], p["sale_price"],
                                p["min_quantity"], p["unit"], p["plu_code"], p["is_weighted"], p["is_favorite"],
                                wholesale_price=round(p["cost_price"] * 1.12, 1))
    customers.add_customer("بقالة الحي (جملة)", "0599887766", credit_limit=3000, price_level="wholesale")
    for cid in cids[:2]:
        sales.create_sale([{"product_id": pids[9], "product_name": "زيت زيتون", "quantity": 3, "unit_price": 38}],
                          customer_id=cid)
    print("تمت إضافة البيانات التجريبية. الدخول: admin / admin  أو  cashier / 1234")


if __name__ == "__main__":
    main()
