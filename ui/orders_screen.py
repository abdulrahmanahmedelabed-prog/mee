# -*- coding: utf-8 -*-
"""الطلبات الأونلاين: طلبات الزبائن من صفحة المتجر /shop — تجهيز، إبلاغ الزبون بواتساب، وتحويلها لفاتورة"""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QSplitter
from PySide6.QtCore import Qt

from core import orders, settings, config, whatsapp
from core.i18n import tr
from ui.widgets import Table, button, page, hint, warn, ask, m, qty_cell, open_whatsapp, card, title


class OrdersScreen(QWidget):
    load_into_pos = Signal(dict)
    new_orders = Signal(int)

    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("الطلبات المفتوحة", "open")
        for k, v in orders.STATUS.items():
            self.filter.addItem(v, k)
        self.filter.addItem("الكل", None)
        self.filter.currentIndexChanged.connect(lambda _: self.load())
        row.addWidget(QLabel("عرض:"))
        row.addWidget(self.filter)
        row.addStretch()
        self.link = QLabel("")
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.link)
        lay.addLayout(row)

        split = QSplitter(Qt.Vertical)
        self.table = Table(["رقم الطلب", "الوقت", "الزبون", "الهاتف", "الاستلام", "العنوان", "المجموع", "الحالة"], stretch=5)
        self.table.itemSelectionChanged.connect(self.show_items)
        self.table.doubleClicked.connect(self.to_pos)
        split.addWidget(self.table)
        c, cl = card()
        self.detail = title("", "subTitle")
        cl.addWidget(self.detail)
        self.items = Table(["الصنف", "الكمية", "السعر", "الإجمالي"], stretch=0, sortable=False)
        cl.addWidget(self.items)
        split.addWidget(c)
        split.setSizes([420, 260])
        lay.addWidget(split, 1)

        b = QHBoxLayout()
        b.addWidget(button("🧾 تحويل لفاتورة في نقطة البيع", "successBtn", self.to_pos))
        b.addWidget(button("👨‍🍳 قيد التجهيز", "secondaryBtn", lambda: self.set_status("preparing")))
        b.addWidget(button("✅ جاهز", "secondaryBtn", lambda: self.set_status("ready")))
        b.addWidget(button("📱 إبلاغ الزبون (واتساب)", "secondaryBtn", self.notify))
        b.addWidget(button("✖ إلغاء الطلب", "dangerBtn", lambda: self.set_status("cancelled")))
        b.addStretch()
        lay.addLayout(b)
        lay.addWidget(hint("الزبائن يطلبون من صفحة المتجر على جوالاتهم، والدفع عند الاستلام. "
                           "فعّل المتجر من الإعدادات ← المتجر الإلكتروني. تتحدث القائمة تلقائياً كل 30 ثانية."))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(30000)
        self._last_new = 0

    def refresh(self):
        port = config.get("server_port") or 8765
        self.link.setText(tr("رابط المتجر:") + f" http://{config.local_ip()}:{port}/shop"
                          if settings.get_bool("online_store_enabled") else tr("المتجر الإلكتروني غير مفعّل"))
        self.load()

    def poll(self):
        try:
            n = orders.new_count()
        except Exception:
            return
        if n != self._last_new:
            self._last_new = n
            self.new_orders.emit(n)
            if self.isVisible():
                self.load()

    def load(self):
        rows = orders.list_orders(self.filter.currentData())
        colors = {"new": "#DCFCE7", "preparing": "#FEF3C7", "ready": "#DBEAFE", "cancelled": "#F1F5F9"}
        self.table.set_rows([[r["order_number"], r["created_at"][5:16], r["customer_name"], r["phone"],
                              orders.FULFILMENT.get(r["fulfilment"], r["fulfilment"]), r["address"] or "",
                              float(r["total"]), orders.STATUS.get(r["status"], r["status"])] for r in rows], rows,
                            [colors.get(r["status"]) for r in rows])
        self.items.set_rows([])
        self.detail.setText("")

    def current(self):
        o = self.table.selected_data()
        if not o:
            warn(self, "اختر طلباً")
        return o

    def show_items(self):
        o = self.table.selected_data()
        if not o:
            return
        self.detail.setText(f"{o['order_number']} — {o['customer_name']} {o['phone']}  {o['note'] or ''}")
        self.items.set_rows([[i["name"], qty_cell(i["quantity"]), float(i["unit_price"]),
                              float(i["quantity"] * i["unit_price"])] for i in o["items"]])

    def set_status(self, status):
        o = self.current()
        if not o:
            return
        if status == "cancelled" and not ask(self, "إلغاء هذا الطلب؟"):
            return
        orders.set_status(o["id"], status)
        self.load()

    def notify(self):
        o = self.current()
        if o:
            msg = orders.status_message(orders.get_order(o["id"]))
            open_whatsapp(self, whatsapp.link(o["phone"], msg), msg)

    def to_pos(self):
        o = self.current()
        if not o:
            return
        if o["status"] in ("done", "cancelled"):
            warn(self, "هذا الطلب مكتمل أو ملغى")
            return
        self.load_into_pos.emit(orders.get_order(o["id"]))
