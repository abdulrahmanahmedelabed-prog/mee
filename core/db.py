# -*- coding: utf-8 -*-
"""
طبقة قاعدة البيانات: الاتصال، المعاملات، إنشاء الجداول والترقية من النسخ السابقة.

- كل العمليات المالية تتم داخل معاملة واحدة (tx) فإما أن تنجح كاملة أو تُلغى كاملة.
- الأوقات تُخزّن بالتوقيت المحلي للجهاز (وليس UTC) حتى تكون تقارير "اليوم" صحيحة.
"""

import os
import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime

SCHEMA_VERSION = 3


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


def get_connection():
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
    refund_method TEXT NOT NULL,     -- نقدي / خصم من الدين
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
    "products": [
        ("plu_code", "TEXT"),                       # رمز الميزان للمنتجات الموزونة
        ("is_weighted", "INTEGER NOT NULL DEFAULT 0"),
        ("is_favorite", "INTEGER NOT NULL DEFAULT 0"),  # يظهر كزر سريع في نقطة البيع
        ("updated_at", "TEXT"),
    ],
    "customers": [
        ("address", "TEXT"),
        ("credit_limit", "REAL NOT NULL DEFAULT 0"),  # 0 = بلا حد
        ("notes", "TEXT"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
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
        ("status", "TEXT NOT NULL DEFAULT 'completed'"),
        ("note", "TEXT"),
        ("user_id", "INTEGER"),
        ("shift_id", "INTEGER"),
        ("terminal", "TEXT"),
    ],
    "invoice_items": [
        ("returned_qty", "REAL NOT NULL DEFAULT 0"),
        ("unit_name", "TEXT"),
        ("factor", "REAL NOT NULL DEFAULT 1"),     # كم وحدة أساسية في الوحدة المباعة
    ],
    "return_items": [
        ("factor", "REAL NOT NULL DEFAULT 1"),
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
"""


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
        conn.commit()
    finally:
        conn.close()

    # إعدادات افتراضية + مستخدم مدير أول مرة
    from core import settings, auth
    settings.ensure_defaults()
    auth.ensure_admin()


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
