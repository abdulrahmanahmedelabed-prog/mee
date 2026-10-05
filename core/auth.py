# -*- coding: utf-8 -*-
"""المستخدمون وكلمات المرور والصلاحيات"""

import hashlib
import hmac
import os

from core import db, context, i18n

ROLES = {
    "admin": "مدير النظام",
    "manager": "مدير المحل",
    "cashier": "كاشير",
}

PERMISSIONS = {
    "dashboard": "لوحة التحكم",
    "pos": "نقطة البيع",
    "invoices": "سجل الفواتير",
    "returns": "المرتجعات",
    "price_override": "تغيير السعر في البيع",
    "big_discount": "خصم أعلى من الحد المسموح",
    "over_credit_limit": "تجاوز حد الدين للعميل",
    "inventory": "المخزون",
    "customers": "العملاء",
    "suppliers": "الموردون والمشتريات",
    "expenses": "المصاريف",
    "cash": "الصندوق والورديات",
    "reports": "التقارير والأرباح",
    "settings": "الإعدادات",
    "users": "المستخدمون",
    "backup": "النسخ الاحتياطي",
    "accounting": "المحاسبة (القيود والميزانية)",
    "cheques": "الشيكات",
    "promotions": "العروض ونقاط الولاء",
}

ROLE_PERMISSIONS = {
    "admin": set(PERMISSIONS),
    "manager": set(PERMISSIONS) - {"users", "settings"},
    "cashier": {"pos", "invoices", "customers", "cash"},  # الشيكات والمحاسبة للمدير فقط
}

# ---------------- كلمات المرور ----------------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 120_000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


# ---------------- المستخدمون ----------------

def ensure_admin():
    if db.scalar("SELECT COUNT(*) FROM users") == 0:
        with db.tx() as conn:
            conn.execute("""INSERT INTO users(username, full_name, password_hash, role, must_change_password, created_at)
                            VALUES ('admin', ?, ?, 'admin', 1, ?)""",
                         ("المدير" if i18n.is_rtl() else "Administrator", hash_password("admin"), db.now()))


def authenticate(username, password):
    row = db.query_one("SELECT * FROM users WHERE username=? AND is_active=1", (username.strip(),))
    if row and verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def login(username, password):
    user = authenticate(username, password)
    if user:
        context.set_user(user)
        from core import audit
        audit.log("تسجيل دخول", user["username"])
    return user


def set_current_user(user):
    context.set_user(user)


def current_user():
    return context.user()


def current_user_id():
    u = context.user()
    return u["id"] if u else None


def logout():
    context.set_user(None)


def has_permission(perm, user=None):
    user = user or context.user()
    if not user:
        return False
    return perm in ROLE_PERMISSIONS.get(user["role"], set())


def list_users():
    return db.query("SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY id")


def create_user(username, full_name, password, role):
    if role not in ROLES:
        raise ValueError("دور غير معروف")
    if not username.strip() or len(password) < 4:
        raise ValueError("اسم المستخدم مطلوب وكلمة المرور 4 أحرف على الأقل")
    with db.tx() as conn:
        conn.execute("""INSERT INTO users(username, full_name, password_hash, role, created_at)
                        VALUES (?, ?, ?, ?, ?)""", (username.strip(), full_name, hash_password(password), role, db.now()))


def update_user(user_id, full_name, role, is_active):
    if role not in ROLES:
        raise ValueError("دور غير معروف")
    with db.tx() as conn:
        # لا نسمح بتعطيل آخر مدير نظام
        if role != "admin" or not is_active:
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1 AND id!=?",
                                  (user_id,)).fetchone()[0]
            if admins == 0:
                raise ValueError("لا يمكن إزالة آخر مدير نظام فعّال")
        conn.execute("UPDATE users SET full_name=?, role=?, is_active=? WHERE id=?",
                     (full_name, role, 1 if is_active else 0, user_id))
        if not is_active:
            conn.execute("DELETE FROM web_sessions WHERE user_id=?", (user_id,))


def change_password(user_id, new_password):
    if len(new_password) < 4:
        raise ValueError("كلمة المرور يجب أن تكون 4 أحرف على الأقل")
    with db.tx() as conn:
        conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
                     (hash_password(new_password), user_id))
        conn.execute("DELETE FROM web_sessions WHERE user_id=?", (user_id,))   # تُغلق جلسات الجوال القديمة
    u = context.user()
    if u and u["id"] == user_id:
        u["must_change_password"] = 0
