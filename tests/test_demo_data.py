# -*- coding: utf-8 -*-
"""البيانات التدريبية متعددة السنوات: الدفاتر متوازنة، والدفاتر الفرعية تطابق الأستاذ، والتقارير الدورية تطابق بعضها"""
from datetime import date

from core import db, ledger, reports, products, shifts, suppliers, wallets


def test_multi_year_demo_is_consistent(monkeypatch):
    monkeypatch.setenv("SHOP_DEMO_DAYS", "400")        # أكثر من سنة: يغطي رمضان والصيف وبداية سنة جديدة
    from tools import demo_data
    demo_data.main()
    first = db.scalar("SELECT MIN(date(created_at)) FROM invoices")
    last = db.today()
    assert db.scalar("SELECT COUNT(*) FROM invoices") > 20000
    assert ledger.trial_balance(None, last)["totals"]["balanced"] and ledger.balance_sheet()["balanced"]
    bal = ledger._balances(None, last)
    b = lambda code: round(sum(bal.get(code, [0, 0, 0])[i] * s for i, s in ((0, 1), (1, 1), (2, -1))), 2)
    assert b(ledger.RECEIVABLES) == round(db.scalar("SELECT SUM(amount) FROM customer_transactions"), 2)
    assert -b(ledger.PAYABLES) == round(suppliers.total_dues(), 2)
    assert b(ledger.CASH) == round(sum(shifts.summary(s["id"])["expected_cash"] for s in shifts.open_shifts()), 2)
    assert abs(b(ledger.INVENTORY) - products.inventory_value()["cost_value"]) < 50      # فروق تقريب متوسط التكلفة
    assert db.scalar("SELECT COUNT(*) FROM products WHERE quantity < -0.001") == 0
    pl = reports.profit_and_loss(first, last)
    assert pl["net_profit"] == ledger.income_statement(first, last)["net_income"]
    for g in ("day", "week", "month", "year"):
        assert round(sum(r["net_profit"] for r in reports.period_summary(first, last, g)), 2) == pl["net_profit"]
    months = reports.period_summary(first, last, "month")
    assert len(months) >= 13 and all(m["net_sales"] > 0 for m in months)
    # الدفع الإلكتروني يزداد مع الوقت، وكل الطرق ظاهرة في تقرير المطابقة
    assert months[-1]["wallet"] / months[-1]["net_sales"] > months[0]["wallet"] / months[0]["net_sales"]
    assert {r["name"] for r in wallets.summary(first, last)} == {"PalPay", "Jawwal Pay", "تحويل بنكي فوري"}
    assert db.scalar("SELECT COUNT(*) FROM cheques WHERE status='bounced'") <= 1
    assert date.fromisoformat(first) < date.today()
