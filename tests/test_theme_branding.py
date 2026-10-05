# -*- coding: utf-8 -*-
"""السمة الداكنة (وضوح الألوان)، شعار المحل في العرض والطباعة، وسرعة تبديل اللغة/السمة"""
import base64
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core import settings, branding, receipts, products, sales, payroll, installments, customers


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _lum(hexcolor):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_dark_palette_is_readable():
    from ui import theme
    for bg in (theme.BG, theme.SURFACE, theme.SURFACE2):
        assert contrast(theme.TEXT, bg) >= 12
        assert contrast(theme.TEXT2, bg) >= 9
        assert contrast(theme.MUTED, bg) >= 4.5           # WCAG AA للنص الثانوي
        assert contrast(theme.FAINT, bg) >= 4.0
    # كل لون نص دلالي (أحمر الدين، أخضر الربح...) يُقرأ على البطاقات الداكنة
    for light in ("#2563EB", "#16A34A", "#DC2626", "#D97706", "#7C3AED", "#9333EA", "#0F766E", "#0369A1",
                  "#B42318", "#B54708", "#027A48", "#175CD3", "#1D4ED8", "#667085", "#101828"):
        assert contrast(theme.INLINE_MAP[light], theme.SURFACE) >= 4.5, light
    # وخلفيات الصفوف الملونة تبقى داكنة فيُقرأ عليها النص الفاتح
    for soft in ("#FEE2E2", "#FEF3C7", "#DCFCE7", "#EFF6FF", "#F1F5F9", "#FEF3F2", "#FFFAEB", "#ECFDF3"):
        assert contrast(theme.TEXT, theme.INLINE_MAP[soft]) >= 10, soft
    # ألوان الوضع الفاتح الأساسية واضحة أيضاً
    assert contrast("#101828", "#FFFFFF") >= 15 and contrast("#667085", "#FFFFFF") >= 4.5


def test_dark_theme_converts_sheets_and_inline_styles(app):
    from ui import theme
    from PySide6.QtWidgets import QLabel
    try:
        theme.apply(app, "dark")
        assert theme.is_dark()
        sheet = app.styleSheet()
        assert "#F4F6FB" not in sheet and theme.BG in sheet
        assert "background-color: white" not in sheet and "background: white" not in sheet
        lbl = QLabel()
        lbl.setStyleSheet("color:#DC2626; background:#FEE2E2;")
        assert "#F87171" in lbl.styleSheet() and "#FEE2E2" not in lbl.styleSheet()
        lbl.setStyleSheet("/*fixed*/color:#0F172A;")              # شاشة الزبون تبقى كما صُممت
        assert "#0F172A" in lbl.styleSheet()
        assert app.palette().window().color().name().upper() == theme.BG
        assert theme.c("#FEE2E2") != "#FEE2E2" and theme.c(None) is None
    finally:
        theme.apply(app, "light")
    assert not theme.is_dark() and "#F4F6FB" in app.styleSheet()
    assert theme.resolve("auto") in ("light", "dark")


def _png_b64(app):
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    img = QImage(60, 60, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    for x in range(10, 50):
        for y in range(10, 50):
            img.setPixelColor(x, y, QColor("#16A34A"))
    buf = QByteArray()
    io = QBuffer(buf)
    io.open(QIODevice.WriteOnly)
    img.save(io, "PNG")
    return img, base64.b64encode(bytes(buf)).decode()


def test_thermal_logo_has_white_background(app):
    from ui.settings_screen import logo_for_thermal
    img, _ = _png_b64(app)
    gray = logo_for_thermal(img)
    assert gray.pixelColor(0, 0).lightness() == 255             # الشفاف أبيض وليس أسود على الفاتورة
    assert gray.pixelColor(30, 30).lightness() < 200


def test_logo_appears_in_every_printout_and_display(app):
    _, b = _png_b64(app)
    assert branding.logo_img() == ""
    settings.set_many({"shop_logo": b, "shop_logo_color": b, "shop_address": "شارع السلام"})
    tag = "data:image/png;base64,"
    pid = products.add_product("أرز", "5001", "", 3, 5, 50, 2)
    cid = customers.add_customer("سامي", "0599000000", opening_balance=300)
    inv = sales.create_sale([{"product_id": pid, "product_name": "أرز", "quantity": 2, "unit_price": 5}])["invoice_id"]
    emp = payroll.add_employee("يوسف", 1000)
    pay = payroll.pay_salary(emp, "2026-01", method=payroll.PAY_BANK)
    plan = installments.create_plan(cid, 3, "2026-02-01")
    from core import financial_audit, owner_web, orders
    docs = {
        "receipt": receipts.invoice_html(inv),
        "statement": receipts.statement_html(cid),
        "payslip": payroll.payslip_html(pay["id"]),
        "installments": installments.schedule_html(plan),
        "audit": financial_audit.report_html(financial_audit.run("2026-01-01", "2026-12-31")),
        "a4 report": branding.document("<p>x</p>", "تقرير"),
        "owner web": owner_web.login_page(),
        "online store": orders.store_page(),
    }
    for name, html in docs.items():
        assert tag in html, name
    assert "شارع السلام" in branding.print_header()
    # الواجهة: القائمة الجانبية وشاشة الدخول وشاشة الزبون
    from ui.main_window import MainWindow
    from ui.dialogs import LoginDialog
    from ui.customer_display import CustomerDisplay
    w = MainWindow()
    assert w.logo_tile.pixmap() is not None and not w.logo_tile.pixmap().isNull()
    from PySide6.QtWidgets import QLabel
    d = LoginDialog()
    assert any(lbl.pixmap() and not lbl.pixmap().isNull() for lbl in d.findChildren(QLabel))
    cd = CustomerDisplay()
    assert tag in cd.shop.text() and tag in cd.items.text()
    cd.close()
    w.close()


def test_pages_build_on_demand_and_switch_is_fast(app):
    from ui import theme
    from ui.main_window import MainWindow, PAGES
    w = MainWindow()
    w.show()
    built = set(dict.keys(w.pages))
    assert "pos" in built and "orders" in built and len(built) < len(PAGES)
    w.go("reports")
    assert "reports" in dict.keys(w.pages)
    t = time.time()
    w2 = w.switch_theme("dark")
    assert theme.is_dark() and w2.current_key == "reports"
    w3 = w2.switch_theme("light")
    assert not theme.is_dark()
    assert time.time() - t < 6
    from core import i18n
    w4 = w3.switch_language("en")
    assert "Accounting" in w4.windowTitle()                   # عنوان النافذة يتبع اللغة
    w5 = w4.switch_language("ar")
    assert "برنامج المحاسبة" in w5.windowTitle() and i18n.language() == "ar"
    w5.close()
