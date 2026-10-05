# -*- coding: utf-8 -*-
"""تقسيط ديون الزبائن"""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import db, customers, installments, insights  # noqa: E402


def test_installment_plan_tracks_paid_overdue_and_finishes():
    c = customers.add_customer("أبو سامر", "0599222", opening_balance=1000)
    first = (date.today() - timedelta(days=40)).isoformat()   # القسط الأول والثاني فات موعدهما
    pid = installments.create_plan(c, 4, first, 30)
    with pytest.raises(ValueError):
        installments.create_plan(c, 2, first)                 # خطة واحدة قائمة لكل عميل
    p = installments.active_plan(c)
    s = installments.summary(p)
    assert [r["amount"] for r in s["rows"]] == [250, 250, 250, 250]
    assert [r["status"] for r in s["rows"]][:2] == ["overdue", "overdue"] and s["overdue_amount"] == 500
    assert any(x["key"] == "installments" for x in insights.insights())
    assert "قسط مستحق" in installments.reminder_message(c)

    customers.receive_payment(c, 300, "نقدي")                 # يُطفئ القسط الأول وجزءاً من الثاني
    s = installments.summary(p)
    assert [r["paid"] for r in s["rows"]] == [250, 50, 0, 0] and s["remaining"] == 700
    assert [o["amount"] for o in installments.overdue()] == [200]

    customers.receive_payment(c, 700, "نقدي")
    installments.refresh_status()
    assert installments.active_plan(c) is None
    assert db.scalar("SELECT status FROM installment_plans WHERE id=?", (pid,)) == "done"
    assert "جدول أقساط" in installments.schedule_html(pid)


def test_plan_cannot_exceed_debt():
    c = customers.add_customer("زبون", "0599", opening_balance=100)
    with pytest.raises(ValueError):
        installments.create_plan(c, 3, date.today().isoformat(), 30, total=150)
    pid = installments.create_plan(c, 3, date.today().isoformat(), 7, total=90)
    rows = installments.schedule(installments.active_plan(c))
    assert [r["amount"] for r in rows] == [30, 30, 30] and rows[0]["status"] == "due"
    assert rows[1]["due"] == (date.today() + timedelta(days=7)).isoformat()
    installments.cancel_plan(pid)
    assert installments.active_plan(c) is None
