# -*- coding: utf-8 -*-
"""
الباقات: مجاني • بلس • برو • ماكس.

- أول شهر من التشغيل: باقة «ماكس» كاملة مجاناً (كل الميزات وأجهزة غير محدودة).
- بعده ينتقل البرنامج تلقائياً للباقة المجانية: البيع لا يتوقف أبداً، ولا تُحجز أي بيانات أو تقارير؛
  فقط الميزات المتقدمة تظهر بقفل 🔒 مع شرح ما تقدمه وزر الترقية.
- الترقية بمفتاح تفعيل موقّع (license.py) يحدد الباقة وعدد الأجهزة ومدة الاشتراك.
- عند انتهاء الاشتراك المدفوع: يعود للمجانية (لا يتوقف البيع).
"""

FREE, PLUS, PRO, MAX = "free", "plus", "pro", "max"
TIERS = [FREE, PLUS, PRO, MAX]
NAMES = {FREE: "مجاني", PLUS: "بلس", PRO: "برو", MAX: "ماكس"}
TAGLINES = {FREE: "للبقالة والمحل الصغير — مجاني للأبد",
            PLUS: "للمحل الذي يريد أن يبيع أكثر",
            PRO: "للسوبرماركت والمحل المنظّم محاسبياً",
            MAX: "للسلاسل والفروع — كل القوى الخارقة"}
TERMINALS = {FREE: 1, PLUS: 2, PRO: 5, MAX: 0}          # 0 = غير محدود
COLORS = {FREE: "#64748B", PLUS: "#0EA5E9", PRO: "#7C3AED", MAX: "#F59E0B"}
ICONS = {FREE: "🌱", PLUS: "⚡", PRO: "💎", MAX: "👑"}

# مفاتيح التفعيل القديمة تبقى صالحة وتُترجم لباقاتها الجديدة
LEGACY = {"basic": PLUS, "subscription": PRO, "enterprise": MAX}

# الميزة: (أدنى باقة، الاسم، ما تقدمه للمحل)
FEATURES = {
    # المجانية — كل ما يحتاجه محل ليبيع ويعرف وضعه
    "pos": (FREE, "نقطة بيع كاملة بالباركود والميزان", "بيع سريع، تعليق فواتير، مرتجعات، درج نقود"),
    "inventory": (FREE, "المخزون والصلاحية", "كميات، تنبيهات النقص، تواريخ الصلاحية والدفعات"),
    "debts": (FREE, "ديون العملاء والموردين", "كشوف حساب وتذكير واتساب"),
    "payments": (FREE, "البطاقات والمحافظ الإلكترونية", "بطاقة، محافظ وتطبيقات البنوك، دفع مختلط"),
    "reports": (FREE, "التقارير الأساسية والضريبة", "أرباح وخسائر، يومي، أصناف، ضريبة القيمة المضافة"),
    "shifts": (FREE, "الصندوق والورديات", "فتح وإغلاق الوردية وعدّ الصندوق"),
    # بلس — يبيع أكثر
    "insights": (PLUS, "المستشار الذكي", "توصيات يومية: ما ينفد، ما يركد، ما يخسر، وتحليل ABC"),
    "reorder": (PLUS, "الطلبيات الذكية", "كميات الشراء المقترحة لكل مورد حسب سرعة البيع"),
    "promotions": (PLUS, "العروض ونقاط الولاء", "خصومات تلقائية، اشترِ X واحصل على Y، نقاط ولاء"),
    "cheques": (PLUS, "الشيكات", "واردة وصادرة، تنبيهات الاستحقاق"),
    "installments": (PLUS, "تقسيط ديون العملاء", "جدول أقساط وتذكير بالمتأخر"),
    "mobile": (PLUS, "تطبيق الموظفين على الجوال", "جرد وفحص أسعار واستلام بضاعة من الجوال"),
    # برو — منظّم محاسبياً
    "accounting": (PRO, "المحاسبة والميزانية", "قيد مزدوج تلقائي، ميزان مراجعة، ميزانية عمومية، قائمة دخل"),
    "audit": (PRO, "التدقيق المالي الآلي", "33 إجراء تدقيق على كل العمليات مع رأي ودرجة وتقرير"),
    "payroll": (PRO, "الموظفون والرواتب", "سلف، صرف رواتب، قسائم رواتب"),
    "online": (PRO, "المتجر الأونلاين والطلبات", "صفحة طلبات لزبائنك تصل لنقطة البيع مباشرة"),
    "owner": (PRO, "لوحة المالك من أي مكان", "مبيعات وأرباح لحظية على جوال المالك"),
    "zakat": (PRO, "حاسبة الزكاة", "زكاة عروض التجارة بالنصاب والحول من دفاترك مباشرة"),
    # ماكس — القوى الخارقة
    "ask": (MAX, "اسأل محلك", "اكتب سؤالك بالعربي أو الإنجليزي فيجيبك من بياناتك فوراً، بدون إنترنت"),
    "forecast": (MAX, "التنبؤ بالمبيعات والسيولة", "مبيعات الثلاثين يوماً القادمة والنقد المتوقع ومتى ينقص"),
    "seasons": (MAX, "مخطط المواسم ورمضان", "كم تشتري لرمضان والعيد والمدارس حسب مبيعاتك في الموسم الماضي"),
    "branches": (MAX, "الفروع والسلاسل", "تقرير موحّد لكل الفروع وأجهزة غير محدودة"),
}

# الشاشة ← الميزة التي تفتحها
PAGE_FEATURE = {"insights": "insights", "reorder": "reorder", "promotions": "promotions", "cheques": "cheques",
                "accounting": "accounting", "audit": "audit", "payroll": "payroll", "orders": "online"}

# الأسعار المقترحة (يعدّلها الموزّع في core/vendor.py إن أراد)
PRICES = {FREE: ("0", "مجاني للأبد"), PLUS: ("49 ₪", "شهرياً • 490 ₪ سنوياً"),
          PRO: ("99 ₪", "شهرياً • 990 ₪ سنوياً"), MAX: ("179 ₪", "شهرياً • 1,790 ₪ سنوياً")}


def normalize(plan):
    plan = (plan or "").lower()
    plan = LEGACY.get(plan, plan)
    return plan if plan in TIERS else PRO


def rank(tier):
    return TIERS.index(tier) if tier in TIERS else 0


def label(tier):
    return f"{ICONS[tier]} {NAMES[tier]}"


def prices():
    try:
        from core import vendor
        return getattr(vendor, "PRICES", None) or PRICES
    except ImportError:
        return PRICES


def current():
    """الباقة الفعلية الآن (التجربة = ماكس)"""
    from core import license
    try:
        return license.status().get("tier") or FREE
    except Exception:
        return FREE


def required(feature):
    return FEATURES[feature][0] if feature in FEATURES else FREE


def has(feature, tier=None):
    return rank(tier or current()) >= rank(required(feature))


def page_allowed(key, tier=None):
    f = PAGE_FEATURE.get(key)
    return not f or has(f, tier)


def features_of(tier, only_new=False):
    """ميزات الباقة (only_new: ما تضيفه على الباقة التي قبلها)"""
    r = rank(tier)
    return [(k, v[1], v[2]) for k, v in FEATURES.items()
            if (rank(v[0]) == r if only_new else rank(v[0]) <= r)]


def upgrade_message(feature=None, tier=None):
    """رسالة واتساب جاهزة لطلب الترقية"""
    from core import license, settings
    tier = tier or (required(feature) if feature else PRO)
    lines = [f"طلب ترقية إلى باقة {NAMES[tier]}",
             f"المحل: {settings.get('shop_name')}", f"الهاتف: {settings.get('shop_phone') or '-'}",
             f"رمز الجهاز: {license.machine_id()}"]
    if feature in FEATURES:
        lines.insert(1, f"الميزة المطلوبة: {FEATURES[feature][1]}")
    return "\n".join(lines)
