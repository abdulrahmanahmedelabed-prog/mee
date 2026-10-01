# -*- coding: utf-8 -*-
"""
لقطات الإعلان والإنفوجرافيك من البرنامج نفسه (على بيانات التدريب):

    SHOP_DATA_DIR=<مجلد بيانات التدريب> python marketing/ad/capture_shots.py

تُحفظ في marketing/ad/shots بنفس الأسماء التي يستخدمها make_ad.py و make_infographic.py.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    from ui.style import STYLE_SHEET, load_fonts
    f = QFont()
    f.setFamilies([load_fonts() or "Noto Sans Arabic"])
    f.setPointSize(10)
    app.setFont(f)
    app.setStyleSheet(STYLE_SHEET)
    from core import auth, db, wallets, backup, settings
    import tempfile
    db.init_db()
    auth.login("admin", "admin")
    settings.set_many({"backup_mirror_dir": tempfile.mkdtemp()})   # محل منظّم: نسخ احتياطية يومية ونسخة ثانية
    backup.create_backup()
    from ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1366, 886)
    w.show()

    def snap(key, name, setup=None):
        w.go(key)
        w.license_bar.hide()
        if setup:
            setup(w.pages[key])
        for _ in range(3):
            app.processEvents()
        w.grab().save(os.path.join(OUT, name))

    def fill_pos(pg):
        for pid, q in db.query("""SELECT product_id, 1 + (COUNT(*) % 3) FROM invoice_items GROUP BY product_id
                                  ORDER BY COUNT(*) DESC LIMIT 5"""):
            pg.add_product(dict(db.query_one("SELECT * FROM products WHERE id=?", (pid,))), q)

    def first_row(pg):
        app.processEvents()
        pg.table.setCurrentCell(0, 0)

    def audit(pg):
        pg.run()
        for i in range(pg.table.rowCount()):
            if "محفظة" in pg.table.item(i, 2).text():
                pg.table.setCurrentCell(i, 0)

    snap("pos", "pos.png", fill_pos)
    snap("dashboard", "dashboard.png")
    snap("customers", "customers.png", first_row)
    snap("insights", "insights.png")
    snap("audit", "audit.png", audit)
    snap("reports", "reports.png")
    from ui.pos_screen import PaymentDialog, WalletDialog
    d = PaymentDialog(w, 86.5, None)
    d.show()
    app.processEvents()
    d.grab().save(os.path.join(OUT, "payment.png"))
    d.close()
    name = (wallets.all_wallets() or [{"name": ""}])[0]["name"]
    wd = WalletDialog(w, wallets.get(name), 86.5)
    wd.ref.setText("48213377")
    wd.show()
    app.processEvents()
    wd.grab().save(os.path.join(OUT, "wallet_pay.png"))
    print("✓", OUT)


if __name__ == "__main__":
    main()
