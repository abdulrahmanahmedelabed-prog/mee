# -*- coding: utf-8 -*-
"""الرواتب والسلف: القيود، الأرباح، الوردية"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import db, payroll, shifts, reports, ledger, financial_audit  # noqa: E402


def bal(code):
    row = ledger._balances(None, db.today()).get(code, [0, 0, 0])
    return round(row[0] + row[1] - row[2], 2)


def test_advances_are_recovered_from_salary_and_books_balance():
    sid = shifts.open_shift(1000)
    e = payroll.add_employee("سامي", 2400, "كاشير")
    payroll.give_advance(e, 300, payroll.PAY_DRAWER, shift_id=sid)
    payroll.give_advance(e, 200, payroll.PAY_BANK)
    assert payroll.advances_balance(e) == 500 and bal(ledger.EMP_ADVANCES) == 500
    r = payroll.pay_salary(e, "2026-09", bonus=100, deductions=50, method=payroll.PAY_DRAWER, shift_id=sid)
    assert (r["gross"], r["advances"], r["net"]) == (2450, 500, 1950)
    assert payroll.advances_balance(e) == 0 and bal(ledger.EMP_ADVANCES) == 0
    with pytest.raises(ValueError):
        payroll.pay_salary(e, "2026-09")                       # لا يُصرف نفس الشهر مرتين
    # الوردية: خرج من الدرج 300 سلفة + 1950 صافي الراتب
    d = shifts.summary(sid)
    assert d["payroll_cash"] == 2250 and d["expected_cash"] == 1000 - 2250
    # الأرباح: الراتب المستحق مصروف (السلفة ليست مصروفاً)
    t = db.today()
    p = reports.profit_and_loss(t, t)
    assert p["payroll"] == 2450 and p["expenses"] == 2450
    assert ledger.income_statement(t, t)["net_income"] == p["net_profit"]
    assert ledger.trial_balance(None, t)["totals"]["balanced"] and ledger.balance_sheet()["balanced"]
    assert round(sum(x["net_profit"] for x in reports.period_summary(t, t, "month")), 2) == p["net_profit"]
    assert "قسيمة راتب" in payroll.payslip_html(r["id"])
    assert financial_audit.run(t, t)["counts"]["critical"] == 0


def test_advance_larger_than_salary_carries_over():
    e = payroll.add_employee("أحمد", 1000)
    payroll.give_advance(e, 1500, payroll.PAY_BANK)
    r = payroll.pay_salary(e, "2026-08", method=payroll.PAY_BANK)
    assert (r["advances"], r["net"]) == (1000, 0) and payroll.advances_balance(e) == 500
    r2 = payroll.pay_salary(e, "2026-09", method=payroll.PAY_BANK)
    assert (r2["advances"], r2["net"]) == (500, 500)
    with pytest.raises(ValueError):
        payroll.pay_salary(e, "2026-10", advances=50, method=payroll.PAY_BANK)   # لا سلف متبقية
