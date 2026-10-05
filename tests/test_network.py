# -*- coding: utf-8 -*-
"""اختبار تعدد نقاط البيع: خادم حقيقي في عملية منفصلة + جهاز كاشير فرعي يتصل به"""
import json
import os
import socket
import subprocess
import sys
import time

import pytest

from core import remote, auth, products, sales, shifts, reports, customers, settings, context, db, license

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start(data, port):
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "server_headless.py"), str(data), str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = proc.stdout.readline()
    assert line.startswith("READY"), proc.stderr.read()
    return proc


@pytest.fixture
def server(tmp_path):
    data = tmp_path / "server_data"
    data.mkdir()
    (data / "terminal.json").write_text(json.dumps({"mode": "server", "link_code": "ABC123",
                                                    "terminal_name": "الجهاز الرئيسي"}), encoding="utf-8")
    port = free_port()
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "server_headless.py"), str(data), str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = proc.stdout.readline()
    assert line.startswith("READY"), proc.stderr.read()
    yield port
    remote.uninstall_client()
    proc.terminate()
    proc.wait(timeout=10)


def test_two_terminals_share_data(server):
    local_user = auth.current_user()
    client = remote.install_client("127.0.0.1", server, "WRONG", "كاشير 2")
    assert client.ping()["ok"]
    assert auth.login("admin", "admin") is None and "رمز الربط" in client.last_error
    client.link_code = "abc123"   # غير حساس لحالة الأحرف
    user = auth.login("admin", "admin")
    assert user["username"] == "admin" and "password_hash" not in user

    pid = products.add_product("حليب", "729", "ألبان", 4, 5.5, 10, 2)
    assert products.lookup_code("729")[0]["name"] == "حليب"
    sid = shifts.open_shift(100)
    assert shifts.current_shift()["terminal"] == "كاشير 2"
    r = sales.create_sale([{"product_id": pid, "product_name": "حليب", "quantity": 2, "unit_price": 5.5}],
                          shift_id=sid, cash_received=20)
    assert r["change"] == 9 and r["invoice_number"] == "INV-000001"
    with pytest.raises(sales.SaleError):
        sales.create_sale([{"product_id": pid, "product_name": "حليب", "quantity": 50, "unit_price": 5.5}])
    assert products.get_product(pid)["quantity"] == 8
    assert shifts.summary(sid)["expected_cash"] == 111

    cid = customers.add_customer("أبو أحمد", "0599")
    opening, rows = customers.statement(cid)
    assert opening == 0 and rows == []

    settings.set_many({"shop_name": "بقالة الشبكة", "printer_name": "طابعة الكاشير 2"})
    assert settings.get("shop_name") == "بقالة الشبكة"

    t = db.today()
    assert reports.profit_and_loss(t, t)["net_sales"] == 11
    assert reports.sales_by_terminal(t, t)[0]["terminal"] == "كاشير 2"

    # جهاز كاشير آخر يرى نفس البيانات ووردية مستقلة
    client.terminal = "كاشير 3"
    context.set_terminal("كاشير 3")
    assert shifts.current_shift() is None
    assert products.get_product(pid)["quantity"] == 8

    # جلسة منتهية: إعادة دخول تلقائية بالبيانات المحفوظة في الذاكرة، وبدونها رفض
    client.token = "fake"
    assert products.get_all_products()
    client.token, client._creds = "fake", None
    with pytest.raises(remote.RemoteError):
        products.get_all_products()
    remote.uninstall_client()
    auth.set_current_user(local_user)


def test_owner_page_and_server_side_permissions(server):
    import urllib.request, urllib.parse
    base = f"http://127.0.0.1:{server}"
    html = urllib.request.urlopen(base + "/owner").read().decode("utf-8")
    assert "لوحة المالك" in html and "كلمة المرور" in html
    # الدخول بكلمة مرور صحيحة يعطي كوكي الجلسة ثم لوحة المالك
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    body = urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode()
    page = opener.open(base + "/owner/login", data=body).read().decode("utf-8")
    assert "كلمة المرور الافتراضية" in page and "مبيعات اليوم" not in page   # admin/admin لا يفتح من الشبكة
    # بعد تغيير كلمة المرور الافتراضية (كما يطلب البرنامج عند أول دخول) يفتح من الشبكة
    def post(path, payload):
        r = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(r).read())
    tok = post("/login", {"username": "admin", "password": "admin", "link_code": "ABC123", "terminal": "t"})
    post("/rpc", {"token": tok["token"], "module": "auth", "func": "change_password", "args": [tok["user"]["id"], "admin"]})
    page = opener.open(base + "/owner/login", data=body).read().decode("utf-8")
    assert "مبيعات اليوم" in page

    # المتجر الإلكتروني العام
    assert "المتجر الإلكتروني غير مفعّل" in urllib.request.urlopen(base + "/shop").read().decode("utf-8")
    req = urllib.request.Request(base + "/shop/order", data=json.dumps({"name": "x"}).encode(),
                                 headers={"Content-Type": "application/json"})
    assert "error" in json.loads(urllib.request.urlopen(req).read())

    local_user = auth.current_user()
    client = remote.install_client("127.0.0.1", server, "ABC123", "كاشير 2")
    assert auth.login("admin", "admin")
    settings.set_many({"online_store_enabled": "1"})
    pid = products.add_product("تمر", "t77", "", 5, 9, 10, 0)
    req = urllib.request.Request(base + "/shop/order", data=json.dumps(
        {"name": "Sam", "phone": "+15551234567", "items": [{"product_id": pid, "quantity": 2}]}).encode(),
        headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req).read())
    assert res["total"] == 18 and "تمر" in urllib.request.urlopen(base + "/shop").read().decode("utf-8")
    from core import orders
    assert orders.new_count() == 1
    # تطبيق الجوال للموظفين: دخول، بحث، جرد (الكاشير لا يستطيع الجرد)
    m = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    assert "manifest" in m.open(base + "/m").read().decode("utf-8")
    m.open(base + "/m/login", data=urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode())
    found = json.loads(m.open(base + "/m/api/find?q=t77").read())
    assert found[0]["name"] == "تمر" and found[0]["qty"] == 10
    res = json.loads(m.open(urllib.request.Request(base + "/m/api/count", data=json.dumps(
        {"product_id": pid, "counted": 7}).encode(), headers={"Content-Type": "application/json"})).read())
    assert res == {"diff": -3, "qty": 7}
    import urllib.error
    with pytest.raises(urllib.error.HTTPError):          # بدون تسجيل دخول
        urllib.request.urlopen(base + "/m/api/find?q=t77")
    auth.create_user("kashier", "كاشير", "1234", "cashier")
    assert auth.login("kashier", "1234")["role"] == "cashier"
    with pytest.raises(remote.RemoteError):
        auth.create_user("hacker", "x", "1234", "admin")         # الخادم يرفض حتى لو تجاوز الجهاز الواجهة
    with pytest.raises(remote.RemoteError):
        auth.change_password(1, "owned")                          # لا يغيّر كلمة مرور المدير
    with pytest.raises(remote.RemoteError):
        settings.save_shared({"shop_name": "x"})
    assert license.status()["state"] == "trial"                   # حالة الترخيص تأتي من الجهاز الرئيسي
    remote.uninstall_client()
    auth.set_current_user(local_user)



def test_offline_selling_and_sync(tmp_path):
    from core import offline
    data = tmp_path / "srv"
    data.mkdir()
    (data / "terminal.json").write_text(json.dumps({"mode": "server", "link_code": "ABC123",
                                                    "terminal_name": "الرئيسي"}), encoding="utf-8")
    port = free_port()
    proc = _start(data, port)
    local_user = auth.current_user()
    try:
        remote.install_client("127.0.0.1", port, "ABC123", "كاشير 5")
        assert auth.login("admin", "admin")
        pid = products.add_product("خبز", "b100", "", 1, 2, 5, 0)
        sid = shifts.open_shift(50)
        assert offline.refresh_cache() == 1
        # الجهاز الرئيسي ينطفئ
        proc.terminate()
        proc.wait(timeout=10)
        with pytest.raises(remote.ConnectionFailed):
            products.lookup_code("b100")
        p, q, unit = offline.lookup_code("b100")
        assert p["name"] == "خبز"
        cart = [{"product_id": pid, "product_name": "خبز", "quantity": 8, "unit_price": 2}]   # أكثر من المخزون
        pay = offline.queue_sale(cart, 0, 0, 16, 0, 20, sid)
        assert pay["change"] == 4 and offline.pending_count() == 1
        assert offline.sync() == (0, 0) and offline.pending_count() == 1       # ما زال منقطعاً
        # يعود الجهاز الرئيسي (الجلسة ضاعت ← دخول تلقائي)
        proc = _start(data, port)
        assert offline.sync() == (1, 0) and offline.pending_count() == 0
        inv = sales.get_invoices(limit=1)[0]
        assert inv["total"] == 16 and inv["created_at"] == pay["created_at"] and "انقطاع" in inv["note"]
        assert products.get_product(pid)["quantity"] == -3                     # البيع تم فعلاً فيُسجّل
        assert shifts.summary(sid)["expected_cash"] == 66
        # ترحيل مكرر (انقطع قبل وصول الرد) لا يُنشئ فاتورة ثانية
        assert sales.import_offline_sale(pay)["duplicate"] is True
        assert len(sales.get_invoices()) == 1
    finally:
        remote.uninstall_client()
        auth.set_current_user(local_user)
        proc.terminate()
        proc.wait(timeout=10)
