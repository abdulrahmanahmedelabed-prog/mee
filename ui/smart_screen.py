# -*- coding: utf-8 -*-
"""
القوى الخارقة: اسأل محلك • التنبؤ والسيولة • المواسم ورمضان • الزكاة
(كل تبويب يُفتح حسب الباقة؛ المقفل يعرض ما يقدمه وزر الترقية)
"""

from html import escape

from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLineEdit, QTextBrowser, QFrame, QLabel,
                               QComboBox, QCheckBox, QFormLayout, QGridLayout, QDateEdit, QStackedWidget)

from core import assistant, forecast, seasons, zakat, plans, settings
from core.i18n import tr, is_rtl
from core.utils import fmt_qty
from ui import printing, theme
from ui.widgets import Table, button, page, hint, card, KpiCard, BarChart, MoneySpin, m, info


def _gate(widget, feature, on_upgrade):
    """يعرض التبويب إن كان في الباقة، وإلا لوحة القفل"""
    if plans.has(feature):
        return widget
    from ui.plans_dialog import LockedPanel
    lp = LockedPanel()
    lp.show_feature(feature)
    lp.upgrade.connect(on_upgrade)
    return lp


class SmartScreen(QWidget):
    navigate = Signal(str)

    def __init__(self):
        super().__init__()
        w, lay = page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(_gate(self._ask_tab(), "ask", self.upgrade), "💬 اسأل محلك")
        self.tabs.addTab(_gate(self._forecast_tab(), "forecast", self.upgrade), "🔮 التنبؤ والسيولة")
        self.tabs.addTab(_gate(self._seasons_tab(), "seasons", self.upgrade), "🌙 المواسم ورمضان")
        self.tabs.addTab(_gate(self._zakat_tab(), "zakat", self.upgrade), "🕌 الزكاة")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        self._loaded = set()

    def upgrade(self, feature):
        from ui.plans_dialog import PlansDialog
        PlansDialog(self, feature).exec()

    def refresh(self):
        i = self.tabs.currentIndex()
        if i in self._loaded:
            return
        self._loaded.add(i)
        if i == 1 and plans.has("forecast"):
            self.load_forecast()
        elif i == 2 and plans.has("seasons"):
            self.load_seasons()
        elif i == 3 and plans.has("zakat"):
            self.calc_zakat()

    def show_tab(self, key):
        self.tabs.setCurrentIndex({"ask": 0, "forecast": 1, "seasons": 2, "zakat": 3}.get(key, 0))

    # ------------------------------------------------------------------ اسأل محلك
    def _ask_tab(self):
        t = QWidget()
        lay = QVBoxLayout(t)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(hint("اكتب سؤالك كما تقوله لمحاسبك — بالعربي أو الإنجليزي — وستأتيك الإجابة من بيانات محلك فوراً، "
                           "بدون إنترنت. جرّب: «كم ربحت الشهر الماضي؟» أو «شو أجهز لرمضان؟»"))
        self.chat = QTextBrowser()
        self.chat.setOpenLinks(False)
        self.chat.setFrameShape(QFrame.NoFrame)
        self.chat.setStyleSheet("QTextBrowser { background: transparent; font-size: 11pt; }")
        self.chat.anchorClicked.connect(self._on_link)
        lay.addWidget(self.chat, 1)
        from PySide6.QtWidgets import QScrollArea
        strip = QScrollArea()                       # أسئلة جاهزة بنقرة (شريط يتمرر أفقياً على الشاشات الضيقة)
        strip.setWidgetResizable(True)
        strip.setFrameShape(QFrame.NoFrame)
        strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        strip.setFixedHeight(54)
        holder = QWidget()
        chips = QHBoxLayout(holder)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        for q in assistant.EXAMPLES[:10]:
            b = button(q, "ghostBtn", lambda _=False, qq=q: self.ask(qq))
            b.setStyleSheet("padding: 6px 12px; border-radius: 16px; font-weight: 500;")
            chips.addWidget(b)
        chips.addStretch()
        strip.setWidget(holder)
        lay.addWidget(strip)
        row = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setObjectName("bigSearch")
        self.q.setPlaceholderText("✨ اسأل محلك… مثلاً: كم بعت اليوم؟ مين عليه دين؟ كم باقي سكر؟")
        self.q.returnPressed.connect(lambda: self.ask(self.q.text()))
        row.addWidget(self.q, 1)
        row.addWidget(button("اسأل", "primaryBtn", lambda: self.ask(self.q.text())))
        lay.addLayout(row)
        self._history = []
        self._render()
        return t

    def ask(self, question):
        question = (question or "").strip()
        if not question:
            return
        if not plans.has("ask"):
            self.upgrade("ask")
            return
        self.tabs.setCurrentIndex(0)
        r = assistant.answer(question)
        self.q.clear()
        if r.get("go"):
            self.navigate.emit(r["go"])
        self._history.append((question, r))
        self._history = self._history[-20:]
        self._render()

    def _on_link(self, url):
        s = url.toString()
        if s.startswith("go:"):
            self.navigate.emit(s[3:])
        elif s.startswith("ask:"):
            from urllib.parse import unquote
            self.ask(unquote(s[4:]))

    def _render(self):
        side = "right" if is_rtl() else "left"
        other = "left" if is_rtl() else "right"
        parts = []
        if not self._history:
            r = assistant.answer("مساعدة")
            parts.append(self._card(r, side))
        for q, r in self._history:
            parts.append(f"<p align='{other}' style='margin:10px 0 4px 0'><span style='background-color:#2563EB; color:white;"
                         f" padding:6px 12px'>&nbsp;{escape(tr(q))}&nbsp;</span></p>")
            parts.append(self._card(r, side))
        html = f"<div dir='{'rtl' if is_rtl() else 'ltr'}'>{''.join(parts)}</div>"
        self.chat.setHtml(theme.html(html))
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _card(self, r, side):
        lines = "<br>".join(escape(tr(x)) for x in r.get("lines", []))
        table = ""
        t = r.get("table")
        if t and t.get("rows"):
            head = "".join(f"<th align='{side}' style='padding:4px 8px; color:#667085'>{escape(tr(h))}</th>"
                           for h in t["headers"])
            body = "".join("<tr>" + "".join(f"<td style='padding:4px 8px; border-top:1px solid #EEF1F6'>{escape(tr(str(c)))}</td>"
                                            for c in row) + "</tr>" for row in t["rows"])
            table = (f"<table cellspacing='0' cellpadding='0' width='100%' style='margin-top:8px'><tr>{head}</tr>"
                     f"{body}</table>")
        act = ""
        if r.get("action") and r["action"][1]:
            act = f"<br><a href='go:{r['action'][0]}' style='color:#2563EB; font-weight:bold'>↪ {escape(tr(r['action'][1]))}</a>"
        return (f"<table width='100%' cellspacing='0' cellpadding='12' style='background-color:#FFFFFF; margin-bottom:6px'>"
                f"<tr><td align='{side}'><span style='font-size:13pt; font-weight:bold; color:#101828'>"
                f"{escape(tr(r.get('title', '')))}</span><br><span style='color:#344054'>{lines}</span>{table}{act}"
                f"</td></tr></table>")

    # ------------------------------------------------------------------ التنبؤ
    def _forecast_tab(self):
        t = QWidget()
        lay = QVBoxLayout(t)
        lay.setContentsMargins(0, 8, 0, 0)
        g = QGridLayout()
        g.setSpacing(14)
        self.k_sales = KpiCard("مبيعات الثلاثين يوماً القادمة", "#2563EB", "🔮")
        self.k_trend = KpiCard("الاتجاه الأسبوعي", "#7C3AED", "📈")
        self.k_cash = KpiCard("النقد المتوقع بعد 30 يوماً", "#16A34A", "💵")
        self.k_low = KpiCard("أدنى نقطة للنقد", "#D97706", "⚠")
        for i, k in enumerate((self.k_sales, self.k_trend, self.k_cash, self.k_low)):
            g.addWidget(k, 0, i)
        lay.addLayout(g)
        c, cl = card()
        self.f_title = QLabel("المبيعات المتوقعة يوماً بيوم")
        self.f_title.setObjectName("subTitle")
        cl.addWidget(self.f_title)
        self.f_chart = BarChart("#7C3AED", 200)
        cl.addWidget(self.f_chart)
        lay.addWidget(c)
        tabs = QTabWidget()
        self.cash_table = Table(["التاريخ", "مقبوض متوقع", "مدفوع متوقع", "النقد المتوقع"])
        self.stockout_table = Table(["الصنف", "الموجود", "بيع يومي", "ينفد بعد (أيام)", "اطلب", "المورد"])
        self.wd_table = Table(["اليوم", "معامل البيع"])
        tabs.addTab(self.cash_table, "💵 السيولة يوماً بيوم")
        tabs.addTab(self.stockout_table, "⏳ أصناف ستنفد")
        tabs.addTab(self.wd_table, "📅 أيام الأسبوع")
        lay.addWidget(tabs, 1)
        self.f_note = hint("")
        lay.addWidget(self.f_note)
        return t

    def load_forecast(self):
        s = forecast.sales_forecast(30)
        if not s.get("enough_data"):
            self.f_note.setText("أحتاج أسبوعين من المبيعات على الأقل لأتوقع.")
            return
        self.k_sales.set(m(s["total"]), f"بين {m(s['low'])} و{m(s['high'])}" +
                         (f" • {s['change_pct']:+.1f}% عن آخر 30 يوماً" if s["change_pct"] is not None else ""))
        self.k_trend.set(f"{s['trend_pct_week']:+.1f}%", f"أقوى يوم: {s['best_day']} • أضعف يوم: {s['worst_day']}")
        self.f_chart.set_data([d["date"][5:] for d in s["days"]], [d["value"] for d in s["days"]],
                              [f"{tr(d['weekday'])}: {m(d['value'])} ({m(d['low'])} – {m(d['high'])})" for d in s["days"]])
        c = forecast.cash_forecast(30)
        self.k_cash.set(m(c["end"]), f"الآن {m(c['start'])}")
        self.k_low.set(m(c["lowest"]), (f"⚠ قد ينقص النقد يوم {c['first_negative']}" if c["first_negative"]
                                         else f"يوم {c['lowest_date']}"))
        self.k_low.value.setStyleSheet(f"color:{'#DC2626' if c['first_negative'] else '#D97706'};")
        self.cash_table.set_rows([[r["date"], float(r["in"]), float(r["out"]), float(r["balance"])] for r in c["rows"]],
                                 colors=[("#FEE2E2" if r["balance"] < 0 else None) for r in c["rows"]])
        rows = forecast.stockouts(14)
        self.stockout_table.set_rows([[r["name"], qty_txt(r["stock"]), f"{r['daily_rate']:.1f}",
                                       (str(round(r["days_left"])), r["days_left"]), f"{r['order_units']} {r['unit_name']}",
                                       r["supplier_name"]] for r in rows], rows)
        self.wd_table.set_rows([[k, f"×{v}"] for k, v in s["weekday_factors"].items()])
        self.f_note.setText(f"التوقع من آخر 16 أسبوعاً: مستوى البيع × نمط أيام الأسبوع × الاتجاه، والنطاق ثقة 80%. السيولة تفترض "
                            f"أن {c['paid_share']}% من المبيعات تُقبض فوراً، وتحصيل ديون {m(c['avg_collect'])} يومياً، "
                            f"ومشتريات {m(c['avg_purchases'])} ومصاريف {m(c['avg_expenses'])} يومياً، ورواتب {m(c['salaries'])} "
                            f"يوم {c['pay_day']} من الشهر، والشيكات في مواعيدها.")

    # ------------------------------------------------------------------ المواسم
    def _seasons_tab(self):
        t = QWidget()
        lay = QVBoxLayout(t)
        lay.setContentsMargins(0, 8, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("الموسم:"))
        self.season = QComboBox()
        self.season.currentIndexChanged.connect(lambda _: self.load_season())
        row.addWidget(self.season, 1)
        row.addWidget(button("📤 تصدير", "secondaryBtn", lambda: self.season_table.export_csv(self, "خطة الموسم.csv")))
        row.addWidget(button("🖨 طباعة", "secondaryBtn", self.print_season))
        lay.addLayout(row)
        g = QGridLayout()
        g.setSpacing(14)
        self.s_when = KpiCard("يبدأ بعد", "#7C3AED", "🗓")
        self.s_order = KpiCard("اطلب قبل", "#D97706", "🚚")
        self.s_sales = KpiCard("المبيعات المتوقعة في الموسم", "#16A34A", "💰")
        self.s_cost = KpiCard("تكلفة الطلبية الأولى", "#2563EB", "🧾")
        for i, k in enumerate((self.s_when, self.s_order, self.s_sales, self.s_cost)):
            g.addWidget(k, 0, i)
        lay.addLayout(g)
        self.season_table = Table(["الصنف", "بيع الموسم الماضي", "ارتفاع البيع", "المتوقع يومياً", "الموجود",
                                   "الطلبية الأولى (10 أيام)", "التكلفة"])
        lay.addWidget(self.season_table, 1)
        self.s_note = hint("")
        lay.addWidget(self.s_note)
        return t

    def load_seasons(self):
        self.season.blockSignals(True)
        self.season.clear()
        for s in seasons.upcoming():
            when = "الآن 🔥" if s["in_season"] else f"بعد {s['days_until']} يوماً"
            self.season.addItem(f"{s['icon']} {s['name']} — {s['start']} {s['hijri']} ({when})", s["key"])
        self.season.blockSignals(False)
        self.load_season()

    def load_season(self):
        key = self.season.currentData()
        if not key:
            return
        p = seasons.plan(key)
        self._season = p
        if not p["enough_data"]:
            self.season_table.set_rows([])
            self.s_note.setText(p["message"])
            for k in (self.s_when, self.s_order, self.s_sales, self.s_cost):
                k.set("—")
            return
        self.s_when.set(f"{p['days_until']} يوماً", f"{p['start']} {p['hijri']}")
        self.s_order.set(p["order_by"], "حتى تصل البضاعة قبل الزحمة")
        self.s_sales.set(m(p["expected_sales"]), f"الموسم الماضي {m(p['last_season_sales'])} • نمو المحل {p['growth_pct']:+.1f}%")
        self.s_cost.set(m(p["order_cost"]), f"{len(p['items'])} صنفاً")
        self.season_table.set_rows([[i["name"], qty_txt(i["last_season"]), (f"×{i['uplift']}" if i["uplift"] else "موسمي فقط",
                                     i["uplift"] or 99), f"{i['per_day']}", qty_txt(i["stock"]), (str(i["order"]), i["order"]),
                                     float(i["est_cost"])] for i in p["items"]],
                                   p["items"], colors=[("#DCFCE7" if (i["uplift"] or 9) >= 1.3 else None) for i in p["items"]])
        self.s_note.setText(f"قارنا مبيعات {p['name']} الماضي ({p['last_year'][0]} → {p['last_year'][1]}) بالأسابيع الأربعة التي سبقته. "
                            f"الأخضر: أصناف يرتفع بيعها في الموسم 30% فأكثر. الطلبية الأولى تغطي أول 10 أيام؛ "
                            f"والطازج يُكمَّل على دفعات خلال الموسم.")

    def print_season(self):
        p = getattr(self, "_season", None)
        if not p or not p.get("items"):
            return
        from core import branding
        rows = "".join(f"<tr><td>{escape(i['name'])}</td><td>{fmt_qty(i['last_season'])}</td>"
                       f"<td>{('×' + str(i['uplift'])) if i['uplift'] else '—'}</td><td>{fmt_qty(i['stock'])}</td>"
                       f"<td><b>{i['order']}</b></td></tr>" for i in p["items"])
        html = branding.document(
            f"<p>يبدأ {p['start']} {escape(p['hijri'])} — اطلب قبل {p['order_by']}</p>"
            f"<table width='100%' border='1' cellspacing='0' cellpadding='5' style='border-collapse:collapse'>"
            f"<tr style='background:#eee'><th>الصنف</th><th>بيع الموسم الماضي</th><th>ارتفاع</th><th>الموجود</th>"
            f"<th>الطلبية الأولى</th></tr>{rows}</table>", f"خطة الاستعداد لـ{p['name']}")
        printing.print_html(self, html, width_mm=210, preview=True)

    # ------------------------------------------------------------------ الزكاة
    def _zakat_tab(self):
        t = QWidget()
        lay = QHBoxLayout(t)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)
        c, cl = card()
        f = QFormLayout()
        self.z_gold = MoneySpin()
        self.z_gold.setValue(settings.get_float("zakat_gold_price", 0))
        f.addRow("سعر غرام الذهب (عيار 24):", self.z_gold)
        self.z_val = QComboBox()
        self.z_val.addItem("سعر البيع (قول الجمهور)", "sale")
        self.z_val.addItem("سعر التكلفة", "cost")
        f.addRow("تقويم البضاعة:", self.z_val)
        self.z_cal = QComboBox()
        self.z_cal.addItem("سنة هجرية (2.5%)", "hijri")
        self.z_cal.addItem("سنة ميلادية (2.577%)", "gregorian")
        f.addRow("الحَوْل:", self.z_cal)
        self.z_doubt = QCheckBox("احسب الديون المشكوك في تحصيلها أيضاً")
        f.addRow("", self.z_doubt)
        self.z_cash = MoneySpin()
        f.addRow("نقد آخر للتجارة خارج البرنامج:", self.z_cash)
        self.z_debts = MoneySpin()
        f.addRow("ديون حالّة أخرى على المحل:", self.z_debts)
        self.z_hawl = QDateEdit()
        self.z_hawl.setCalendarPopup(True)
        self.z_hawl.setDisplayFormat("yyyy-MM-dd")
        from core import db
        start = settings.get("zakat_hawl_start") or db.scalar("SELECT MIN(date(created_at)) FROM invoices")
        self.z_hawl.setDate(QDate.fromString(str(start), "yyyy-MM-dd") if start else QDate.currentDate())
        f.addRow("بداية الحَوْل:", self.z_hawl)
        cl.addLayout(f)
        cl.addWidget(button("🕌 احسب الزكاة", "successBtn", self.calc_zakat))
        cl.addWidget(hint("الأصول الثابتة (الرفوف والثلاجات) لا زكاة فيها. للحالات الخاصة (شركاء، قروض طويلة) استشر أهل العلم."))
        cl.addStretch()
        c.setMaximumWidth(460)
        lay.addWidget(c)
        r, rl = card()
        self.z_title = QLabel("")
        self.z_title.setObjectName("subTitle")
        rl.addWidget(self.z_title)
        self.z_table = Table(["البند", "المبلغ"], stretch=0, sortable=False)
        rl.addWidget(self.z_table, 1)
        self.z_result = QLabel("")
        self.z_result.setObjectName("bigNumber")
        self.z_result.setWordWrap(True)
        rl.addWidget(self.z_result)
        self.z_sub = hint("")
        rl.addWidget(self.z_sub)
        rl.addWidget(button("🖨 طباعة تقرير الزكاة", "secondaryBtn", self.print_zakat), alignment=Qt.AlignLeft)
        lay.addWidget(r, 1)
        return t

    def calc_zakat(self):
        settings.set_many({"zakat_gold_price": f"{self.z_gold.value():g}",
                           "zakat_hawl_start": self.z_hawl.date().toString("yyyy-MM-dd")})
        r = zakat.compute(gold_price=self.z_gold.value() or None, valuation=self.z_val.currentData(),
                          include_doubtful=self.z_doubt.isChecked(), calendar=self.z_cal.currentData(),
                          other_cash=self.z_cash.value(), other_debts=self.z_debts.value())
        self._zakat = r
        self.z_title.setText(f"حساب الزكاة في {r['as_of']} — {r['hijri']}")
        rows = [[k, float(v)] for k, v in r["assets"]] + [[f"− {k}", float(-v)] for k, v in r["deductions"]]
        rows.append(["= الوعاء الزكوي", float(r["base"])])
        if r["nisab"]:
            rows.append(["النصاب (85 غرام ذهب)", float(r["nisab"])])
        self.z_table.set_rows(rows, colors=[("#EFF6FF" if k.startswith("=") else None) for k, _ in rows])
        if r["nisab"] is None:
            self.z_result.setText(f"الزكاة 2.5%: {m(r['base'] * r['rate'])}")
            self.z_sub.setText("أدخل سعر غرام الذهب لمعرفة إن كان المال قد بلغ النصاب.")
        elif r["reaches_nisab"]:
            self.z_result.setText(f"الزكاة الواجبة: {m(r['zakat'])}")
            self.z_sub.setText(f"الحَوْل القادم: {r['next_hawl']['date']} ({r['next_hawl']['hijri']}) بعد "
                               f"{r['next_hawl']['days_left']} يوماً. ديون مشكوك فيها لم تُحسب: {m(r['doubtful'])}.")
        else:
            self.z_result.setText("لم يبلغ المال النصاب — لا زكاة واجبة")
            self.z_sub.setText("")

    def print_zakat(self):
        if not getattr(self, "_zakat", None):
            self.calc_zakat()
        printing.print_html(self, zakat.report_html(self._zakat), width_mm=210, preview=True)


def qty_txt(v):
    return fmt_qty(v)
