# -*- coding: utf-8 -*-
"""اختبار دخاني للواجهة: يفتح كل الشاشات بدون عرض (offscreen) ويحفظ لقطات شاشة"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core import db, auth, products


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    client = os.environ.get("SHOT_CLIENT")  # host:port:code  لتجربة نقطة بيع فرعية
    if client:
        from core import remote
        host, port, code = client.split(":")
        remote.install_client(host, int(port), code, "كاشير 2")
    else:
        db.init_db()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    f = QFont()
    f.setFamilies(["Noto Sans Arabic", "DejaVu Sans"])
    f.setPointSize(10)
    app.setFont(f)
    from ui.style import STYLE_SHEET
    app.setStyleSheet(STYLE_SHEET.replace("'Segoe UI', 'Tahoma', ", ""))
    auth.login("admin", "admin")
    from ui.main_window import MainWindow, PAGES
    w = MainWindow()
    w.resize(1366, 740)
    w.show()
    app.processEvents()

    # تجهيز سلة في نقطة البيع
    pos = w.pages["pos"]
    for p in products.get_all_products()[:4]:
        pos.add_product(products.get_product(p["id"]), 2 if p["unit"] != "كغم" else 1.25)
    for code in ("5449000000996", "7290000001028", "7290000001011"):   # كرتونة كولا + لبنة منتهية + حليب قريب
        pos.search.setText(code)
        pos.on_enter()

    for key, *_ in PAGES:
        w.go(key)
        if key == "pos":
            pos.search.setText("")
        app.processEvents()
        w.grab().save(os.path.join(out_dir, f"{key}.png"))
        print("ok", key, w.width(), flush=True)
    # تبويبات التقارير
    rep = w.pages["reports"]
    w.go("reports")
    for i in range(rep.tabs.count()):
        rep.tabs.setCurrentIndex(i)
        app.processEvents()
        w.grab().save(os.path.join(out_dir, f"reports_{i}.png"))
    print("ok reports tabs")

    # نافذة الدفع
    from ui.pos_screen import PaymentDialog
    d = PaymentDialog(w, 57.5, None)
    d.cash.setValue(100)
    d.show()
    app.processEvents()
    d.grab().save(os.path.join(out_dir, "payment.png"))
    # فاتورة
    from core import receipts, sales
    from ui import printing
    inv = sales.get_invoices(limit=1)
    if inv:
        printing.save_pdf(receipts.invoice_html(inv[0]["id"]), os.path.join(out_dir, "receipt.pdf"), 80)
    pos.clear_cart()
    w.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
