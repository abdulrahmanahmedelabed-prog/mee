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

    # جلسة منتهية/مزورة
    client.token = "fake"
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
    assert "مبيعات اليوم" in page

    local_user = auth.current_user()
    client = remote.install_client("127.0.0.1", server, "ABC123", "كاشير 2")
    assert auth.login("admin", "admin")
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
