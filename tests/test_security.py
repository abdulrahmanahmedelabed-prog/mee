# -*- coding: utf-8 -*-
"""الأمان: التحقق من الصلاحيات في الخادم، الحماية من التخمين، جلسات الويب، ورؤوس الأمان"""

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

from core import remote, auth, throttle, web_sessions, mobile_web, owner_web, plans, db


@pytest.fixture(autouse=True)
def _reset_throttle():
    throttle.reset()
    yield
    throttle.reset()


def test_every_remote_function_is_classified():
    """كل وظيفة عبر الشبكة إما لها صلاحية، أو مفتوحة عمداً لكل مستخدم مسجّل (البيع والبحث)"""
    fs = remote.remote_functions()
    open_ok = {"customers", "installments", "license", "loyalty", "orders", "products", "promotions", "sales",
               "settings", "shifts"}
    for key in fs:
        if not remote.needed_permissions(key) and key not in remote.OPEN_FUNCTIONS:
            assert key[0] in open_ok, key
    # الوحدات الحساسة بالكامل محمية
    for key in fs:
        if key[0] in ("ledger", "financial_audit", "expenses", "payroll", "cheques", "backup", "reports", "insights"):
            assert remote.needed_permissions(key), key


def test_cashier_blocked_server_side_and_manager_approval_elevates():
    cashier = {"id": 99, "role": "cashier"}
    for key in [("products", "update_product"), ("products", "delete_product"), ("ledger", "trial_balance"),
                ("expenses", "add_expense"), ("reports", "profit_and_loss"), ("sales", "create_return"),
                ("cheques", "issue_cheque"), ("auth", "create_user"), ("backup", "list_backups"),
                ("suppliers", "pay_supplier")]:
        with pytest.raises(PermissionError):
            remote.check_permission(key, cashier, [], {})
    # ما يحتاجه الكاشير مسموح
    for key in [("sales", "create_sale"), ("products", "lookup_code"), ("customers", "add_customer"),
                ("shifts", "close_shift"), ("customers", "receive_payment")]:
        remote.check_permission(key, cashier, [], {})
    # بعد «موافقة المدير» على نفس الجهاز
    remote.check_permission(("sales", "create_return"), cashier, [], {}, elevated=("returns",))
    with pytest.raises(PermissionError):
        remote.check_permission(("auth", "change_password"), cashier, [1, "x"], {})


def test_throttle_locks_after_repeated_failures():
    for _ in range(throttle.FREE_ATTEMPTS - 1):
        throttle.failed("10.0.0.5", "admin")
    assert throttle.wait_seconds("10.0.0.5", "admin") == 0
    throttle.failed("10.0.0.5", "admin")
    assert throttle.wait_seconds("10.0.0.5", "admin") > 0
    assert throttle.wait_seconds("10.0.0.6", "admin") > 0       # الحساب نفسه مقفل من أي جهاز
    assert throttle.wait_seconds("10.0.0.6", "other") == 0
    throttle.succeeded("10.0.0.5", "admin")
    assert throttle.wait_seconds("10.0.0.5", "admin") == 0


def test_web_login_throttled_and_default_password_refused():
    for _ in range(throttle.FREE_ATTEMPTS):
        token, err = mobile_web.login(b"username=admin&password=wrong", "10.1.1.1")
        assert token is None
    token, err = mobile_web.login(b"username=admin&password=admin", "10.1.1.1")
    assert token is None and ("حاول بعد" in err or "try again" in err.lower())
    throttle.reset()
    token, err = owner_web.login(b"username=admin&password=admin", "10.1.1.2")
    assert token is None and "الافتراضية" in err


def test_web_sessions_persist_and_revoke():
    uid = db.query_one("SELECT id FROM users WHERE username='admin'")["id"]
    auth.change_password(uid, "s3cret!")
    token, err = mobile_web.login(b"username=admin&password=s3cret!", "10.2.2.2")
    assert token and not err
    # محفوظة في قاعدة البيانات (تبقى بعد إعادة تشغيل جهاز المحل)
    assert db.scalar("SELECT COUNT(*) FROM web_sessions WHERE token=?", (token,)) == 1
    assert mobile_web.user_from_cookie(f"{mobile_web.COOKIE}={token}")["username"] == "admin"
    # جلسة الجوال لا تفتح لوحة المالك
    assert owner_web.user_from_cookie(f"{owner_web.COOKIE}={token}") is None
    # تغيير كلمة المرور يغلق كل الجلسات
    auth.change_password(uid, "n3w-pass")
    assert mobile_web.user_from_cookie(f"{mobile_web.COOKIE}={token}") is None
    # جلسة قديمة جداً تنتهي
    token = web_sessions.create(uid, "mobile")
    with db.tx() as conn:
        conn.execute("UPDATE web_sessions SET last_seen='2000-01-01 00:00:00' WHERE token=?", (token,))
    assert web_sessions.user(token, "mobile") is None


def test_mobile_ask_permission():
    admin = dict(db.query_one("SELECT * FROM users WHERE username='admin'"))
    assert mobile_web.can_ask(admin) == plans.has("ask")
    res = mobile_web.ask({"id": 5, "role": "cashier"}, "كم بعت اليوم")
    assert "error" in res


def test_mobile_page_escapes_script_breakout():
    from core import settings
    settings.set_many({"currency_symbol": "</script><script>alert(1)</script>"})
    admin = dict(db.query_one("SELECT * FROM users WHERE username='admin'"))
    html = mobile_web.app_page(admin)
    assert "</script><script>alert(1)" not in html


@pytest.fixture
def live_server():
    addr = remote.start_server("127.0.0.1", 0)
    yield f"http://127.0.0.1:{addr[1]}"
    remote.stop_server()


def test_server_requires_link_code_and_sends_security_headers(live_server):
    from core import config
    def rpc(payload):
        req = urllib.request.Request(live_server + "/rpc", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())
    # إعدادات المحل لا تُقرأ من أي جهاز على الواي فاي بدون رمز الربط
    assert rpc({"module": "settings", "func": "all_values"})["error"]["type"] == "LinkCode"
    ok = rpc({"module": "settings", "func": "all_values", "link_code": config.get("link_code")})
    assert "shop_name" in ok["result"]
    # بدون تسجيل دخول لا شيء
    assert rpc({"module": "products", "func": "get_all_products", "token": "x"})["error"]["type"] == "Auth"
    # رؤوس الأمان والصفحة العامة
    with urllib.request.urlopen(live_server + "/m") as r:
        assert r.headers["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    # /m يفتح في كل الباقات (فحص الأسعار)، ولا يُكشف تفاصيل داخلية
    assert json.loads(urllib.request.urlopen(live_server + "/ping").read())["ok"] is True
