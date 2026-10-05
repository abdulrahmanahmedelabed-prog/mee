# -*- coding: utf-8 -*-
from core import ledger, products, sales, vendor, updates


def test_balance_cache_never_stale():
    pid = products.add_product("أرز", "5501", "", 4, 6, 50, 0)
    item = {"product_id": pid, "product_name": "أرز", "quantity": 1, "unit_price": 6, "cost_price": 4}
    sales.create_sale([dict(item)])
    first = ledger.trial_balance(None, None)
    assert ledger.trial_balance(None, None) == first          # من التخزين المؤقت
    sales.create_sale([dict(item)])
    after = ledger.trial_balance(None, None)
    assert after != first                                     # أي حفظ يُبطل التخزين المؤقت


def test_vendor_details_and_update_source():
    assert vendor.VENDOR_PHONE == "970592458157" and "الحسن" in vendor.VENDOR_NAME
    assert vendor.UPDATE_URL.startswith("https://")
    assert updates.check(url="http://example.com/x.json") is None     # لا تحديث من رابط غير آمن
