# -*- coding: utf-8 -*-
"""
تشغيل عدة نقاط بيع على نفس البيانات عبر الشبكة المحلية (راوتر المحل، بدون إنترنت).

- الجهاز الرئيسي (خادم): يحفظ قاعدة البيانات ويشغّل خادماً صغيراً (HTTP) على المنفذ 8765.
- أجهزة الكاشير الفرعية (عميل): لا تحتوي بيانات؛ كل عملية (بيع، بحث، تقرير...) تُرسل للخادم وتنفَّذ هناك
  داخل معاملة واحدة، فلا يحدث تضارب في المخزون ولا تتكرر أرقام الفواتير.

الأمان: رمز ربط سري يظهر في إعدادات الجهاز الرئيسي ويُدخل في الأجهزة الفرعية، ثم تسجيل دخول عادي بمستخدم وكلمة مرور.
لماذا ليس مجلد مشترك؟ لأن فتح ملف SQLite من عدة أجهزة عبر الشبكة يعرّضه للتلف.
"""

import inspect
import json
import secrets
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import (config, context, auth, products, sales, customers, suppliers, expenses, shifts, reports, audit,
                  backup, settings, db, ledger, cheques, promotions, loyalty, reorder, license, insights, orders,
                  wallets, financial_audit, payroll, installments, branches, assistant, forecast, seasons, zakat,
                  accountant, notes)

PROTOCOL_VERSION = 2
MAX_BODY = 20 * 1024 * 1024     # أكبر طلب مقبول من جهاز فرعي

MODULES = {"products": products, "sales": sales, "customers": customers, "suppliers": suppliers,
           "expenses": expenses, "shifts": shifts, "reports": reports, "audit": audit, "backup": backup,
           "settings": settings, "auth": auth, "ledger": ledger, "cheques": cheques, "promotions": promotions,
           "loyalty": loyalty, "reorder": reorder, "license": license, "insights": insights,
           "orders": orders, "wallets": wallets, "financial_audit": financial_audit,
           "payroll": payroll, "installments": installments, "branches": branches, "assistant": assistant,
           "forecast": forecast, "seasons": seasons, "zakat": zakat, "accountant": accountant,
           "notes": notes}

# دوال تبقى على الجهاز نفسه (لا تحتاج قاعدة البيانات أو تستدعي دوال أخرى تُرسل للخادم تلقائياً)
LOCAL_ONLY = {
    "settings": {"get", "get_bool", "get_float", "set", "set_many", "reload", "expense_categories", "ensure_defaults"},
    "auth": {"hash_password", "verify_password", "login", "set_current_user", "current_user", "current_user_id",
             "logout", "has_permission", "ensure_admin"},
    "sales": {"compute_totals", "payment_label", "refund_methods", "round_up_amount"},
    "products": {"is_loss_reason", "export_csv", "import_csv", "price_for"},
    "promotions": {"compute"},
    "backup": {"restore_backup", "validate_backup", "auto_daily_backup"},
    "ledger": {"account_type", "is_debit_normal"},
    "loyalty": {"enabled", "points_for", "value_of"},
    "license": {"normalize_machine", "sign", "verify_signature", "make_key", "parse_key"},
    "wallets": {"all_wallets", "get", "names", "to_json", "presets", "qr_text"},
    "financial_audit": {"report_html", "benford"},
    "assistant": {"norm", "parse_period", "previous_period", "detect"},
    "zakat": {"report_html"},
    "notes": {"next_due", "describe_due"},
}

# صلاحيات يتحقق منها الخادم نفسه (لا نعتمد على الواجهة وحدها: جهاز فرعي معدّل قد يرسل أي طلب)
REQUIRED_PERMISSION = {
    ("auth", "create_user"): "users", ("auth", "update_user"): "users", ("auth", "list_users"): "users",
    ("settings", "save_shared"): "settings", ("license", "activate"): "settings",
    ("wallets", "summary"): "reports", ("wallets", "invoices"): "reports",
    ("backup", "create_backup"): "backup", ("backup", "list_backups"): "backup", ("backup", "prune"): "backup",
    ("backup", "mirror_backup"): "backup",
    ("ledger", "add_manual_entry"): "accounting", ("ledger", "void_entry"): "accounting",
    ("ledger", "add_account"): "accounting",
    ("promotions", "add_promotion"): "promotions", ("promotions", "update_promotion"): "promotions",
    ("promotions", "delete_promotion"): "promotions",
    ("loyalty", "adjust"): "promotions",
    ("insights", "apply_price_update"): "inventory",
    ("financial_audit", "run"): "accounting", ("financial_audit", "aging"): "accounting",
    ("payroll", "add_employee"): "expenses", ("payroll", "update_employee"): "expenses",
    ("payroll", "give_advance"): "expenses", ("payroll", "pay_salary"): "expenses",
    ("payroll", "list_employees"): "expenses", ("payroll", "history"): "expenses",
    ("installments", "create_plan"): "customers", ("installments", "cancel_plan"): "customers",
    ("branches", "consolidated"): "reports", ("branches", "add_branch_file"): "reports",
    ("assistant", "answer"): "reports", ("forecast", "sales_forecast"): "reports", ("forecast", "cash_forecast"): "reports",
    ("forecast", "stockouts"): "reports", ("seasons", "plan"): "reports", ("seasons", "upcoming"): "reports",
    ("zakat", "compute"): "accounting",
}
# ميزات الباقات يتحقق منها الخادم أيضاً (جهاز فرعي لا يتجاوز باقة المحل)
PLAN_FEATURE = {("assistant", "answer"): "ask", ("forecast", "sales_forecast"): "forecast",
                ("forecast", "cash_forecast"): "forecast", ("seasons", "plan"): "seasons", ("zakat", "compute"): "zakat",
                ("financial_audit", "run"): "audit", ("payroll", "pay_salary"): "payroll",
                ("installments", "create_plan"): "installments", ("branches", "consolidated"): "branches",
                ("accountant", "close_month"): "accounting", ("accountant", "add_asset"): "accounting",
                ("accountant", "daily_audit"): "audit"}


# صلاحيات بقية الوظائف (يكفي أي واحدة منها). كل وحدة لها صلاحية افتراضية، والاستثناءات بالاسم.
# الهدف: جهاز فرعي معدّل أو مستخدم يعرف رمز الربط لا يستطيع تنفيذ ما لا تسمح به صلاحياته.
MODULE_PERMISSION = {
    "ledger": ("accounting",), "financial_audit": ("accounting",), "zakat": ("accounting",), "accountant": ("accounting",),
    "reports": ("reports",), "insights": ("reports",), "branches": ("reports",), "assistant": ("reports",),
    "forecast": ("reports",), "seasons": ("reports",),
    "cheques": ("cheques",), "expenses": ("expenses",), "payroll": ("expenses",),
    "suppliers": ("suppliers",), "reorder": ("suppliers",), "backup": ("backup",),
}
FUNCTION_PERMISSION = {
    # لوحة التحكم
    ("reports", "dashboard"): ("reports", "dashboard"), ("reports", "last_n_days"): ("reports", "dashboard"),
    ("reports", "top_products"): ("reports", "dashboard"), ("reports", "daily_summary_text"): ("reports", "dashboard"),
    ("audit", "recent"): ("reports",),
    # المخزون
    **{("products", f): ("inventory",) for f in (
        "add_product", "update_product", "delete_product", "adjust_stock", "set_stock_count", "set_units",
        "assign_internal_barcode", "next_internal_barcode", "write_off_batch", "stock_movements", "get_batches",
        "fill_english_names", "mark_labels_printed")},
    ("products", "inventory_value"): ("inventory", "reports"),
    ("products", "expiring_batches"): ("inventory", "reports", "dashboard"),
    ("products", "get_low_stock_products"): ("inventory", "reports", "dashboard", "suppliers"),
    # العملاء
    **{("customers", f): ("customers",) for f in (
        "adjust_balance", "deactivate_customer", "receive_payment", "statement", "update_customer", "total_debts",
        "reminder_message")},
    ("customers", "add_customer"): ("customers", "pos"),
    ("installments", "summary"): ("customers",), ("installments", "schedule_html"): ("customers",),
    ("installments", "reminder_message"): ("customers",), ("installments", "overdue"): ("customers", "reports"),
    # البيع والفواتير والمرتجعات
    **{("sales", f): ("pos",) for f in ("create_sale", "import_offline_sale", "hold_cart", "take_held_cart",
                                       "list_held_carts", "cart_discounts")},
    ("shifts", "open_shift"): ("pos", "cash"),
    ("sales", "create_return"): ("returns",),
    ("sales", "get_invoices"): ("invoices", "returns", "reports"), ("sales", "get_returns"): ("invoices", "returns", "reports"),
    ("sales", "returnable_items"): ("returns", "invoices"),
    # الصندوق
    ("shifts", "close_shift"): ("cash",), ("shifts", "cash_movement"): ("cash",), ("shifts", "list_shifts"): ("cash",),
    ("shifts", "movements"): ("cash",), ("shifts", "summary"): ("cash", "reports"),
    # الطلبات الأونلاين
    ("orders", "set_status"): ("pos",), ("orders", "list_orders"): ("pos",), ("orders", "get_order"): ("pos",),
    ("orders", "new_count"): ("pos",), ("orders", "status_message"): ("pos",),
    # العروض والولاء
    ("promotions", "list_promotions"): ("promotions",), ("loyalty", "top_members"): ("promotions",),
    ("loyalty", "history"): ("promotions", "customers"), ("loyalty", "liability"): ("promotions", "reports"),
    # الموردون: القائمة تظهر أيضاً في فلاتر التقارير والشيكات، والإضافة من استيراد البيانات
    ("suppliers", "list_suppliers"): ("suppliers", "reports", "cheques"),
    ("suppliers", "add_supplier"): ("suppliers", "settings"),
    ("cheques", "due_soon"): ("cheques", "reports", "dashboard"),
    ("payroll", "payslip_html"): ("expenses",),
}
# متاحة لكل مستخدم مسجّل (يحتاجها البيع والطباعة على كل الأجهزة)
OPEN_FUNCTIONS = {("auth", "authenticate"), ("auth", "change_password"), ("audit", "log")}
# الملاحظات والتذكيرات لكل مستخدم (يرى ملاحظاته والمشتركة فقط؛ التحقق داخل core/notes.py)
OPEN_FUNCTIONS |= {("notes", f) for f in ("add_note", "update_note", "delete_note", "complete", "reopen", "snooze",
                                          "list_notes", "due_now", "pop_new_due", "counts")}

ELEVATION_SECONDS = 300      # موافقة المدير على جهاز الكاشير صالحة 5 دقائق لهذه الجلسة


def needed_permissions(key):
    if key in OPEN_FUNCTIONS:
        return ()
    if key in REQUIRED_PERMISSION:
        return (REQUIRED_PERMISSION[key],)
    if key in FUNCTION_PERMISSION:
        return FUNCTION_PERMISSION[key]
    return MODULE_PERMISSION.get(key[0], ())


def _allowed(perm, user, elevated):
    return auth.has_permission(perm, user) or perm in (elevated or ())


def check_permission(key, user, args, kwargs, elevated=None):
    """يرفع PermissionError إن لم يكن للمستخدم حق تنفيذ الوظيفة عبر الشبكة.
    elevated: صلاحيات مدير وافق عليها للتو على نفس الجهاز (نافذة «موافقة المدير»)"""
    if key == ("auth", "change_password"):
        target = args[0] if args else kwargs.get("user_id")
        if target != user["id"] and not _allowed("users", user, elevated):
            raise PermissionError("لا يمكنك تغيير كلمة مرور مستخدم آخر")
        return
    if key == ("sales", "create_sale") and ("offline" in kwargs or len(args) > 12):
        raise PermissionError("الترحيل يتم عبر import_offline_sale فقط")
    perms = needed_permissions(key)
    if perms and not any(_allowed(p, user, elevated) for p in perms):
        raise PermissionError(f"ليست لديك صلاحية: {auth.PERMISSIONS.get(perms[0], perms[0])}")
    feature = PLAN_FEATURE.get(key)
    if feature:
        from core import plans
        if not plans.has(feature):
            raise PermissionError(f"هذه الميزة متاحة في باقة {plans.NAMES[plans.required(feature)]} وما فوقها")


# دوال مسموحة قبل تسجيل الدخول
PUBLIC = {("settings", "all_values"), ("license", "reset_admin_password"), ("license", "machine_id")}

SENSITIVE_KEYS = {"password_hash"}


class RemoteError(Exception):
    pass


class ConnectionFailed(RemoteError):
    pass


class SessionExpired(RemoteError):
    """الجهاز الرئيسي أُعيد تشغيله فضاعت الجلسة: نعيد تسجيل الدخول تلقائياً"""
    pass


def remote_functions():
    out = {}
    for mod_name, mod in MODULES.items():
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith("_") or fn.__module__ != mod.__name__ or name in LOCAL_ONLY.get(mod_name, set()):
                continue
            out[(mod_name, name)] = fn
    return out


def to_json(obj):
    if isinstance(obj, sqlite3.Row):
        obj = dict(obj)
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items() if k not in SENSITIVE_KEYS}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# الخادم
# ---------------------------------------------------------------------------

class _Server:
    def __init__(self):
        self.httpd = None
        self.thread = None
        self.tokens = {}          # token -> user_id
        self.functions = remote_functions()
        self.clients = {}         # terminal -> آخر اتصال
        self.elevations = {}      # token -> (صلاحيات المدير الموافق، تنتهي في)


SERVER = _Server()


class Handler(BaseHTTPRequestHandler):
    server_version = "ShopAccounting/4"

    def log_message(self, *args):
        pass

    # رؤوس أمان لكل رد: لا تُعرض الصفحات داخل إطار موقع آخر، ولا تُحمَّل موارد من خارج جهاز المحل
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self' data: blob: 'unsafe-inline'; frame-ancestors 'none'; "
                                   "form-action 'self'; base-uri 'none'",
    }

    def end_headers(self):
        for k, v in self.SECURITY_HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def _ip(self):
        return self.client_address[0] if self.client_address else ""

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code, html, headers=None):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _mobile_get(self, path):
        from core import mobile_web
        from urllib.parse import urlparse, parse_qs
        user = mobile_web.user_from_cookie(self.headers.get("Cookie"))
        if path == "/m/manifest.json":
            body = mobile_web.manifest().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/m/logout":
            mobile_web.logout(self.headers.get("Cookie"))
            self._redirect("/m", f"{mobile_web.COOKIE}=; Max-Age=0; Path=/m; HttpOnly; SameSite=Strict")
        elif path.startswith("/m/api/"):
            if not user:
                self._send(401, {"error": "login"})
                return
            fn = mobile_web.API_GET.get(path[len("/m/api/"):])
            if not fn:
                self._send(404, {"error": "not found"})
                return
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0][:200]
            from core import i18n
            try:
                with context.request(user, "جوال"):
                    self._send(200, to_json(fn(user, q)))
            except (PermissionError, ValueError) as e:
                self._send(200, {"error": i18n.tr(str(e))})
        elif user:
            self._html(200, mobile_web.app_page(user))
        else:
            self._html(200, mobile_web.login_page())

    def _mobile_post(self, path):
        from core import mobile_web, i18n
        length = min(int(self.headers.get("Content-Length", 0) or 0), 10000)
        body = self.rfile.read(length)
        if path == "/m/login":
            token, err = mobile_web.login(body, self._ip())
            if err:
                self._html(200, mobile_web.login_page(i18n.tr(err)))
            else:
                from core import web_sessions
                self._redirect("/m", f"{mobile_web.COOKIE}={token}; Max-Age={web_sessions.MAX_AGE_SECONDS}; "
                                     f"Path=/m; HttpOnly; SameSite=Strict")
            return
        user = mobile_web.user_from_cookie(self.headers.get("Cookie"))
        if not user:
            self._send(401, {"error": "login"})
            return
        try:
            data = json.loads(body or b"{}")
            if path == "/m/api/order":
                self._send(200, mobile_web.order_status(user, data["id"], data["status"]))
                return
            self._send(200, mobile_web.count(user, data["product_id"], data["counted"]))
        except (PermissionError, ValueError, KeyError, TypeError) as e:
            self._send(200, {"error": i18n.tr(str(e))})

    def _plan_locked(self, path):
        """الواجهات الويب حسب الباقة: الجوال (بلس)، لوحة المالك والمتجر (برو)"""
        from core import plans
        # تطبيق الجوال يفتح في كل الباقات (الأسعار والكميات)؛ الجرد منه في بلس، والسؤال في ماكس
        feature = ("owner" if path.startswith("/owner") else "online" if path.startswith("/shop")
                   else "mobile" if path in ("/m/api/count", "/m/api/low", "/m/api/customers")
                   else "online" if path in ("/m/api/orders", "/m/api/order")
                   else "ask" if path == "/m/api/ask" else None)
        if not feature or plans.has(feature):
            return False
        from core import i18n
        tier = plans.required(feature)
        name, _, _ = plans.FEATURES[feature]
        page = (f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                f"<body style='font-family:Tahoma,sans-serif;text-align:center;padding:60px 20px;color:#0F172A'>"
                f"<div style='font-size:48px'>🔒</div><h2>{name}</h2>"
                f"<p>هذه الميزة متاحة في باقة {plans.NAMES[tier]} وما فوقها.</p>"
                f"<p style='color:#64748B'>اطلب الترقية من صاحب المحل: الإعدادات ← الترخيص والتفعيل.</p></body></html>")
        if self.command == "POST":
            self._send(200, {"error": i18n.tr(f"هذه الميزة متاحة في باقة {plans.NAMES[tier]} وما فوقها.")})
        else:
            self._html(200, i18n.tr_html(page))
        return True

    def do_GET(self):
        from core import owner_web
        path = self.path.split("?", 1)[0].rstrip("/")
        if self._plan_locked(path):
            return
        if path == "/ping":
            self._send(200, {"ok": True, "shop": settings.get("shop_name"), "protocol": PROTOCOL_VERSION})
        elif path == "/owner":
            user = owner_web.user_from_cookie(self.headers.get("Cookie"))
            if user:
                with context.request(user, "لوحة المالك"):
                    self._html(200, owner_web.dashboard_page())
            else:
                self._html(200, owner_web.login_page())
        elif path == "/shop":
            self._html(200, orders.store_page())
        elif path.startswith("/m"):
            self._mobile_get(path)
        elif path == "/owner/logout":
            owner_web.logout(self.headers.get("Cookie"))
            self._redirect("/owner", f"{owner_web.COOKIE}=; Max-Age=0; Path=/owner; HttpOnly; SameSite=Strict")
        else:
            self._send(404, {"error": {"type": "NotFound", "message": "not found"}})

    def do_POST(self):
        if self._plan_locked(self.path.split("?", 1)[0]):
            return
        if self.path.split("?", 1)[0] == "/shop/order":
            from core import i18n
            try:
                length = min(int(self.headers.get("Content-Length", 0) or 0), 50000)
                data = json.loads(self.rfile.read(length) or b"{}")
                res = orders.create_order(data, self.client_address[0])
                self._send(200, res)
            except (orders.OrderError, ValueError) as e:
                self._send(200, {"error": i18n.tr(str(e))})
            return
        if self.path.split("?", 1)[0] in ("/m/login", "/m/api/count", "/m/api/order"):
            self._mobile_post(self.path.split("?", 1)[0])
            return
        if self.path.split("?", 1)[0] == "/owner/login":
            from core import owner_web
            length = min(int(self.headers.get("Content-Length", 0) or 0), 10000)
            token, err = owner_web.login(self.rfile.read(length), self._ip())
            if err:
                self._html(200, owner_web.login_page(err))
            else:
                from core import web_sessions
                self._redirect("/owner", f"{owner_web.COOKIE}={token}; Max-Age={web_sessions.MAX_AGE_SECONDS}; "
                                         f"Path=/owner; HttpOnly; SameSite=Strict")
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length < 0 or length > MAX_BODY:
                self._send(413, {"error": {"type": "BadRequest", "message": "طلب كبير جداً"}})
                return
            req = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(req, dict):
                raise ValueError("bad request")
        except (ValueError, OSError):
            self._send(400, {"error": {"type": "BadRequest", "message": "طلب غير صالح"}})
            return
        if self.path == "/login":
            self._login(req)
        elif self.path == "/rpc":
            self._rpc(req)
        else:
            self._send(404, {"error": {"type": "NotFound", "message": "not found"}})

    def _link_ok(self, req):
        return secrets.compare_digest(str(req.get("link_code") or "").strip().upper(),
                                      str(config.get("link_code") or "").upper()) and bool(config.get("link_code"))

    def _login(self, req):
        from core import throttle
        username = str(req.get("username") or "")[:100]
        wait = throttle.wait_seconds(self._ip(), username)
        if wait:
            self._send(429, {"error": {"type": "Throttle", "message": throttle.message(wait)}})
            return
        if not self._link_ok(req):
            throttle.failed(self._ip())
            self._send(403, {"error": {"type": "LinkCode", "message": "رمز الربط غير صحيح"}})
            return
        user = auth.authenticate(username, str(req.get("password") or "")[:200])
        if not user:
            throttle.failed(self._ip(), username)
            self._send(401, {"error": {"type": "Auth", "message": "اسم المستخدم أو كلمة المرور غير صحيحة"}})
            return
        throttle.succeeded(self._ip(), username)
        terminal = req.get("terminal")
        limit = license.max_terminals()
        if limit and terminal not in SERVER.clients:
            active = [t for t in SERVER.clients if t and t != config.get("terminal_name")]
            if len(active) + 1 >= limit:
                self._send(403, {"error": {"type": "License", "message":
                                           f"وصلت للحد الأقصى من الأجهزة المرخّصة ({limit}). للترقية تواصل مع مزوّد البرنامج."}})
                return
        token = secrets.token_urlsafe(24)
        SERVER.tokens[token] = user["id"]
        SERVER.clients[terminal] = db.now()
        with context.request(user, req.get("terminal")):
            audit.log("تسجيل دخول", f"{user['username']} من الجهاز {req.get('terminal')}")
        self._send(200, {"token": token, "user": to_json(user)})

    def _rpc(self, req):
        import time
        from core import throttle
        key = (req.get("module"), req.get("func"))
        fn = SERVER.functions.get(key)
        if not fn:
            self._send(404, {"error": {"type": "NotFound", "message": "وظيفة غير معروفة"}})
            return
        user = None
        token = req.get("token")
        if key in PUBLIC:
            # قبل تسجيل الدخول: للأجهزة المربوطة فقط (رمز الربط)، لا لأي جهاز على واي فاي المحل
            wait = throttle.wait_seconds(self._ip())
            if wait or not self._link_ok(req):
                if not wait:
                    throttle.failed(self._ip())
                self._send(403, {"error": {"type": "LinkCode", "message": "رمز الربط غير صحيح"}})
                return
        else:
            uid = SERVER.tokens.get(token) if isinstance(token, str) else None
            row = db.query_one("SELECT * FROM users WHERE id=? AND is_active=1", (uid,)) if uid else None
            if not row:
                self._send(401, {"error": {"type": "Auth", "message": "انتهت الجلسة، سجّل الدخول مرة أخرى"}})
                return
            user = dict(row)
        terminal = req.get("terminal")
        if user is not None:
            SERVER.clients[terminal] = db.now()
        args, kwargs = req.get("args", []), req.get("kwargs", {})
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            self._send(400, {"error": {"type": "BadRequest", "message": "طلب غير صالح"}})
            return
        elevated = None
        if user is not None:
            perms, until = SERVER.elevations.get(token, ((), 0))
            if until > time.time():
                elevated = perms
            else:
                SERVER.elevations.pop(token, None)
        try:
            if user is not None:
                check_permission(key, user, args, kwargs, elevated)
        except PermissionError as e:
            self._send(403, {"error": {"type": "Permission", "message": str(e)}})
            return
        if key == ("auth", "authenticate"):       # «موافقة المدير» من جهاز الكاشير: محمية من التخمين
            name = str((args or [kwargs.get("username", "")])[0] or "")[:100]
            wait = throttle.wait_seconds(self._ip(), name)
            if wait:
                self._send(200, {"result": None})
                return
        try:
            with context.request(user, terminal):
                result = fn(*args, **kwargs)
            if key == ("auth", "authenticate"):
                if result:
                    throttle.succeeded(self._ip(), name)
                    SERVER.elevations[token] = (tuple(p for p in auth.PERMISSIONS if auth.has_permission(p, result)),
                                                time.time() + ELEVATION_SECONDS)
                    result = {k: result[k] for k in ("id", "username", "full_name", "role", "permissions")
                              if k in result.keys()}
                else:
                    throttle.failed(self._ip(), name)
            self._send(200, {"result": to_json(result)})
        except sales.SaleError as e:
            self._send(200, {"error": {"type": "SaleError", "message": str(e)}})
        except ValueError as e:
            self._send(200, {"error": {"type": "ValueError", "message": str(e)}})
        except PermissionError as e:
            self._send(403, {"error": {"type": "Permission", "message": str(e)}})
        except TypeError:
            self._send(400, {"error": {"type": "BadRequest", "message": "طلب غير صالح"}})
        except Exception as e:  # خطأ غير متوقع: لا نوقف الخادم ولا نكشف تفاصيله الداخلية
            import logging
            logging.getLogger(__name__).exception("RPC %s failed", key)
            self._send(500, {"error": {"type": "Internal", "message": f"خطأ غير متوقع في الجهاز الرئيسي ({type(e).__name__})"}})


def start_server(host="0.0.0.0", port=None):
    if SERVER.httpd:
        return SERVER.httpd.server_address
    port = int(port or config.get("server_port") or 8765)
    SERVER.httpd = ThreadingHTTPServer((host, port), Handler)
    SERVER.httpd.daemon_threads = True
    SERVER.thread = threading.Thread(target=SERVER.httpd.serve_forever, daemon=True)
    SERVER.thread.start()
    return SERVER.httpd.server_address


def stop_server():
    if SERVER.httpd:
        SERVER.httpd.shutdown()
        SERVER.httpd.server_close()
        SERVER.httpd = None


def connected_terminals():
    return dict(SERVER.clients)


# ---------------------------------------------------------------------------
# العميل (نقطة البيع الفرعية)
# ---------------------------------------------------------------------------

class Client:
    def __init__(self, host, port, link_code, terminal, timeout=20):
        self.base = f"http://{host}:{int(port)}"
        self.link_code = link_code
        self.terminal = terminal
        self.timeout = timeout
        self.token = None

    def _post(self, path, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except ValueError:
                raise RemoteError(f"خطأ من الجهاز الرئيسي ({e.code})")
        except (urllib.error.URLError, OSError) as e:
            raise ConnectionFailed(f"تعذر الاتصال بالجهاز الرئيسي {self.base}\n"
                                   f"تأكد أنه يعمل وأنه على نفس الشبكة.\n({getattr(e, 'reason', e)})")
        if "error" in body:
            err = body["error"]
            if err["type"] == "SaleError":
                raise sales.SaleError(err["message"])
            if err["type"] in ("ValueError",):
                raise ValueError(err["message"])
            if err["type"] == "Auth" and path == "/rpc":
                raise SessionExpired(err["message"])
            raise RemoteError(err["message"])
        return body

    def ping(self):
        req = urllib.request.Request(self.base + "/ping")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ConnectionFailed(f"تعذر الوصول إلى الجهاز الرئيسي {self.base}\n({getattr(e, 'reason', e)})")

    def login(self, username, password):
        body = self._post("/login", {"username": username, "password": password, "link_code": self.link_code,
                                     "terminal": self.terminal})
        self.token = body["token"]
        self._creds = (username, password)   # في الذاكرة فقط، لإعادة الدخول بعد إعادة تشغيل الجهاز الرئيسي
        return body["user"]

    def call(self, module, func, *args, **kwargs):
        payload = {"terminal": self.terminal, "module": module, "func": func, "args": list(args), "kwargs": kwargs,
                   "link_code": self.link_code}
        try:
            return self._post("/rpc", dict(payload, token=self.token)).get("result")
        except SessionExpired:
            creds = getattr(self, "_creds", None)
            if not creds:
                raise
            self.login(*creds)
            return self._post("/rpc", dict(payload, token=self.token)).get("result")


CLIENT = None
_ORIGINALS = {}


def install_client(host, port, link_code, terminal):
    """تحويل هذا الجهاز لنقطة بيع فرعية: كل دوال البيانات تُستبدل بدوال ترسل الطلب للجهاز الرئيسي"""
    global CLIENT
    CLIENT = Client(host, port, link_code, terminal)
    CLIENT.last_error = None
    context.set_terminal(terminal)
    for (mod_name, name), fn in remote_functions().items():
        _ORIGINALS[(mod_name, name)] = fn
        setattr(MODULES[mod_name], name, _stub(mod_name, name, fn))

    def remote_login(username, password):
        CLIENT.last_error = None
        try:
            user = CLIENT.login(username, password)
        except (RemoteError, ValueError) as e:
            CLIENT.last_error = str(e)
            return None
        context.set_user(user)
        return user

    _ORIGINALS[("auth", "login")] = auth.login
    auth.login = remote_login
    settings._cache.clear()
    return CLIENT


def uninstall_client():
    """إرجاع الدوال الأصلية (للاختبارات)"""
    global CLIENT
    for (mod_name, name), fn in _ORIGINALS.items():
        setattr(MODULES[mod_name], name, fn)
    _ORIGINALS.clear()
    CLIENT = None
    settings._cache.clear()


def is_client():
    return CLIENT is not None


def _stub(mod_name, name, original):
    def stub(*args, **kwargs):
        return CLIENT.call(mod_name, name, *args, **kwargs)
    stub.__name__ = name
    stub.__doc__ = original.__doc__
    stub.remote = True
    return stub
