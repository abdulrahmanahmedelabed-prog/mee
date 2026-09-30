# -*- coding: utf-8 -*-
"""النافذة الرئيسية: شريط جانبي للتنقل + شريط علوي (المستخدم، الوردية، الساعة)"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QPushButton,
                               QStackedWidget, QButtonGroup, QDialog, QScrollArea)

from core import auth, settings, shifts, backup, config, remote, license, vendor
from ui.widgets import button, ask
from ui.dialogs import ChangePasswordDialog, LoginDialog

from ui.dashboard_screen import DashboardScreen
from ui.pos_screen import POSScreen
from ui.invoices_screen import InvoicesScreen
from ui.inventory_screen import InventoryScreen
from ui.customers_screen import CustomersScreen
from ui.suppliers_screen import SuppliersScreen
from ui.expenses_screen import ExpensesScreen
from ui.cash_screen import CashScreen
from ui.reports_screen import ReportsScreen
from ui.expiry_screen import ExpiryScreen
from ui.settings_screen import SettingsScreen
from ui.accounting_screen import AccountingScreen
from ui.cheques_screen import ChequesScreen
from ui.promotions_screen import PromotionsScreen
from ui.reorder_screen import ReorderScreen
from ui.insights_screen import InsightsScreen
from ui.orders_screen import OrdersScreen
from ui.help_screen import HelpScreen

VERSION = vendor.VERSION
# تُخفى في الوضع المبسّط (تظهر عند إلغائه من الإعدادات)
ADVANCED_PAGES = {"insights", "orders", "reorder", "promotions", "cheques", "accounting"}

PAGES = [
    ("dashboard", "🏠   لوحة التحكم", ("dashboard",), DashboardScreen),
    ("insights", "🤖   المستشار الذكي", ("reports",), InsightsScreen),
    ("pos", "🧾   نقطة البيع", ("pos",), POSScreen),
    ("orders", "🛵   الطلبات الأونلاين", ("pos",), OrdersScreen),
    ("invoices", "📄   الفواتير والمرتجعات", ("invoices",), InvoicesScreen),
    ("inventory", "📦   المخزون", ("inventory",), InventoryScreen),
    ("expiry", "⏳   الصلاحية", ("inventory",), ExpiryScreen),
    ("customers", "👥   العملاء والديون", ("customers",), CustomersScreen),
    ("suppliers", "🚚   الموردون والمشتريات", ("suppliers",), SuppliersScreen),
    ("reorder", "🧠   الطلبيات الذكية", ("suppliers",), ReorderScreen),
    ("promotions", "🎁   العروض والولاء", ("promotions",), PromotionsScreen),
    ("expenses", "💸   المصاريف", ("expenses",), ExpensesScreen),
    ("cash", "💵   الصندوق والورديات", ("cash",), CashScreen),
    ("cheques", "🏦   الشيكات", ("cheques",), ChequesScreen),
    ("reports", "📊   التقارير", ("reports",), ReportsScreen),
    ("accounting", "📚   المحاسبة والميزانية", ("accounting",), AccountingScreen),
    ("settings", "⚙   الإعدادات", ("settings", "backup"), SettingsScreen),
    ("help", "❓   المساعدة", ("pos", "dashboard"), HelpScreen),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1360, 820)
        from ui.i18n_qt import direction
        self.setLayoutDirection(direction())
        self.pages = {}
        self.nav_buttons = {}

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- الشريط الجانبي
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(264)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(0, 18, 0, 14)
        sl.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(18, 0, 18, 12)
        head.setSpacing(10)
        logo = QLabel("🏪")
        logo.setObjectName("logoTile")
        logo.setFixedSize(44, 44)
        head.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.brand = QLabel()
        self.brand.setObjectName("brand")
        self.brand.setWordWrap(True)
        names.addWidget(self.brand)
        sub = QLabel(f"المحاسبة ونقاط البيع • v{VERSION}")
        sub.setObjectName("brandSub")
        names.addWidget(sub)
        head.addLayout(names, 1)
        sl.addLayout(head)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        # قائمة التنقل داخل منطقة تمرير حتى لا تفرض ارتفاعاً على الشاشات الصغيرة (1366×768)
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        nav_w = QWidget()
        nav = QVBoxLayout(nav_w)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(2)
        for key, label, perms, _ in PAGES:
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.group.addButton(b)
            self.nav_buttons[key] = b
            nav.addWidget(b)
        nav.addStretch()
        nav_scroll.setWidget(nav_w)
        sl.addWidget(nav_scroll, 1)
        # بطاقة المستخدم أسفل القائمة (مثل تطبيقات الجوال)
        ucard = QFrame()
        ucard.setObjectName("userCard")
        ul = QHBoxLayout(ucard)
        ul.setContentsMargins(10, 8, 8, 8)
        ul.setSpacing(8)
        self.avatar = QLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(36, 36)
        ul.addWidget(self.avatar)
        who = QVBoxLayout()
        who.setSpacing(0)
        self.user_lbl = QLabel()
        self.user_lbl.setObjectName("userName")
        self.role_lbl = QLabel()
        self.role_lbl.setObjectName("userRole")
        who.addWidget(self.user_lbl)
        who.addWidget(self.role_lbl)
        ul.addLayout(who, 1)
        pw = button("🔑", "iconBtn", lambda: ChangePasswordDialog(self).exec(), "تغيير كلمة المرور")
        out = button("🚪", "iconBtn", self.logout, "تسجيل خروج")
        ul.addWidget(pw)
        ul.addWidget(out)
        uwrap = QHBoxLayout()
        uwrap.setContentsMargins(12, 8, 12, 0)
        uwrap.addWidget(ucard)
        sl.addLayout(uwrap)
        root.addWidget(self.sidebar)

        # ---- المحتوى
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        top = QFrame()
        top.setObjectName("topbar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 16, 24, 6)
        tl.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel()
        self.page_title.setObjectName("topTitle")
        self.greeting = QLabel()
        self.greeting.setObjectName("topSub")
        titles.addWidget(self.page_title)
        titles.addWidget(self.greeting)
        tl.addLayout(titles)
        tl.addStretch()
        self.shift_chip = QLabel()
        self.shift_chip.setCursor(Qt.PointingHandCursor)
        self.shift_chip.mousePressEvent = lambda e: self.go("cash")
        tl.addWidget(self.shift_chip)
        self.net_chip = QLabel()
        self.net_chip.setObjectName("chip")
        tl.addWidget(self.net_chip)
        self.clock = QLabel()
        self.clock.setObjectName("chip")
        tl.addWidget(self.clock)
        content.addWidget(top)
        # شريط الترخيص (يظهر في التجربة أو عند الانتهاء)
        self.license_bar = QFrame()
        self.license_bar.setObjectName("licenseBar")
        lb = QHBoxLayout(self.license_bar)
        lb.setContentsMargins(16, 8, 10, 8)
        self.license_lbl = QLabel()
        self.license_lbl.setObjectName("licenseText")
        self.license_lbl.setWordWrap(True)
        lb.addWidget(self.license_lbl, 1)
        lb.addWidget(button("🔑 تفعيل البرنامج", "warnBtn", self.open_license))
        lwrap = QHBoxLayout()
        lwrap.setContentsMargins(24, 4, 24, 4)
        lwrap.addWidget(self.license_bar)
        content.addLayout(lwrap)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        wrap = QWidget()
        wrap.setLayout(content)
        root.addWidget(wrap, 1)
        self.setCentralWidget(central)

        for key, label, perms, cls in PAGES:
            w = cls()
            self.pages[key] = w
            self.stack.addWidget(w)
        self.pages["pos"].sale_completed.connect(self.update_header)
        self.pages["cash"].shift_changed.connect(self.update_header)
        self.pages["dashboard"].navigate.connect(self.go)
        self.pages["insights"].navigate.connect(self.go)
        self.pages["orders"].load_into_pos.connect(self.order_to_pos)
        self.pages["orders"].new_orders.connect(self.on_new_orders)

        self._update_info = None
        import threading
        from core import updates
        threading.Thread(target=lambda: setattr(self, "_update_info", updates.check()), daemon=True).start()
        QTimer.singleShot(8000, self.show_update)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(15000)
        self.apply_user()

    # ------------------------------------------------------------------
    def apply_user(self):
        u = auth.current_user()
        first = self.refresh_nav()
        from core.i18n import tr
        name = u["full_name"] or u["username"]
        self.user_lbl.setText(name)
        self.role_lbl.setText(tr(auth.ROLES.get(u["role"], u["role"])))
        short = tr(name).strip()
        if short.startswith("ال") and len(short) > 2:
            short = short[2:]
        self.avatar.setText((short[:1] or "؟").upper())
        self.update_header()
        # الكاشير يبدأ مباشرة بنقطة البيع
        self.go("pos" if u["role"] == "cashier" else (first or "pos"))

    def refresh_nav(self):
        """إظهار الشاشات حسب الصلاحيات، وإخفاء المتقدمة في الوضع المبسّط"""
        simple = settings.get_bool("simple_mode")
        first = None
        for key, label, perms, _ in PAGES:
            allowed = any(auth.has_permission(p) for p in perms) and not (simple and key in ADVANCED_PAGES)
            self.nav_buttons[key].setVisible(allowed)
            if allowed and first is None:
                first = key
        return first

    def update_header(self):
        try:
            self._update_header()
        except remote.RemoteError:   # نقطة بيع فرعية فقدت الاتصال: نقطة البيع تعمل محلياً
            self.shift_chip.setText("⚠ لا اتصال بالجهاز الرئيسي")
            self.tick()

    def _update_header(self):
        self.brand.setText(settings.get("shop_name"))
        self.setWindowTitle(f"{settings.get('shop_name')} — برنامج المحاسبة ونقاط البيع")
        s = shifts.current_shift()
        if s:
            self.shift_chip.setText(f"🟢 وردية #{s['id']} مفتوحة")
            self.shift_chip.setObjectName("chipOk")
        else:
            self.shift_chip.setText("🟠 لا توجد وردية مفتوحة")
            self.shift_chip.setObjectName("chipWarn")
        mode = config.get("mode")
        term = config.get("terminal_name")
        self.net_chip.setVisible(mode != config.MODE_STANDALONE)
        if mode == config.MODE_SERVER:
            self.net_chip.setText(f"🖧 {term} (رئيسي) {config.local_ip()}")
        elif mode == config.MODE_CLIENT:
            self.net_chip.setText(f"💻 {term} ← {config.get('server_host')}")
        self.shift_chip.style().unpolish(self.shift_chip)
        self.shift_chip.style().polish(self.shift_chip)
        self.update_license()
        self.tick()

    def show_update(self):
        info = self._update_info
        if info:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            b = button(f"⬆ نسخة جديدة {info.get('version')}", "successBtn",
                       lambda: QDesktopServices.openUrl(QUrl(info.get("url", ""))), info.get("notes", ""))
            self.license_bar.layout().insertWidget(1, b)
            self.license_bar.show()

    def order_to_pos(self, order):
        pos = self.pages["pos"]
        if pos.cart and not ask(self, "توجد سلة غير مكتملة في نقطة البيع. استبدالها بالطلب؟"):
            return
        self.go("pos")
        pos.load_order(order)

    def on_new_orders(self, n):
        from core.i18n import tr
        base = self.nav_buttons["orders"].property("_i18n_setText") or self.nav_buttons["orders"].text()
        label = base.split(" (")[0]
        self.nav_buttons["orders"].setText(f"{label} ({n})" if n else label)
        if n:
            from PySide6.QtWidgets import QApplication
            QApplication.beep()

    def update_license(self):
        try:
            st = license.status()
        except Exception:
            self.license_bar.hide()
            return
        show = st["state"] != "licensed" or (st["days_left"] is not None and st["days_left"] <= 15)
        self.license_bar.setVisible(show)
        if st["state"] in ("expired", "license_expired"):
            self.license_bar.setStyleSheet("QFrame#licenseBar { background:#FEF3F2; border:1px solid #FECDCA; }")
            self.license_lbl.setStyleSheet("color:#B42318; font-weight:700;")
        text = st["message"]
        if vendor.VENDOR_PHONE:
            text += f"   —   للتفعيل والدعم: {vendor.VENDOR_NAME} {vendor.VENDOR_PHONE}"
        self.license_lbl.setText("🔑 " + text)

    def open_license(self):
        if not auth.has_permission("settings"):
            from ui.widgets import info
            info(self, "التفعيل من حساب مدير النظام: الإعدادات ← الترخيص والتفعيل.")
            return
        self.go("settings")
        self.pages["settings"].show_license_tab()

    def tick(self):
        days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        n = datetime.now()
        self.clock.setText(f"🕒 {n:%H:%M}")
        from core.i18n import tr
        self.greeting.setText(f"{tr(days[n.weekday()])} • {n:%Y-%m-%d}")

    def go(self, key):
        if key not in self.pages or not self.nav_buttons[key].isVisible():
            return
        self.nav_buttons[key].setChecked(True)
        w = self.pages[key]
        self.stack.setCurrentWidget(w)
        self.page_title.setText(self.nav_buttons[key].text().split("   ")[-1])
        if hasattr(w, "refresh"):
            w.refresh()

    def logout(self):
        pos = self.pages["pos"]
        if pos.cart and not ask(self, "توجد سلة غير مكتملة في نقطة البيع. تسجيل الخروج سيُفرغها. متابعة؟"):
            return
        pos.clear_cart()
        auth.logout()
        self.hide()
        dlg = LoginDialog()
        if dlg.exec() != QDialog.Accepted:
            self.close()
            return
        if auth.current_user().get("must_change_password"):
            ChangePasswordDialog(None, forced=True).exec()
        self.apply_user()
        self.show()

    def closeEvent(self, event):
        pos = self.pages["pos"]
        if pos.cart and not ask(self, "توجد سلة غير مكتملة. هل تريد الخروج؟"):
            event.ignore()
            return
        if not remote.is_client():
            try:
                backup.create_backup(tag="close")
            except Exception:
                pass
        event.accept()
