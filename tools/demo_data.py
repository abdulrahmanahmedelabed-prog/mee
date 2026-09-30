# -*- coding: utf-8 -*-
"""
بيانات تجريبية وتدريبية: سوبرماركت كامل بتاريخ عمل 3 سنوات حتى اليوم.

تشمل: مبيعات يومية بمواسم (رمضان، الصيف، الأعياد، نهاية الأسبوع) ونمو سنوي وتضخم في الأسعار،
دفع نقدي وبطاقة ومحافظ إلكترونية (تزداد حصتها عاماً بعد عام) وآجل، ورديتان يومياً بكاشيرين،
مشتريات دورية من الموردين بتواريخ صلاحية، إتلاف المنتهي، مرتجعات، ديون وتسديدات، شيكات واردة وصادرة،
مصاريف شهرية، تسليم النقد للمالك وإيداعه في البنك، تحويل أرصدة المحافظ للبنك مع عمولاتها، وجرد ربع سنوي.

كل ذلك عبر عمليات البرنامج نفسها، فالقيود والتقارير اليومية والأسبوعية والشهرية والسنوية متطابقة ومتوازنة.

الاستخدام:  python tools/demo_data.py [مجلد البيانات]
           SHOP_DEMO_DAYS=90 لمدة أقصر (الافتراضي 3 سنوات)
لا يعمل إذا كانت قاعدة البيانات تحتوي فواتير حقيقية.
"""

import os
import random
import sys
from collections import deque
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__" and len(sys.argv) > 1:
    os.environ["SHOP_DATA_DIR"] = sys.argv[1]

from core import (db, auth, products, customers, suppliers, sales, expenses, shifts, settings,  # noqa: E402
                  promotions, cheques, ledger, license, wallets, loyalty)
from core.utils import money  # noqa: E402

DEFAULT_DAYS = 3 * 365

PRODUCTS = [
    # الاسم، الفئة، الوحدة، التكلفة، البيع، الشعبية (مبيعات يومية تقريبية)، الحد الأدنى، باركود، مفضلة
    ("حليب طازج 1 لتر", "ألبان", "قطعة", 4.2, 5.5, 30, 15, "7290000001011", False),
    ("لبنة 500 غم", "ألبان", "علبة", 9, 12, 8, 8, "7290000001028", False),
    ("جبنة بيضاء 250 غم", "ألبان", "علبة", 8, 11, 7, 6, "7290000001035", False),
    ("لبن رائب 1 كغم", "ألبان", "علبة", 6, 8, 9, 6, "7290000001042", False),
    ("خبز عربي", "مخبوزات", "ربطة", 3, 4, 45, 10, None, True),
    ("كعك بالسمسم", "مخبوزات", "قطعة", 1.5, 2.5, 25, 10, None, True),
    ("أرز بسمتي 5 كغم", "مواد تموينية", "كيس", 32, 42, 3, 5, "6281007031113", False),
    ("سكر 1 كغم", "مواد تموينية", "كيس", 3.8, 5, 9, 10, "6281007031120", False),
    ("طحين 5 كغم", "مواد تموينية", "كيس", 17, 22, 3, 4, "6281007031137", False),
    ("زيت زيتون 1 لتر", "مواد تموينية", "قطعة", 28, 38, 2, 5, "6281007031144", False),
    ("زيت ذرة 1.8 لتر", "مواد تموينية", "قطعة", 14, 19, 4, 6, "6281007031151", False),
    ("عدس أحمر 1 كغم", "مواد تموينية", "كيس", 6, 8.5, 3, 5, "6281007031168", False),
    ("شاي 100 كيس", "مشروبات ساخنة", "علبة", 11, 15, 4, 5, "6281007031175", False),
    ("قهوة عربية 200 غم", "مشروبات ساخنة", "علبة", 14, 20, 5, 5, "6281007031182", False),
    ("نسكافيه 3×1 (علبة 30)", "مشروبات ساخنة", "علبة", 25, 33, 2, 4, "6281007031199", False),
    ("كولا 1.5 لتر", "مشروبات باردة", "قطعة", 5, 7, 18, 12, "5449000000439", False),
    ("مياه معدنية 1.5 لتر", "مشروبات باردة", "قطعة", 1.5, 2.5, 35, 24, "5449000000446", False),
    ("عصير برتقال 1 لتر", "مشروبات باردة", "قطعة", 5.5, 8, 8, 6, "5449000000453", False),
    ("بسكويت شاي", "حلويات وسناكات", "قطعة", 2, 3, 20, 15, "6223000000011", False),
    ("شيبس كبير", "حلويات وسناكات", "قطعة", 3.5, 5, 15, 10, "6223000000028", False),
    ("شوكولاتة بار", "حلويات وسناكات", "قطعة", 2.2, 3.5, 22, 20, "6223000000035", False),
    ("مسحوق غسيل 3 كغم", "منظفات", "قطعة", 24, 32, 2, 3, "8690000000017", False),
    ("سائل جلي 1 لتر", "منظفات", "قطعة", 5, 7.5, 4, 6, "8690000000024", False),
    ("محارم ورقية 10 رول", "منظفات", "قطعة", 15, 20, 3, 4, "8690000000031", False),
    ("بندورة", "خضار وفواكه", "كغم", 3, 5, 14, 8, None, True),
    ("خيار", "خضار وفواكه", "كغم", 2.5, 4, 12, 8, None, True),
    ("بطاطا", "خضار وفواكه", "كغم", 2, 3.5, 15, 10, None, True),
    ("موز", "خضار وفواكه", "كغم", 5, 8, 8, 5, None, True),
    ("لحمة عجل", "ملحمة", "كغم", 55, 75, 4, 5, None, False),
    ("دجاج كامل", "ملحمة", "كغم", 13, 18, 9, 8, None, False),
    ("تمر مجدول 1 كغم", "مواد تموينية", "علبة", 22, 30, 1, 3, "6281007031205", False),
    ("حمص حب 1 كغم", "مواد تموينية", "كيس", 6.5, 9, 2, 4, "6281007031212", False),
    ("معكرونة 500 غم", "مواد تموينية", "كيس", 2.5, 3.5, 8, 10, "6281007031229", False),
    ("تونة علبة", "معلبات", "علبة", 4.5, 6.5, 7, 10, "6281007031236", False),
    ("فول مدمس علبة", "معلبات", "علبة", 2.5, 3.5, 6, 10, "6281007031243", False),
    ("بيض 30 حبة", "ألبان", "كرتونة", 16, 21, 6, 4, "7290000001059", False),
    ("شامبو 400 مل", "عناية شخصية", "قطعة", 11, 16, 2, 3, "8690000000048", False),
    ("معجون أسنان", "عناية شخصية", "قطعة", 6, 9, 3, 4, "8690000000055", False),
    ("حفاضات أطفال (40)", "عناية شخصية", "علبة", 38, 49, 1, 2, "8690000000062", False),
    ("آيس كريم كوب", "حلويات وسناكات", "قطعة", 2, 3.5, 6, 10, "6223000000042", False),
]

CUSTOMERS = [("أبو أحمد", "0599123456", 500), ("أم محمد", "0598765432", 300), ("محمود السائق", "0569112233", 0),
             ("أبو خليل", "0597001122", 1000), ("سارة", "0592334455", 200)]
MORE_CUSTOMERS = ["أبو يوسف", "أم خالد", "أبو رامي", "حنان", "أبو علي", "أم سامي", "رامي الحداد", "أبو فادي",
                  "أم ليث", "أبو عمر", "نادر", "أم ياسر", "أبو جهاد", "ريم", "أبو زيد", "أم حسن", "عادل النجار",
                  "أبو مازن", "أم رائد", "سامر", "أبو صالح", "هبة", "أبو ناصر", "أم عمر", "وليد", "أبو كرم",
                  "أم فراس", "أبو إياد", "لينا", "أبو حازم", "أم باسل", "ماهر", "أبو شادي", "أم وسيم", "إياد",
                  "أبو طارق", "أم أنس", "بلال", "أبو هاني", "أم نور"]
SUPPLIERS = {  # المورد: الفئات، أيام التوريد (0 = الاثنين ... 6 = الأحد)
    "شركة الجنيدي للألبان": (["ألبان"], (0, 3, 5)),
    "مخابز الأمل": (["مخبوزات"], (0, 1, 2, 3, 4, 5, 6)),
    "موزع المواد التموينية": (["مواد تموينية", "معلبات", "مشروبات ساخنة"], (1,)),
    "شركة المشروبات الوطنية": (["مشروبات باردة", "حلويات وسناكات"], (2, 5)),
    "مؤسسة النظافة": (["منظفات", "عناية شخصية"], (3,)),
    "سوق الخضار المركزي": (["خضار وفواكه"], (0, 2, 4, 6)),
    "ملحمة الريف (توريد)": (["ملحمة"], (0, 3, 5)),
}
SHELF_LIFE = {"ألبان": 21, "مخبوزات": 3, "ملحمة": 6, "معلبات": 540, "مواد تموينية": 365, "مشروبات ساخنة": 365,
              "مشروبات باردة": 180, "حلويات وسناكات": 180}
COVER_DAYS = {"مخبوزات": 1.1, "ملحمة": 3, "خضار وفواكه": 3, "ألبان": 5}
RAMADAN = [date(2022, 4, 2), date(2023, 3, 23), date(2024, 3, 11), date(2025, 3, 1), date(2026, 2, 18),
           date(2027, 2, 8), date(2028, 1, 28), date(2029, 1, 16), date(2030, 1, 6), date(2030, 12, 26),
           date(2031, 12, 15)]
HOURS = [7, 8, 8, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 13, 13, 14, 15, 16, 17, 17, 18, 18, 18, 19, 19, 19, 20, 20, 21]

_CLOCK = [None]


def _patch_clock():
    """ساعة محاكاة: كل عملية تُسجَّل بتاريخها ووقتها في الماضي كما لو حدثت فعلاً"""
    orig = (db.now, db.today)
    db.now = lambda: _CLOCK[0].strftime("%Y-%m-%d %H:%M:%S")
    db.today = lambda: _CLOCK[0].strftime("%Y-%m-%d")
    return orig


def _in_ramadan(d):
    return any(0 <= (d - r).days < 30 for r in RAMADAN)


def _season(d):
    """معامل الطلب لليوم: نهاية الأسبوع، رمضان والعيد، الصيف"""
    f = {4: 1.25, 5: 1.15, 6: 0.95}.get(d.weekday(), 1.0)   # الجمعة والسبت أعلى
    for r in RAMADAN:
        days = (d - r).days
        if 0 <= days < 30:
            f *= 1.35
        elif 30 <= days < 33:
            f *= 1.6          # عيد الفطر
    if d.month in (7, 8):
        f *= 1.1
    return f


def _cat_boost(cat, d):
    if cat == "مشروبات باردة" and d.month in (6, 7, 8, 9):
        return 1.8
    if cat == "حلويات وسناكات" and d.month in (6, 7, 8):
        return 1.3
    if _in_ramadan(d) and cat in ("مواد تموينية", "ألبان", "مشروبات باردة"):
        return 1.3
    return 1.0


class Shop:
    def __init__(self, days, progress=None):
        self.progress = progress or (lambda f, t: None)
        self.rnd = random.Random(7)
        self.today = date.today()
        self.start = self.today - timedelta(days=days)

    def at(self, d, hour, minute=0):
        _CLOCK[0] = datetime(d.year, d.month, d.day, hour, minute, self.rnd.randint(0, 59))

    # ------------------------------------------------------------------ التجهيز
    def setup(self):
        r = self.rnd
        self.at(self.start, 7)
        settings.set_many({"shop_name": "سوبرماركت النور", "shop_address": "الخليل - شارع السلام",
                           "shop_phone": "02-2220000", "loyalty_enabled": "1", "vat_enabled": "1", "vat_rate": "16",
                           "prices_include_vat": "1",
                           "wallets": wallets.to_json([
                               {"name": "PalPay", "account": "0599 000 111", "dest": "wallet"},
                               {"name": "Jawwal Pay", "account": "0599 000 222", "dest": "wallet"},
                               {"name": "تحويل بنكي فوري", "account": "PS92 PALS 0000 0000 0400 1234 567",
                                "dest": "bank"}])})
        db.set_meta("setup_done", "1")
        auth.create_user("cashier", "أحمد الكاشير", "1234", "cashier")
        auth.create_user("cashier2", "سامي الكاشير", "1234", "cashier")
        self.cashiers = [dict(db.query_one("SELECT * FROM users WHERE username=?", (u,))) for u in ("cashier", "cashier2")]
        self.admin = dict(db.query_one("SELECT * FROM users WHERE username='admin'"))
        ledger.add_manual_entry(self.start.isoformat(), "رأس مال المحل عند بدء استخدام البرنامج",
                                [{"account": ledger.BANK, "debit": 60000}, {"account": ledger.CAPITAL, "credit": 60000}])
        self.pids, self.info = [], {}
        for name, cat, unit, cost, price, pop, mn, bc, fav in PRODUCTS:
            weighted = unit == "كغم" and not fav
            plu = str(100 + len(self.pids)) if weighted else None
            pid = products.add_product(name, bc, cat, cost, price, round(pop * 12), mn, unit, plu_code=plu,
                                       is_weighted=weighted or fav and unit == "كغم", is_favorite=fav,
                                       wholesale_price=round(cost * 1.12, 1) if cat in ("مواد تموينية", "مشروبات باردة")
                                       else 0)
            self.pids.append(pid)
            self.info[pid] = {"cat": cat, "unit": unit, "cost": cost, "pop": pop}
        self.sold = {pid: deque([self.info[pid]["pop"]] * 14, maxlen=14) for pid in self.pids}
        self.today_sold = {pid: 0.0 for pid in self.pids}
        self.custs = [customers.add_customer(n, p, credit_limit=l) for n, p, l in CUSTOMERS]
        self.wholesale = customers.add_customer("بقالة الحي (جملة)", "0599887766", credit_limit=3000,
                                                price_level="wholesale")
        self.more = list(MORE_CUSTOMERS)
        r.shuffle(self.more)
        self.sups = {}
        for name, (cats, days) in SUPPLIERS.items():
            sid = suppliers.add_supplier(name, f"059{r.randint(1000000, 9999999)}",
                                         opening_balance=850 if name.startswith("موزع") else 0)
            self.sups[name] = (sid, cats, days)
        self.week_cash = 0.0
        self.wallet_bal = 0.0
        self.bounced = False
        self.sid = None

    # ------------------------------------------------------------------ يوم عمل
    def year_index(self, d):
        return (d - self.start).days / 365.0

    def payment(self, d, total, cust):
        y = self.year_index(d)
        r = self.rnd.random()
        wallet_share = min(0.38, 0.06 + 0.12 * y)      # الدفع الإلكتروني يزداد عاماً بعد عام
        card_share = 0.14 + 0.02 * y
        if r < wallet_share:
            w = self.rnd.choices(["PalPay", "Jawwal Pay", "تحويل بنكي فوري"], [5, 3, 2])[0]
            return {"wallet_amount": total, "wallet_name": w, "cash_amount": 0,
                    "wallet_ref": f"{self.rnd.randint(10**7, 10**8 - 1)}"}
        if r < wallet_share + card_share:
            return {"card_amount": total, "cash_amount": 0}
        if cust and self.rnd.random() < 0.45:
            return {"credit_amount": total, "cash_amount": 0}
        return {"cash_received": total + self.rnd.choice([0, 0, 0, 1, 2, 5, 10, 20])}

    def basket(self, d, wholesale=False):
        cart = []
        k = self.rnd.randint(8, 16) if wholesale else \
            self.rnd.choices([1, 2, 3, 4, 5, 6, 8], [22, 22, 18, 14, 10, 8, 6])[0]
        if getattr(self, "_wday", None) != d:     # أوزان الطلب تُحسب مرة لكل يوم
            self._wday, self._weights = d, [self.info[p]["pop"] * _cat_boost(self.info[p]["cat"], d) for p in self.pids]
        weights = self._weights
        for pid in set(self.rnd.choices(self.pids, weights, k=k)):
            p = products.get_product(pid)
            i = self.info[pid]
            if i["unit"] == "كغم":
                q = round(self.rnd.uniform(0.4, 2.5), 3)
            else:
                q = self.rnd.randint(3, 12) if wholesale else self.rnd.choices([1, 2, 3, 6], [60, 25, 10, 5])[0]
            if p["quantity"] < q:
                continue
            price = products.price_for(p, {"price_level": "wholesale"} if wholesale else None)
            cart.append({"product_id": pid, "product_name": p["name"], "quantity": q, "unit_price": price,
                         "list_price": price})
        return cart

    def sell(self, d, half):
        y = self.year_index(d)
        n = int(62 * (1 + 0.1 * y) * _season(d) * self.rnd.uniform(0.85, 1.15))
        times = sorted((self.rnd.choice(HOURS), self.rnd.randint(0, 59)) for _ in range(n))
        limit = datetime.now() if d == self.today else None
        for h, mi in times:
            if (h >= 15) != (half == 1):
                continue
            if limit and (h, mi) >= (limit.hour, limit.minute):
                break
            self.at(d, h, mi)
            self.one_sale(d)

    def one_sale(self, d, wholesale=False):
        cart = self.basket(d, wholesale)
        if not cart:
            return
        cust = None
        if wholesale:
            cust = self.wholesale
        elif self.rnd.random() < 0.22 and self.custs:
            cust = self.rnd.choice(self.custs)
        pts = 0.0
        if cust and not wholesale and self.rnd.random() < 0.3:
            # الزبون الدائم يستبدل نقاطه أحياناً (مئات كاملة، وبما لا يتجاوز نصف الفاتورة)
            have = loyalty.balance(cust)
            half = sales.compute_totals(cart)["total"] / 2 / max(settings.get_float("loyalty_point_value", 0.05), 0.001)
            pts = float(int(min(have, half) // 100) * 100) if have >= 300 else 0.0
        disc = sales.cart_discounts(cart, points=pts)["total"] if pts else 0.0
        total = sales.compute_totals(cart, disc)["total"]
        pay = {"credit_amount": total, "cash_amount": 0} if wholesale else self.payment(d, total, cust)
        try:
            res = sales.create_sale(cart, customer_id=cust, shift_id=self.sid, points_redeemed=pts, **pay)
        except sales.SaleError:          # تجاوز حد الدين: يدفع نقداً
            res = sales.create_sale(cart, customer_id=cust, shift_id=self.sid, points_redeemed=pts)
            pay = {}
        for it in cart:
            self.today_sold[it["product_id"]] += it["quantity"]
        if pay.get("wallet_amount") and wallets.get(pay["wallet_name"])["dest"] == wallets.DEST_WALLET:
            self.wallet_bal += pay["wallet_amount"]
        if not pay.get("credit_amount") and self.rnd.random() < 0.004:
            # مرتجع يُعاد بنفس طريقة الدفع: نقداً، أو للبطاقة، أو لنفس المحفظة
            method = pay.get("wallet_name") if pay.get("wallet_amount") else \
                (sales.REFUND_CARD if pay.get("card_amount") else sales.REFUND_CASH)
            it = sales.returnable_items(res["invoice_id"])[0]
            sales.create_return(res["invoice_id"], [{"invoice_item_id": it["id"], "quantity": min(1, it["remaining"])}],
                                refund_method=method, reason=self.rnd.choice(["تالف", "غير مطابق", "غيّر رأيه"]),
                                shift_id=self.sid)

    def restock(self, d):
        infl = 1.035 ** self.year_index(d)       # غلاء الأسعار عند الموردين
        for name, (sup, cats, days) in self.sups.items():
            if d.weekday() not in days:
                continue
            self.at(d, 8, self.rnd.randint(0, 50))
            items = []
            for pid in self.pids:
                i = self.info[pid]
                if i["cat"] not in cats:
                    continue
                avg = sum(self.sold[pid]) / len(self.sold[pid]) * _cat_boost(i["cat"], d)
                target = avg * COVER_DAYS.get(i["cat"], 12)
                q = products.get_product(pid)["quantity"]
                if q >= target * 0.6 and i["cat"] != "مخبوزات":
                    continue
                need = target - q
                if need <= 0.5:
                    continue
                need = round(need, 1) if i["unit"] == "كغم" else max(6, round(need / 6 + 0.49) * 6)
                life = SHELF_LIFE.get(i["cat"])
                items.append({"product_id": pid, "quantity": need,
                              "unit_cost": money(i["cost"] * infl * self.rnd.uniform(0.97, 1.03)),
                              "expiry_date": (d + timedelta(days=life)).isoformat() if life else None})
            if not items:
                continue
            total = money(sum(money(x["quantity"] * x["unit_cost"]) for x in items))
            daily = name.startswith(("مخابز", "سوق"))
            suppliers.create_purchase(sup, items, paid=total if daily else 0,
                                      payment_method=suppliers.PAY_DRAWER if daily else suppliers.PAY_BANK,
                                      shift_id=self.sid if daily else None, update_sale_prices=False,
                                      tax=0.0 if daily else money(total * 16 / 116))

    def write_off_expired(self, d):
        self.at(d, 7, 20)
        for b in db.query("SELECT id FROM product_batches WHERE remaining > 0 AND expiry_date < ?", (d.isoformat(),)):
            try:
                products.write_off_batch(b["id"])
            except ValueError:
                pass

    def money_matters(self, d):
        """المصاريف، الديون، الموردون، الشيكات، البنك، الجرد"""
        r = self.rnd
        y = self.year_index(d)
        if d.day == 1:
            self.at(d, 15, 30)
            expenses.add_expense("إيجار", 3000, "إيجار الشهر", from_drawer=False, expense_date=d.isoformat())
            expenses.add_expense("رواتب", money(2 * 2400 * (1.04 ** int(y))), "رواتب الكاشيرين",
                                 from_drawer=False, expense_date=d.isoformat())
            expenses.add_expense("إنترنت واتصالات", 150, from_drawer=False, expense_date=d.isoformat())
            if self.wallet_bal > 1:          # تحويل رصيد المحافظ للبنك مع عمولة المزوّد
                fee = money(self.wallet_bal * 0.005)
                ledger.add_manual_entry(d.isoformat(), "تحويل رصيد المحافظ الإلكترونية إلى البنك",
                                        [{"account": ledger.BANK, "debit": money(self.wallet_bal - fee)},
                                         {"account": ledger.PAYMENT_FEES, "debit": fee},
                                         {"account": ledger.WALLETS, "credit": money(self.wallet_bal)}])
                self.wallet_bal = 0.0
            for name, (sup, _, _) in self.sups.items():
                bal = suppliers.balance(sup)
                if bal > 300:
                    suppliers.pay_supplier(sup, money(bal * 0.7), suppliers.PAY_BANK, "تحويل شهري")
            big = self.sups["موزع المواد التموينية"][0]
            bal = suppliers.balance(big)
            if bal > 500:
                cheques.issue_cheque(big, money(bal * 0.8), (d + timedelta(days=30)).isoformat(),
                                     f"{r.randint(100000, 999999)}", "البنك العربي")
        if d.day == 15 and d.month % 2 == 1:     # إقرار ضريبة القيمة المضافة كل شهرين: مقاصة المدخلات ثم الدفع
            self.at(d, 11, 0)
            bal = ledger._balances(None, (d - timedelta(days=1)).isoformat())
            get = lambda code: money(sum(bal.get(code, [0, 0, 0])[i] * (1 if i < 2 else -1) for i in range(3)))
            out, inp = -get(ledger.VAT), get(ledger.VAT_INPUT)
            if inp > 0:
                ledger.add_manual_entry(d.isoformat(), "مقاصة ضريبة المدخلات مع الضريبة المستحقة (إقرار ضريبي)",
                                        [{"account": ledger.VAT, "debit": inp}, {"account": ledger.VAT_INPUT, "credit": inp}])
            due = money(out - inp)
            if due > 0:
                short = money(due - get(ledger.BANK) + 1000)
                if short > 0:
                    ledger.add_manual_entry(d.isoformat(), "إيداع مال من المالك في البنك (من جاري المالك)",
                                            [{"account": ledger.BANK, "debit": short},
                                             {"account": ledger.OWNER, "credit": short}])
                ledger.add_manual_entry(d.isoformat(), "دفع ضريبة القيمة المضافة المستحقة من البنك",
                                        [{"account": ledger.VAT, "debit": due}, {"account": ledger.BANK, "credit": due}])
        if d.day == 28:
            self.at(d, 16)
            season = 1.5 if d.month in (7, 8, 12, 1, 2) else 1.0
            expenses.add_expense("كهرباء", money(r.uniform(700, 1000) * season), from_drawer=False,
                                 expense_date=d.isoformat())
            expenses.add_expense("ماء", money(r.uniform(80, 160)), from_drawer=False, expense_date=d.isoformat())
        if d.weekday() == 2 and r.random() < 0.7:
            self.at(d, 16, 10)
            expenses.add_expense(r.choice(["ضيافة", "تنظيف", "مواصلات", "صيانة"]), money(r.uniform(20, 180)),
                                 from_drawer=True, shift_id=self.sid, expense_date=d.isoformat())
        if r.random() < 0.05 and self.more:      # عملاء جدد مع الوقت
            self.at(d, 16, 20)
            self.custs.append(customers.add_customer(self.more.pop(), f"059{r.randint(1000000, 9999999)}",
                                                     credit_limit=r.choice([0, 300, 500, 800])))
        if r.random() < 0.6:                     # تسديد ديون: نقداً أو بالمحفظة
            self.at(d, r.choice([17, 18, 19]), r.randint(0, 59))
            for cid in r.sample(self.custs, min(3, len(self.custs))):
                bal = customers.balance(cid)
                if bal > 30:
                    by_wallet = r.random() < min(0.5, 0.1 + 0.15 * y)
                    amt = money(bal * r.uniform(0.4, 1.0))
                    customers.receive_payment(cid, amt, "PalPay" if by_wallet else "نقدي",
                                              shift_id=None if by_wallet else self.sid)
                    if by_wallet:
                        self.wallet_bal += amt
        if d.weekday() == 0:                     # تاجر الجملة: طلبية أسبوعية آجلة
            self.at(d, 15, 40)
            self.one_sale(d, wholesale=True)
        if d.day == 12:                          # إرجاع بضاعة تالفة لمورد كبير مع ضريبة مدخلاتها
            self.at(d, 9, 15)
            name, (sup, cats, _) = r.choice([(n, v) for n, v in self.sups.items() if not n.startswith(("مخابز", "سوق"))])
            pool = [p for p in self.pids if self.info[p]["cat"] in cats and self.info[p]["unit"] != "كغم"
                    and products.get_product(p)["quantity"] >= 8]
            if pool:
                pid = r.choice(pool)
                net = money(2 * products.get_product(pid)["cost_price"])
                suppliers.create_purchase_return(sup, [{"product_id": pid, "quantity": 2}], "تالف",
                                                 tax=money(net * 0.16))
        if d.day == 15:
            self.at(d, 16, 30)
            bal = customers.balance(self.wholesale)
            if bal > 200:
                cheques.receive_cheque(self.wholesale, money(bal * 0.9), (d + timedelta(days=20)).isoformat(),
                                       f"{r.randint(100000, 999999)}", "بنك فلسطين")
            c = self.custs[3]   # أبو خليل
            if customers.balance(c) > 100:
                cheques.receive_cheque(c, money(customers.balance(c) * 0.8), (d + timedelta(days=10)).isoformat(),
                                       f"{r.randint(100000, 999999)}", "بنك القدس")
        self.at(d, 15, 10)                       # صرف الشيكات المستحقة (وشيك واحد راجع للتعلم)
        for ch in db.query("SELECT id, direction FROM cheques WHERE status='pending' AND due_date <= ?",
                           (d.isoformat(),)):
            if ch["direction"] == "in" and not self.bounced and y > 1:
                cheques.bounce_cheque(ch["id"], "رصيد غير كافٍ")
                self.bounced = True
            else:
                cheques.clear_cheque(ch["id"], d.isoformat())
        if d.day == 20 and d.month in (3, 6, 9, 12):   # جرد ربع سنوي بعجز بسيط
            self.at(d, 21, 30)
            for pid in r.sample(self.pids, 6):
                q = products.get_product(pid)["quantity"]
                if q > 3:
                    products.set_stock_count(pid, q - r.choice([1, 1, 2]))
        if d.month == 1 and d.day == 2:          # رفع أسعار البيع مع بداية كل سنة
            with db.tx() as conn:
                conn.execute("UPDATE products SET sale_price = round(sale_price * 1.04 * 2) / 2.0")

    def run_day(self, d):
        is_today = d == self.today
        now = datetime.now()
        self.write_off_expired(d)
        self.today_sold = {pid: 0.0 for pid in self.pids}
        for half in (0, 1):
            if is_today and half == 1 and now.hour < 15:
                break
            auth.set_current_user(self.cashiers[(d.toordinal() + half) % 2])
            self.at(d, 7 if half == 0 else 15, 30 if half == 0 else 0)
            self.sid = shifts.open_shift(300)
            if half == 0:
                self.restock(d)
            else:
                self.money_matters(d)
            self.sell(d, half)
            if is_today and (half == 1 or now.hour < 15):
                break                            # وردية اليوم تبقى مفتوحة
            self.at(d, 14 if half == 0 else 22, 55 if half == 0 else 0)
            exp = shifts.summary(self.sid)["expected_cash"]
            if exp > 300:
                shifts.cash_movement(-money(exp - 300), "تسليم النقد للمالك")
                self.week_cash += exp - 300
            counted = shifts.summary(self.sid)["expected_cash"] + self.rnd.choice([0, 0, 0, 0, 0, -5, -10, 2, 5])
            shifts.close_shift(max(0.0, money(counted)))
        for pid, q in self.today_sold.items():
            self.sold[pid].append(q)
        if d.weekday() == 5 and self.week_cash > 0 and not is_today:   # إيداع أسبوعي في البنك
            auth.set_current_user(self.admin)
            self.at(d, 22, 30)
            dep = money(self.week_cash * 0.85)
            ledger.add_manual_entry(d.isoformat(), "إيداع مال من المالك في البنك (من جاري المالك)",
                                    [{"account": ledger.BANK, "debit": dep}, {"account": ledger.OWNER, "credit": dep}])
            self.week_cash = 0.0

    def history(self):
        total_days = (self.today - self.start).days + 1
        with db.bulk_session() as commit:
            self.setup()
            for i in range(total_days):
                self.run_day(self.start + timedelta(days=i))
                if i % 10 == 0:
                    commit()
                    self.progress(i / total_days, (self.start + timedelta(days=i)).isoformat())
        auth.set_current_user(self.admin)


def finishing_touches(pids, cids):
    """حالات تدريبية جاهزة اليوم: كراتين، صلاحيات قريبة ومنتهية، عروض، شيكات مستحقة، مرتجع لمورد"""
    today = date.today()
    exp = lambda days: (today + timedelta(days=days)).isoformat()
    products.set_units(pids[15], [{"name": "كرتونة", "factor": 6, "barcode": "5449000000996", "sale_price": 39}])
    products.set_units(pids[16], [{"name": "شرنك", "factor": 6, "barcode": "5449000000989", "sale_price": 13}])
    products.set_units(pids[20], [{"name": "علبة", "factor": 24, "barcode": "6223000000998", "sale_price": 75}])
    s1 = db.scalar("SELECT id FROM suppliers WHERE name LIKE 'شركة الجنيدي%'")
    s3 = db.scalar("SELECT id FROM suppliers WHERE name LIKE 'موزع%'")
    suppliers.create_purchase(s1, [
        {"product_id": pids[0], "quantity": 2, "unit_cost": 50, "factor": 12, "unit_name": "كرتونة", "expiry_date": exp(4)},
        {"product_id": pids[1], "quantity": 10, "unit_cost": 9, "expiry_date": exp(-3)},
        {"product_id": pids[2], "quantity": 12, "unit_cost": 8, "expiry_date": exp(12)},
        {"product_id": pids[3], "quantity": 20, "unit_cost": 6, "expiry_date": exp(25)},
    ], paid=0, update_sale_prices=False)
    promotions.add_promotion("اشترِ 2 واحصل على 1 — بسكويت شاي", "buy_get", product_id=pids[18], buy_qty=2, get_qty=1)
    promotions.add_promotion("3 مياه بـ 6 شيكل", "bundle", product_id=pids[16], bundle_qty=3, bundle_price=6)
    promotions.add_promotion("خصم 10% على المنظفات", "percent", category="منظفات", percent=10, end_date=exp(10))
    for cid, due, no, bank in ((cids[3], 5, "100245", "بنك فلسطين"), (cids[0], 20, "558812", "بنك القدس")):
        owed = customers.balance(cid)
        if owed < 60:          # زبون بلا دين كافٍ: فاتورة آجلة أولاً حتى يكون الشيك عن دين حقيقي
            p = products.get_product(max(pids, key=lambda i: products.get_product(i)["quantity"]))
            cart = [{"product_id": p["id"], "product_name": p["name"], "quantity": 5, "unit_price": p["sale_price"]}]
            total = sales.compute_totals(cart, sales.cart_discounts(cart)["total"])["total"]
            sales.create_sale(cart, customer_id=cid, cash_amount=0, credit_amount=total)
            owed = customers.balance(cid)
        cheques.receive_cheque(cid, money(min(400, owed * 0.8)), exp(due), no, bank)
    cheques.issue_cheque(s3, 600, exp(3), "000731", "البنك العربي")
    suppliers.create_purchase_return(s1, [{"product_id": pids[1], "quantity": 4}], "منتهي الصلاحية")


def main(progress=None):
    days = int(os.environ.get("SHOP_DEMO_DAYS") or DEFAULT_DAYS)
    db.init_db()
    if db.scalar("SELECT COUNT(*) FROM invoices"):
        print("قاعدة البيانات تحتوي فواتير. لن تُضاف بيانات تجريبية.")
        return
    auth.set_current_user(auth.authenticate("admin", "admin") or dict(db.query_one("SELECT * FROM users LIMIT 1")))
    orig_clock = _patch_clock()
    orig_license = license.require_active
    license.require_active = lambda: None
    try:
        shop = Shop(days, progress)
        shop.history()
    finally:
        db.now, db.today = orig_clock
        license.require_active = orig_license
    finishing_touches(shop.pids, shop.custs)
    if progress:
        progress(1.0, "")
    n = db.scalar("SELECT COUNT(*) FROM invoices")
    print(f"\nتمت إضافة البيانات التجريبية: {n:,} فاتورة خلال {days} يوماً. الدخول: admin / admin  أو  cashier / 1234")


if __name__ == "__main__":
    main(lambda f, t: print(f"\r{f:5.0%} {t}", end="", flush=True))
