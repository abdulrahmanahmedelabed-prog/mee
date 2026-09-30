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
                  wallets, financial_audit)

PROTOCOL_VERSION = 2

MODULES = {"products": products, "sales": sales, "customers": customers, "suppliers": suppliers,
           "expenses": expenses, "shifts": shifts, "reports": reports, "audit": audit, "backup": backup,
           "settings": settings, "auth": auth, "ledger": ledger, "cheques": cheques, "promotions": promotions,
           "loyalty": loyalty, "reorder": reorder, "license": license, "insights": insights,
           "orders": orders, "wallets": wallets, "financial_audit": financial_audit}

# دوال تبقى على الجهاز نفسه (لا تحتاج قاعدة البيانات أو تستدعي دوال أخرى تُرسل للخادم تلقائياً)
LOCAL_ONLY = {
    "settings": {"get", "get_bool", "get_float", "set", "set_many", "reload", "expense_categories", "ensure_defaults"},
    "auth": {"hash_password", "verify_password", "login", "set_current_user", "current_user", "current_user_id",
             "logout", "has_permission", "ensure_admin"},
    "sales": {"compute_totals", "payment_label", "refund_methods"},
    "products": {"is_loss_reason", "export_csv", "import_csv", "price_for"},
    "promotions": {"compute"},
    "backup": {"restore_backup", "validate_backup", "auto_daily_backup"},
    "ledger": {"account_type", "is_debit_normal"},
    "loyalty": {"enabled", "points_for", "value_of"},
    "license": {"normalize_machine", "sign", "verify_signature", "make_key", "parse_key"},
    "wallets": {"all_wallets", "get", "names", "to_json", "presets", "qr_text"},
    "financial_audit": {"report_html", "benford"},
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
}


def check_permission(key, user, args, kwargs):
    """يرفع PermissionError إن لم يكن للمستخدم حق تنفيذ الوظيفة عبر الشبكة"""
    if key == ("auth", "change_password"):
        target = args[0] if args else kwargs.get("user_id")
        if target != user["id"] and not auth.has_permission("users", user):
            raise PermissionError("لا يمكنك تغيير كلمة مرور مستخدم آخر")
        return
    if key == ("sales", "create_sale") and ("offline" in kwargs or len(args) > 12):
        raise PermissionError("الترحيل يتم عبر import_offline_sale فقط")
    perm = REQUIRED_PERMISSION.get(key)
    if perm and not auth.has_permission(perm, user):
        raise PermissionError(f"ليست لديك صلاحية: {auth.PERMISSIONS.get(perm, perm)}")
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


SERVER = _Server()


class Handler(BaseHTTPRequestHandler):
    server_version = "ShopAccounting/4"

    def log_message(self, *args):
        pass

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
            self._redirect("/m", f"{mobile_web.COOKIE}=; Max-Age=0; Path=/m; HttpOnly; SameSite=Strict")
        elif path == "/m/api/find":
            if not user:
                self._send(401, {"error": "login"})
                return
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            with context.request(user, "جوال"):
                self._send(200, to_json(mobile_web.find(q)))
        elif user:
            self._html(200, mobile_web.app_page(user))
        else:
            self._html(200, mobile_web.login_page())

    def _mobile_post(self, path):
        from core import mobile_web, i18n
        length = min(int(self.headers.get("Content-Length", 0) or 0), 10000)
        body = self.rfile.read(length)
        if path == "/m/login":
            token, err = mobile_web.login(body)
            if err:
                self._html(200, mobile_web.login_page(i18n.tr(err)))
            else:
                self._redirect("/m", f"{mobile_web.COOKIE}={token}; Path=/m; HttpOnly; SameSite=Strict")
            return
        user = mobile_web.user_from_cookie(self.headers.get("Cookie"))
        if not user:
            self._send(401, {"error": "login"})
            return
        try:
            data = json.loads(body or b"{}")
            self._send(200, mobile_web.count(user, data["product_id"], data["counted"]))
        except (PermissionError, ValueError, KeyError, TypeError) as e:
            self._send(200, {"error": i18n.tr(str(e))})

    def do_GET(self):
        from core import owner_web
        path = self.path.split("?", 1)[0].rstrip("/")
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
        if self.path.split("?", 1)[0] in ("/m/login", "/m/api/count"):
            self._mobile_post(self.path.split("?", 1)[0])
            return
        if self.path.split("?", 1)[0] == "/owner/login":
            from core import owner_web
            length = min(int(self.headers.get("Content-Length", 0) or 0), 10000)
            token, err = owner_web.login(self.rfile.read(length))
            if err:
                self._html(200, owner_web.login_page(err))
            else:
                self._redirect("/owner", f"{owner_web.COOKIE}={token}; Path=/owner; HttpOnly; SameSite=Strict")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            self._send(400, {"error": {"type": "BadRequest", "message": "طلب غير صالح"}})
            return
        if self.path == "/login":
            self._login(req)
        elif self.path == "/rpc":
            self._rpc(req)
        else:
            self._send(404, {"error": {"type": "NotFound", "message": "not found"}})

    def _login(self, req):
        if not secrets.compare_digest(req.get("link_code", "").strip().upper(), str(config.get("link_code")).upper()):
            self._send(403, {"error": {"type": "LinkCode", "message": "رمز الربط غير صحيح"}})
            return
        user = auth.authenticate(req.get("username", ""), req.get("password", ""))
        if not user:
            self._send(401, {"error": {"type": "Auth", "message": "اسم المستخدم أو كلمة المرور غير صحيحة"}})
            return
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
        key = (req.get("module"), req.get("func"))
        fn = SERVER.functions.get(key)
        if not fn:
            self._send(404, {"error": {"type": "NotFound", "message": f"وظيفة غير معروفة {key}"}})
            return
        user = None
        if key not in PUBLIC:
            uid = SERVER.tokens.get(req.get("token"))
            row = db.query_one("SELECT * FROM users WHERE id=? AND is_active=1", (uid,)) if uid else None
            if not row:
                self._send(401, {"error": {"type": "Auth", "message": "انتهت الجلسة، سجّل الدخول مرة أخرى"}})
                return
            user = dict(row)
        terminal = req.get("terminal")
        if user is not None:
            SERVER.clients[terminal] = db.now()
        args, kwargs = req.get("args", []), req.get("kwargs", {})
        try:
            if user is not None:
                check_permission(key, user, args, kwargs)
        except PermissionError as e:
            self._send(403, {"error": {"type": "Permission", "message": str(e)}})
            return
        try:
            with context.request(user, terminal):
                result = fn(*args, **kwargs)
            self._send(200, {"result": to_json(result)})
        except sales.SaleError as e:
            self._send(200, {"error": {"type": "SaleError", "message": str(e)}})
        except ValueError as e:
            self._send(200, {"error": {"type": "ValueError", "message": str(e)}})
        except Exception as e:  # خطأ غير متوقع: لا نوقف الخادم
            self._send(500, {"error": {"type": type(e).__name__, "message": str(e)}})


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
        payload = {"terminal": self.terminal, "module": module, "func": func, "args": list(args), "kwargs": kwargs}
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
