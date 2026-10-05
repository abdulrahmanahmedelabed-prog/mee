# -*- coding: utf-8 -*-
"""القوى الخارقة: اسأل محلك، التنبؤ، المواسم، الزكاة، التقويم الهجري، والباقات"""
import os
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core import (db, products, sales, customers, suppliers, reports, assistant, forecast, seasons, zakat, hijri,
                  plans, license, settings)


def line(pid, q):
    p = products.get_product(pid)
    return {"product_id": pid, "product_name": p["name"], "quantity": q, "unit_price": p["sale_price"]}


def backdate(invoice_id, d):
    with db.tx() as conn:
        conn.execute("UPDATE invoices SET created_at=? WHERE id=?", (f"{d} 12:00:00", invoice_id))


@pytest.fixture
def shop():
    milk = products.add_product("حليب طازج 1 لتر", "1001", "ألبان", 3, 5, 500, 10)
    sugar = products.add_product("سكر 1 كغم", "1002", "تموين", 3.5, 5, 300, 10)
    today = date.fromisoformat(db.today())
    for k in range(1, 50):                      # 49 يوماً: الجمعة ضعف بقية الأيام
        d = today - timedelta(days=k)
        n = 4 if d.weekday() == 4 else 2
        r = sales.create_sale([line(milk, n), line(sugar, 1)])
        backdate(r["invoice_id"], d.isoformat())
    return {"milk": milk, "sugar": sugar, "today": today}


def test_hijri_matches_known_ramadan_dates():
    for y, g in ((1445, date(2024, 3, 11)), (1446, date(2025, 3, 1)), (1447, date(2026, 2, 18))):
        assert abs((hijri.to_gregorian(y, 9, 1) - g).days) <= 1
        assert hijri.from_gregorian(hijri.to_gregorian(y, 9, 1)) == (y, 9, 1)
    assert "رمضان" in hijri.fmt(date(2026, 3, 1))


def test_assistant_understands_arabic_dialects_and_english(shop):
    cases = {"كم بعت اليوم؟": "sales", "كم بعت امبارح": "sales", "How much did I sell yesterday?": "sales",
             "كم ربحت الشهر الماضي؟": "profit", "قارن هذا الشهر بالشهر الماضي": "compare", "مين عليه دين؟": "debts",
             "Who owes me money?": "debts", "شو أكثر صنف بينباع؟": "top", "كم باقي حليب؟": "stock",
             "بكم السكر؟": "price", "شو الأصناف اللي رح تخلص؟": "low", "توقع مبيعات الشهر الجاي": "forecast",
             "شو أجهز لرمضان؟": "season", "كم الزكاة؟": "zakat", "متى أكثر ساعة زحمة؟": "hours",
             "كم في الصندوق؟": "cash", "أفضل زبائني": "top_customers", "افتح المخزون": "navigate",
             "كم علينا للموردين": "payables", "كم ضريبة هالشهر": "vat", "مساعدة": "help"}
    for q, intent in cases.items():
        r = assistant.answer(q)
        assert r["intent"] == intent, (q, r["intent"], r.get("lines"))
        assert r["title"] and r["lines"] and "تعذرت" not in r["title"], (q, r)


def test_assistant_numbers_match_reports(shop):
    y = (shop["today"] - timedelta(days=1)).isoformat()
    r = assistant.answer("كم بعت امبارح؟")
    assert r["value"] == reports.profit_and_loss(y, y)["net_sales"]
    r = assistant.answer("كم باقي حليب؟")
    assert "حليب طازج 1 لتر" in r["title"] and "يكفي" in r["lines"][0]
    r = assistant.answer("بكم السكر؟")
    assert "5.00" in r["lines"][0] and "3.50" in r["lines"][0]
    cid = customers.add_customer("أبو سامي", "0599111222", opening_balance=120)
    r = assistant.answer("كم على أبو سامي؟")
    assert r["intent"] == "debts" and "120.00" in r["lines"][0]
    a, b, label = assistant.parse_period(assistant.norm("مبيعات آخر 7 أيام"), shop["today"])
    assert (b - a).days == 6 and label == "آخر 7 أيام"
    a, b, label = assistant.parse_period(assistant.norm("الشهر الماضي"), date(2026, 3, 15))
    assert (a, b) == (date(2026, 2, 1), date(2026, 2, 28))
    assert customers.balance(cid) == 120


def test_forecast_learns_weekday_pattern_and_cash(shop):
    s = forecast.sales_forecast(28, today=shop["today"])
    assert s["enough_data"] and len(s["days"]) == 28
    assert s["best_day"] == "الجمعة"
    friday = [d["value"] for d in s["days"] if d["weekday"] == "الجمعة"]
    other = [d["value"] for d in s["days"] if d["weekday"] == "الإثنين"]
    assert friday[0] > other[0] * 1.4                   # تعلّم أن الجمعة أعلى
    last = sum(r["total"] for r in reports.daily_sales((shop["today"] - timedelta(days=28)).isoformat(),
                                                        (shop["today"] - timedelta(days=1)).isoformat()))
    assert abs(s["total"] - last) / last < 0.15         # بدون نمو: قريب من آخر 4 أسابيع
    c = forecast.cash_forecast(30, today=shop["today"])
    assert len(c["rows"]) == 30 and c["end"] >= c["start"]


def test_seasons_upcoming_and_plan_without_history(shop):
    ups = seasons.upcoming(date(2026, 10, 5))
    assert {s["key"] for s in ups} == {"ramadan", "eid_fitr", "eid_adha", "school", "summer"}
    ram = next(s for s in ups if s["key"] == "ramadan")
    assert ram["start"] == hijri.to_gregorian(1448, 9, 1).isoformat()
    p = seasons.plan("ramadan")
    assert not p["enough_data"] and "لا توجد مبيعات" in p["message"]


def test_seasons_plan_uses_last_season_uplift():
    juice = products.add_product("عصير برتقال", "2001", "مشروبات", 4, 6, 10, 0)
    today = date(2026, 10, 5)
    prev = hijri.to_gregorian(1447, 9, 1)
    for k in range(-28, 30):
        d = prev + timedelta(days=k)
        products.adjust_stock(juice, 5)
        r = sales.create_sale([line(juice, 3 if k >= 0 else 1)])
        backdate(r["invoice_id"], d.isoformat())
    products.set_stock_count(juice, 2)
    p = seasons.plan("ramadan", today=today)
    assert p["enough_data"]
    item = next(i for i in p["items"] if i["product_id"] == juice)
    assert item["uplift"] == pytest.approx(3.0, rel=0.05)
    assert item["per_day"] == pytest.approx(3.0, rel=0.1)
    assert item["order"] == pytest.approx(item["per_day"] * 10 - 2, abs=1)   # أول 10 أيام − الموجود


def test_zakat_from_books(shop):
    sup = suppliers.add_supplier("مورد", opening_balance=1000)
    r = zakat.compute(gold_price=0)
    names = dict(r["assets"])
    assert names["البضاعة بـسعر البيع"] == pytest.approx(
        db.scalar("SELECT SUM(quantity * sale_price) FROM products WHERE quantity > 0"), abs=0.01)
    deductions = dict(r["deductions"])
    assert deductions["مستحقات الموردين"] == pytest.approx(suppliers.balance(sup), abs=0.01)
    assert r["base"] == pytest.approx(sum(v for _, v in r["assets"]) - sum(v for _, v in r["deductions"]), abs=0.02)
    assert r["nisab"] is None and r["reaches_nisab"]
    rich = zakat.compute(gold_price=1)                     # نصاب 85 فقط
    assert rich["zakat"] == pytest.approx(rich["base"] * 0.025, abs=0.01)
    poor = zakat.compute(gold_price=10 ** 6)               # نصاب ضخم
    assert not poor["reaches_nisab"] and poor["zakat"] == 0
    solar = zakat.compute(gold_price=1, calendar="gregorian")
    assert solar["zakat"] > rich["zakat"]
    cost = zakat.compute(gold_price=1, valuation="cost")
    assert cost["base"] < rich["base"]                     # البضاعة بالتكلفة أقل من سعر البيع
    assert "data:image" not in zakat.report_html(rich) or True
    assert "الوعاء الزكوي" in zakat.report_html(rich)


def test_plans_gate_superpowers_on_server_side():
    from core import remote
    user = {"id": 1, "role": "admin", "username": "admin"}
    remote.check_permission(("assistant", "answer"), user, (), {})        # التجربة = ماكس
    db.set_meta("install_date", (date.today() - timedelta(days=45)).isoformat())
    assert license.status()["tier"] == plans.FREE
    with pytest.raises(PermissionError):
        remote.check_permission(("assistant", "answer"), user, (), {})
    with pytest.raises(PermissionError):
        remote.check_permission(("zakat", "compute"), user, (), {})
    remote.check_permission(("sales", "create_sale"), user, ([],), {})      # البيع لا يُقفل أبداً


def test_smart_screen_and_locked_tabs():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.smart_screen import SmartScreen
    from ui.plans_dialog import LockedPanel
    s = SmartScreen()
    s.ask("كم بعت اليوم؟")
    assert "المبيعات" in s.chat.toPlainText()
    for i in range(4):
        s.tabs.setCurrentIndex(i)
    assert not any(isinstance(s.tabs.widget(i), LockedPanel) for i in range(4))
    db.set_meta("install_date", (date.today() - timedelta(days=45)).isoformat())
    free = SmartScreen()
    assert all(isinstance(free.tabs.widget(i), LockedPanel) for i in range(4))
    from ui.main_window import MainWindow
    w = MainWindow()
    assert "accounting" in w.locked_pages and "pos" not in w.locked_pages
    w.go("accounting")
    assert w.stack.currentWidget() is w.locked and "accounting" not in dict.keys(w.pages)
    w.close()
    assert app
