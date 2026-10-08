# -*- coding: utf-8 -*-
"""الآلة الحاسبة: العبارات في خانات المبالغ، النسبة المئوية، حاسبة التسعير، الإدراج في الخانة، والمساعد"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from core import calc, settings


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("expr,value", [
    ("12*3.5+4", 46), ("12*3+4", 40), ("100+16%", 116), ("250-10%", 225), ("80*5%", 4), ("16%", 0.16),
    ("(2+3)*4", 20), ("-5+2", -3), ("١٢×٣", 36), ("1,250/5", 250), ("10÷4", 2.5), ("١٢٫٥+٠٫٥", 13), ("2*(3+4)-1", 13),
])
def test_expressions(expr, value):
    assert calc.evaluate(expr) == pytest.approx(value)
    assert calc.is_expression(expr)


@pytest.mark.parametrize("bad", ["12*", "(2+3", "abc", "1/0", "2**3", "__import__('os')", "", "1..2", "5)"])
def test_bad_expressions_raise(bad):
    with pytest.raises(ValueError):
        calc.evaluate(bad)


def test_plain_numbers_are_not_expressions():
    for t in ("12", "-12", "1,250.50", "٣٤"):
        assert not calc.is_expression(t)


def test_pricing_both_ways():
    r = calc.pricing(10, 16, markup=25)
    assert r["net"] == 12.5 and r["gross"] == 14.5 and r["vat"] == 2 and r["margin"] == 20
    assert calc.pricing(10, 16, margin=20)["gross"] == 14.5
    back = calc.pricing(10, 16, price=14.5)
    assert back["markup"] == 25 and back["profit"] == 2.5
    assert calc.pricing(10, 16, markup=23, round_to=0.25)["gross"] == 14.5      # 14.268 ← 14.50 للأعلى
    assert calc.pricing(10, 0, price=8)["profit"] == -2
    with pytest.raises(ValueError):
        calc.pricing(10, 0, margin=100)


def test_money_field_accepts_typed_expression(app):
    from ui.widgets import MoneySpin
    w = MoneySpin()
    w.show()
    w.setFocus()
    w.lineEdit().selectAll()
    QTest.keyClicks(w, "12*3.5+4")
    assert w.lineEdit().text() == "12*3.5+4"           # لا يُعاد تنسيق العبارة أثناء الكتابة
    QTest.keyClick(w, Qt.Key_Return)
    assert w.value() == 46
    w.lineEdit().setText("١٠٠+١٦٪")                     # أرقام عربية
    w.interpretText()
    assert w.value() == 116
    w.setValue(7)
    w.lineEdit().setText("12*")                         # عبارة ناقصة: تبقى القيمة السابقة
    w.interpretText()
    assert w.value() == 7
    w.close()


def test_expression_out_of_range_keeps_value(app):
    from ui.widgets import CalcDoubleSpinBox
    w = CalcDoubleSpinBox()
    w.setRange(0, 100)
    w.setValue(5)
    w.lineEdit().setText("60*2")
    w.interpretText()
    assert w.value() == 5


def test_calculator_inserts_into_last_field(app):
    from ui import calculator
    from ui.widgets import MoneySpin
    calculator.track_focus()
    host = MoneySpin()
    host.show()
    host.activateWindow()
    calculator._track(None, host.lineEdit())            # كما يحدث عند النقر على الخانة
    win = calculator.open_calculator(None)
    panel = win.calc
    for k in ("1", "2", "×", "3", "+", "4"):
        panel.press(k)
    assert panel.display.text() == "12×3+4"
    assert panel.result.text() == "= 40"
    assert panel.insert()
    assert host.value() == 40
    assert panel.history.count() == 1
    panel.display.setText("100+16%")
    assert panel.equals() == 116
    note = QLineEdit()                                   # خانة نصية (الكمية، البحث)
    note.show()
    calculator._track(None, note)
    assert panel.insert() and note.text() == "116"
    panel.press("C")
    assert panel.display.text() == ""
    win.close()
    host.close()
    note.close()


def test_pricing_panel(app):
    from ui.calculator import PricingPanel
    settings.set_many({"vat_enabled": "1", "vat_rate": "16", "prices_include_vat": "1"})
    p = PricingPanel(cost=10)
    p.pct.setValue(25)
    assert p.price.value() == 14.5 and p.result["profit"] == 2.5
    p.price.setValue(17.4)                               # العكس: ما ربحي بهذا السعر؟
    assert p.pct.value() == pytest.approx(50)
    p.carton.setValue(240)                               # كرتونة 240 ÷ 24 حبة
    p.pieces.setValue(24)
    assert p.cost.value() == 10
    got = []
    p.on_apply = got.append
    p.apply()
    assert got and got[0] > 0
    settings.set("prices_include_vat", "0")
    assert p.shelf_price() == p.result["net"]


def test_assistant_math_and_calculator():
    from core import assistant
    a = assistant.answer("كم 12*3.5+4؟")
    assert a["intent"] == "math" and a["lines"] == ["= 46"]
    assert assistant.answer("احسب 250-10%")["lines"] == ["= 225"]
    assert assistant.answer("افتح الحاسبة")["action"][0] == "calculator"
    assert assistant.answer("كيف اسعر منتج؟")["action"][0] == "pricing"
    assert assistant.answer("كم بعت اليوم")["intent"] == "sales"
