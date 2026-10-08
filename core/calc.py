# -*- coding: utf-8 -*-
"""
حساب العبارات في خانات المبالغ والآلة الحاسبة: «12*3.5+4» = 46.
- بلا eval: محلل صغير يقبل الأرقام والعمليات + − × ÷ والأقواس والنسبة المئوية فقط.
- النسبة كما في حاسبة المحل: 100+16% = 116، 250−10% = 225، 80×5% = 4، و16% وحدها = 0.16.
- يقبل الأرقام العربية (١٢٫٥) و× و÷ وفاصل الآلاف (1,250).
"""

_MAP = str.maketrans({"٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8",
                      "٩": "9", "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7",
                      "۸": "8", "۹": "9", "٫": ".", "×": "*", "x": "*", "X": "*", "÷": "/", "−": "-", "–": "-",
                      "٪": "%", "،": ",", "٬": ","})
OPERATORS = set("+-*/()%")


def normalize(text):
    t = str(text or "").translate(_MAP).replace(" ", "").replace(" ", "")
    return t.replace(",", "")                     # فاصل الآلاف


def is_expression(text):
    """هل في النص عملية حسابية (وليس رقماً عادياً أو سالباً)؟"""
    t = normalize(text)
    return any(ch in OPERATORS for ch in t.lstrip("+-"))


class _Parser:
    def __init__(self, text):
        self.s, self.i = text, 0

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def take(self, ch):
        if self.peek() == ch:
            self.i += 1
            return True
        return False

    def expr(self):
        value, _ = self.term()
        while self.peek() in ("+", "-"):
            op = self.s[self.i]
            self.i += 1
            right, pct = self.term()
            if pct:                                   # 100+16% ← 100 × 1.16
                right = value * right
            value = value + right if op == "+" else value - right
        return value

    def term(self):
        value, pct = self.factor()
        while self.peek() in ("*", "/"):
            op = self.s[self.i]
            self.i += 1
            right, _ = self.factor()
            if op == "*":
                value *= right
            else:
                if right == 0:
                    raise ValueError("القسمة على صفر")
                value /= right
            pct = False
        return value, pct

    def factor(self):
        if self.take("-"):
            v, p = self.factor()
            return -v, p
        if self.take("+"):
            return self.factor()
        if self.take("("):
            v = self.expr()
            if not self.take(")"):
                raise ValueError("قوس غير مغلق")
        else:
            start = self.i
            while self.peek().isdigit() or self.peek() == ".":
                self.i += 1
            num = self.s[start:self.i]
            if not num or num.count(".") > 1 or num == ".":
                raise ValueError("عبارة غير مكتملة")
            v = float(num)
        if self.take("%"):
            return v / 100, True
        return v, False


def evaluate(text):
    """قيمة العبارة، أو ValueError إن لم تكن صحيحة أو مكتملة"""
    t = normalize(text)
    if not t:
        raise ValueError("فارغ")
    if len(t) > 200 or any(not (ch.isdigit() or ch in OPERATORS or ch == ".") for ch in t):
        raise ValueError("رموز غير مسموحة")
    p = _Parser(t)
    v = p.expr()
    if p.i != len(t):
        raise ValueError("عبارة غير مكتملة")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("نتيجة غير صحيحة")
    return v


# ---------------------------------------------------------------------------
# حاسبة التسعير: من التكلفة إلى سعر البيع والعكس، مع الضريبة
# ---------------------------------------------------------------------------

def pricing(cost, vat_rate=0.0, markup=None, margin=None, price=None, price_has_vat=True, round_to=0.0):
    """
    أعطِ واحداً من: markup (ربح % على التكلفة) أو margin (هامش % من سعر البيع) أو price (سعر بيع معروف).
    round_to: تقريب السعر النهائي للأعلى (0.05، 0.25، 1...) ليكون سعراً «جميلاً».
    يرجع: net (قبل الضريبة)، vat، gross (شامل الضريبة)، profit، markup، margin
    """
    import math
    cost = float(cost or 0)
    r = max(float(vat_rate or 0), 0) / 100
    if price is not None:
        gross = float(price) if price_has_vat else float(price) * (1 + r)
    elif margin is not None:
        if float(margin) >= 100:
            raise ValueError("الهامش يجب أن يكون أقل من 100%")
        gross = cost / (1 - float(margin) / 100) * (1 + r)
    else:
        gross = cost * (1 + float(markup or 0) / 100) * (1 + r)
    if round_to and round_to > 0 and gross > 0:
        gross = math.ceil(round(gross / round_to, 9)) * round_to
    gross = round(gross, 4)
    net = gross / (1 + r)
    profit = net - cost
    return {"net": round(net, 4), "vat": round(gross - net, 4), "gross": gross, "profit": round(profit, 4),
            "markup": round(profit / cost * 100, 2) if cost else 0.0,
            "margin": round(profit / net * 100, 2) if net else 0.0}
