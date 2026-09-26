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

VERSION = vendor.VERSION

PAGES = [
    ("dashboard", "🏠   لوحة التحكم", ("dashboard",), DashboardScreen),
    ("pos", "🧾   نقطة البيع", ("pos",), POSScreen),
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
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1360, 820)
        self.setLayoutDirection(Qt.RightToLeft)
        self.pages = {}
        self.nav_buttons = {}

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- الشريط الجانبي
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(225)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(0, 0, 0, 12)
        sl.setSpacing(2)
        self.brand = QLabel()
        self.brand.setObjectName("brand")
        self.brand.setWordWrap(True)
        sl.addWidget(self.brand)
        sub = QLabel(f"برنامج المحاسبة ونقاط البيع • v{VERSION}")
        sub.setObjectName("brandSub")
        sl.addWidget(sub)
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
        self.user_lbl = QLabel()
        self.user_lbl.setObjectName("brandSub")
        self.user_lbl.setWordWrap(True)
        sl.addWidget(self.user_lbl)
        pw = QPushButton("🔑   تغيير كلمة المرور")
        pw.setObjectName("navBtn")
        pw.clicked.connect(lambda: ChangePasswordDialog(self).exec())
        sl.addWidget(pw)
        out = QPushButton("🚪   تسجيل خروج")
        out.setObjectName("navBtn")
        out.clicked.connect(self.logout)
        sl.addWidget(out)
        root.addWidget(self.sidebar)

        # ---- المحتوى
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        top = QFrame()
        top.setObjectName("topbar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 10, 20, 10)
        self.page_title = QLabel()
        self.page_title.setObjectName("topTitle")
        tl.addWidget(self.page_title)
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
        self.license_bar.setStyleSheet("QFrame { background:#FEF3C7; border-bottom:1px solid #FDE68A; }")
        lb = QHBoxLayout(self.license_bar)
        lb.setContentsMargins(20, 6, 20, 6)
        self.license_lbl = QLabel()
        self.license_lbl.setStyleSheet("color:#92400E; font-weight:700;")
        lb.addWidget(self.license_lbl)
        lb.addStretch()
        lb.addWidget(button("🔑 تفعيل البرنامج", "warnBtn", self.open_license))
        content.addWidget(self.license_bar)
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

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(15000)
        self.apply_user()

    # ------------------------------------------------------------------
    def apply_user(self):
        u = auth.current_user()
        first = None
        for key, label, perms, _ in PAGES:
            allowed = any(auth.has_permission(p) for p in perms)
            self.nav_buttons[key].setVisible(allowed)
            if allowed and first is None:
                first = key
        self.user_lbl.setText(f"👤 {u['full_name'] or u['username']} — {auth.ROLES.get(u['role'], u['role'])}")
        self.update_header()
        # الكاشير يبدأ مباشرة بنقطة البيع
        self.go("pos" if u["role"] == "cashier" else (first or "pos"))

    def update_header(self):
        self.brand.setText(f"🏪 {settings.get('shop_name')}")
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

    def update_license(self):
        try:
            st = license.status()
        except Exception:
            self.license_bar.hide()
            return
        show = st["state"] != "licensed" or (st["days_left"] is not None and st["days_left"] <= 15)
        self.license_bar.setVisible(show)
        if st["state"] in ("expired", "license_expired"):
            self.license_bar.setStyleSheet("QFrame { background:#FEE2E2; border-bottom:1px solid #FECACA; }")
            self.license_lbl.setStyleSheet("color:#991B1B; font-weight:700;")
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
        self.clock.setText(f"{days[n.weekday()]} {n:%Y-%m-%d  %H:%M}")

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
