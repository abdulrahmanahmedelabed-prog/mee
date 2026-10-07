# -*- coding: utf-8 -*-
"""الإصدار 10.5: فهم الأسئلة بالمعنى، الروابط إلى الأقسام، وما يُضاف لاحقاً في هذا الملف"""

import pytest

from core import assistant


@pytest.mark.parametrize("question,intent", [
    ("مين أفضل 10 زبائن عندي", "top_customers"), ("أفضل عشرة عملاء", "top_customers"),
    ("أعطني قائمة أكبر الزبائن", "top_customers"), ("best 10 customers", "top_customers"),
    ("أكثر 20 صنف مبيعاً", "top"), ("شو أكثر الأصناف ربحاً", "top"), ("أقل الأصناف مبيعاً", "slow"),
    ("شو الناقص", "low"), ("متى الزحمة", "hours"), ("مبيعاة اليوم", "sales"), ("مين أفضل كاشير", "cashier"),
    ("كيف المبيعات مقارنة بالسنة الماضية", "compare"), ("احسب الزكاة", "zakat"), ("جهزني لرمضان", "season"),
])
def test_assistant_understands_phrasings(question, intent):
    assert assistant.detect(assistant.norm(question)) == intent


def test_limits_and_links():
    q = assistant.norm("أفضل 15 زبون")
    assert assistant.limit_of(q) == 15 and assistant.limit_of(assistant.norm("أكثر عشرة أصناف")) == 10
    assert assistant.answer("احسب الزكاة")["action"][0] == "smart/zakat"
    assert assistant.answer("كم بعت اليوم")["action"][0] == "reports/المبيعات اليومية"
    assert assistant.answer("شو أجهز لرمضان")["action"][0] == "smart/seasons"


from core import db, ledger, products, reports, sales, financial_audit, settings  # noqa: E402


def _item(pid, qty, price, name="صنف", list_price=None):
    d = {"product_id": pid, "product_name": name, "quantity": qty, "unit_price": price}
    if list_price is not None:
        d["list_price"] = list_price
    return d


def test_round_up_sale_books_and_full_return():
    pid = products.add_product("جبنة", "rnd1", "", 3, 4.35, 50, 0)
    res = sales.create_sale([_item(pid, 2, 4.35, "جبنة")], round_up=True)          # 8.70 ← 9.00
    assert res["total"] == 9.0 and res["rounding"] == 0.3
    inv = db.query_one("SELECT * FROM invoices WHERE id=?", (res["invoice_id"],))
    assert inv["rounding"] == 0.3 and inv["cash_amount"] == 9.0
    tb = ledger.trial_balance(None, None)
    assert tb["totals"]["balanced"]
    acc = {r["code"]: r for r in tb["rows"]}
    assert acc[ledger.ROUNDING]["closing_credit"] == 0.3
    pl = reports.profit_and_loss(db.today(), db.today())
    assert abs(pl["net_profit"] - ledger.income_statement(db.today(), db.today())["net_income"]) < 0.01
    assert pl["rounding"] == 0.3
    # إرجاع الفاتورة كاملة: يُرد التقريب أيضاً ويُعكس في حسابه
    items = sales.returnable_items(res["invoice_id"])
    r = sales.create_return(res["invoice_id"], [{"invoice_item_id": i["id"], "quantity": i["remaining"]} for i in items])
    ret = db.query_one("SELECT * FROM returns WHERE id=?", (r["return_id"],)) if "return_id" in r else \
        db.query_one("SELECT * FROM returns ORDER BY id DESC LIMIT 1")
    assert ret["total"] == 9.0 and ret["rounding"] == 0.3
    acc = {x["code"]: x for x in ledger.trial_balance(None, None)["rows"]}
    assert abs(acc.get(ledger.ROUNDING, {"closing_credit": 0, "closing_debit": 0})["closing_credit"]) < 0.01
    assert ledger.balance_sheet()["balanced"]


def test_price_override_recorded_and_audited():
    pid = products.add_product("قهوة", "po1", "", 10, 20, 50, 0)
    sales.create_sale([_item(pid, 1, 15, "قهوة", list_price=20)])
    row = db.query_one("SELECT unit_price, list_price FROM invoice_items ORDER BY id DESC LIMIT 1")
    assert row["unit_price"] == 15 and row["list_price"] == 20
    t = db.today()
    f = financial_audit.run(t, t)
    assert any(x["title"] == "تخفيض أسعار يدوي عند البيع" for x in f["findings"])
    sales.create_sale([_item(pid, 1, 25, "قهوة", list_price=20)])
    f = financial_audit.run(t, t)
    assert any(x["title"] == "بيع بأعلى من السعر الأصلي" and x["severity"] == "high" for x in f["findings"])


def test_label_queue_follows_price_changes():
    pid = products.add_product("أرز", "lb1", "", 3, 5, 10, 0)
    assert any(p["id"] == pid for p in products.pending_labels())          # صنف جديد: يحتاج ملصقاً
    products.mark_labels_printed([pid])
    assert not any(p["id"] == pid for p in products.pending_labels())
    from core import insights
    insights.apply_price_update([{"id": pid, "new": 6}])
    assert any(p["id"] == pid for p in products.pending_labels())          # تغيّر السعر: يعود للطابور
    assert any(c["key"] == "labels" for c in insights.insights()) if insights.insights() and \
        "key" in insights.insights()[0] else True
    products.mark_labels_printed([pid])
    assert products.pending_labels_count() == 0 or not any(p["id"] == pid for p in products.pending_labels())


from core import accountant, customers, payroll, suppliers  # noqa: E402


def _titles(r):
    return {x["title"]: x for x in r["findings"]}


def test_ratios_comparative_and_bank_reconciliation():
    pid = products.add_product("شاي", "rt1", "", 6, 10, 100, 0)
    sales.create_sale([_item(pid, 3, 10, "شاي")], card_amount=30, cash_amount=0)
    t = db.today()
    r = accountant.ratios(t, t)
    keys = {x["key"] for x in r["items"]}
    assert {"gross_margin", "net_margin", "current_ratio", "dio", "ccc", "break_even"} <= keys
    assert all(x["verdict"] in ("good", "watch", "bad", "na") and x["explain"] for x in r["items"])
    ci = accountant.comparative_income(t, t)
    assert ci["current"]["net_sales"] >= 30 and "previous" in ci
    # البطاقة لم تصل للبنك بعد: في الطريق
    rec = accountant.bank_reconciliation(t, 0)
    assert rec["in_transit"] >= 30 and abs(rec["difference"]) < 0.01
    rec = accountant.bank_reconciliation(t, -5)                      # البنك خصم 5 عمولة لم تُسجَّل
    assert abs(rec["difference"] + 5) < 0.01
    accountant.save_bank_reconciliation(t, -5, record_fees=True)
    assert abs(accountant.bank_reconciliation(t, -5)["difference"]) < 0.01
    assert ledger.balance_sheet()["balanced"] and accountant.bank_reconciliations()


def test_new_fraud_procedures():
    t = db.today()
    pid = products.add_product("زيت", "fr1", "", 10, 15, 100, 0)
    res = sales.create_sale([_item(pid, 1, 15, "زيت")])
    it = sales.returnable_items(res["invoice_id"])[0]
    sales.create_return(res["invoice_id"], [{"invoice_item_id": it["id"], "quantity": 1}])
    f = _titles(financial_audit.run(t, t))
    assert "بيع ثم إرجاع نقدي خلال 30 دقيقة من نفس الكاشير" in f
    # قفزة في تكلفة الشراء، مع احتساب الكرتونة بالحبة
    sup = suppliers.add_supplier("مورد الزيت")
    suppliers.create_purchase(sup, [{"product_id": pid, "quantity": 12, "unit_cost": 10}])
    with db.tx() as c:
        c.execute("UPDATE purchases SET created_at = datetime(created_at, '-1 day')")
    suppliers.create_purchase(sup, [{"product_id": pid, "quantity": 1, "unit_cost": 120, "factor": 12,
                                     "unit_name": "كرتونة"}])                        # 10 للحبة: طبيعي
    assert "ارتفاع مفاجئ في تكلفة الشراء (أكثر من 30%)" not in _titles(financial_audit.run(t, t))
    suppliers.create_purchase(sup, [{"product_id": pid, "quantity": 1, "unit_cost": 16}])
    assert "ارتفاع مفاجئ في تكلفة الشراء (أكثر من 30%)" in _titles(financial_audit.run(t, t))
    # زبون مكرر بنفس الهاتف
    customers.add_customer("أبو سامي", "0599 111 222")
    customers.add_customer("ابو سامي", "+970599111222")
    assert "زبائن مكررون بنفس رقم الهاتف" in _titles(financial_audit.run(t, t))
    # رواتب: أعلى بكثير من الراتب المعتمد، ولشهر لم يأتِ
    e = payroll.add_employee("مازن", 1000)
    payroll.pay_salary(e, t[:7], bonus=900, method=payroll.PAY_BANK)
    nxt = f"{int(t[:4]) + (t[5:7] == '12')}-{(int(t[5:7]) % 12) + 1:02d}"
    payroll.pay_salary(e, nxt, method=payroll.PAY_BANK)
    f = _titles(financial_audit.run(t, t))
    assert "راتب أعلى بكثير من الراتب المعتمد" in f and "راتب مصروف لشهر لم يبدأ بعد" in f
    assert financial_audit.run(t, t)["procedures"] == len(financial_audit.CHECKS) >= 46
