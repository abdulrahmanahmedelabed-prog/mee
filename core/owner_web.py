# -*- coding: utf-8 -*-
"""
لوحة المالك على الجوال: صفحة ويب يفتحها المالك من هاتفه (على شبكة المحل، أو من أي مكان عبر VPN مثل Tailscale)
ليتابع مبيعات اليوم والأرباح والنقد في الأدراج والنواقص والشيكات — للقراءة فقط.

العنوان: http://<عنوان الجهاز الرئيسي>:8765/owner  — الدخول بحساب مدير (صلاحية التقارير).
"""

import secrets
from html import escape
from urllib.parse import parse_qs

from core import auth, reports, products, customers, suppliers, shifts, cheques, settings, db
from core.utils import money, fmt_qty

COOKIE = "owner_session"


def _m(v):
    return f"{money(v):,.2f}"


CSS = """
:root{--bg:#F1F5F9;--card:#fff;--text:#0F172A;--muted:#64748B;--line:#E2E8F0;--accent:#2563EB;--ok:#16A34A;--bad:#DC2626;--warn:#D97706}
@media (prefers-color-scheme: dark){:root{--bg:#0B1220;--card:#131C2E;--text:#E2E8F0;--muted:#94A3B8;--line:#23324A;--accent:#60A5FA;--ok:#4ADE80;--bad:#F87171;--warn:#FBBF24}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Tahoma,'Segoe UI',system-ui,sans-serif;font-size:15px}
header{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--card);border-bottom:1px solid var(--line)}
header b{font-size:17px}header a{color:var(--muted);text-decoration:none;font-size:13px}
main{max-width:900px;margin:0 auto;padding:12px 16px 40px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.k{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.k small{color:var(--muted);display:block}.k b{font-size:21px;display:block;margin-top:4px}.k i{font-style:normal;color:var(--muted);font-size:12px}
h2{font-size:15px;margin:22px 0 8px;color:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
html,body{overflow-x:hidden}td,th{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;overflow-wrap:anywhere}th{color:var(--muted);font-weight:normal;font-size:13px}
td.n{text-align:left;font-variant-numeric:tabular-nums;white-space:nowrap}
.bars{display:flex;align-items:flex-end;gap:6px;height:130px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}
.bar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;font-size:11px;color:var(--muted);height:100%}
.bar span{display:block;width:100%;background:var(--accent);border-radius:4px 4px 0 0;min-height:2px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
form{max-width:340px;margin:60px auto;background:var(--card);padding:22px;border-radius:14px;border:1px solid var(--line)}
input{width:100%;padding:12px;margin:6px 0 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font-size:16px}
button{width:100%;padding:12px;border:0;border-radius:8px;background:var(--accent);color:#fff;font-size:16px}
"""


def _page(body, refresh=False):
    from core import i18n
    meta = "<meta http-equiv='refresh' content='60'>" if refresh else ""
    return i18n.tr_html(f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>{meta}"
            f"<title>لوحة المالك</title><style>{CSS}</style></head><body>{body}</body></html>")


def _brand(size):
    """شعار المحل واسمه (أو أيقونة المتجر إن لم يوجد شعار)"""
    from core import branding
    logo = branding.logo_img(size, style="vertical-align:middle; border-radius:6px")
    return f"{logo or '🏪'} {escape(settings.get('shop_name'))}"


def login_page(error=""):
    err = f"<p class='bad'>{escape(error)}</p>" if error else ""
    return _page(f"""<form method='post' action='/owner/login'>
        <h3>{_brand(64)}</h3><p style='color:var(--muted)'>لوحة المالك — للقراءة فقط</p>{err}
        <label>اسم المستخدم</label><input name='username' autocomplete='username'>
        <label>كلمة المرور</label><input name='password' type='password' autocomplete='current-password'>
        <button>دخول</button></form>""")


def login(body_bytes, ip=""):
    """يرجع (token, None) عند النجاح أو (None, رسالة خطأ)"""
    from core import web_sessions, throttle
    form = parse_qs(body_bytes.decode("utf-8", "replace"))
    username = form.get("username", [""])[0][:100]
    wait = throttle.wait_seconds(ip, username)
    if wait:
        return None, throttle.message(wait)
    user = auth.authenticate(username, form.get("password", [""])[0][:200])
    if not user:
        throttle.failed(ip, username)
        return None, "اسم المستخدم أو كلمة المرور غير صحيحة"
    throttle.succeeded(ip, username)
    if user.get("must_change_password"):
        return None, "غيّر كلمة المرور الافتراضية من البرنامج على الكمبيوتر أولاً، ثم ادخل بها"
    if not auth.has_permission("reports", user):
        return None, "هذا الحساب لا يملك صلاحية التقارير"
    return web_sessions.create(user["id"], "owner"), None


def user_from_cookie(cookie_header):
    from core import web_sessions
    u = web_sessions.user(web_sessions.cookie_value(cookie_header, COOKIE), "owner")
    return u if u and auth.has_permission("reports", u) else None


def logout(cookie_header):
    from core import web_sessions
    token = web_sessions.cookie_value(cookie_header, COOKIE)
    if token:
        web_sessions.delete(token)


def dashboard_page():
    today = db.today()
    d = reports.dashboard(today)
    t = d["today"]
    open_sh = shifts.open_shifts()
    drawer_total = money(sum(shifts.summary(s["id"])["expected_cash"] for s in open_sh))
    week = reports.last_n_days(7)
    mx = max([x["total"] for x in week] + [1])
    bars = "".join(f"<div class='bar'><span style='height:{max(x['total'] / mx * 100, 1):.0f}%'></span>{x['date'][8:]}</div>"
                   for x in week)
    top = reports.top_products(today, today, 8, "total")
    low = products.get_low_stock_products()[:12]
    due = cheques.due_soon(7)
    np_cls = "ok" if t["net_profit"] >= 0 else "bad"

    def rows(items, cols):
        return "".join("<tr>" + "".join(cols(i)) + "</tr>" for i in items) or \
            "<tr><td colspan='5' style='color:var(--muted)'>لا يوجد</td></tr>"

    body = f"""<header><b>{_brand(28)}</b><span><small>{db.now()[:16]}</small>
      &nbsp; <a href='/owner/logout'>خروج</a></span></header><main>
    <div class='grid'>
      <div class='k'><small>مبيعات اليوم</small><b>{_m(t['net_sales'])}</b><i>{t['invoice_count']} فاتورة • متوسط {_m(t['avg_basket'])}</i></div>
      <div class='k'><small>مجمل الربح</small><b class='ok'>{_m(t['gross_profit'])}</b><i>هامش {t['gross_margin']}%</i></div>
      <div class='k'><small>صافي ربح اليوم</small><b class='{np_cls}'>{_m(t['net_profit'])}</b><i>بعد المصاريف {_m(t['expenses'])}</i></div>
      <div class='k'><small>النقد في الأدراج</small><b>{_m(drawer_total)}</b><i>{len(open_sh)} وردية مفتوحة</i></div>
      <div class='k'><small>ديون العملاء</small><b class='warn'>{_m(d['customer_debts'])}</b><i>آجل اليوم {_m(t['credit_sales'])}</i></div>
      <div class='k'><small>مستحقات الموردين</small><b class='bad'>{_m(d['supplier_dues'])}</b></div>
      <div class='k'><small>قيمة المخزون</small><b>{_m(d['inventory']['cost_value'])}</b><i>{d['inventory']['items']} صنف</i></div>
      <div class='k'><small>تنبيهات</small><b class='warn'>{d['low_stock']} ناقص</b><i>{d['expiring']} صلاحية قريبة • {len(due)} شيك مستحق</i></div>
    </div>
    <h2>المبيعات آخر 7 أيام</h2><div class='bars'>{bars}</div>
    <h2>الورديات المفتوحة</h2><table><tr><th>الجهاز</th><th>الكاشير</th><th>منذ</th><th>النقد المتوقع</th></tr>
      {rows(open_sh, lambda s: [f"<td>{escape(s['terminal'] or '-')}</td>", f"<td>{escape(s['full_name'] or s['username'] or '-')}</td>",
                                f"<td>{s['opened_at'][11:16]}</td>", f"<td class='n'>{_m(shifts.summary(s['id'])['expected_cash'])}</td>"])}</table>
    <h2>الأكثر مبيعاً اليوم</h2><table><tr><th>الصنف</th><th>الكمية</th><th>المبيعات</th></tr>
      {rows(top, lambda r: [f"<td>{escape(r['product_name'])}</td>", f"<td class='n'>{fmt_qty(r['qty'])}</td>", f"<td class='n'>{_m(r['total'])}</td>"])}</table>
    <h2>شيكات تستحق خلال أسبوع</h2><table><tr><th>النوع</th><th>الجهة</th><th>الاستحقاق</th><th>المبلغ</th></tr>
      {rows(due, lambda c: [f"<td>{'وارد' if c['direction'] == 'in' else 'صادر'}</td>", f"<td>{escape(c['party'] or '-')}</td>",
                            f"<td>{c['due_date']}</td>", f"<td class='n'>{_m(c['amount'])}</td>"])}</table>
    <h2>نواقص تحتاج طلبية</h2><table><tr><th>الصنف</th><th>المتوفر</th><th>الحد الأدنى</th></tr>
      {rows(low, lambda p: [f"<td>{escape(p['name'])}</td>", f"<td class='n'>{fmt_qty(p['quantity'])}</td>", f"<td class='n'>{fmt_qty(p['min_quantity'])}</td>"])}</table>
    <p style='color:var(--muted);font-size:12px;margin-top:18px'>تتحدث الصفحة تلقائياً كل دقيقة.</p></main>"""
    return _page(body, refresh=True)
