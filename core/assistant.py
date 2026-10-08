# -*- coding: utf-8 -*-
"""
«اسأل محلك»: مساعد يفهم سؤالك بالعربي (فصحى أو عامية) أو الإنجليزي ويجيب من بيانات المحل فوراً، بدون إنترنت.

أمثلة: كم بعت اليوم؟ • كم ربحت الشهر الماضي؟ • شو أكثر صنف بينباع؟ • مين عليه دين؟ • كم باقي حليب؟
       قارن هذا الشهر بالماضي • متى رح يخلص الرز؟ • كم مصاريف الكهرباء هالسنة؟ • توقع مبيعات الشهر الجاي
       كم الزكاة؟ • شو أجهز لرمضان؟ • How much did I sell yesterday? • Who owes me money?

الفهم: تطبيع الحروف العربية + كلمات مفتاحية لكل نية (مع العامية الشائعة) + استخراج الفترة الزمنية
والصنف/العميل/المورد المذكور، ثم استدعاء نفس دوال التقارير التي يعتمد عليها البرنامج (الأرقام نفسها في كل مكان).
"""

import re
from datetime import date, timedelta

from core import db
from core.utils import money, fmt_qty

_TASHKEEL = re.compile(r"[ً-ْـ]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def norm(text):
    t = (text or "").lower().translate(_AR_DIGITS)
    t = _TASHKEEL.sub("", t)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي"), ("گ", "ك")):
        t = t.replace(a, b)
    t = re.sub(r"[^\w\s\-]", " ", t)
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def _has(q, words):
    return any((" " + w + " ") in q or (len(w) > 3 and w in q) for w in words)


def _m(v):
    return f"{money(v):,.2f}"


def _n(n, one, few, many=None):
    """عدد مع معدوده: 3 فواتير، 12 فاتورة"""
    n = int(n)
    return f"{n} {few if 3 <= n % 100 <= 10 else (many or one)}"


# ---------------------------------------------------------------------------
# الفترات الزمنية
# ---------------------------------------------------------------------------
MONTHS = {1: ["يناير", "كانون الثاني", "january", "jan"], 2: ["فبراير", "شباط", "february", "feb"],
          3: ["مارس", "اذار", "march", "mar"], 4: ["ابريل", "نيسان", "april", "apr"], 5: ["مايو", "ايار", "may"],
          6: ["يونيو", "حزيران", "june", "jun"], 7: ["يوليو", "تموز", "july", "jul"],
          8: ["اغسطس", "اب", "august", "aug"], 9: ["سبتمبر", "ايلول", "september", "sep"],
          10: ["اكتوبر", "تشرين الاول", "october", "oct"], 11: ["نوفمبر", "تشرين الثاني", "november", "nov"],
          12: ["ديسمبر", "كانون الاول", "december", "dec"]}


def _month_range(y, m):
    a = date(y, m, 1)
    b = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return a, b


def parse_period(q, today=None, default="today"):
    """(من، إلى، وصف) من نص السؤال"""
    today = today or date.fromisoformat(db.today())
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", q)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d, d, d.isoformat()
    m = re.search(r"(?:اخر|last|past)\s+(\d+)\s*(يوم|ايام|days?|اسابيع|اسبوع|weeks?|شهور|اشهر|months?)", q)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        days = n * (7 if unit.startswith(("اسب", "اسا", "week")) else 30 if unit.startswith(("شه", "اشه", "month")) else 1)
        return today - timedelta(days=days - 1), today, f"آخر {_n(days, 'يوماً', 'أيام')}"
    if _has(q, ["امس", "البارحه", "مبارح", "yesterday"]):
        d = today - timedelta(days=1)
        return d, d, "أمس"
    if _has(q, ["اول امس", "اول مبارح"]):
        d = today - timedelta(days=2)
        return d, d, "أول أمس"
    week_start = today - timedelta(days=(today.weekday() - 5) % 7)          # الأسبوع يبدأ السبت
    if _has(q, ["الاسبوع الماضي", "الاسبوع الفايت", "الجمعه الماضيه", "last week"]):
        return week_start - timedelta(days=7), week_start - timedelta(days=1), "الأسبوع الماضي"
    if _has(q, ["الشهر الماضي", "الشهر الفايت", "الشهر اللي فات", "الشهر السابق", "last month", "previous month"]):
        a = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        return a, today.replace(day=1) - timedelta(days=1), "الشهر الماضي"
    if _has(q, ["السنه الماضيه", "السنه الفايته", "العام الماضي", "last year"]):
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "السنة الماضية"
    if _has(q, ["اخر اسبوع", "past week", "last 7"]):
        return today - timedelta(days=6), today, "آخر 7 أيام"
    if _has(q, ["اخر شهر", "past month", "last 30"]):
        return today - timedelta(days=29), today, "آخر 30 يوماً"
    if _has(q, ["هذا الاسبوع", "هالاسبوع", "الاسبوع", "this week"]):
        return week_start, today, "هذا الأسبوع"
    if _has(q, ["هذا الشهر", "هالشهر", "الشهر", "this month"]):
        return today.replace(day=1), today, "هذا الشهر"
    if _has(q, ["هذه السنه", "هالسنه", "هذا العام", "السنه", "this year", "year"]):
        return date(today.year, 1, 1), today, "هذه السنة"
    for num, names in MONTHS.items():
        if any((" " + n + " ") in q for n in names):
            y = today.year if num <= today.month else today.year - 1
            a, b = _month_range(y, num)
            return a, min(b, today), f"{names[0]} {y}"
    if _has(q, ["رمضان", "ramadan"]) and not _has(q, ["جهز", "اجهز", "حضر", "اطلب", "prepare", "plan"]):
        from core import hijri
        y = hijri.from_gregorian(today)[0]
        a = hijri.to_gregorian(y, 9, 1)
        if a > today:
            a = hijri.to_gregorian(y - 1, 9, 1)
        return a, min(a + timedelta(days=29), today), "رمضان الماضي"
    if _has(q, ["اليوم", "today", "النهارده", "هلا"]):
        return today, today, "اليوم"
    if default == "month":
        return today.replace(day=1), today, "هذا الشهر"
    if default == "30":
        return today - timedelta(days=29), today, "آخر 30 يوماً"
    return today, today, "اليوم"


def previous_period(a, b):
    n = (b - a).days + 1
    if a.day == 1 and (b + timedelta(days=1)).day == 1:                 # شهر كامل ← الشهر السابق كاملاً
        pa = (a - timedelta(days=1)).replace(day=1)
        return pa, a - timedelta(days=1)
    if a.day == 1 and n < 32:                                           # الشهر الحالي حتى اليوم ← نفس الأيام من السابق
        pa = (a - timedelta(days=1)).replace(day=1)
        return pa, min(pa + timedelta(days=n - 1), a - timedelta(days=1))
    return a - timedelta(days=n), a - timedelta(days=1)


# ---------------------------------------------------------------------------
# الكيانات: صنف، عميل، مورد، فئة مصروف
# ---------------------------------------------------------------------------
_STOP = set("كم شو ايش اش وش ماذا ما هو هي في من على عن الى الي لل ال عندي عندنا باقي بقي اليوم امس هذا هذه "
            "الشهر السنه الاسبوع بعت بيع مبيعات سعر بكم كيلو قطعه علبه how much many the of is are what did "
            "sell sold stock left price for in on my me we have do does to and اكثر افضل صنف اصناف منتج".split())


def _tokens(q):
    out = []
    for w in q.split():
        for pre in ("وبال", "بال", "وال", "فال", "كال", "لل", "ال"):
            if w.startswith(pre) and len(w) - len(pre) >= 3:
                w = w[len(pre):]
                break
        if len(w) >= 3 and w not in _STOP and ("ال" + w) not in _STOP:
            out.append(w)
    return out


def find_products(q, limit=8):
    rows = db.query("SELECT id, name, quantity, sale_price, cost_price, unit, min_quantity FROM products WHERE is_active=1")
    full = [r for r in rows if norm(r["name"]).strip() and norm(r["name"]).strip() in q]
    if full:
        full.sort(key=lambda r: -len(r["name"]))
        return full[:limit]
    toks = _tokens(q)
    out = []
    for r in rows:
        nt = norm(r["name"]).split()
        if any(t in nt or (len(t) >= 4 and any(w.startswith(t) for w in nt)) for t in toks):
            out.append(r)
    return out[:limit]


def _find_named(table, q, extra=""):
    rows = db.query(f"SELECT * FROM {table} WHERE is_active=1 {extra}")
    hits = [r for r in rows if norm(r["name"]).strip() and norm(r["name"]).strip() in q]
    if not hits:
        toks = set(_tokens(q))
        hits = [r for r in rows if norm(r["name"]).split() and norm(r["name"]).split()[0] in toks]
    return hits


# ---------------------------------------------------------------------------
# النيات
# ---------------------------------------------------------------------------
INTENTS = [
    ("help", ["مساعده", "ساعدني", "شو بتعرف", "ماذا تستطيع", "ايش تقدر", "امثله", "help", "what can you"]),
    ("pair", ["اربط الجوال", "ربط الجوال", "اربط جوال", "تطبيق الجوال", "تطبيق الموبايل", "اربط الموبايل",
              "ربط الموبايل", "رمز الربط", "اربط تلفوني", "اربط هاتفي", "تطبيق اندرويد", "pair phone", "mobile app",
              "connect phone", "android app"]),
    ("navigate", ["افتح", "روح", "اذهب", "وديني", "خذني", "open", "go to", "show me the"]),
    ("zakat", ["زكاه", "الزكاه", "zakat"]),
    ("season", ["رمضان", "العيد", "عيد", "موسم", "المواسم", "المدارس", "الصيف", "ramadan", "eid", "season", "school"]),
    ("forecast", ["توقع", "متوقع", "تنبا", "الجاي", "القادم", "الجايه", "القادمه", "رح ابيع", "forecast", "predict",
                  "next month", "next week"]),
    ("compare", ["قارن", "مقارنه", "مقابل", "مقارنة", "compare", "versus", " vs "]),
    ("low", ["ناقص", "نواقص", "نفد", "نفذ", "يخلص", "رح يخلص", "بيخلص", "خلصان", "قرب يخلص", "تخلص", "رح تخلص",
             "بتخلص", "تنفد", "ستنفد", "سينفد", "قربت تخلص", "low stock",
             "out of stock", "running out", "run out", "reorder"]),
    ("expiry", ["صلاحيه", "منتهي", "ينتهي", "تنتهي", "منتهيه", "expire", "expiry", "expired"]),
    ("slow", ["راكد", "راكده", "ما بيبيع", "ما بينباع", "ما ينباع", "لا يباع", "واقف", "slow", "dead stock",
              "not selling"]),
    ("top_customers", ["افضل زبون", "افضل زبائن", "افضل زبائني", "اكثر زبون", "اكثر زبائن", "افضل عميل", "افضل العملاء",
                       "اهم زبائن", "اهم عملاء", "اكبر زبون", "best customer", "top customer", "best customers"]),
    ("top", ["اكثر صنف", "اكثر اصناف", "افضل صنف", "افضل اصناف", "اكثر منتج", "اكثر شي", "اكثر اشي", "الاكثر مبيعا",
             "اكثر مبيعا", "best selling", "top selling", "top products", "best seller", "most sold", "bestseller"]),
    ("debts", ["دين", "ديون", "الديون", "مديون", "مديونين", "عليه", "عليهم", "ذمم", "الدين", "debt", "debts", "owe",
               "owes", "receivable"]),
    ("payables", ["مستحقات الموردين", "للموردين", "علينا", "ندين", "payable", "payables", "i owe", "we owe"]),
    ("cash", ["صندوق", "الصندوق", "الدرج", "كاش", "الكاش", "النقد", "نقدي", "سيوله", "cash", "drawer", "till"]),
    ("cashier", ["كاشير", "الكاشير", "كاشيرات", "الموظفين", "cashier", "cashiers", "staff"]),
    ("hours", ["ساعه", "ساعات", "الذروه", "زحمه", "اي وقت", "peak", "busiest", "busy", "hour"]),
    ("vat", ["ضريبه", "الضريبه", "vat", "tax"]),
    ("returns", ["مرتجع", "مرتجعات", "ارجاع", "refund", "returns", "returned"]),
    ("worth", ["راس المال", "قيمه المحل", "اصول", "ميزانيه", "حق المالك", "net worth", "worth", "assets",
               "balance sheet"]),
    ("audit", ["تدقيق", "مدقق", "audit"]),
    ("category", ["فئه", "فئات", "قسم", "اقسام", "category", "categories"]),
    ("expenses", ["مصاريف", "مصروف", "مصروفات", "صرفت", "صرفنا", "نفقات", "فواتير الكهرباء", "expense", "expenses",
                  "spent", "spend"]),
    ("price", ["سعر", "بكم", "اسعار", "price", "how much is", "cost of"]),
    ("profit", ["ربح", "ارباح", "ربحت", "ربحنا", "كسبت", "الربح", "مكسب", "هامش", "profit", "profits", "margin",
                "earn", "earned"]),
    ("stock", ["كم باقي", "كم بقي", "كم عندي", "كم عنا", "موجود", "مخزون", "المخزون", "بالمخزن", "stock",
               "how many", "in stock", "left"]),
    ("invoices", ["فاتوره", "فواتير", "invoice", "invoices", "receipts", "transactions"]),
    ("sales", ["مبيعات", "بعت", "بعنا", "بيع", "مبيع", "دخل", "ايراد", "ايرادات", "الغله", "غله", "sales", "sold",
               "sell", "revenue", "turnover", "income"]),
]
INTENTS = [(k, [norm(w).strip() for w in words]) for k, words in INTENTS]
# عند تعارض النيات: الأخص أولاً
PRIORITY = {k: i for i, (k, _) in enumerate(INTENTS)}
NAV_VERBS = ("افتح", "روح", "اذهب", "وديني", "خذني", "اعرض شاشه", "open", "go to")
PLAN_WORDS = ["جهز", "اجهز", "حضر", "احضر", "اطلب", "استعد", "الاستعداد", "خطط", "prepare", "plan", "stock up"]
SALES_WORDS = ["بعت", "بعنا", "مبيعات", "بيع", "ربح", "ربحت", "ارباح", "sales", "sold", "sell", "profit"]


# ---------------------------------------------------------------------------
# الفهم بالمعنى: جذور الكلمات + الأعداد + الأخطاء الإملائية
# ---------------------------------------------------------------------------
_PREFIXES = ("وبال", "فبال", "بال", "وال", "فال", "كال", "لل", "ال", "و", "ف", "ب", "ل")
_SUFFIXES = ("اتنا", "اتي", "ينا", "هم", "ها", "نا", "ي", "ك", "ه")

SUPERLATIVE = ["افضل", "اكثر", "اكبر", "اهم", "اعلى", "احسن", "اقوى", "ابرز", "top", "best", "most", "biggest",
               "largest", "highest", "leading"]
LEAST = ["اقل", "اضعف", "اسوا", "ادنى", "least", "worst", "lowest", "fewest"]
CONCEPTS = {
    "customer": ["زبون", "زباين", "زبائن", "عميل", "عملاء", "العملا", "مشتري", "customer", "customers", "client",
                 "clients", "buyer", "buyers"],
    "product": ["صنف", "اصناف", "منتج", "منتجات", "سلعه", "سلع", "بضاعه", "بضايع", "مواد", "اشي", "شي", "item",
                "items", "product", "products", "goods"],
    "supplier": ["مورد", "موردين", "الموردين", "تاجر", "تجار", "supplier", "suppliers", "vendor", "vendors"],
    "cashier": ["كاشير", "موظف", "موظفين", "بياع", "cashier", "cashiers", "employee", "staff"],
    "profit": ["ربح", "ارباح", "مربح", "ربحا", "profit", "profitable", "margin"],
}
NUMBER_WORDS = {"واحد": 1, "اثنين": 2, "اثنان": 2, "ثنين": 2, "ثلاث": 3, "ثلاثه": 3, "تلات": 3, "تلاته": 3, "اربع": 4,
                "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثمانيه": 8,
                "تمانيه": 8, "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10, "عشرين": 20, "ثلاثين": 30, "خمسين": 50,
                "مئه": 100, "ميه": 100, "five": 5, "ten": 10, "twenty": 20, "three": 3, "fifty": 50, "hundred": 100}


def stem(word):
    """«زبائني» ← زبائن، «بالزحمه» ← زحمه، «للموردين» ← موردين"""
    w = word
    for pre in _PREFIXES:
        if w.startswith(pre) and len(w) - len(pre) >= 3:
            w = w[len(pre):]
            break
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    return w


def stems(q):
    return " " + " ".join(stem(w) for w in q.split()) + " "


def has_concept(q, key):
    words = CONCEPTS[key] if isinstance(key, str) and key in CONCEPTS else key
    qs = stems(q)
    for w in words:
        w2 = stem(norm(w).strip())
        if (" " + w + " ") in q or (" " + w2 + " ") in qs or (len(w2) >= 4 and w2 in qs):
            return True
    return False


def limit_of(q, default=10, cap=100):
    """«أفضل 10 زبائن» / «أكثر عشرة أصناف» / «top 5»"""
    m = re.search(r"(?<![\d-])(\d{1,3})(?![\d-])", q)
    if m and not re.search(r"\d{4}-\d{2}", q):
        n = int(m.group(1))
        if 1 <= n <= cap:
            return n
    for w in q.split():
        for cand in (w, stem(w)):
            if cand in NUMBER_WORDS:
                return min(NUMBER_WORDS[cand], cap)
    return default


def _by_meaning(q):
    """نية من تركيب المعنى: (أفضل/أكثر/أقل) + (زبون/صنف/مورد/كاشير)"""
    sup = has_concept(q, SUPERLATIVE)
    least = has_concept(q, LEAST)
    if not (sup or least):
        return None
    if has_concept(q, "customer"):
        return "top_customers"
    if has_concept(q, "cashier"):
        return "cashier"
    if has_concept(q, "supplier"):
        return "payables"
    if has_concept(q, "product") or has_concept(q, ["مبيعا", "بيعا", "selling", "sold", "sell", "مبيعات"]):
        return "slow" if least and not sup and not has_concept(q, "profit") else "top"
    return None


def _fuzzy(q):
    """أقرب نية لكلمات فيها أخطاء إملائية («مبيعاة»، «زكاه»...)"""
    import difflib
    vocab = {}
    for key, words in INTENTS:
        for w in words:
            if " " not in w and len(w) >= 4:
                vocab.setdefault(w, key)
    best, score = None, 0.0
    for tok in q.split():
        if len(tok) < 4:
            continue
        for cand in difflib.get_close_matches(stem(tok), vocab, n=1, cutoff=0.82):
            r = difflib.SequenceMatcher(None, stem(tok), cand).ratio()
            if r > score:
                best, score = vocab[cand], r
    return best


def detect(q):
    if q.strip().startswith(NAV_VERBS):
        return "navigate"
    meaning = _by_meaning(q)
    if meaning:
        return meaning
    scores = {}
    qs = stems(q)
    for key, words in INTENTS:
        hits = [w for w in words if (" " + w + " ") in q or (" " + w + " ") in qs or (len(w) > 4 and w in q)]
        if hits:
            scores[key] = sum(len(h) for h in hits)
    if not scores:
        return _fuzzy(q)
    # «كم ربحت من الحليب» ربح وليس مخزون؛ «كم باقي حليب» مخزون
    best = max(scores.values())
    cands = [k for k, s in scores.items() if s >= best * 0.6]
    return min(cands, key=lambda k: PRIORITY[k])


def answer(question, today=None):
    """يرجع: {intent, title, lines, table:{headers, rows}?, action:(page, label)?, period}"""
    q = norm(question)
    today = today or date.fromisoformat(db.today())
    intent = detect(q)
    if not intent:
        def named(table):
            return [r for r in db.query(f"SELECT name FROM {table} WHERE is_active=1")
                    if len(norm(r["name"]).strip()) >= 3 and norm(r["name"]).strip() in q]
        if named("customers"):                 # «كم على أبو سامي؟»
            intent = "debts"
        elif named("suppliers"):
            intent = "payables"
        elif find_products(q):
            intent = "stock"
        else:
            return _help(unknown=True)
    if intent == "season" and _has(q, SALES_WORDS) and not _has(q, PLAN_WORDS):
        intent = "profit" if _has(q, ["ربح", "ربحت", "ارباح", "profit"]) else "sales"     # «كم بعت في رمضان»
    try:
        return HANDLERS[intent](q, today)
    except Exception as e:           # لا يتعطل المساعد أبداً بسبب سؤال غريب
        return {"intent": intent, "title": "تعذرت الإجابة", "lines": [f"حدث خطأ أثناء الحساب: {e}"]}


# ---------------------------------------------------------------------------
# المعالجات
# ---------------------------------------------------------------------------
EXAMPLES = ["كم بعت اليوم؟", "كم ربحت الشهر الماضي؟", "قارن هذا الشهر بالشهر الماضي", "شو أكثر صنف بينباع هالشهر؟",
            "مين عليه دين؟", "كم باقي حليب؟", "شو الأصناف اللي رح تخلص؟", "كم مصاريف الكهرباء هالسنة؟",
            "توقع مبيعات الشهر الجاي", "شو أجهز لرمضان؟", "كم الزكاة عليّ؟", "متى أكثر ساعة زحمة؟",
            "كم في الصندوق؟", "أفضل زبائني", "شو الأصناف الراكدة؟", "افتح المخزون"]


def _help(q=None, today=None, unknown=False):
    lines = (["لم أفهم السؤال تماماً. جرّب أن تسأل بطريقة أخرى، مثلاً:"] if unknown else
             ["اسألني بالعربي أو الإنجليزي عن أي شيء في محلك، وسأجيبك من بياناتك فوراً:"])
    return {"intent": "help", "title": "🤖 اسأل محلك", "lines": lines + ["• " + e for e in EXAMPLES[:12]],
            "suggestions": EXAMPLES[:6]}


def _sales(q, today):
    from core import reports
    a, b, label = parse_period(q, today)
    prods = find_products(q) if _tokens(q) else []
    if prods:
        rows = []
        for p in prods:
            r = db.query_one("""SELECT SUM((ii.quantity - ii.returned_qty) * ii.factor) AS qn,
                                       SUM((ii.quantity - ii.returned_qty) * ii.unit_price) AS t,
                                       SUM((ii.quantity - ii.returned_qty) * (ii.unit_price - ii.cost_price)) AS pr
                                FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                                WHERE ii.product_id=? AND date(i.created_at) BETWEEN date(?) AND date(?)""",
                             (p["id"], a.isoformat(), b.isoformat()))
            rows.append([p["name"], fmt_qty(r["qn"] or 0), _m(r["t"] or 0), _m(r["pr"] or 0)])
        rows.sort(key=lambda r: -float(r[2].replace(",", "")))
        top = rows[0]
        return {"intent": "sales", "title": f"🧾 مبيعات {top[0]} — {label}", "period": label,
                "lines": [f"بعت {top[1]} بقيمة {top[2]} وربح {top[3]}."],
                "table": {"headers": ["الصنف", "الكمية", "المبيعات", "الربح"], "rows": rows} if len(rows) > 1 else None,
                "action": ("reports/المبيعات اليومية", "المبيعات اليومية في التقارير")}
    p = reports.profit_and_loss(a.isoformat(), b.isoformat())
    pa, pb = previous_period(a, b)
    prev = reports.profit_and_loss(pa.isoformat(), pb.isoformat())
    lines = [f"صافي المبيعات: {_m(p['net_sales'])} من {_n(p['invoice_count'], 'فاتورة', 'فواتير')} "
             f"(متوسط الفاتورة {_m(p['avg_basket'])})."]
    if a == b == today:                    # اليوم لم ينتهِ: نقارن بأمس حتى نفس الساعة
        now = db.now()[11:19]
        y = (today - timedelta(days=1)).isoformat()
        prev = {"net_sales": money(db.scalar("""SELECT SUM(total) FROM invoices WHERE date(created_at)=date(?)
                                                AND time(created_at) <= time(?)""", (y, now)))}
        if prev["net_sales"]:
            ch = (p["net_sales"] / prev["net_sales"] - 1) * 100
            lines.append(f"{'📈 أعلى' if ch >= 0 else '📉 أقل'} بنسبة {abs(ch):.1f}% من أمس حتى نفس الساعة "
                         f"({_m(prev['net_sales'])}).")
    elif prev["net_sales"]:
        ch = (p["net_sales"] / prev["net_sales"] - 1) * 100
        lines.append(f"{'📈 أعلى' if ch >= 0 else '📉 أقل'} بنسبة {abs(ch):.1f}% من الفترة السابقة ({_m(prev['net_sales'])}).")
    lines.append(f"نقدي {_m(p['cash_sales'])} • بطاقة {_m(p['card_sales'])} • محافظ {_m(p['wallet_sales'])} • "
                 f"آجل {_m(p['credit_sales'])}")
    return {"intent": "sales", "title": f"🧾 المبيعات — {label}", "period": label, "lines": lines,
            "action": ("reports/المبيعات اليومية", "المبيعات اليومية في التقارير"), "value": p["net_sales"]}


def _profit(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "month" if not _has(q, ["اليوم", "today"]) else "today")
    prods = find_products(q) if _tokens(q) else []
    if prods:
        return _sales(q, today)
    p = reports.profit_and_loss(a.isoformat(), b.isoformat())
    pa, pb = previous_period(a, b)
    prev = reports.profit_and_loss(pa.isoformat(), pb.isoformat())
    lines = [f"مجمل الربح: {_m(p['gross_profit'])} (هامش {p['gross_margin']}%).",
             f"صافي الربح بعد المصاريف ({_m(p['expenses'])}) والخسائر: {_m(p['net_profit'])}."]
    if prev["net_profit"]:
        ch = p["net_profit"] - prev["net_profit"]
        lines.append(f"{'📈 زيادة' if ch >= 0 else '📉 نقص'} {_m(abs(ch))} عن الفترة السابقة ({_m(prev['net_profit'])}).")
    return {"intent": "profit", "title": f"💰 الربح — {label}", "period": label, "lines": lines,
            "action": ("reports/الأرباح والخسائر", "الأرباح والخسائر في التقارير"), "value": p["net_profit"]}


def _expenses(q, today):
    from core import expenses
    a, b, label = parse_period(q, today, "month")
    rows = expenses.totals_by_category(a.isoformat(), b.isoformat())
    payroll = money(db.scalar("""SELECT SUM(base + bonus - deductions) FROM payroll_payments
                                 WHERE date(created_at) BETWEEN date(?) AND date(?)""", (a.isoformat(), b.isoformat())))
    cats = [r for r in rows if norm(r["category"]).strip() in q or any(t in norm(r["category"]) for t in _tokens(q))]
    if cats:
        total = sum(r["total"] for r in cats)
        return {"intent": "expenses", "title": f"💸 مصاريف {cats[0]['category']} — {label}", "period": label,
                "lines": [f"المجموع: {_m(total)}."], "action": ("expenses", "المصاريف")}
    total = sum(r["total"] for r in rows) + payroll
    table = [[r["category"], _m(r["total"])] for r in rows]
    if payroll:
        table.append(["رواتب", _m(payroll)])
    table.sort(key=lambda r: -float(r[1].replace(",", "")))
    return {"intent": "expenses", "title": f"💸 المصاريف — {label}", "period": label,
            "lines": [f"المجموع: {_m(total)}" + (f"، أكبرها {table[0][0]} ({table[0][1]})." if table else ".")],
            "table": {"headers": ["البند", "المبلغ"], "rows": table[:12]}, "action": ("expenses", "المصاريف")}


def _top(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "month")
    order = "profit" if _has(q, ["ربح", "ارباح", "profit"]) else "qty" if _has(q, ["كميه", "عدد", "quantity"]) else "total"
    if has_concept(q, "profit"):
        order = "profit"
    n = limit_of(q)
    rows = reports.top_products(a.isoformat(), b.isoformat(), n, order)
    if not rows and label == "هذا الشهر" and not _has(q, ["هذا الشهر", "هالشهر", "this month"]):
        a, label = today - timedelta(days=29), "آخر 30 يوماً"
        rows = reports.top_products(a.isoformat(), b.isoformat(), n, order)
    table = [[r["product_name"], fmt_qty(r["qty"] or 0), _m(r["total"] or 0), _m(r["profit"] or 0)] for r in rows]
    lines = [f"الأول: {rows[0]['product_name']} — {fmt_qty(rows[0]['qty'])} بقيمة {_m(rows[0]['total'])}."] if rows else \
        ["لا توجد مبيعات في هذه الفترة."]
    title = f"🏆 أكثر {_n(n, 'صنفاً', 'أصناف')} ربحاً — {label}" if order == "profit" else \
        f"🏆 أكثر {_n(n, 'صنفاً', 'أصناف')} مبيعاً — {label}"
    return {"intent": "top", "title": title, "period": label,
            "lines": lines, "table": {"headers": ["الصنف", "الكمية", "المبيعات", "الربح"], "rows": table},
            "action": ("reports/الأصناف الأكثر مبيعاً", "الأكثر مبيعاً في التقارير")}


def _slow(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "30")
    if label == "اليوم":
        a, label = today - timedelta(days=29), "آخر 30 يوماً"
    rows = reports.slow_products(a.isoformat(), b.isoformat())
    value = sum(r["stock_value"] or 0 for r in rows)
    return {"intent": "slow", "title": f"🧊 أصناف راكدة — لم تُبع خلال {label}", "period": label,
            "lines": [f"{_n(len(rows), 'صنفاً', 'أصناف')} فيها رأس مال مجمّد بقيمة {_m(value)}. اعرضها بخصم أو أعدها للمورد."
                      if rows else "لا توجد أصناف راكدة — كل بضاعتك تتحرك 👍"],
            "table": {"headers": ["الصنف", "الموجود", "قيمة المخزون", "آخر بيع"],
                      "rows": [[r["name"], fmt_qty(r["quantity"]), _m(r["stock_value"] or 0),
                                (r["last_sold"] or "لم يُبع")[:10]] for r in rows[:15]]},
            "action": ("reports/أصناف راكدة", "الأصناف الراكدة في التقارير")}


def _debts(q, today):
    from core import customers
    named = _find_named("customers", q)
    if named:
        rows = [[c["name"], c["phone"] or "", _m(customers.balance(c["id"]))] for c in named[:8]]
        c = named[0]
        bal = customers.balance(c["id"])
        line = (f"على {c['name']} دين بقيمة {_m(bal)}." if bal > 0.009 else
                f"{c['name']} ليس عليه دين" + (f"، وله رصيد {_m(-bal)}." if bal < -0.009 else "."))
        return {"intent": "debts", "title": f"📒 حساب {c['name']}", "lines": [line],
                "table": {"headers": ["العميل", "الهاتف", "الرصيد"], "rows": rows} if len(rows) > 1 else None,
                "action": ("customers", "العملاء والديون")}
    rows = customers.list_customers(debtors_only=True)          # مرتبة من الأكبر دَيناً
    total = customers.total_debts()
    lines = [f"مجموع ديون العملاء: {_m(total)} على {_n(len(rows), 'عميلاً', 'عملاء')}."]
    if _has(q, ["متاخر", "قديم", "overdue", "old"]):
        from core import financial_audit
        ag = [r for r in financial_audit.aging(today.isoformat()) if sum(r["buckets"][1:]) > 0.009]
        ag.sort(key=lambda r: -sum(r["buckets"][1:]))
        lines.append(f"منها {_m(sum(sum(r['buckets'][1:]) for r in ag))} أقدم من 30 يوماً.")
        table = [[r["name"], _m(r["balance"]), _m(sum(r["buckets"][1:]))] for r in ag[:12]]
        return {"intent": "debts", "title": "📒 الديون المتأخرة", "lines": lines,
                "table": {"headers": ["العميل", "الدين", "أقدم من 30 يوماً"], "rows": table},
                "action": ("customers", "العملاء والديون")}
    return {"intent": "debts", "title": "📒 ديون العملاء", "lines": lines,
            "table": {"headers": ["العميل", "الهاتف", "الدين"],
                      "rows": [[r["name"], r["phone"] or "", _m(r["balance_due"])] for r in rows[:limit_of(q, 12)]]},
            "action": ("customers", "العملاء والديون"), "value": total}


def _payables(q, today):
    from core import suppliers
    named = _find_named("suppliers", q)
    if named:
        s = named[0]
        bal = suppliers.balance(s["id"])
        return {"intent": "payables", "title": f"🚚 حساب {s['name']}",
                "lines": [f"المستحق للمورد {s['name']}: {_m(bal)}." if bal > 0.009 else f"لا شيء مستحق لـ{s['name']}."],
                "action": ("reports/الديون والمستحقات", "الديون والمستحقات")}
    rows = sorted(suppliers.list_suppliers(), key=lambda r: -(r["balance_due"] or 0))
    rows = [r for r in rows if (r["balance_due"] or 0) > 0.009]
    return {"intent": "payables", "title": "🚚 مستحقات الموردين",
            "lines": [f"المجموع: {_m(suppliers.total_dues())} لـ{_n(len(rows), 'مورداً', 'موردين')}."],
            "table": {"headers": ["المورد", "المستحق"], "rows": [[r["name"], _m(r["balance_due"])] for r in rows[:12]]},
            "action": ("reports/الديون والمستحقات", "الديون والمستحقات")}


def _stock(q, today):
    prods = find_products(q)
    if not prods:
        from core import products
        v = products.inventory_value()
        return {"intent": "stock", "title": "📦 المخزون",
                "lines": [f"قيمة المخزون بالتكلفة: {_m(v['cost_value'])}، وبسعر البيع: {_m(v.get('sale_value', 0))}.",
                          "اذكر اسم الصنف لأعرف كم باقي منه، مثلاً: «كم باقي سكر؟»"],
                "action": ("inventory", "المخزون")}
    since = (today - timedelta(days=29)).isoformat()
    rows = []
    for p in prods:
        sold = db.scalar("""SELECT SUM((ii.quantity - ii.returned_qty) * ii.factor) FROM invoice_items ii
                            JOIN invoices i ON i.id=ii.invoice_id WHERE ii.product_id=? AND i.created_at >= date(?)""",
                         (p["id"], since)) or 0
        rate = sold / 30
        days = (p["quantity"] / rate) if rate > 0 else None
        rows.append([p["name"], f"{fmt_qty(p['quantity'])} {p['unit'] or ''}".strip(), f"{rate:.1f}",
                     (_n(round(days), "يوماً", "أيام") if days is not None else "—")])
    p = prods[0]
    lines = [f"باقي من {rows[0][0]}: {rows[0][1]}" + (f"، يكفي حوالي {rows[0][3]} بمعدل البيع الحالي." if rows[0][3] != "—" else ".")]
    if p["quantity"] <= (p["min_quantity"] or 0):
        lines.append("⚠ وصل للحد الأدنى — اطلبه من المورد.")
    return {"intent": "stock", "title": f"📦 {p['name']}", "lines": lines,
            "table": {"headers": ["الصنف", "الموجود", "بيع يومي", "يكفي"], "rows": rows} if len(rows) > 1 else None,
            "action": ("inventory", "المخزون")}


def _low(q, today):
    from core import forecast
    rows = forecast.stockouts(14)
    return {"intent": "low", "title": "⏳ أصناف ستنفد خلال أسبوعين",
            "lines": [f"{_n(len(rows), 'صنفاً', 'أصناف')} ستنفد قريباً بمعدل بيعها الحالي." if rows else "لا يوجد صنف سينفد خلال أسبوعين 👍"],
            "table": {"headers": ["الصنف", "الموجود", "يكفي (أيام)", "اطلب", "المورد"],
                      "rows": [[r["name"], fmt_qty(r["stock"]), f"{r['days_left']:.0f}", f"{r['order_units']} {r['unit_name']}",
                                r["supplier_name"]] for r in rows[:15]]} if rows else None,
            "action": ("reorder", "الطلبيات الذكية")}


def _expiry(q, today):
    from core import products
    rows = products.expiring_batches(14)
    value = sum((r["quantity"] or 0) * (r["cost_price"] or 0) for r in rows) if rows and "cost_price" in rows[0].keys() else None
    return {"intent": "expiry", "title": "⏳ صلاحية تنتهي خلال أسبوعين",
            "lines": [f"{len(rows)} دفعة" + (f" بقيمة {_m(value)}" if value else "") + ". اعرضها بخصم قبل أن تتلف."
                      if rows else "لا توجد بضاعة تنتهي صلاحيتها خلال أسبوعين 👍"],
            "table": {"headers": ["الصنف", "الكمية", "تنتهي"],
                      "rows": [[r["name"] if "name" in r.keys() else r["product_name"], fmt_qty(r["quantity"]),
                                r["expiry_date"]] for r in rows[:15]]} if rows else None,
            "action": ("expiry", "شاشة الصلاحية")}


def _cash(q, today):
    from core import shifts, ledger
    s = shifts.current_shift()
    bal = {a: v[1] - v[2] for a, v in ledger._balances(None, today.isoformat()).items()}
    lines = []
    if s:
        lines.append(f"المتوقع في درج الوردية #{s['id']} الآن: {_m(shifts.summary(s['id'])['expected_cash'])}.")
    else:
        lines.append("لا توجد وردية مفتوحة الآن.")
    lines.append(f"النقد في الأدراج (حسب الدفاتر): {_m(bal.get(ledger.CASH, 0))} • البنك: {_m(bal.get(ledger.BANK, 0))} • "
                 f"المحافظ: {_m(bal.get(ledger.WALLETS, 0))}")
    return {"intent": "cash", "title": "💵 النقد والسيولة", "lines": lines, "action": ("cash", "الصندوق والورديات")}


def _top_customers(q, today):
    a, b, label = parse_period(q, today, "month")
    if label == "اليوم":
        a, label = today.replace(day=1), "هذا الشهر"
    n = limit_of(q)
    explicit = parse_period(q, today, "none")[2] != "اليوم" or _has(q, ["اليوم", "today"])
    sql = """SELECT c.name, COUNT(*) AS n, SUM(i.total) AS t FROM invoices i JOIN customers c ON c.id=i.customer_id
             WHERE date(i.created_at) BETWEEN date(?) AND date(?) GROUP BY c.id ORDER BY t DESC LIMIT ?"""
    rows = db.query(sql, (a.isoformat(), b.isoformat(), n))
    if not rows and not explicit:                     # لا مشتريات هذا الشهر بعد: آخر 90 يوماً
        a, label = today - timedelta(days=89), "آخر 90 يوماً"
        rows = db.query(sql, (a.isoformat(), b.isoformat(), n))
    return {"intent": "top_customers", "title": f"⭐ أفضل {_n(n, 'زبوناً', 'زبائن')} — {label}", "period": label,
            "lines": [f"الأول: {rows[0]['name']} بمشتريات {_m(rows[0]['t'])} في {rows[0]['n']} زيارة."] if rows else
            ["لا توجد مشتريات مسجلة بأسماء زبائن في هذه الفترة."],
            "table": {"headers": ["الزبون", "الزيارات", "المشتريات"],
                      "rows": [[r["name"], r["n"], _m(r["t"])] for r in rows]} if rows else None,
            "action": ("customers", "العملاء والديون")}


def _cashier(q, today):
    from core import reports
    ranking = has_concept(q, SUPERLATIVE) or has_concept(q, LEAST)
    a, b, label = parse_period(q, today, "month" if ranking else "today")
    rows = reports.sales_by_cashier(a.isoformat(), b.isoformat())
    if not rows and ranking:
        a, label = today - timedelta(days=29), "آخر 30 يوماً"
        rows = reports.sales_by_cashier(a.isoformat(), b.isoformat())
    return {"intent": "cashier", "title": f"🧑‍💼 الكاشير — {label}", "period": label,
            "lines": [f"الأعلى مبيعاً: {rows[0]['cashier']} ({_m(rows[0]['total'])})."] if rows else ["لا توجد مبيعات."],
            "table": {"headers": ["الكاشير", "الفواتير", "المبيعات", "الخصومات"],
                      "rows": [[r["cashier"], r["cnt"], _m(r["total"]), _m(r["discount"] or 0)] for r in rows]},
            "action": ("reports/حسب الكاشير", "المبيعات حسب الكاشير")}


def _hours(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "30")
    if label == "اليوم":
        a, label = today - timedelta(days=29), "آخر 30 يوماً"
    rows = [r for r in reports.sales_by_hour(a.isoformat(), b.isoformat()) if r["count"]]
    if not rows:
        return {"intent": "hours", "title": "🕐 ساعات الذروة", "lines": ["لا توجد مبيعات في هذه الفترة."]}
    best = sorted(rows, key=lambda r: -r["total"])[:3]
    quiet = sorted(rows, key=lambda r: r["total"])[0]
    return {"intent": "hours", "title": f"🕐 ساعات الذروة — {label}", "period": label,
            "lines": [f"أكثر الساعات زحمة: " + "، ".join(f"{r['hour']}:00" for r in best) + ".",
                      f"أهدأ ساعة: {quiet['hour']}:00 — مناسبة للجرد وترتيب الرفوف."],
            "table": {"headers": ["الساعة", "الفواتير", "المبيعات"],
                      "rows": [[f"{r['hour']}:00", r["count"], _m(r["total"])] for r in rows]},
            "action": ("reports/ساعات الذروة", "ساعات الذروة في التقارير")}


def _price(q, today):
    prods = find_products(q)
    if not prods:
        return {"intent": "price", "title": "🏷 الأسعار", "lines": ["اذكر اسم الصنف، مثلاً: «بكم السكر؟»"]}
    rows = []
    for p in prods:
        margin = ((p["sale_price"] - p["cost_price"]) / p["sale_price"] * 100) if p["sale_price"] else 0
        rows.append([p["name"], _m(p["sale_price"]), _m(p["cost_price"]), f"{margin:.1f}%"])
    return {"intent": "price", "title": f"🏷 {rows[0][0]}",
            "lines": [f"سعر البيع {rows[0][1]} • التكلفة {rows[0][2]} • هامش الربح {rows[0][3]}."],
            "table": {"headers": ["الصنف", "سعر البيع", "التكلفة", "الهامش"], "rows": rows} if len(rows) > 1 else None,
            "action": ("inventory", "المخزون")}


def _compare(q, today):
    from core import reports
    if _has(q, ["هذا الشهر", "هالشهر", "this month"]):
        a, b, label = today.replace(day=1), today, "هذا الشهر"
    elif _has(q, ["هذا الاسبوع", "هالاسبوع", "this week"]):
        a, b, label = parse_period(" هذا الاسبوع ", today)
    elif _has(q, ["هذه السنه", "هالسنه", "this year"]):
        a, b, label = date(today.year, 1, 1), today, "هذه السنة"
    else:
        a, b, label = parse_period(q, today, "month")
    if label == "اليوم" and not _has(q, ["اليوم", "today"]):
        a, b, label = today.replace(day=1), today, "هذا الشهر"
    # «مقارنة بالسنة/بالشهر الماضي»: الفترة المذكورة هي الأساس والمقارنة للفترة الحالية المقابلة
    if re.search(r"(مقارنه|مقابل|compared|vs|versus)\s+(ب|مع|with|to)?\s*(ال)?(سنه|عام|شهر|اسبوع|last)", q) or \
            _has(q, ["بالسنه الماضيه", "بالشهر الماضي", "بالاسبوع الماضي", "compared to last"]):
        if label == "السنة الماضية":
            a, b, label = date(today.year, 1, 1), today, "هذه السنة"
            pa, pb = a.replace(year=a.year - 1), b.replace(year=b.year - 1)
        elif label == "الشهر الماضي":
            a, b, label = today.replace(day=1), today, "هذا الشهر"
            pa, pb = previous_period(a, b)
        elif label == "الأسبوع الماضي":
            a, b, label = parse_period(" هذا الاسبوع ", today)
            pa, pb = a - timedelta(days=7), b - timedelta(days=7)
        else:
            pa, pb = previous_period(a, b)
    else:
        pa, pb = previous_period(a, b)
    if _has(q, ["السنه الماضيه", "العام الماضي", "last year"]) and label not in ("السنة الماضية", "هذه السنة"):
        pa, pb = a.replace(year=a.year - 1), b.replace(year=b.year - 1)
    cur = reports.profit_and_loss(a.isoformat(), b.isoformat())
    prev = reports.profit_and_loss(pa.isoformat(), pb.isoformat())
    rows = []
    for k, name in (("net_sales", "صافي المبيعات"), ("invoice_count", "عدد الفواتير"), ("avg_basket", "متوسط الفاتورة"),
                    ("gross_profit", "مجمل الربح"), ("expenses", "المصاريف"), ("net_profit", "صافي الربح")):
        c, p = cur[k], prev[k]
        ch = f"{(c / p - 1) * 100:+.1f}%" if p else "—"
        fmt = (lambda v: str(v)) if k == "invoice_count" else _m
        rows.append([name, fmt(c), fmt(p), ch])
    ch = (cur["net_sales"] / prev["net_sales"] - 1) * 100 if prev["net_sales"] else 0
    return {"intent": "compare", "title": f"⚖ {label} ({a.isoformat()} → {b.isoformat()}) مقابل {pa.isoformat()} → {pb.isoformat()}",
            "period": label,
            "lines": [f"المبيعات {'ارتفعت' if ch >= 0 else 'انخفضت'} {abs(ch):.1f}%، وصافي الربح {_m(cur['net_profit'])} "
                      f"مقابل {_m(prev['net_profit'])}."],
            "table": {"headers": ["البند", "الفترة", "السابقة", "التغير"], "rows": rows}, "action": ("reports/ملخص الفترات", "ملخص الفترات في التقارير")}


def _forecast(q, today):
    from core import forecast
    s = forecast.sales_forecast(30, today=today)
    if not s.get("enough_data"):
        return {"intent": "forecast", "title": "🔮 التوقعات", "lines": ["أحتاج أسبوعين من المبيعات على الأقل لأتوقع."]}
    c = forecast.cash_forecast(30, today=today)
    lines = [f"المبيعات المتوقعة خلال 30 يوماً: {_m(s['total'])} (بين {_m(s['low'])} و{_m(s['high'])}).",
             f"أقوى يوم عندك {s['best_day']} وأضعفها {s['worst_day']}؛ الاتجاه {s['trend_pct_week']:+.1f}% أسبوعياً."]
    lines.append(f"النقد المتوقع بعد 30 يوماً: {_m(c['end'])}" + (f" ⚠ قد ينقص النقد يوم {c['first_negative']}."
                                                                    if c["first_negative"] else
                                                                    f"، وأدنى نقطة {_m(c['lowest'])} يوم {c['lowest_date']}."))
    return {"intent": "forecast", "title": "🔮 توقعات الشهر القادم", "lines": lines,
            "table": {"headers": ["اليوم", "التاريخ", "متوقع", "من", "إلى"],
                      "rows": [[d["weekday"], d["date"], _m(d["value"]), _m(d["low"]), _m(d["high"])] for d in s["days"][:14]]},
            "action": ("smart/forecast", "التنبؤ والسيولة")}


def _zakat(q, today):
    from core import zakat
    r = zakat.compute(today.isoformat())
    lines = [f"الوعاء الزكوي الآن: {_m(r['base'])} (نقد وبضاعة وديون مرجوّة − ديون حالّة)."]
    if r["nisab"]:
        lines.append(f"الزكاة الواجبة: {_m(r['zakat'])}" if r["reaches_nisab"] else "الوعاء أقل من النصاب: لا زكاة.")
    else:
        lines.append(f"الزكاة (2.5%) إن بلغ النصاب: {_m(money(r['base'] * r['rate']))} — أدخل سعر غرام الذهب لمعرفة النصاب.")
    lines.append(f"الحَوْل القادم: {r['next_hawl']['date']} ({r['next_hawl']['hijri']}) بعد {r['next_hawl']['days_left']} يوماً.")
    return {"intent": "zakat", "title": "🕌 الزكاة", "lines": lines, "action": ("smart/zakat", "حاسبة الزكاة")}


def _season(q, today):
    from core import seasons
    ups = seasons.upcoming(today)
    key = None
    for k, words in (("ramadan", ["رمضان", "ramadan"]), ("eid_fitr", ["الفطر", "fitr"]), ("eid_adha", ["الاضحى", "adha"]),
                     ("school", ["المدارس", "مدارس", "school"]), ("summer", ["الصيف", "صيف", "summer"])):
        if _has(q, words):
            key = k
            break
    key = key or ups[0]["key"]
    p = seasons.plan(key, today)
    if not p["enough_data"]:
        return {"intent": "season", "title": f"{p['icon']} {p['name']}", "lines": [p["message"]], "action": ("smart/seasons", "مخطط المواسم ورمضان")}
    lines = [f"{p['name']} يبدأ {p['start']} {('(' + p['hijri'] + ')') if p['hijri'] else ''} — بعد {p['days_until']} يوماً. "
             f"اطلب قبل {p['order_by']}.",
             f"مبيعاتك في الموسم الماضي: {_m(p['last_season_sales'])}" +
             (f" (أعلى من المعتاد ×{p['overall_uplift']})" if p["overall_uplift"] else "") +
             f"، والمتوقع هذا الموسم: {_m(p['expected_sales'])}."]
    return {"intent": "season", "title": f"{p['icon']} الاستعداد لـ{p['name']}", "lines": lines,
            "table": {"headers": ["الصنف", "بيع الموسم الماضي", "ارتفاع", "الطلبية الأولى"],
                      "rows": [[i["name"], fmt_qty(i["last_season"]), (f"×{i['uplift']}" if i["uplift"] else "موسمي"),
                                fmt_qty(i["order"])] for i in p["items"][:12]]},
            "action": ("smart/seasons", "مخطط المواسم ورمضان")}


def _vat(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "month")
    r = reports.vat_report(a.isoformat(), b.isoformat())
    rows = [["المبيعات الخاضعة (بدون ضريبة)", _m(r["taxable_sales"])], ["ضريبة المخرجات (على المبيعات)", _m(r["output_tax"])],
            ["المشتريات الخاضعة (بدون ضريبة)", _m(r["taxable_purchases"])], ["ضريبة المدخلات (على المشتريات)", _m(r["input_tax"])],
            ["= الصافي المستحق للدولة", _m(r["net_due"])]]
    return {"intent": "vat", "title": f"🧾 الضريبة — {label}", "period": label,
            "lines": [f"صافي الضريبة المستحقة: {_m(r['net_due'])} (مخرجات {_m(r['output_tax'])} − مدخلات {_m(r['input_tax'])})."],
            "table": {"headers": ["البند", "المبلغ"], "rows": rows},
            "action": ("reports/ضريبة القيمة المضافة", "إقرار الضريبة في التقارير")}


def _returns(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "month")
    p = reports.profit_and_loss(a.isoformat(), b.isoformat())
    rate = (p["returns"] / p["sales_after_discount"] * 100) if p["sales_after_discount"] else 0
    return {"intent": "returns", "title": f"↩ المرتجعات — {label}", "period": label,
            "lines": [f"{_n(p['returns_count'], 'مرتجعاً', 'مرتجعات')} بقيمة {_m(p['returns'])} ({rate:.1f}% من المبيعات)."
                      if p["returns_count"] else "لا توجد مرتجعات في هذه الفترة 👍"],
            "action": ("invoices", "الفواتير والمرتجعات")}


def _worth(q, today):
    from core import ledger
    bs = ledger.balance_sheet(today.isoformat())
    return {"intent": "worth", "title": "💎 قيمة المحل الآن",
            "lines": [f"ما يملكه المحل: {_m(bs['total_assets'])} • ما عليه: {_m(bs['total_liabilities'])}",
                      f"صافي حق المالك: {_m(bs['net_worth'])}."],
            "table": {"headers": ["البند", "المبلغ"], "rows": [[x["name"], _m(x["amount"])] for x in bs["assets"][:10]]},
            "action": ("accounting/الميزانية العمومية", "الميزانية العمومية")}


def _audit(q, today):
    from core import financial_audit
    a, b, label = parse_period(q, today, "month")
    if label == "اليوم":
        a, label = today.replace(day=1), "هذا الشهر"
    r = financial_audit.run(a.isoformat(), b.isoformat())
    c = r["counts"]
    return {"intent": "audit", "title": f"🔎 التدقيق — {label}", "period": label,
            "lines": [f"الدرجة {r['score']}/100 — الرأي: {r['opinion']}.",
                      f"ملاحظات: حرج {c['critical']} • مرتفع {c['high']} • متوسط {c['medium']} • منخفض {c['low']}."],
            "action": ("audit", "التدقيق المالي")}


def _category(q, today):
    from core import reports
    a, b, label = parse_period(q, today, "month")
    rows = reports.sales_by_category(a.isoformat(), b.isoformat())
    return {"intent": "category", "title": f"🗂 المبيعات حسب الفئة — {label}", "period": label,
            "lines": [f"الأعلى: {rows[0]['category']} ({_m(rows[0]['total'])})."] if rows else ["لا توجد مبيعات."],
            "table": {"headers": ["الفئة", "المبيعات", "الربح"],
                      "rows": [[r["category"], _m(r["total"] or 0), _m(r["profit"] or 0)] for r in rows[:12]]},
            "action": ("reports/حسب الفئة", "المبيعات حسب الفئة")}


def _invoices(q, today):
    a, b, label = parse_period(q, today)
    r = db.query_one("""SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS t, COALESCE(MAX(total),0) AS mx FROM invoices
                        WHERE date(created_at) BETWEEN date(?) AND date(?)""", (a.isoformat(), b.isoformat()))
    return {"intent": "invoices", "title": f"🧾 الفواتير — {label}", "period": label,
            "lines": [f"{_n(r['n'], 'فاتورة', 'فواتير')} بمجموع {_m(r['t'])}" + (f"، متوسطها {_m(r['t'] / r['n'])} وأكبرها {_m(r['mx'])}."
                                                                 if r["n"] else ".")],
            "action": ("invoices", "الفواتير والمرتجعات")}


NAV = {"dashboard": ["لوحه التحكم", "الرئيسيه", "dashboard", "home"], "pos": ["نقطه البيع", "الكاشير", "البيع", "pos"],
       "inventory": ["المخزون", "البضاعه", "inventory"], "customers": ["العملاء", "الزبائن", "الديون", "customers"],
       "suppliers": ["الموردين", "المشتريات", "suppliers"], "expenses": ["المصاريف", "expenses"],
       "reports": ["التقارير", "reports"], "accounting": ["المحاسبه", "الميزانيه", "accounting"],
       "settings": ["الاعدادات", "settings"], "cash": ["الصندوق", "الورديات", "cash"], "expiry": ["الصلاحيه", "expiry"],
       "audit": ["التدقيق", "audit"], "payroll": ["الرواتب", "الموظفين", "payroll"], "reorder": ["الطلبيات", "reorder"],
       "invoices": ["الفواتير", "invoices"], "insights": ["المستشار", "advisor"], "promotions": ["العروض", "promotions"],
       "cheques": ["الشيكات", "cheques"], "help": ["المساعده", "الدليل", "help"]}


def _navigate(q, today):
    for key, words in NAV.items():
        if _has(q, words):
            return {"intent": "navigate", "title": "↪ فتح الشاشة", "lines": ["تفضل."], "action": (key, ""), "go": key}
    return _help(unknown=True)


def _pair(q, today):
    """كيف أربط الجوال؟ الخطوات وزر يفتح نافذة الرموز"""
    return {"intent": "pair", "title": "📱 ربط تطبيق الجوال",
            "lines": ["1. حمّل تطبيق أندرويد: امسح رمز التحميل في نافذة «ربط الجوال».",
                      "2. افتح التطبيق والجوال على واي فاي المحل: يجد المحل وحده، أو امسح «رمز الربط» من نفس النافذة.",
                      "3. ادخل باسم المستخدم وكلمة المرور نفسها التي في البرنامج.",
                      "النافذة متاحة دائماً من زر 📱 أعلى الشاشة."],
            "action": ("pair", "ربط الجوال")}


HANDLERS = {"pair": _pair, "help": _help, "navigate": _navigate, "sales": _sales, "profit": _profit, "expenses": _expenses,
            "top": _top, "slow": _slow, "debts": _debts, "payables": _payables, "stock": _stock, "low": _low,
            "expiry": _expiry, "cash": _cash, "top_customers": _top_customers, "cashier": _cashier, "hours": _hours,
            "price": _price, "compare": _compare, "forecast": _forecast, "zakat": _zakat, "season": _season,
            "vat": _vat, "returns": _returns, "worth": _worth, "audit": _audit, "category": _category,
            "invoices": _invoices}
