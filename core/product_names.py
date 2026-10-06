# -*- coding: utf-8 -*-
"""
أسماء الأصناف بالإنجليزية في الواجهة الإنجليزية.

1) الاسم الإنجليزي الذي يكتبه صاحب المحل للصنف (حقل «الاسم بالإنجليزية») له الأولوية دائماً.
2) وإلا تُترجم الأسماء تلقائياً بدون إنترنت: قاموس لأشهر أصناف البقالة والسوبرماركت والعلامات التجارية
   والوحدات، مع ترتيب الصفة قبل الموصوف («حليب طازج» ← Fresh Milk)، وما لا يُعرف يُكتب بحروف لاتينية
   («الجنيدي» ← Al-Janidi).
تُستخدم أيضاً للفئات وأسماء العملاء والموردين القصيرة في الواجهة الإنجليزية فقط؛ البيانات المحفوظة لا تتغير.
"""

import re
import threading
import time

_TASHKEEL = re.compile(r"[ً-ْـ]")


def norm(word):
    w = _TASHKEEL.sub("", word)
    return (w.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه"))


# ---------------------------------------------------------------- القاموس
_RAW_WORDS = {
    # ألبان وأجبان
    "حليب": "Milk", "لبن": "Laban", "لبنة": "Labneh", "جبنة": "Cheese", "جبن": "Cheese", "زبدة": "Butter",
    "زبده": "Butter", "قشطة": "Cream", "قشطه": "Cream", "كريمة": "Cream", "زبادي": "Yogurt", "روب": "Yogurt",
    "شنينة": "Ayran", "عيران": "Ayran", "حلوم": "Halloumi", "حلومي": "Halloumi", "نابلسية": "Nabulsi", "عكاوي": "Akkawi",
    "موزاريلا": "Mozzarella", "شيدر": "Cheddar", "فيتا": "Feta", "مثلثات": "Triangles", "سمنة": "Ghee", "سمن": "Ghee",
    "ألبان": "Dairy", "البان": "Dairy", "بيض": "Eggs", "بيضة": "Egg",
    # مخبوزات وحبوب
    "خبز": "Bread", "كعك": "Ka'ak", "كعكة": "Cake", "كيك": "Cake", "كرواسون": "Croissant", "توست": "Toast",
    "صمون": "Bread Rolls", "طحين": "Flour", "دقيق": "Flour", "أرز": "Rice", "ارز": "Rice", "رز": "Rice",
    "سكر": "Sugar", "ملح": "Salt", "عدس": "Lentils", "فول": "Fava Beans", "حمص": "Chickpeas", "فاصولياء": "Beans",
    "فاصوليا": "Beans", "برغل": "Bulgur", "سميد": "Semolina", "شوفان": "Oats", "معكرونة": "Pasta", "مكرونة": "Pasta",
    "معكرونه": "Pasta", "شعيرية": "Vermicelli", "نشا": "Starch", "ذرة": "Corn", "فريكة": "Freekeh", "كسكس": "Couscous",
    "مخبوزات": "Bakery", "حبوب": "Cereals", "كورن": "Corn", "فليكس": "Flakes", "بسكويت": "Biscuits", "بسكوت": "Biscuits",
    "ويفر": "Wafer", "مخابز": "Bakery",
    # زيوت ومعلبات وبهارات
    "زيت": "Oil", "زيتون": "Olives", "تونة": "Tuna", "تونا": "Tuna", "سردين": "Sardines", "معلبات": "Canned Food",
    "معجون": "Paste", "صلصة": "Sauce", "صلصه": "Sauce", "كاتشب": "Ketchup", "مايونيز": "Mayonnaise", "خردل": "Mustard",
    "طحينة": "Tahini", "طحينيه": "Tahini", "حلاوة": "Halva", "مربى": "Jam", "عسل": "Honey", "دبس": "Molasses",
    "خل": "Vinegar", "بهارات": "Spices", "كمون": "Cumin", "فلفل": "Pepper", "كركم": "Turmeric", "زعتر": "Za'atar",
    "سماق": "Sumac", "قرفة": "Cinnamon", "هيل": "Cardamom", "يانسون": "Anise", "بابونج": "Chamomile", "ميرمية": "Sage",
    "نعناع": "Mint", "مرقة": "Stock", "مكعبات": "Cubes", "خميرة": "Yeast", "بيكنج": "Baking", "باودر": "Powder",
    "فانيلا": "Vanilla", "بزر": "Seeds", "بذور": "Seeds", "مكسرات": "Nuts", "لوز": "Almonds", "فستق": "Pistachios",
    "كاجو": "Cashews", "جوز": "Walnuts", "بندق": "Hazelnuts", "سمسم": "Sesame", "تمر": "Dates", "تمور": "Dates",
    "زبيب": "Raisins", "مخلل": "Pickles", "مخللات": "Pickles", "تونه": "Tuna",
    # مشروبات
    "ماء": "Water", "مياه": "Water", "مي": "Water", "عصير": "Juice", "شاي": "Tea", "قهوة": "Coffee", "قهوه": "Coffee",
    "نسكافيه": "Nescafe", "كاكاو": "Cocoa", "مشروب": "Drink", "مشروبات": "Beverages", "غازية": "Soft Drink",
    "غازي": "Sparkling", "كولا": "Cola", "صودا": "Soda", "طاقة": "Energy", "شراب": "Syrup", "شاى": "Tea",
    # فواكه وخضار
    "برتقال": "Orange", "تفاح": "Apple", "تفاحة": "Apple", "موز": "Bananas", "عنب": "Grapes", "مانجا": "Mango",
    "مانجو": "Mango", "فراولة": "Strawberry", "ليمون": "Lemon", "أناناس": "Pineapple", "اناناس": "Pineapple",
    "خوخ": "Peach", "مشمش": "Apricot", "رمان": "Pomegranate", "بطيخ": "Watermelon", "شمام": "Melon", "كيوي": "Kiwi",
    "جوافة": "Guava", "تين": "Figs", "كرز": "Cherry", "فواكه": "Fruits", "فاكهة": "Fruit", "خضار": "Vegetables",
    "خضروات": "Vegetables", "بندورة": "Tomatoes", "طماطم": "Tomatoes", "خيار": "Cucumbers", "بطاطا": "Potatoes",
    "بطاطس": "Potatoes", "بصل": "Onions", "ثوم": "Garlic", "جزر": "Carrots", "كوسا": "Zucchini", "باذنجان": "Eggplant",
    "ملفوف": "Cabbage", "زهرة": "Cauliflower", "خس": "Lettuce", "بقدونس": "Parsley", "كزبرة": "Coriander",
    "سبانخ": "Spinach", "ملوخية": "Molokhia", "بامية": "Okra", "فطر": "Mushrooms", "بازيلاء": "Peas", "فلافل": "Falafel",
    # لحوم ومجمدات
    "لحمة": "Meat", "لحم": "Meat", "لحوم": "Meat", "دجاج": "Chicken", "جاج": "Chicken", "فراخ": "Chicken",
    "صدر": "Breast", "صدور": "Breasts", "أفخاذ": "Thighs", "افخاذ": "Thighs", "أجنحة": "Wings", "اجنحه": "Wings",
    "كبدة": "Liver", "كفتة": "Kofta", "برغر": "Burger", "نقانق": "Sausages", "مرتديلا": "Mortadella",
    "سلامي": "Salami", "سمك": "Fish", "روبيان": "Shrimp", "جمبري": "Shrimp", "عجل": "Veal", "غنم": "Lamb",
    "خروف": "Lamb", "بقر": "Beef", "مفروم": "Minced", "مجمدات": "Frozen Food", "دواجن": "Poultry", "ملحمة": "Butcher",
    "شاورما": "Shawarma", "ناجتس": "Nuggets", "زنجر": "Zinger",
    # حلويات وتسالي
    "شوكولاتة": "Chocolate", "شوكولاته": "Chocolate", "شوكلاته": "Chocolate", "شوكولا": "Chocolate",
    "حلويات": "Sweets", "حلوى": "Candy", "سكاكر": "Candy", "علكة": "Chewing Gum", "شيبس": "Chips", "شبس": "Chips",
    "تسالي": "Snacks", "سناكات": "Snacks", "سناك": "Snack", "بوظة": "Ice Cream", "ايس": "Ice", "آيس": "Ice",
    "كريم": "Cream", "جلي": "Jelly", "كسترد": "Custard", "بودنج": "Pudding", "بوشار": "Popcorn", "فشار": "Popcorn",
    "معمول": "Ma'amoul", "بقلاوة": "Baklava", "كنافة": "Knafeh", "هريسة": "Harissa",
    # تنظيف وعناية
    "منظف": "Cleaner", "منظفات": "Detergents", "صابون": "Soap", "شامبو": "Shampoo", "بلسم": "Conditioner",
    "معطر": "Freshener", "مطهر": "Disinfectant", "كلور": "Bleach", "كلوركس": "Clorox", "مسحوق": "Powder",
    "سائل": "Liquid", "غسيل": "Laundry", "أسنان": "Teeth", "اسنان": "Teeth", "فرشاة": "Brush",
    "فرشايه": "Brush", "مناديل": "Tissues", "محارم": "Tissues", "ورق": "Paper", "ورقية": "Paper", "تواليت": "Toilet",
    "حفاضات": "Diapers", "حفاض": "Diapers", "فوط": "Pads", "شفرات": "Razors", "مزيل": "Remover", "عرق": "Deodorant",
    "كريمات": "Creams", "لوشن": "Lotion", "عطر": "Perfume", "معقم": "Sanitizer", "أكياس": "Bags", "اكياس": "Bags",
    "نفايات": "Garbage", "زبالة": "Garbage", "ألمنيوم": "Aluminum Foil", "المنيوم": "Aluminum Foil", "نايلون": "Plastic Wrap",
    "إسفنج": "Sponge", "اسفنج": "Sponge", "ليفة": "Scrubber", "قفازات": "Gloves", "شمع": "Candles", "ولاعة": "Lighter",
    "كبريت": "Matches", "بطارية": "Battery", "بطاريات": "Batteries", "لمبة": "Light Bulb", "نظافة": "Cleaning",
    "تنظيف": "Cleaning", "عناية": "Care", "شخصية": "Personal", "منزلية": "Household", "أدوات": "Tools", "ادوات": "Tools",
    "قرطاسية": "Stationery", "دفتر": "Notebook", "قلم": "Pen", "أقلام": "Pens", "سجائر": "Cigarettes", "دخان": "Tobacco",
    "معسل": "Shisha Tobacco", "فحم": "Charcoal", "غاز": "Gas", "أطفال": "Kids", "اطفال": "Kids", "طفل": "Baby",
    "رضع": "Infant", "مواد": "Goods", "تموينية": "Groceries", "تموين": "Groceries",
    "بقالة": "Grocery", "سوبرماركت": "Supermarket", "متفرقات": "Miscellaneous", "أخرى": "Other", "اخرى": "Other",
    "عامة": "General", "عام": "General", "خدمات": "Services", "خدمة": "Service", "توصيل": "Delivery", "رسوم": "Fee",
    "تغليف": "Packaging", "كيس": "Bag", "شنطة": "Bag", "كرتونة": "Carton", "كرتونه": "Carton", "كرتون": "Carton",
    "علبة": "Pack", "علبه": "Pack", "قنينة": "Bottle", "زجاجة": "Bottle", "عبوة": "Pack", "ربطة": "Bundle",
    "طرد": "Parcel", "صندوق": "Box", "باكيت": "Packet", "كوب": "Cup", "أكواب": "Cups", "صحون": "Plates",
    "ملاعق": "Spoons", "شوك": "Forks", "رول": "Roll", "رولات": "Rolls", "قطع": "Pieces", "وجبة": "Meal",
    "شرنك": "Shrink Pack", "دزينة": "Dozen", "طبق": "Tray", "حزمة": "Bundle",
    # صفات
    "طازج": "Fresh", "طازجة": "Fresh", "طازه": "Fresh", "طازة": "Fresh", "أبيض": "White", "ابيض": "White",
    "بيضاء": "White", "بيضا": "White", "أحمر": "Red", "احمر": "Red", "حمراء": "Red", "أخضر": "Green",
    "اخضر": "Green", "خضراء": "Green", "أسود": "Black", "اسود": "Black", "سوداء": "Black", "أصفر": "Yellow",
    "صفراء": "Yellow", "بني": "Brown", "كامل": "Full", "كاملة": "Full", "الدسم": "Fat", "دسم": "Fat",
    "قليل": "Low", "قليلة": "Low", "خالي": "Free", "خالية": "Free", "كبير": "Large", "كبيرة": "Large",
    "صغير": "Small", "صغيرة": "Small", "وسط": "Medium", "متوسط": "Medium", "عائلي": "Family Size",
    "مجمد": "Frozen", "مجمدة": "Frozen", "مبرد": "Chilled", "مبردة": "Chilled", "باردة": "Cold", "بارد": "Cold",
    "ساخنة": "Hot", "ساخن": "Hot", "حار": "Spicy", "حارة": "Spicy", "حلو": "Sweet", "حلوة": "Sweet",
    "مالح": "Salted", "مملح": "Salted", "مدخن": "Smoked", "مقلي": "Fried", "مشوي": "Grilled", "محمص": "Roasted",
    "عضوي": "Organic", "طبيعي": "Natural", "طبيعية": "Natural", "بلدي": "Local", "بلدية": "Local",
    "مستورد": "Imported", "رائب": "Rayeb", "بسمتي": "Basmati", "مصري": "Egyptian", "أمريكي": "American",
    "امريكي": "American", "تركي": "Turkish", "سوري": "Syrian", "فلسطيني": "Palestinian", "أردني": "Jordanian",
    "ناعم": "Fine", "ناعمة": "Fine", "خشن": "Coarse", "جاف": "Dry", "جافة": "Dry", "معدنية": "Mineral",
    "معدني": "Mineral", "مدمس": "Cooked", "مجدول": "Medjool", "مجهول": "Medjool", "مطبوخ": "Cooked", "سريع": "Instant", "سريعة": "Instant",
    "فوري": "Instant", "فورية": "Instant", "مركز": "Concentrate", "مركزة": "Concentrated", "خفيف": "Light",
    "لايت": "Light", "دايت": "Diet", "زيرو": "Zero", "حب": "Whole", "مقشر": "Peeled", "مطحون": "Ground",
    "مبشور": "Grated", "شرائح": "Slices", "مكعب": "Cubed", "تالف": "Damaged", "جديد": "New", "جديدة": "New",
    "ممتاز": "Premium", "ممتازة": "Premium", "فاخر": "Deluxe", "اقتصادي": "Economy", "توفير": "Value Pack",
    "عربي": "Arabic", "عربية": "Arabic", "إيطالي": "Italian", "ايطالي": "Italian", "فرنسي": "French",
    "صيني": "Chinese", "هندي": "Indian", "مغربي": "Moroccan", "لبناني": "Lebanese", "يوناني": "Greek",
    "بالسمسم": "with Sesame", "بالشوكولاتة": "with Chocolate", "بالحليب": "with Milk", "بالجبنة": "with Cheese",
    "بالفراولة": "Strawberry", "بالتمر": "with Dates", "بالزعتر": "with Za'atar", "بالليمون": "Lemon",
    "بالنعناع": "Mint", "بالعسل": "Honey", "بالفانيلا": "Vanilla",
    # كلمات وصل
    "مع": "with", "و": "&", "او": "or", "أو": "or", "من": "of", "في": "in", "بدون": "without", "بلا": "without",
    "على": "on", "عرض": "Offer",
    # أسماء شائعة (العملاء والموردون)
    "محمد": "Mohammad", "أحمد": "Ahmad", "احمد": "Ahmad", "محمود": "Mahmoud", "علي": "Ali", "عمر": "Omar",
    "خالد": "Khaled", "يوسف": "Yousef", "إبراهيم": "Ibrahim", "ابراهيم": "Ibrahim", "مصطفى": "Mustafa",
    "حسن": "Hasan", "حسين": "Hussein", "عبد": "Abd", "عبدالله": "Abdullah", "الله": "Allah", "الرحمن": "Al-Rahman",
    "الرحيم": "Al-Rahim", "العزيز": "Al-Aziz", "الكريم": "Al-Karim", "سعيد": "Saeed", "سامي": "Sami", "سامر": "Samer",
    "رامي": "Rami", "فادي": "Fadi", "شادي": "Shadi", "هاني": "Hani", "ماهر": "Maher", "ناصر": "Nasser",
    "نادر": "Nader", "وليد": "Waleed", "ياسر": "Yasser", "طارق": "Tareq", "زيد": "Zaid", "إياد": "Iyad",
    "اياد": "Iyad", "باسل": "Basel", "بلال": "Bilal", "جهاد": "Jihad", "حازم": "Hazem", "رائد": "Raed",
    "عادل": "Adel", "فراس": "Firas", "كريم": "Karim", "مازن": "Mazen", "وسيم": "Waseem", "ليث": "Laith",
    "أنس": "Anas", "انس": "Anas", "خليل": "Khalil", "صالح": "Saleh", "سارة": "Sara", "ريم": "Reem", "لينا": "Lina",
    "هبة": "Hiba", "حنان": "Hanan", "نور": "Nour", "مريم": "Mariam", "فاطمة": "Fatima", "عائشة": "Aisha",
    "أبو": "Abu", "ابو": "Abu", "أم": "Umm", "ام": "Umm", "بن": "bin", "العابد": "Al-Abed", "النجار": "Al-Najjar",
    "الحداد": "Al-Haddad", "شركة": "Company", "مؤسسة": "Est.", "محل": "Shop", "محلات": "Stores", "سوق": "Market",
    "مخزن": "Store", "موزع": "Distributor", "مورد": "Supplier", "معرض": "Showroom", "مكتب": "Office",
    "القدس": "Jerusalem", "الخليل": "Hebron", "نابلس": "Nablus", "رام": "Ram", "غزة": "Gaza", "جنين": "Jenin",
    "فلسطين": "Palestine", "الوطنية": "National", "الحي": "Neighborhood", "الريف": "Countryside",
    "الأمل": "Al-Amal", "السلام": "Al-Salam", "النور": "Al-Nour", "هدية": "Gift", "مجانا": "Free", "مجاناً": "Free", "جملة": "Wholesale",
}

# علامات تجارية شائعة في المنطقة
_BRANDS = {
    "المراعي": "Almarai", "مراعي": "Almarai", "نيدو": "Nido", "نستله": "Nestle", "نستلة": "Nestle",
    "بيبسي": "Pepsi", "كوكاكولا": "Coca-Cola", "كوكا": "Coca", "فانتا": "Fanta", "سبرايت": "Sprite",
    "ميرندا": "Mirinda", "شويبس": "Schweppes", "ريدبول": "Red Bull",
    "ريد": "Red", "بول": "Bull", "تايد": "Tide", "اريال": "Ariel", "أريال": "Ariel", "داوني": "Downy",
    "فيري": "Fairy", "ليبتون": "Lipton", "جالاكسي": "Galaxy", "كيتكات": "KitKat", "سنيكرز": "Snickers",
    "تويكس": "Twix", "باونتي": "Bounty", "مارس": "Mars", "اوريو": "Oreo", "أوريو": "Oreo", "ليز": "Lay's",
    "شيبسي": "Chipsy", "دوريتوس": "Doritos", "برينجلز": "Pringles", "كيري": "Kiri", "بوك": "Puck",
    "نادك": "Nadec", "لورباك": "Lurpak", "هاينز": "Heinz", "كنور": "Knorr", "ماجي": "Maggi", "عافية": "Afia",
    "بانتين": "Pantene", "سيجنال": "Signal", "كولجيت": "Colgate", "لوكس": "Lux", "دوف": "Dove",
    "بامبرز": "Pampers", "هجيز": "Huggies", "فاين": "Fine", "كلينكس": "Kleenex", "سانيتا": "Sanita",
    "اكوافينا": "Aquafina", "أكوافينا": "Aquafina", "نوفا": "Nova", "الجنيدي": "Al-Junaidi", "جنيدي": "Junaidi",
    "سنيورة": "Siniora", "حمودة": "Hamoudeh", "تبوزينا": "Tapuzina", "بريل": "Pril", "بونكس": "Bonux",
    "نيفيا": "Nivea", "جيليت": "Gillette", "هيد": "Head", "شولدرز": "Shoulders", "هيرباليف": "Herbalife",
    "نوتيلا": "Nutella", "لوزين": "Lusine", "بوني": "Bonny", "فريسكو": "Fresco", "الصافي": "Al Safi",
    "بيرسيل": "Persil", "فلاش": "Flash", "ديتول": "Dettol", "بيبي": "Baby", "جونسون": "Johnson's",
    "كادبوري": "Cadbury", "ميلكا": "Milka", "توبليرون": "Toblerone", "فيريرو": "Ferrero", "روشيه": "Rocher",
    "مالبورو": "Marlboro", "ونستون": "Winston", "تشيتوس": "Cheetos",
    "نسكويك": "Nesquik", "سيريلاك": "Cerelac", "سيميلاك": "Similac",
    "أبتاميل": "Aptamil", "ابتاميل": "Aptamil", "بيبيلاك": "Bebelac",
}

# عبارات من أكثر من كلمة
_RAW_PHRASES = {
    "معجون أسنان": "Toothpaste", "معجون اسنان": "Toothpaste", "فرشاة أسنان": "Toothbrush",
    "سائل جلي": "Dish Soap", "سائل غسيل": "Liquid Detergent", "مسحوق غسيل": "Laundry Powder",
    "ورق تواليت": "Toilet Paper", "ورق محارم": "Tissues", "محارم ورقية": "Tissues", "مزيل عرق": "Deodorant",
    "فول مدمس": "Fava Beans (Ful)", "حمص حب": "Chickpeas", "زيت زيتون": "Olive Oil", "زيت ذرة": "Corn Oil",
    "زيت دوار الشمس": "Sunflower Oil", "زيت نباتي": "Vegetable Oil", "معجون طماطم": "Tomato Paste",
    "معجون بندورة": "Tomato Paste", "رب بندورة": "Tomato Paste", "ماء معدني": "Mineral Water",
    "مياه معدنية": "Mineral Water", "ماء معدنية": "Mineral Water", "مشروب غازي": "Soft Drink",
    "مشروبات غازية": "Soft Drinks", "مشروب طاقة": "Energy Drink", "شاي أخضر": "Green Tea", "شاي اخضر": "Green Tea",
    "قهوة عربية": "Arabic Coffee", "قهوة تركية": "Turkish Coffee", "كامل الدسم": "Full Fat",
    "قليل الدسم": "Low Fat", "خالي الدسم": "Fat Free", "خالي من السكر": "Sugar Free", "بدون سكر": "Sugar Free",
    "لبن رائب": "Yogurt (Laban)", "جبنة بيضاء": "White Cheese", "جبنة صفراء": "Yellow Cheese",
    "جبنة مثلثات": "Cheese Triangles", "آيس كريم": "Ice Cream", "ايس كريم": "Ice Cream", "بيكنج باودر": "Baking Powder",
    "رقائق الذرة": "Corn Flakes", "كورن فليكس": "Corn Flakes", "حليب أطفال": "Infant Formula", "حليب اطفال": "Infant Formula",
    "حليب بودرة": "Powdered Milk", "حليب مجفف": "Powdered Milk", "حلاوة طحينية": "Halva", "مكعبات مرق": "Stock Cubes",
    "ورق ألمنيوم": "Aluminum Foil", "ورق المنيوم": "Aluminum Foil", "أكياس نفايات": "Garbage Bags",
    "اكياس نفايات": "Garbage Bags", "أكياس زبالة": "Garbage Bags", "معطر جو": "Air Freshener",
    "منظف أرضيات": "Floor Cleaner", "منظف ارضيات": "Floor Cleaner", "منظف زجاج": "Glass Cleaner",
    "عناية شخصية": "Personal Care", "أدوات منزلية": "Household Items", "ادوات منزلية": "Household Items",
    "مواد تموينية": "Groceries", "مواد غذائية": "Food", "مواد تنظيف": "Cleaning Supplies", "خبز عربي": "Arabic Bread",
    "خبز توست": "Toast Bread", "كعك بالسمسم": "Sesame Ka'ak", "رأس عجل": "Ras Ajal", "سفن أب": "7Up", "سفن اب": "7Up",
    "ريد بول": "Red Bull", "هيد اند شولدرز": "Head & Shoulders", "هيد آند شولدرز": "Head & Shoulders",
    "رسوم توصيل": "Delivery Fee", "دجاج كامل": "Whole Chicken", "جاج كامل": "Whole Chicken", "خضار وفواكه": "Fruits & Vegetables", "خضار و فواكه": "Fruits & Vegetables",
    "حب العزيز": "Tiger Nuts", "بزر بطيخ": "Watermelon Seeds", "بزر عباد الشمس": "Sunflower Seeds",
}

# الوحدات بعد الأرقام
_UNITS = {"لتر": "L", "ليتر": "L", "ل": "L", "مل": "ml", "ملل": "ml", "ملي": "ml", "غم": "g", "غ": "g",
          "غرام": "g", "جرام": "g", "جم": "g", "جرام.": "g", "كغم": "kg", "كغ": "kg", "كيلو": "kg", "كيلوغرام": "kg",
          "كجم": "kg", "كلغ": "kg", "حبة": "pcs", "حبه": "pcs", "حبات": "pcs", "قطعة": "pcs", "قطع": "pcs",
          "سم": "cm", "متر": "m", "م": "m", "رول": "rolls", "كيس": "bags", "علبة": "packs", "علب": "packs"}

# أسماء تأتي في العربية أولاً ثم ما يضاف إليها (عصير برتقال ← Orange Juice)
_HEADS = {"Juice", "Oil", "Paste", "Sauce", "Powder", "Liquid", "Soap", "Shampoo", "Jam", "Cake", "Biscuits",
          "Chips", "Bread", "Tea", "Coffee", "Water", "Milk", "Yogurt", "Cheese", "Cream", "Ice Cream", "Chocolate",
          "Cleaner", "Bags", "Pack", "Bottle", "Carton", "Box", "Bag", "Jelly", "Syrup", "Drink", "Candy", "Seeds",
          "Brush", "Spices", "Wafer", "Flour", "Pasta", "Stock", "Meat", "Burger", "Sausages", "Labneh", "Laban"}
_ADJ = {"Fresh", "White", "Red", "Green", "Black", "Yellow", "Brown", "Large", "Small", "Medium", "Family Size",
        "Frozen", "Chilled", "Cold", "Hot", "Spicy", "Sweet", "Salted", "Smoked", "Fried", "Grilled", "Roasted",
        "Organic", "Natural", "Local", "Imported", "Basmati", "Egyptian", "American", "Turkish", "Syrian",
        "Palestinian", "Jordanian", "Fine", "Coarse", "Dry", "Mineral", "Cooked", "Instant", "Light", "Diet",
        "Peeled", "Ground", "Grated", "Damaged", "New", "Premium", "Deluxe", "Economy", "Arabic", "Italian",
        "French", "Chinese", "Indian", "Moroccan", "Lebanese", "Greek", "Sparkling", "Concentrated", "Personal",
        "Household", "Minced", "Rayeb", "Whole", "Medjool"}

WORDS = {norm(k.rstrip("_")): v for k, v in _RAW_WORDS.items()}
WORDS.update({norm(k): v for k, v in _BRANDS.items() if not k.endswith("_")})
PHRASES = {tuple(norm(w) for w in k.split()): v for k, v in _RAW_PHRASES.items()}
_MAX_PHRASE = max(len(k) for k in PHRASES)
UNITS = {norm(k): v for k, v in _UNITS.items()}
_BRAND_VALUES = set(_BRANDS.values())

# ---------------------------------------------------------------- كتابة ما لا يُعرف بحروف لاتينية
_LAT = {"ا": "a", "أ": "a", "إ": "i", "آ": "aa", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
        "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z",
        "ع": "'", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "a",
        "و": "o", "ي": "i", "ى": "a", "ء": "'", "ؤ": "o", "ئ": "e", "پ": "p", "ڤ": "v", "گ": "g", "چ": "ch"}
_VOWELS = set("اأإآةوىيؤئ")


def transliterate(word):
    w = _TASHKEEL.sub("", word)
    prefix = ""
    if w.startswith("ال") and len(w) > 3:
        prefix, w = "Al-", w[2:]
    out, prev_cons, prev2_cons = [], False, False
    for i, ch in enumerate(w):
        if ch == "و":
            lat = "w" if i == 0 or (i + 1 < len(w) and w[i + 1] in "اي") else "o"
        elif ch == "ي":
            lat = "y" if i == 0 or (i + 1 < len(w) and w[i + 1] in "او") else "i"
        elif ch == "ع":
            lat = "a" if i == 0 else "'"
        elif ch in ("ه",) and i == len(w) - 1 and i > 0:
            lat = "a" if w[i - 1] not in _VOWELS else "h"
        else:
            lat = _LAT.get(ch, ch)
        cons = ch not in _VOWELS and lat not in ("a", "i", "o", "'")
        if lat and lat[0] in "aeiou":
            cons = False
        if cons and prev_cons and (len(out) == 1 or prev2_cons):
            out.append("a")                       # «سنيورة» ← Saniora بدل Sniora
            prev2_cons = False
        else:
            prev2_cons = prev_cons
        out.append(lat)
        prev_cons = cons
    s = "".join(out).replace("''", "'").strip("'")
    s = s[:1].upper() + s[1:] if s else s
    return prefix + s if prefix else s


# ---------------------------------------------------------------- الترجمة
_NUM = re.compile(r"^[\d٠-٩]+([.,٫][\d٠-٩]+)?$")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def _word(tok):
    """(الإنجليزية، هل من القاموس)"""
    n = norm(tok)
    if n in WORDS:
        return WORDS[n], True
    for pre, eng in (("بال", "with "), ("وال", "& "), ("لل", "for "), ("ال", ""), ("و", "& "), ("ب", "with ")):
        if n.startswith(pre) and len(n) - len(pre) >= 2:
            rest = n[len(pre):]
            if rest in WORDS:
                return (eng + WORDS[rest]).strip(), True
            if pre in ("وال", "بال", "لل") and "ال" + rest in WORDS:
                return (eng + WORDS["ال" + rest]).strip(), True
    return transliterate(tok), False


def auto_translate(text):
    """ترجمة تلقائية لاسم قصير (صنف، فئة، اسم)"""
    toks = text.split()
    out = []           # (english, kind)  kind: noun / adj / brand / num / unit / x
    i = 0
    while i < len(toks):
        hit = None
        for n in range(min(_MAX_PHRASE, len(toks) - i), 1, -1):
            key = tuple(norm(t) for t in toks[i:i + n])
            if key in PHRASES:
                hit = (PHRASES[key], n)
                break
        if hit:
            out.append((hit[0], "noun"))
            i += hit[1]
            continue
        tok = toks[i]
        t = tok.translate(_AR_DIGITS)
        if _NUM.match(t) or not re.search(r"[؀-ۿ]", tok):
            out.append((t, "num" if _NUM.match(t) else "x"))
        elif norm(tok) in UNITS and out and out[-1][1] == "num":
            out.append((UNITS[norm(tok)], "unit"))
        else:
            eng, known = _word(tok)
            kind = "brand" if eng in _BRAND_VALUES else ("adj" if eng in _ADJ else "noun") if known else "x"
            out.append((eng, kind))
        i += 1
    # الصفة قبل الموصوف، والمضاف إليه قبل المضاف (حليب طازج ← Fresh Milk، عصير برتقال ← Orange Juice)
    j = 1
    while j < len(out):
        (a, ka), (b, kb) = out[j - 1], out[j]
        if ka == "noun" and kb == "adj":
            out[j - 1], out[j] = out[j], out[j - 1]
        elif ka == "noun" and kb == "noun" and a in _HEADS:
            out[j - 1], out[j] = out[j], out[j - 1]
        j += 1
    # الترتيب الإنجليزي قبل الأرقام: العلامة التجارية ثم الصفات ثم الأسماء (عصير تفاح طبيعي ← Natural Apple Juice)
    cut = next((k for k, x in enumerate(out) if x[1] in ("num", "unit")), len(out))
    head, tail = out[:cut], out[cut:]
    head = [x for x in head if x[1] == "brand"] + [x for x in head if x[1] == "adj"] + \
        [x for x in head if x[1] not in ("brand", "adj")]
    out = head + tail
    words = []
    for eng, kind in out:
        if kind == "unit" and words:
            words[-1] = words[-1] + " " + eng
        else:
            words.append(eng)
    return " ".join(words).replace("& &", "&").strip()


# ---------------------------------------------------------------- أسماء صاحب المحل
_custom = {}
_loaded_at = 0.0
_lock = threading.Lock()
_busy = threading.local()
TTL = 30


def _custom_names():
    global _custom, _loaded_at
    if time.time() - _loaded_at < TTL:
        return _custom
    if getattr(_busy, "on", False):
        return _custom
    _busy.on = True
    try:
        from core import products, remote
        if remote.is_client() and not getattr(remote.CLIENT, "token", None):
            raise RuntimeError("not signed in yet")
        new = dict(products.english_names())
    except Exception:
        new = _custom
    finally:
        _busy.on = False
    with _lock:
        changed = new != _custom
        _custom, _loaded_at = new, time.time()
    if changed:
        from core import i18n
        i18n.clear_cache()
    return _custom


def invalidate():
    """بعد حفظ اسم إنجليزي لصنف: يظهر فوراً"""
    global _loaded_at
    _loaded_at = 0.0
    from core import i18n
    i18n.clear_cache()


_SKIP = re.compile(r"[:؟?!\n،؛]|\.\s|\.$|https?://|@")


def english(text):
    """الاسم الإنجليزي لنص بيانات قصير، أو None إن لم يكن مناسباً (جملة طويلة أو نص واجهة)"""
    s = text.strip()
    if not s:
        return None
    custom = _custom_names().get(s)
    if custom:
        return text.replace(s, custom)
    if _SKIP.search(s) or len(s.split()) > 8:
        return None
    out = auto_translate(s)
    return text.replace(s, out) if out and out != s else None
