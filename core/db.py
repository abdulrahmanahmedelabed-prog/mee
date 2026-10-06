# -*- coding: utf-8 -*-
"""
طبقة قاعدة البيانات: الاتصال، المعاملات، إنشاء الجداول والترقية من النسخ السابقة.

- كل العمليات المالية تتم داخل معاملة واحدة (tx) فإما أن تنجح كاملة أو تُلغى كاملة.
- الأوقات تُخزّن بالتوقيت المحلي للجهاز (وليس UTC) حتى تكون تقارير "اليوم" صحيحة.
"""

import os
import threading
import urllib.parse
import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

SCHEMA_VERSION = 9


def app_dir():
    """مجلد البرنامج (يعمل أيضاً بعد التحويل لملف exe عبر PyInstaller)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DATA_DIR = os.environ.get("SHOP_DATA_DIR") or os.path.join(app_dir(), "data")
DB_PATH = os.path.join(DATA_DIR, "accounting.db")


def set_db_path(path):
    """تغيير مسار قاعدة البيانات (يُستخدم في الاختبارات)"""
    global DB_PATH, DATA_DIR
    DB_PATH = path
    DATA_DIR = os.path.dirname(path)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


_SHARED = None   # اتصال مشترك أثناء bulk_session فقط (توليد بيانات كثيرة بسرعة)


class _SharedConn:
    """غلاف للاتصال المشترك: الإغلاق والحفظ يتمان مرة واحدة في نهاية الجلسة"""

    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, name):
        return getattr(self._c, name)

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


@contextmanager
def bulk_session(commit_every=None):
    """لأدوات التوليد والاستيراد الكبيرة: كل العمليات على اتصال واحد، وكل معاملة تبقى ذرّية بنقطة حفظ (SAVEPOINT).
    يرجع دالة commit() لحفظ ما سبق دورياً."""
    global _SHARED
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("BEGIN")
    _SHARED = _SharedConn(conn)

    def commit():
        conn.execute("COMMIT")
        conn.execute("BEGIN")
    try:
        yield commit
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        _SHARED = None
        conn.close()


_READONLY = threading.local()     # قراءة تقارير من ملف آخر (نسخة فرع) في هذا الخيط فقط


@contextmanager
def reading(path):
    """داخل هذا السياق تقرأ استعلامات هذا الخيط من ملف قاعدة بيانات آخر للقراءة فقط (تقارير الفروع).
    الخيوط الأخرى (خادم الشبكة، الواجهة) لا تتأثر."""
    prev = getattr(_READONLY, "path", None)
    _READONLY.path = path
    try:
        yield
    finally:
        _READONLY.path = prev


def get_connection():
    ro = getattr(_READONLY, "path", None)
    if ro:
        path = os.path.abspath(ro).replace(os.sep, "/")
        path = path if path.startswith("/") else "/" + path          # C:/... في ويندوز
        uri = "file://" + urllib.parse.quote(path, safe="/:") + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn
    if _SHARED is not None:
        return _SHARED
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def tx():
    """معاملة ذرّية: commit عند النجاح و rollback عند أي خطأ"""
    conn = get_connection()
    if conn is _SHARED:
        conn.execute("SAVEPOINT tx")
        try:
            yield conn
            conn.execute("RELEASE tx")
        except Exception:
            conn.execute("ROLLBACK TO tx")
            conn.execute("RELEASE tx")
            raise
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, params=()):
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def query_one(sql, params=()):
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def scalar(sql, params=(), default=0):
    row = query_one(sql, params)
    if row is None or row[0] is None:
        return default
    return row[0]


def next_number(conn, name, prefix):
    """ترقيم تسلسلي آمن لا يتكرر حتى لو حُذفت سجلات (بخلاف COUNT(*) في النسخة الأولى)"""
    conn.execute("INSERT OR IGNORE INTO counters(name, value) VALUES (?, 0)", (name,))
    conn.execute("UPDATE counters SET value = value + 1 WHERE name=?", (name,))
    value = conn.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()[0]
    return f"{prefix}-{value:06d}"


# ---------------------------------------------------------------------------
# إنشاء الجداول
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'cashier',
    must_change_password INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    barcode TEXT UNIQUE,
    category TEXT,
    cost_price REAL NOT NULL DEFAULT 0,
    sale_price REAL NOT NULL DEFAULT 0,
    quantity REAL NOT NULL DEFAULT 0,
    min_quantity REAL NOT NULL DEFAULT 0,
    unit TEXT DEFAULT 'قطعة',
    created_at TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    balance REAL DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS customer_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    type TEXT NOT NULL,              -- sale / payment / return / opening / adjust
    amount REAL NOT NULL,            -- موجب = يزيد دين العميل، سالب = ينقصه
    method TEXT,                     -- طريقة الدفع عند التسديد
    invoice_id INTEGER,
    note TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS supplier_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    type TEXT NOT NULL,              -- purchase / payment / return / opening / adjust
    amount REAL NOT NULL,            -- موجب = يزيد ما علينا للمورد
    method TEXT,
    purchase_id INTEGER,
    note TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    total REAL NOT NULL DEFAULT 0,
    discount REAL NOT NULL DEFAULT 0,
    paid REAL NOT NULL DEFAULT 0,
    payment_method TEXT DEFAULT 'نقدي',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    product_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    cost_price REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_number TEXT UNIQUE,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    total REAL NOT NULL,
    tax REAL NOT NULL DEFAULT 0,
    cost_total REAL NOT NULL DEFAULT 0,
    refund_method TEXT NOT NULL,     -- نقدي / خصم من الدين / بطاقة / اسم المحفظة
    reason TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    invoice_item_id INTEGER NOT NULL REFERENCES invoice_items(id),
    product_id INTEGER NOT NULL,
    product_name TEXT,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    cost_price REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_number TEXT UNIQUE,
    supplier_id INTEGER REFERENCES suppliers(id),
    supplier_ref TEXT,
    total REAL NOT NULL DEFAULT 0,
    paid REAL NOT NULL DEFAULT 0,
    payment_method TEXT,
    note TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    product_name TEXT,
    quantity REAL NOT NULL,
    unit_cost REAL NOT NULL,
    total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT,
    from_drawer INTEGER NOT NULL DEFAULT 1,
    expense_date TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    opened_at TEXT,
    closed_at TEXT,
    opening_cash REAL NOT NULL DEFAULT 0,
    expected_cash REAL,
    counted_cash REAL,
    difference REAL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS cash_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL REFERENCES shifts(id),
    amount REAL NOT NULL,            -- موجب = إدخال للصندوق، سالب = سحب
    reason TEXT,
    user_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS held_carts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT,
    data TEXT NOT NULL,
    user_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    change_qty REAL NOT NULL,
    reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS product_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name TEXT NOT NULL,              -- مثل: كرتونة، علبة 6، درزن
    factor REAL NOT NULL,            -- كم وحدة أساسية فيها (كرتونة = 24 حبة)
    barcode TEXT UNIQUE,
    sale_price REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS product_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    batch_no TEXT,
    expiry_date TEXT,
    quantity REAL NOT NULL,          -- الكمية المستلمة (بالوحدة الأساسية)
    remaining REAL NOT NULL,         -- المتبقي منها
    purchase_id INTEGER,
    created_at TEXT
);

-- ===== النسخة 4 =====
CREATE TABLE IF NOT EXISTS accounts (
    code TEXT PRIMARY KEY,           -- رقم الحساب في دليل الحسابات (مثل 1110 الصندوق)
    name TEXT NOT NULL,
    type TEXT NOT NULL,              -- asset / liability / equity / revenue / expense
    is_system INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_number TEXT UNIQUE,
    entry_date TEXT NOT NULL,
    description TEXT,
    is_void INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_code TEXT NOT NULL,
    debit REAL NOT NULL DEFAULT 0,
    credit REAL NOT NULL DEFAULT 0,
    note TEXT
);

CREATE TABLE IF NOT EXISTS cheques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,         -- in = شيك وارد من عميل / out = شيك صادر لمورد
    cheque_number TEXT,
    bank TEXT,
    amount REAL NOT NULL,
    due_date TEXT NOT NULL,          -- تاريخ الاستحقاق (الشيك المؤجل)
    customer_id INTEGER REFERENCES customers(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / cleared / bounced
    status_date TEXT,
    note TEXT,
    user_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,              -- buy_get / bundle / percent
    product_id INTEGER REFERENCES products(id),
    category TEXT,
    buy_qty REAL NOT NULL DEFAULT 0,
    get_qty REAL NOT NULL DEFAULT 0,
    bundle_qty REAL NOT NULL DEFAULT 0,
    bundle_price REAL NOT NULL DEFAULT 0,
    percent REAL NOT NULL DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS loyalty_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    points REAL NOT NULL,            -- موجب = نقاط مكتسبة، سالب = مستبدلة أو ملغاة بمرتجع
    invoice_id INTEGER,
    note TEXT,
    user_id INTEGER,
    created_at TEXT
);

-- ===== الموظفون والرواتب =====
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    job TEXT,
    salary REAL NOT NULL DEFAULT 0,      -- الراتب الشهري الأساسي
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS employee_advances (     -- سلف الموظفين (تُسترد من الرواتب)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    amount REAL NOT NULL,
    method TEXT NOT NULL,
    note TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS payroll_payments (      -- صرف راتب شهر
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    period TEXT NOT NULL,                -- YYYY-MM
    base REAL NOT NULL DEFAULT 0,
    bonus REAL NOT NULL DEFAULT 0,
    deductions REAL NOT NULL DEFAULT 0,
    advances REAL NOT NULL DEFAULT 0,    -- ما خُصم من السلف
    net REAL NOT NULL DEFAULT 0,         -- المدفوع فعلاً
    method TEXT NOT NULL,
    note TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

-- ===== أقساط الزبائن =====
CREATE TABLE IF NOT EXISTS web_sessions (
    token TEXT PRIMARY KEY,           -- جلسة تطبيق الجوال أو لوحة المالك (تبقى بعد إعادة تشغيل جهاز المحل)
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,               -- mobile / owner
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS installment_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    total REAL NOT NULL,
    count INTEGER NOT NULL,
    first_due TEXT NOT NULL,
    every_days INTEGER NOT NULL DEFAULT 30,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',      -- active / done / cancelled
    start_balance REAL NOT NULL DEFAULT 0,      -- رصيد العميل عند إنشاء الخطة (لاحتساب ما سُدد منها)
    paid_before REAL NOT NULL DEFAULT 0,        -- مجموع تسديداته قبل الخطة
    user_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS purchase_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_number TEXT UNIQUE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    total REAL NOT NULL,             -- القيمة المخصومة من حساب المورد
    cost_total REAL NOT NULL DEFAULT 0,   -- قيمة البضاعة بالتكلفة الدفترية
    reason TEXT,
    user_id INTEGER,
    shift_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS purchase_return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL REFERENCES purchase_returns(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    product_name TEXT,
    quantity REAL NOT NULL,          -- بالوحدة الأساسية
    unit_cost REAL NOT NULL,
    book_cost REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL
);

-- ===== النسخة 6 =====
CREATE TABLE IF NOT EXISTS online_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT,
    fulfilment TEXT NOT NULL DEFAULT 'pickup',   -- pickup = استلام من المحل / delivery = توصيل
    note TEXT,
    items TEXT NOT NULL,                          -- JSON: [{product_id, name, quantity, unit_price}]
    total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',           -- new / preparing / ready / done / cancelled
    invoice_id INTEGER,
    source_ip TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fixed_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cost REAL NOT NULL,
    salvage REAL NOT NULL DEFAULT 0,
    purchase_date TEXT NOT NULL,
    life_months INTEGER NOT NULL,
    paid_from TEXT,                  -- حساب الدفع (NULL = مسجّل مسبقاً في الدفاتر، بلا قيد شراء)
    disposed_at TEXT,
    disposal_proceeds REAL NOT NULL DEFAULT 0,
    disposal_account TEXT,
    note TEXT,
    user_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT
);
"""

# أعمدة أُضيفت في النسخة الثانية (تُضاف تلقائياً لقواعد بيانات النسخة الأولى)
ADDED_COLUMNS = {
    "audit_log": [("chain", "TEXT")],                # ختم كل سطر في سجل العمليات (core/integrity.py)
    "products": [
        ("is_service", "INTEGER NOT NULL DEFAULT 0"),  # خدمة بلا مخزون (رسوم توصيل، تغليف...)
        ("plu_code", "TEXT"),                       # رمز الميزان للمنتجات الموزونة
        ("is_weighted", "INTEGER NOT NULL DEFAULT 0"),
        ("is_favorite", "INTEGER NOT NULL DEFAULT 0"),  # يظهر كزر سريع في نقطة البيع
        ("updated_at", "TEXT"),
        ("wholesale_price", "REAL NOT NULL DEFAULT 0"),   # سعر الجملة (0 = لا يوجد)
        ("name_en", "TEXT"),                        # الاسم بالإنجليزية (اختياري؛ وإلا ترجمة تلقائية)
    ],
    "customers": [
        ("address", "TEXT"),
        ("credit_limit", "REAL NOT NULL DEFAULT 0"),  # 0 = بلا حد
        ("notes", "TEXT"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("price_level", "TEXT NOT NULL DEFAULT 'retail'"),  # retail = مفرق / wholesale = جملة
    ],
    "invoices": [
        ("subtotal", "REAL NOT NULL DEFAULT 0"),
        ("tax", "REAL NOT NULL DEFAULT 0"),
        ("cost_total", "REAL NOT NULL DEFAULT 0"),
        ("cash_amount", "REAL NOT NULL DEFAULT 0"),
        ("card_amount", "REAL NOT NULL DEFAULT 0"),
        ("credit_amount", "REAL NOT NULL DEFAULT 0"),
        ("cash_received", "REAL NOT NULL DEFAULT 0"),
        ("change_given", "REAL NOT NULL DEFAULT 0"),
        ("returned_total", "REAL NOT NULL DEFAULT 0"),
        ("offline_ref", "TEXT"),                  # معرّف فاتورة بيعت أثناء انقطاع الشبكة (لمنع التكرار)
        ("card_ref", "TEXT"),                     # مرجع عملية البطاقة من جهاز الدفع (رقم الموافقة، RRN، آخر 4 أرقام)
        ("wallet_amount", "REAL NOT NULL DEFAULT 0"),  # المدفوع بمحفظة إلكترونية أو تطبيق بنكي
        ("wallet_name", "TEXT"),                  # اسم طريقة الدفع (PalPay، CliQ...)
        ("wallet_ref", "TEXT"),                   # رقم العملية من إشعار الزبون
        ("wallet_bank", "INTEGER NOT NULL DEFAULT 0"),  # 1 = المال يصل للبنك مباشرة، 0 = رصيد المحفظة
        ("status", "TEXT NOT NULL DEFAULT 'completed'"),
        ("note", "TEXT"),
        ("user_id", "INTEGER"),
        ("shift_id", "INTEGER"),
        ("terminal", "TEXT"),
        ("promo_discount", "REAL NOT NULL DEFAULT 0"),   # خصم العروض التلقائية (جزء من discount)
        ("points_redeemed", "REAL NOT NULL DEFAULT 0"),  # نقاط ولاء مستبدلة
        ("points_value", "REAL NOT NULL DEFAULT 0"),     # قيمتها (جزء من discount)
        ("points_earned", "REAL NOT NULL DEFAULT 0"),
        ("seal", "TEXT"),                           # ختم ضد العبث (core/integrity.py)
    ],
    "invoice_items": [
        ("returned_qty", "REAL NOT NULL DEFAULT 0"),
        ("unit_name", "TEXT"),
        ("factor", "REAL NOT NULL DEFAULT 1"),     # كم وحدة أساسية في الوحدة المباعة
    ],
    "return_items": [
        ("factor", "REAL NOT NULL DEFAULT 1"),
    ],
    "returns": [
        ("refund_account", "TEXT"),               # حساب الاسترداد: الصندوق/البنك/المحفظة/ذمم العملاء (فارغ = حسب الطريقة)
    ],
    "purchase_returns": [
        ("tax", "REAL NOT NULL DEFAULT 0"),       # ضريبة المدخلات المشمولة في المرتجع (تُعكس من حساب ضريبة المدخلات)
    ],
    "loyalty_transactions": [
        ("value", "REAL"),                        # قيمة النقاط بالعملة وقت الحركة (التزام تجاه العميل)
    ],
    "purchases": [
        ("tax", "REAL NOT NULL DEFAULT 0"),       # ضريبة المدخلات المشمولة في إجمالي فاتورة المورد
    ],
    "purchase_items": [
        ("unit_name", "TEXT"),
        ("factor", "REAL NOT NULL DEFAULT 1"),
        ("expiry_date", "TEXT"),
        ("batch_no", "TEXT"),
    ],
    "shifts": [
        ("terminal", "TEXT"),
    ],
    "held_carts": [
        ("terminal", "TEXT"),
    ],
    "stock_movements": [
        ("user_id", "INTEGER"),
        ("balance_after", "REAL"),
        ("loss_value", "REAL NOT NULL DEFAULT 0"),   # قيمة الخسارة بالتكلفة (تالف/منتهي/عجز جرد)
        ("unit_cost", "REAL"),                       # تكلفة الحبة وقت الحركة (للقيود المحاسبية)
    ],
}

INDEXES = """
CREATE INDEX IF NOT EXISTS ix_invoices_created ON invoices(created_at);
CREATE INDEX IF NOT EXISTS ix_invoices_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS ix_invoice_items_inv ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS ix_invoice_items_prod ON invoice_items(product_id);
CREATE INDEX IF NOT EXISTS ix_products_name ON products(name);
CREATE INDEX IF NOT EXISTS ix_products_plu ON products(plu_code);
CREATE INDEX IF NOT EXISTS ix_stock_prod ON stock_movements(product_id);
CREATE INDEX IF NOT EXISTS ix_ctx_customer ON customer_transactions(customer_id);
CREATE INDEX IF NOT EXISTS ix_stx_supplier ON supplier_transactions(supplier_id);
CREATE INDEX IF NOT EXISTS ix_returns_created ON returns(created_at);
CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS ix_purchases_created ON purchases(created_at);
CREATE INDEX IF NOT EXISTS ix_units_product ON product_units(product_id);
CREATE INDEX IF NOT EXISTS ix_batches_product ON product_batches(product_id, expiry_date);
CREATE INDEX IF NOT EXISTS ix_batches_expiry ON product_batches(expiry_date);
CREATE INDEX IF NOT EXISTS ix_journal_date ON journal_entries(entry_date);
CREATE INDEX IF NOT EXISTS ix_jlines_entry ON journal_lines(entry_id);
CREATE INDEX IF NOT EXISTS ix_cheques_due ON cheques(status, due_date);
CREATE INDEX IF NOT EXISTS ix_loyalty_customer ON loyalty_transactions(customer_id);
CREATE INDEX IF NOT EXISTS ix_shifts_terminal ON shifts(terminal, id);
CREATE INDEX IF NOT EXISTS ix_invoices_offline ON invoices(offline_ref);
CREATE INDEX IF NOT EXISTS ix_orders_status ON online_orders(status, id);
"""


def upgrade_file(path):
    """ترقية بنية ملف قاعدة بيانات آخر (نسخة فرع من إصدار أقدم) ليُقرأ بتقارير هذا الإصدار. لا يمس بياناته"""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        for table, cols in ADDED_COLUMNS.items():
            have = _columns(conn, table)
            for name, ddl in cols:
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        conn.commit()
    finally:
        conn.close()


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    """إنشاء قاعدة البيانات أو ترقيتها من النسخة الأولى بدون فقدان أي بيانات"""
    conn = get_connection()
    try:
        existing_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        was_v1 = "products" in existing_tables and "meta" not in existing_tables

        conn.executescript(SCHEMA)
        for table, cols in ADDED_COLUMNS.items():
            have = _columns(conn, table)
            for name, ddl in cols:
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        conn.executescript(INDEXES)

        if was_v1:
            _migrate_v1_data(conn)
        _migrate_local_settings(conn)
        from core import config
        conn.execute("UPDATE shifts SET terminal=? WHERE terminal IS NULL", (config.get("terminal_name"),))

        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('install_date', ?)", (today(),))
        conn.commit()
        _refresh_statistics(conn)
    finally:
        conn.close()

    # إعدادات افتراضية + مستخدم مدير أول مرة + دليل الحسابات
    from core import settings, auth, ledger
    settings.ensure_defaults()
    auth.ensure_admin()
    ledger.ensure_accounts()


def _refresh_statistics(conn, force=False):
    """إحصاءات الجداول لمخطِّط الاستعلامات (ANALYZE) مرة أسبوعياً: بدونها يختار SQLite طرقاً بطيئة مع البيانات الكبيرة
    (المستشار الذكي 0.9 ثانية بدلاً من 0.14). تستغرق أجزاء من الثانية."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='analyzed_at'").fetchone()
        has_stats = conn.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'").fetchone()
        stale = not row or not has_stats or row[0] < (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if force or stale:
            conn.execute("ANALYZE")
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('analyzed_at', ?)", (today(),))
            conn.commit()
    except sqlite3.Error:
        pass


def refresh_statistics():
    conn = get_connection()
    try:
        _refresh_statistics(conn, force=True)
    finally:
        if conn is not _SHARED:
            conn.close()


def get_meta(key, default=None):
    row = query_one("SELECT value FROM meta WHERE key=?", (key,))
    return row[0] if row else default


def set_meta(key, value):
    with tx() as conn:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, None if value is None else str(value)))


def _migrate_v1_data(conn):
    """النسخة الأولى كانت تحفظ الوقت بتوقيت UTC وتحفظ ديون العملاء في عمود balance فقط"""
    for table in ("invoices", "stock_movements", "products", "customers"):
        conn.execute(f"UPDATE {table} SET created_at = datetime(created_at, 'localtime') WHERE created_at IS NOT NULL")
    conn.execute("""
        UPDATE invoices SET
            subtotal = total + discount,
            cash_amount = CASE WHEN payment_method = 'نقدي' THEN total ELSE 0 END,
            card_amount = CASE WHEN payment_method = 'بطاقة' THEN total ELSE 0 END,
            credit_amount = CASE WHEN payment_method = 'آجل' THEN total ELSE 0 END,
            cost_total = COALESCE((SELECT SUM(cost_price * quantity) FROM invoice_items WHERE invoice_id = invoices.id), 0)
    """)
    # نقل أرصدة العملاء القديمة كرصيد افتتاحي في دفتر الحركات
    for c in conn.execute("SELECT id, balance FROM customers WHERE COALESCE(balance,0) != 0").fetchall():
        conn.execute("""INSERT INTO customer_transactions(customer_id, type, amount, note, created_at)
                        VALUES (?, 'opening', ?, 'رصيد منقول من النسخة الأولى', ?)""", (c["id"], c["balance"], now()))
    # ضبط عداد الفواتير ليكمل بعد الموجود
    count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO counters(name, value) VALUES ('invoice', ?)", (count,))


def _migrate_local_settings(conn):
    """النسخة 2 كانت تحفظ الطابعة في إعدادات المحل؛ الآن هي من إعدادات الجهاز"""
    from core import config
    if os.path.exists(os.path.join(DATA_DIR, "terminal.json")):
        return
    old = {r[0]: r[1] for r in conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('printer_name','receipt_width_mm','auto_print_receipt')")}
    if old:
        config.save(old)
