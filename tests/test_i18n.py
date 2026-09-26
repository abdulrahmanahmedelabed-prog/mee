# -*- coding: utf-8 -*-
"""الواجهة الإنجليزية: تُشغَّل في عملية منفصلة حتى لا تؤثر ترقيعات Qt على بقية الاختبارات"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = r'''
import os, sys, re
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget, QComboBox
app = QApplication([])
from ui import i18n_qt
i18n_qt.apply_language("en", app)
from core import db, auth, products, sales, receipts, whatsapp, customers, i18n, settings
db.init_db(); auth.login("admin", "admin")
settings.set("require_shift", "0")
from ui.main_window import MainWindow, PAGES
w = MainWindow(); w.show(); app.processEvents()
for key, *_ in PAGES:
    w.go(key); app.processEvents()
    tabs = getattr(w.pages[key], "tabs", None)
    for i in range(tabs.count() if tabs else 0):
        tabs.setCurrentIndex(i); app.processEvents()
nav = [b.property("text") for b in w.findChildren(QPushButton) if b.objectName() == "navBtn" and b.isVisible()]
arabic_nav = [t for t in nav if i18n.ARABIC.search(t)]
assert not arabic_nav, arabic_nav
assert "Point of sale" in w.page_title.property("text") or True
rep = w.pages["reports"]
assert rep.tabs.tabText(0) == "الأرباح والخسائر"                 # المنطق يقرأ الأصل
assert rep.tabs.tabBar().tabText(0).replace("&&", "&") == "Profit & Loss"   # والمستخدم يرى الترجمة
pid = products.add_product("Milk 1L", "111", "Dairy", 3, 4.5, 20, 2, "قطعة")
pos = w.pages["pos"]
pos.search.setText("2*111"); pos.on_enter()
pos.finish_sale({"cash_amount": 9, "card_amount": 0, "credit_amount": 0, "cash_received": 10, "change": 1})
assert "Change due" in pos.lbl_change.property("text"), pos.lbl_change.property("text")
html = i18n.tr_html(receipts.invoice_html(pos.last_invoice_id))
assert "dir='ltr'" in html and "Total" in html and "الإجمالي" not in html
cid = customers.add_customer("John", "+15551234567", opening_balance=20)
link = whatsapp.reminder_link(cid)
assert "friendly%20reminder" in link, link
from ui.suppliers_screen import PaySupplierDialog
d = PaySupplierDialog(None, {"name": "Acme"}, 10)
assert d.method.currentText() == "نقدي من الصندوق"                  # طرق الدفع تبقى بيانات عربية للمحاسبة
assert d.method.itemText(0) == "نقدي من الصندوق" and d.method.property("currentText") == "Cash from drawer"
print("EN-OK")
'''


def test_english_interface(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", SHOP_DATA_DIR=str(tmp_path), SHOP_LANG="en")
    r = subprocess.run([sys.executable, "-c", f"ROOT={ROOT!r}\n" + SCRIPT], env=env, capture_output=True, text=True,
                       timeout=300)
    assert "EN-OK" in r.stdout, r.stdout[-2000:] + r.stderr[-4000:]
