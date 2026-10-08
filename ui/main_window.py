# -*- coding: utf-8 -*-
"""النافذة الرئيسية: شريط جانبي للتنقل + شريط علوي (المستخدم، الوردية، الساعة)"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QPushButton,
                               QStackedWidget, QButtonGroup, QDialog, QScrollArea, QLineEdit)

from core import auth, settings, shifts, backup, config, remote, license, vendor
from ui.widgets import button, ask
from ui import theme
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
from ui.audit_screen import AuditScreen
from ui.payroll_screen import PayrollScreen
from ui.smart_screen import SmartScreen

VERSION = vendor.VERSION
# تُخفى في الوضع المبسّط (تظهر عند إلغائه من الإعدادات)
ADVANCED_PAGES = {"insights", "orders", "reorder", "promotions", "cheques", "accounting", "audit", "payroll", "smart"}

PAGES = [
    ("dashboard", "🏠   لوحة التحكم", ("dashboard",), DashboardScreen),
    ("smart", "🧭   مساعد المحل", ("reports",), SmartScreen),
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
    ("payroll", "👔   الموظفون والرواتب", ("expenses",), PayrollScreen),
    ("cash", "💵   الصندوق والورديات", ("cash",), CashScreen),
    ("cheques", "🏦   الشيكات", ("cheques",), ChequesScreen),
    ("reports", "📊   التقارير", ("reports",), ReportsScreen),
    ("accounting", "📚   المحاسبة والميزانية", ("accounting",), AccountingScreen),
    ("audit", "🔎   التدقيق المالي", ("accounting",), AuditScreen),
    ("settings", "⚙   الإعدادات", ("settings", "backup"), SettingsScreen),
    ("help", "❓   المساعدة", ("pos", "dashboard"), HelpScreen),
]


class _Veil(QFrame):
    """طبقة شفافة فوق النافذة برسالة (تبديل اللغة/السمة)؛ fade=True تتلاشى وحدها بعد ظهور النافذة"""
    def __init__(self, win, text, fade=False):
        from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation
        from ui.i18n_qt import set_raw_text
        super().__init__(win)
        self.text = text
        self.setObjectName("veil")
        self.setStyleSheet("QFrame#veil { background: rgba(15, 23, 42, 150); }"
                           "QLabel { background: palette(window); color: palette(window-text); border-radius: 18px;"
                           " padding: 26px 40px; font-size: 20px; font-weight: 700; }")
        lay = QVBoxLayout(self)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        set_raw_text(lbl, text)
        lay.addWidget(lbl, 0, Qt.AlignCenter)
        self.setGeometry(win.rect())
        self.raise_()
        self.show()
        if fade:
            eff = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(eff)
            self.anim = QPropertyAnimation(eff, b"opacity", self)
            self.anim.setDuration(350)
            self.anim.setStartValue(1.0)
            self.anim.setEndValue(0.0)
            self.anim.finished.connect(self.deleteLater)
            QTimer.singleShot(60, self.anim.start)
        else:
            self.repaint()
            QApplication.processEvents()


class _Pages(dict):
    """قاموس الشاشات: تُنشأ الشاشة عند أول طلب لها"""
    def __init__(self, win):
        super().__init__()
        self.win = win

    def __missing__(self, key):
        cls = next(c for k, _, _, c in PAGES if k == key)
        w = cls()
        self[key] = w
        self.win._page_built(key, w)
        return w


class MainWindow(QMainWindow):
    def __init__(self, start=None):
        super().__init__()
        self.resize(1360, 820)
        self._start = start
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
        self.logo_tile = logo
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
        self.brand_sub = sub
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
        self.pw_btn = pw
        uwrap = QHBoxLayout()
        uwrap.setContentsMargins(12, 8, 12, 0)
        self.uwrap = uwrap
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
        # «اسأل محلك» من أي شاشة (Ctrl+K)
        self.ask_box = QLineEdit()
        self.ask_box.setObjectName("askBox")
        self.ask_box.setPlaceholderText("✨ اسأل محلك…  (Ctrl+K)")
        self.ask_box.setMinimumWidth(40)          # يتقلص ثم يختفي على الشاشات الضيقة (لا يفرض عرضاً على النافذة)
        self.ask_box.setMaximumWidth(320)
        self.ask_box.returnPressed.connect(self.ask_shop)
        tl.addWidget(self.ask_box)
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: (self.ask_box.setFocus(), self.ask_box.selectAll()))
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
        # تبديل اللغة فوراً (يظهر اسم اللغة الأخرى بحروفها)
        from core import i18n as _i18n
        from ui import i18n_qt as _iq
        self.lang_btn = QPushButton()
        self.lang_btn.setObjectName("secondaryBtn")
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        _iq.set_raw_text(self.lang_btn, "🌐 English" if _i18n.is_rtl() else "🌐 العربية")
        self.lang_btn.setToolTip("تغيير لغة الواجهة فوراً")
        self.lang_btn.clicked.connect(lambda: self.switch_language())
        self.plan_chip = QPushButton()
        self.plan_chip.setObjectName("ghostBtn")
        self.plan_chip.setCursor(Qt.PointingHandCursor)
        self.plan_chip.setToolTip("باقتك — اضغط لمقارنة الباقات")
        self.plan_chip.clicked.connect(lambda: self.open_plans())
        self.plan_chip.setMinimumWidth(40)
        tl.addWidget(self.plan_chip)
        tl.addWidget(self.lang_btn)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("secondaryBtn")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        _iq.set_raw_text(self.theme_btn, "☀" if theme.is_dark() else "🌙")
        self.theme_btn.setToolTip("الوضع الفاتح" if theme.is_dark() else "الوضع الداكن")
        self.theme_btn.clicked.connect(lambda: self.switch_theme())
        tl.addWidget(self.theme_btn)
        self.pair_btn = QPushButton()
        self.pair_btn.setObjectName("secondaryBtn")
        self.pair_btn.setCursor(Qt.PointingHandCursor)
        _iq.set_raw_text(self.pair_btn, "📱")
        self.pair_btn.setToolTip("ربط تطبيق الجوال (رمز التحميل ورمز الربط)")
        self.pair_btn.clicked.connect(self.open_pairing)
        self.pair_btn.setMinimumWidth(1)             # لا يفرض عرضاً على النافذة؛ يختفي على الشاشات الضيقة
        tl.addWidget(self.pair_btn)
        self.calc_btn = QPushButton()
        self.calc_btn.setObjectName("secondaryBtn")
        self.calc_btn.setCursor(Qt.PointingHandCursor)
        _iq.set_raw_text(self.calc_btn, "🧮")
        self.calc_btn.setToolTip("الآلة الحاسبة وحاسبة التسعير (Ctrl+=)")
        self.calc_btn.clicked.connect(lambda: self.open_calculator())
        self.calc_btn.setMinimumWidth(1)
        tl.addWidget(self.calc_btn)
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self.open_calculator())
        from ui import calculator as _calc
        _calc.track_focus()
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
        lb.addWidget(button("💎 الباقات والترقية", "warnBtn", self.open_plans))
        lwrap = QHBoxLayout()
        lwrap.setContentsMargins(24, 4, 24, 4)
        lwrap.addWidget(self.license_bar)
        content.addLayout(lwrap)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        from ui.jobs import JobBar
        self.jobs = JobBar()                      # الطباعة الثقيلة في الخلفية مع شريط تقدّم
        content.addWidget(self.jobs)
        wrap = QWidget()
        wrap.setLayout(content)
        root.addWidget(wrap, 1)
        self.setCentralWidget(central)

        # الشاشات تُبنى عند أول فتح لها (فتح البرنامج وتبديل اللغة أسرع بكثير)؛ نقطة البيع والطلبات تُبنى فوراً
        self.page_holders = {}
        self._refresh_cost = {}               # كم تأخذ كل شاشة لتحميل بياناتها (لتبديل السمة بأسرع طريقة)
        self.pages = _Pages(self)
        for key, label, perms, cls in PAGES:
            if key == "pos":                  # نقطة البيع تعيد ترتيب نفسها لتظهر كاملة دائماً بلا تمرير
                holder = self.pages["pos"]
            else:                             # بقية الشاشات تتمرر بدل أن تفرض حجماً أكبر من الشاشة
                holder = QScrollArea()
                holder.setWidgetResizable(True)
                holder.setFrameShape(QFrame.NoFrame)
                holder.setObjectName("pageScroll")
            self.page_holders[key] = holder
            self.stack.addWidget(holder)
        self.pages["orders"]                  # تراقب الطلبات الجديدة في الخلفية
        from ui.plans_dialog import LockedPanel
        self.locked = LockedPanel()
        self.locked.upgrade.connect(self.open_plans)
        self.stack.addWidget(self.locked)
        self._rail = None
        self.setMinimumSize(760, 520)

        self._update_info = None
        import threading
        from core import updates
        threading.Thread(target=lambda: setattr(self, "_update_info", updates.check()), daemon=True).start()
        QTimer.singleShot(8000, self.show_update)
        # المدقق اليومي التلقائي (على جهاز المحل الرئيسي): مرة في اليوم، في الخلفية، وتنبيه عند ملاحظة مهمة
        self._auto_audit = None
        self._audit_tries = 0
        import sys
        from core import remote
        if not remote.is_client() and "pytest" not in sys.modules:
            threading.Thread(target=self._run_auto_audit, daemon=True).start()
            QTimer.singleShot(60000, self.show_audit_alert)
            # الفوترة الإلكترونية: إرسال المعلّق للمنصة في الخلفية كل دقيقة
            self._einv_timer = QTimer(self)
            self._einv_timer.timeout.connect(self._send_einvoices)
            self._einv_timer.start(60000)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(15000)
        self.apply_user()

    def _page_built(self, key, w):
        holder = self.page_holders.get(key)
        if isinstance(holder, QScrollArea):
            holder.setWidget(w)
        signals = {"pos": [("sale_completed", self.update_header), ("sale_completed", self._send_einvoices)], "cash": [("shift_changed", self.update_header)],
                   "dashboard": [("navigate", self.go)], "insights": [("navigate", self.go)],
                   "smart": [("navigate", self.go)],
                   "orders": [("load_into_pos", self.order_to_pos), ("new_orders", self.on_new_orders)]}
        for sig, slot in signals.get(key, []):
            getattr(w, sig).connect(slot)

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
        start, self._start = getattr(self, "_start", None), None
        if start and start in self.page_holders and not self.nav_buttons[start].isHidden():
            self.go(start)                             # بعد تبديل اللغة/السمة: نفس الشاشة
        else:
            self.go("pos" if u["role"] == "cashier" else (first or "pos"))

    def refresh_nav(self):
        """إظهار الشاشات حسب الصلاحيات، وإخفاء المتقدمة في الوضع المبسّط، وقفل 🔒 لما ليس في الباقة"""
        from core import plans
        simple = settings.get_bool("simple_mode")
        tier = plans.current()
        first = None
        self.locked_pages = set()
        for key, label, perms, _ in PAGES:
            allowed = any(auth.has_permission(p) for p in perms) and not (simple and key in ADVANCED_PAGES)
            b = self.nav_buttons[key]
            b.setVisible(allowed)
            locked = not plans.page_allowed(key, tier)
            if locked:
                self.locked_pages.add(key)
            full = f"{label}  🔒" if locked else label
            if not (key == "orders" and getattr(self, "_orders_count", 0)):
                b.setProperty("full_label", full)
            if allowed and not locked and first is None:
                first = key
        self._apply_nav_texts()
        return first

    def update_header(self):
        try:
            self._update_header()
        except remote.RemoteError:   # نقطة بيع فرعية فقدت الاتصال: نقطة البيع تعمل محلياً
            self.shift_chip.setText("⚠ لا اتصال بالجهاز الرئيسي")
            self.tick()

    def _update_header(self):
        self.brand.setText(settings.get("shop_name"))
        from core import branding
        pm = branding.logo_pixmap(40)                 # شعار المحل إن وُجد، وإلا أيقونة المتجر
        if pm:
            self.logo_tile.setPixmap(pm)
            self.logo_tile.setStyleSheet("background: white; border: 1px solid #E9EDF5;")
        else:
            self.logo_tile.setText("🏪")
            self.logo_tile.setStyleSheet("")
        from core.i18n import tr
        title = f"{settings.get('shop_name')} — {tr('برنامج المحاسبة ونقاط البيع')}"
        if getattr(self, "training", False):
            title = f"🎓 {tr('نسخة التدريب (بيانات تجريبية)')} — {title}"
        self.setWindowTitle(title)
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
        self._orders_count = n
        b = self.nav_buttons["orders"]
        base = (b.property("full_label") or b.property("_i18n_setText") or b.text()).split(" (")[0]
        b.setProperty("full_label", f"{base} ({n})" if n else base)
        if self._rail:
            b.setText(base.split("   ")[0] + (f" {n}" if n else ""))
            b.setToolTip(b.property("full_label"))
        else:
            b.setText(f"{base} ({n})" if n else base)
        if n:
            from PySide6.QtWidgets import QApplication
            QApplication.beep()

    def update_license(self):
        try:
            st = license.status()
        except Exception:
            self.license_bar.hide()
            self.plan_chip.hide()
            return
        from core import plans
        tier = st.get("tier") or plans.FREE
        chip = (f"{plans.label(tier)} • تجربة {st['days_left']} يوماً" if st["state"] == "trial" else plans.label(tier))
        self.plan_chip.setText(chip)
        self.plan_chip.setStyleSheet(f"color:{plans.COLORS[tier]}; font-weight:700;")
        self.plan_chip.setVisible(self.width() >= 1000)
        days = st["days_left"]
        show = (st["state"] in ("free", "license_expired") or bool(st.get("key_error"))
                or (days is not None and days <= (7 if st["state"] == "trial" else 15)))
        self.license_bar.setVisible(show)
        if st["state"] == "license_expired":
            self.license_bar.setStyleSheet("QFrame#licenseBar { background:#FEF3F2; border:1px solid #FECDCA; }")
            self.license_lbl.setStyleSheet("color:#B42318; font-weight:700;")
        elif st["state"] == "free":
            self.license_bar.setStyleSheet("QFrame#licenseBar { background:#EEF4FF; border:1px solid #DCE7FF; }")
            self.license_lbl.setStyleSheet("color:#1D4ED8; font-weight:600;")
        text = st["message"]
        if vendor.VENDOR_PHONE:
            text += f"   —   للتفعيل والدعم: {vendor.display_name()} {vendor.VENDOR_PHONE_DISPLAY}"
        self.license_lbl.setText(("💎 " if st["state"] in ("free", "trial") else "🔑 ") + text)

    def ask_shop(self):
        text = self.ask_box.text().strip()
        if not text:
            return
        self.ask_box.clear()
        from core import plans
        if not plans.has("ask"):
            self.open_plans("ask")
            return
        self.go("smart")
        if self.current_key == "smart":
            self.pages["smart"].ask(text)

    def open_plans(self, feature=None):
        from ui.plans_dialog import PlansDialog
        PlansDialog(self, feature if isinstance(feature, str) else None).exec()

    def open_license(self):
        if not auth.has_permission("settings"):
            from ui.widgets import info
            info(self, "التفعيل من حساب مدير النظام: الإعدادات ← الترخيص والتفعيل.")
            return
        self.go("settings")
        self.pages["settings"].show_license_tab()

    def _send_einvoices(self):
        from core import settings as _s
        if not _s.get("einv_system"):
            return
        import threading

        def work():
            try:
                from core import einvoicing
                einvoicing.send_pending()
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _run_auto_audit(self):
        import time
        time.sleep(40)                     # بعد اكتمال فتح البرنامج
        try:
            from core import plans, accountant
            if plans.has("audit"):
                self._auto_audit = accountant.daily_audit()
        except Exception:
            pass

    def show_audit_alert(self):
        r = self._auto_audit
        if r is None:
            self._audit_tries += 1
            if self._audit_tries < 10:
                QTimer.singleShot(30000, self.show_audit_alert)
            return
        if not (r.get("critical") or r.get("high")) or not auth.has_permission("accounting"):
            return
        n = r.get("critical", 0) + r.get("high", 0)
        b = button(f"🔎 المدقق اليومي: {n} ملاحظة مهمة", "dangerBtn" if r.get("critical") else "secondaryBtn",
                   lambda: self.go("audit"), "\n".join(x["title"] for x in r.get("top", [])))
        self.license_bar.layout().insertWidget(1, b)
        self.license_bar.show()

    def tick(self):
        days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        n = datetime.now()
        self.clock.setText(f"🕒 {n:%H:%M}")
        from core.i18n import tr
        self.greeting.setText(f"{tr(days[n.weekday()])} • {n:%Y-%m-%d}")

    def open_pairing(self):
        from ui.pair_dialog import open_pairing
        open_pairing(self)

    def open_calculator(self, tab=0):
        from ui.calculator import open_calculator
        return open_calculator(self, tab)

    def go(self, key):
        if key in ("calculator", "pricing"):                # «افتح الحاسبة» / «احسب سعر البيع» من المساعد
            self.open_calculator(1 if key == "pricing" else 0)
            return
        if key == "pair":                                  # «كيف أربط الجوال؟» من المساعد أو المساعدة
            self.open_pairing()
            return
        section = None
        if isinstance(key, str) and "/" in key:          # «reports/المبيعات اليومية»: الشاشة ثم القسم داخلها
            key, section = key.split("/", 1)
        if key not in self.page_holders or self.nav_buttons[key].isHidden():   # مخفية لعدم الصلاحية أو الوضع المبسّط
            return
        self.current_key = key
        self.nav_buttons[key].setChecked(True)
        b = self.nav_buttons[key]
        self.page_title.setText(next(lbl for k, lbl, _, _ in PAGES if k == key).split("   ")[-1])
        if key in getattr(self, "locked_pages", ()):          # ليست في الباقة: شرح الميزة وزر الترقية
            from core import plans
            self.locked.show_feature(plans.PAGE_FEATURE[key])
            self.stack.setCurrentWidget(self.locked)
            return
        w = self.pages[key]
        self.stack.setCurrentWidget(self.page_holders[key])
        if hasattr(w, "refresh"):
            import time
            t = time.perf_counter()
            w.refresh()
            self._refresh_cost[key] = time.perf_counter() - t
        if section and hasattr(w, "open_section"):
            w.open_section(section)

    def logout(self):
        pos = self.pages["pos"]
        if pos.cart and not ask(self, "توجد سلة غير مكتملة في نقطة البيع. تسجيل الخروج سيُفرغها. متابعة؟"):
            return
        pos.clear_cart()
        auth.logout()
        self.hide()
        from core import i18n
        before = (i18n.language(), theme.is_dark())
        if not LoginDialog.run_login():
            self.close()
            return
        if auth.current_user().get("must_change_password"):
            ChangePasswordDialog(None, forced=True).exec()
        if (i18n.language(), theme.is_dark()) != before:   # غيّر اللغة من شاشة الدخول: النافذة باللغة الجديدة
            self.current_key = None
            self.show()
            self._rebuild("🌐", lambda app: None)
            return
        self.apply_user()
        self.show()

    RAIL_WIDTH = 1300        # أضيق من هذا: القائمة الجانبية أيقونات فقط (مثل تطبيقات الجوال)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_rail(self.width() < self.RAIL_WIDTH)
        self.ask_box.setVisible(self.width() >= 1180)        # الشاشات الضيقة: من شاشة مساعد المحل أو Ctrl+K
        self.plan_chip.setVisible(self.width() >= 1000 and bool(self.plan_chip.text()))
        self.pair_btn.setVisible(self.width() >= 1100)       # الشاشات الضيقة: من المساعدة أو «كيف أربط الجوال؟»
        self.calc_btn.setVisible(self.width() >= 1060)       # الشاشات الضيقة: Ctrl+=

    def set_rail(self, rail):
        if rail == self._rail:
            return
        self._rail = rail
        self.sidebar.setFixedWidth(96 if rail else 264)
        self.brand.setVisible(not rail)
        self.brand_sub.setVisible(not rail)
        self.user_lbl.setVisible(not rail)
        self.role_lbl.setVisible(not rail)
        self.pw_btn.setVisible(not rail)
        self.uwrap.setContentsMargins(*((6, 8, 6, 0) if rail else (12, 8, 12, 0)))
        self._apply_nav_texts()

    def _apply_nav_texts(self):
        rail = bool(self._rail)
        for key, label, _, _ in PAGES:
            b = self.nav_buttons[key]
            full = b.property("full_label") or label
            b.setProperty("full_label", full)
            if rail:
                b.setText(full.split("   ")[0] + (" 🔒" if full.endswith("🔒") else "")
                          + (f" {self._orders_count}" if key == "orders" and getattr(self, "_orders_count", 0) else ""))
                b.setToolTip(full)
                b.setStyleSheet("text-align: center; padding: 11px 0; font-size: 18px;")
            else:
                b.setText(full)
                b.setToolTip("")
                b.setStyleSheet("")

    def switch_language(self, lang=None):
        """تبديل لغة الواجهة فوراً: تُبنى النافذة من جديد باللغة الأخرى على نفس الشاشة، دون إعادة تشغيل أو تسجيل دخول.
        السلة غير المكتملة في نقطة البيع تنتقل للنافذة الجديدة كما هي."""
        from core import i18n
        from ui import i18n_qt
        lang = lang or ("en" if i18n.is_rtl() else "ar")

        def apply(app):
            config.save({"language": lang})
            i18n_qt.apply_language(lang, app)
            app.setLayoutDirection(i18n_qt.direction())
            theme.apply(app)
        return self._rebuild("🌐  جارٍ التبديل إلى العربية…\nSwitching to Arabic…" if lang == "ar"
                             else "🌐  Switching to English…\nجارٍ التبديل إلى الإنجليزية…", apply)

    def switch_theme(self, choice=None):
        """فاتح ↔ داكن فوراً على نفس النافذة (أو تطبيق اختيار الإعدادات: فاتح/داكن/تلقائي).
        لا إعادة بناء ولا إعادة تحميل للبيانات: تتلاشى صورة المظهر القديم فوق الجديد في ربع ثانية."""
        import shiboken6
        from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation
        choice = choice or (theme.LIGHT if theme.is_dark() else theme.DARK)
        app = QApplication.instance()
        shot = QLabel(self)                                  # المظهر الحالي يبقى ظاهراً حتى يكتمل الجديد
        shot.setPixmap(self.grab())
        shot.setGeometry(self.rect())
        shot.show()
        shot.raise_()
        app.setOverrideCursor(Qt.WaitCursor)
        try:
            # الشاشات المبنية تُحذف وتُبنى عند فتحها (كل فتح لشاشة يحدّث بياناتها أصلاً) — بناؤها جديدة أسرع من
            # إعادة تلوين عناصرها. تبقى نقطة البيع (السلة) والطلبات، والشاشة الحالية إن كان فيها حساب ثقيل أو عمل
            # للمستخدم لا نريد إعادته (KEEP_ON_THEME: المحاسبة)، وما فيه عمل للمستخدم يُنقل (theme_state: المحادثة، التدقيق).
            cur = getattr(self, "current_key", None)
            page = dict.get(self.pages, cur)
            keep = {"pos", "orders"} | ({cur} if getattr(page, "KEEP_ON_THEME", False) else set())
            saved = page.theme_state() if cur not in keep and hasattr(page, "theme_state") else None
            for key in [k for k in dict.keys(self.pages) if k not in keep]:
                w = dict.pop(self.pages, key)
                holder = self.page_holders.get(key)
                if isinstance(holder, QScrollArea):
                    holder.takeWidget()
                shiboken6.delete(w)
            config.save({"theme": choice})
            theme.apply(app, choice)
            theme.restyle(app)
            if cur and cur not in dict.keys(self.pages):
                self.go(cur)                                 # تُبنى بالسمة الجديدة
                if saved is not None:
                    self.pages[cur].restore_theme_state(saved)   # نفس ما كان يراه المستخدم (المحادثة، نتيجة التدقيق)
            from ui import i18n_qt as _iq
            _iq.set_raw_text(self.theme_btn, "☀" if theme.is_dark() else "🌙")
            self.theme_btn.setToolTip("الوضع الفاتح" if theme.is_dark() else "الوضع الداكن")
        finally:
            app.restoreOverrideCursor()
        eff = QGraphicsOpacityEffect(shot)
        shot.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", shot)
        anim.setDuration(260)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(shot.deleteLater)
        anim.start()
        return self

    def _rebuild(self, message, apply):
        """إعادة بناء النافذة بعد تغيير اللغة أو السمة، مع إشارة واضحة للمستخدم وتلاشٍ ناعم"""
        from PySide6.QtWidgets import QApplication
        import shiboken6
        app = QApplication.instance()
        pos = self.pages["pos"]
        cart = pos.cart_state() if pos.cart else None
        cur = getattr(self, "current_key", None)
        page = dict.get(self.pages, cur)
        saved = page.theme_state() if page is not None and hasattr(page, "theme_state") else None
        # صورة ثابتة للنافذة الحالية تبقى ظاهرة خلف الرسالة، وتُحذف محتوياتها الثقيلة فوراً
        # (إعادة تنسيق آلاف العناصر القديمة كانت تأخذ أكثر من ثانية)
        self._timer.stop()
        shot = QLabel()
        shot.setPixmap(self.grab())
        shot.setScaledContents(True)
        old = self.takeCentralWidget()
        self.setCentralWidget(shot)
        old.hide()
        shiboken6.delete(old)
        self.pages.clear()
        veil = _Veil(self, message)                  # تظهر فوراً قبل أي عمل
        app.setOverrideCursor(Qt.WaitCursor)
        try:
            apply(app)
            win = MainWindow(start=getattr(self, "current_key", None))
            win.training = getattr(self, "training", False)
            win.update_header()
            win.setGeometry(self.geometry())
            if cart:
                win.pages["pos"].restore_cart(cart)       # السلة تنتقل كما هي
            if saved is not None and cur in dict.keys(win.pages):
                win.pages[cur].restore_theme_state(saved)  # المحادثة ونتيجة التدقيق تنتقل أيضاً
            _Veil(win, veil.text, fade=True)
            win.showMaximized() if self.isMaximized() else win.show()
        finally:
            app.restoreOverrideCursor()
        app._main_window = win                       # يبقى حياً بعد إغلاق النافذة القديمة
        self._replaced = True
        self.setAttribute(Qt.WA_DeleteOnClose)       # تتوقف مؤقتات النافذة القديمة وتُحذف
        self.close()
        return win

    def closeEvent(self, event):
        if getattr(self, "_replaced", False):        # استُبدلت بنافذة بلغة أخرى
            event.accept()
            return
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
