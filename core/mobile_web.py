# -*- coding: utf-8 -*-
"""
تطبيق الجوال للموظفين (/m): فحص السعر والكمية والصلاحية، والجرد من على الرف بالجوال.
يعمل من متصفح أي جوال على شبكة المحل، ويمكن إضافته للشاشة الرئيسية كتطبيق.
- البحث بالاسم أو الباركود (مسح بكاميرا الجوال في المتصفحات التي تدعم BarcodeDetector عبر اتصال آمن،
  أو بماسح باركود بلوتوث متصل بالجوال).
- الجرد يحتاج صلاحية «المخزون».
"""

import json
import secrets
from html import escape
from urllib.parse import parse_qs

from core import auth, products, db, settings, context

COOKIE = "staff_session"


def login(body_bytes, ip=""):
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
    return web_sessions.create(user["id"], "mobile"), None


def user_from_cookie(cookie_header):
    from core import web_sessions
    return web_sessions.user(web_sessions.cookie_value(cookie_header, COOKIE), "mobile")


def logout(cookie_header):
    from core import web_sessions
    token = web_sessions.cookie_value(cookie_header, COOKIE)
    if token:
        web_sessions.delete(token)


def _product_json(p):
    exp = products.expiry_status(p["id"])
    from core import i18n
    return {"id": p["id"], "name": i18n.tr(p["name"]), "barcode": p["barcode"] or "", "price": p["sale_price"],
            "wholesale": p["wholesale_price"] or 0, "qty": p["quantity"], "unit": p["unit"] or "",
            "min": p["min_quantity"], "expiry": exp[0] if exp else ""}


def find(q):
    q = (q or "").strip()
    if not q:
        return []
    p, _, unit = products.lookup_code(q)
    if p:
        return [_product_json(p)]
    return [_product_json(p) for p in products.get_all_products(search=q)[:25]]


def can_ask(user):
    from core import plans
    return auth.has_permission("reports", user) and plans.has("ask")


def ask(user, question):
    """«اسأل محلك» من الجوال (لمن لديه صلاحية التقارير وفي باقة ماكس). الإجابة مترجمة للغة الواجهة"""
    from core import assistant, i18n
    if not can_ask(user):
        return {"error": i18n.tr("هذه الميزة لمن لديه صلاحية التقارير في باقة ماكس")}
    r = assistant.answer(question)
    t = r.get("table") or {}
    return {"title": i18n.tr(r.get("title", "")), "lines": [i18n.tr(x) for x in r.get("lines", [])],
            "headers": [i18n.tr(h) for h in t.get("headers", [])],
            "rows": [[i18n.tr(str(c)) for c in row] for row in (t.get("rows") or [])[:12]]}


def count(user, product_id, counted):
    if not auth.has_permission("inventory", user):
        raise PermissionError("الجرد يحتاج صلاحية المخزون")
    with context.request(user, "جوال"):
        diff = products.set_stock_count(int(product_id), float(counted), "جرد بالجوال")
    return {"diff": diff, "qty": products.get_product(int(product_id))["quantity"]}


# ---------------------------------------------------------------------------
# تبويبات التطبيق: الرئيسية، النواقص، الزبائن والديون، الطلبات الأونلاين
# ---------------------------------------------------------------------------

def caps(user):
    """ما يظهر لهذا المستخدم من تبويبات (حسب صلاحياته وباقة المحل)"""
    from core import plans
    has = lambda p: auth.has_permission(p, user)  # noqa: E731
    return {"count": has("inventory") and plans.has("mobile"),
            "low": (has("inventory") or has("reports")) and plans.has("mobile"),
            "customers": has("customers") and plans.has("mobile"),
            "orders": has("pos") and plans.has("online") and settings.get_bool("online_store_enabled"),
            "money": has("reports") or has("dashboard"),
            "ask": can_ask(user)}


def home(user, _q=None):
    from core import i18n, orders, reports, customers
    c = caps(user)
    out = {"shop": settings.get("shop_name"), "user": user.get("full_name") or user["username"], "cards": []}
    cur = settings.get("currency_symbol") or ""

    def card(icon, label, value, tab=None, tone=""):
        out["cards"].append({"icon": icon, "label": i18n.tr(label), "value": value, "tab": tab, "tone": tone})
    if c["money"]:
        d = reports.dashboard()
        t = d["today"]
        card("💰", "مبيعات اليوم", f"{t['net_sales']:,.2f} {cur}")
        card("🧾", "عدد الفواتير", str(t["invoice_count"]))
        if auth.has_permission("reports", user):
            card("📈", "ربح اليوم", f"{t['net_profit']:,.2f} {cur}", tone="good" if t["net_profit"] >= 0 else "bad")
        if d["drawer_cash"] is not None:
            card("💵", "في الدرج الآن", f"{d['drawer_cash']:,.2f} {cur}")
    if c["low"]:
        n = len(products.get_low_stock_products())
        card("📦", "أصناف ناقصة", str(n), "low", "bad" if n else "good")
    if c["customers"]:
        card("👥", "ديون الزبائن", f"{customers.total_debts():,.2f} {cur}", "customers")
    if c["orders"]:
        n = len(orders.list_orders("open"))
        card("🛵", "طلبات مفتوحة", str(n), "orders", "warn" if n else "")
    return out


def low_stock(user, _q=None):
    if not caps(user)["low"]:
        raise PermissionError("تحتاج صلاحية المخزون")
    from core import i18n
    rows = products.get_low_stock_products()[:150]
    return [{"id": p["id"], "name": i18n.tr(p["name"]), "qty": p["quantity"], "min": p["min_quantity"], "unit": p["unit"] or "",
             "need": max(0.0, round(p["min_quantity"] * 2 - p["quantity"], 2)), "barcode": p["barcode"] or ""} for p in rows]


def customer_list(user, q=None):
    if not caps(user)["customers"]:
        raise PermissionError("تحتاج صلاحية العملاء")
    from core import whatsapp
    q = (q or "").strip()
    rows = __import__("core.customers", fromlist=["x"]).list_customers(search=q or None, debtors_only=not q)[:80]
    out = []
    for r in rows:
        bal = round(r["balance_due"] or 0, 2)
        wa = ""
        if r["phone"] and bal > 0.009:
            try:
                wa = whatsapp.reminder_link(r["id"])
            except Exception:  # noqa: BLE001
                wa = ""
        out.append({"id": r["id"], "name": r["name"], "phone": r["phone"] or "", "balance": bal,
                    "last_payment": (r["last_payment"] or "")[:10], "wa": wa})
    return out


def order_list(user, _q=None):
    if not caps(user)["orders"]:
        raise PermissionError("الطلبات تحتاج صلاحية نقطة البيع")
    from core import orders, whatsapp, i18n
    out = []
    for o in orders.list_orders("open", 60):
        out.append({"id": o["id"], "number": o["order_number"], "customer": o["customer_name"], "phone": o["phone"] or "",
                    "fulfilment": i18n.tr(orders.FULFILMENT.get(o["fulfilment"], o["fulfilment"])),
                    "address": o.get("address") or "", "total": o["total"], "status": o["status"],
                    "status_label": i18n.tr(orders.STATUS[o["status"]]), "created": (o["created_at"] or "")[11:16],
                    "items": [f"{fmt(i.get('quantity', i.get('qty', 0)))} × {i18n.tr(i.get('name', ''))}" for i in o["items"]],
                    "wa": whatsapp.link(o["phone"], orders.status_message(o)) if o["phone"] else ""})
    return out


def fmt(x):
    try:
        return f"{float(x):g}"
    except (TypeError, ValueError):
        return str(x)


def order_status(user, order_id, status):
    """تجهيز الطلب من الجوال: قيد التجهيز / جاهز / ملغى (الإكمال يتم بفاتورة في نقطة البيع)"""
    if not caps(user)["orders"]:
        raise PermissionError("الطلبات تحتاج صلاحية نقطة البيع")
    if status not in ("preparing", "ready", "cancelled"):
        raise ValueError("حالة غير مسموحة من الجوال")
    from core import orders
    o = orders.get_order(int(order_id))
    if not o or o["status"] in ("done", "cancelled"):
        raise ValueError("الطلب غير موجود أو مغلق")
    with context.request(user, "جوال"):
        orders.set_status(o["id"], status)
    o = orders.get_order(o["id"])
    from core import whatsapp
    return {"ok": True, "wa": whatsapp.link(o["phone"], orders.status_message(o)) if o["phone"] else ""}


API_GET = {"home": home, "find": lambda u, q: find(q), "ask": ask, "low": low_stock, "customers": customer_list,
           "orders": order_list}


def _page(body):
    from core import i18n
    return i18n.tr_html(f"""<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='mobile-web-app-capable' content='yes'>
<meta name='apple-mobile-web-app-capable' content='yes'><link rel='manifest' href='/m/manifest.json'>
<title>{escape(settings.get('shop_name'))}</title><style>
:root{{--bg:#F1F5F9;--card:#fff;--text:#0F172A;--muted:#64748B;--line:#E2E8F0;--accent:#2563EB}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0B1220;--card:#131C2E;--text:#E2E8F0;--muted:#94A3B8;--line:#23324A;--accent:#60A5FA}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Tahoma,system-ui,sans-serif}}
main{{max-width:560px;margin:0 auto;padding:0 14px 92px}}h2{{font-size:18px}}
header{{position:sticky;top:0;z-index:5;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:12px 2px;
 background:var(--bg)}}header b{{font-size:17px}}a{{color:var(--accent)}}
input{{width:100%;padding:13px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--text);font-size:17px}}
button,.btn{{border:0;background:var(--accent);color:#fff;border-radius:10px;padding:11px 14px;font-size:15px;text-decoration:none;
 display:inline-block;font-family:inherit;cursor:pointer}}button.ok{{background:#16A34A}}button.ghost,.btn.ghost{{background:transparent;
 color:var(--text);border:1px solid var(--line)}}.btn.wa{{background:#25D366}}
.row{{display:flex;gap:8px;margin:8px 0;flex-wrap:wrap}}.row input{{flex:1;min-width:0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:8px 0}}
.line{{display:flex;justify-content:space-between;align-items:center;gap:10px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.grid .card{{margin:0}}.kpi .ic{{font-size:22px}}
.muted{{color:var(--muted);font-size:13px}}.c{{text-align:center}}.big{{font-size:22px;font-weight:bold;color:var(--accent)}}
.bad .big,.big.bad{{color:#DC2626}}.good .big,.big.good,.card.good{{color:#16A34A}}.warn .big,.big.warn{{color:#D97706}}
.card.bad{{color:#DC2626}}.pill{{font-size:12px;border-radius:20px;padding:3px 10px;background:var(--line);white-space:nowrap}}
.pill.new{{background:#DBEAFE;color:#1E40AF}}.pill.preparing{{background:#FEF3C7;color:#92400E}}.pill.ready{{background:#DCFCE7;color:#166534}}
table{{width:100%;font-size:13px;border-collapse:collapse}}th,td{{text-align:start;padding:4px;border-bottom:1px solid var(--line)}}
nav{{position:fixed;bottom:0;left:0;right:0;display:flex;background:var(--card);border-top:1px solid var(--line);
 padding:6px 4px calc(6px + env(safe-area-inset-bottom));z-index:9}}
nav button{{flex:1;background:transparent;color:var(--muted);padding:4px 0;display:flex;flex-direction:column;align-items:center;gap:2px}}
nav button span{{font-size:21px}}nav button small{{font-size:11px}}nav button.on{{color:var(--accent);font-weight:bold}}
</style></head><body><main>{body}</main></body></html>""")


def _t(text):
    from core import i18n
    return i18n.tr(text)


def login_page(error=""):
    err = f"<p style='color:#DC2626'>{escape(error)}</p>" if error else ""
    return _page(f"""<h2>📱 {escape(settings.get('shop_name'))}</h2><p class='muted'>تطبيق الموظفين: الأسعار والجرد</p>{err}
<form method='post' action='/m/login'><input name='username' placeholder='{escape(_t("اسم المستخدم"))}'><br><br>
<input name='password' type='password' placeholder='{escape(_t("كلمة المرور"))}'><br><br><button style='width:100%'>دخول</button></form>""")


def _js(value):
    """قيمة JSON آمنة داخل <script> (لا يستطيع نص مثل </script> في اسم أو إعداد كسر الصفحة)"""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def app_page(user):
    """تطبيق الموظفين: تبويبات حسب الصلاحية (الرئيسية، الأصناف، النواقص، الزبائن، الطلبات، اسأل)"""
    from core import i18n
    t = i18n.tr
    c = caps(user)
    cur = settings.get("currency_symbol") or ""
    L = {k: t(v) for k, v in {
        "price": "السعر", "stock": "المتوفر", "exp": "أقرب صلاحية", "whole": "سعر الجملة",
        "count": "الكمية الفعلية على الرف:", "save": "حفظ الجرد", "saved": "تم الحفظ",
        "none": "لا يوجد منتج بهذا الاسم", "diff": "الفرق", "home": "الرئيسية", "items": "الأصناف", "low": "النواقص",
        "customers": "الزبائن", "orders": "الطلبات", "ask": "اسأل", "min": "الحد الأدنى", "need": "اطلب تقريباً",
        "nolow": "لا نواقص — كل الأصناف فوق حدها الأدنى 👍", "debt": "الدين", "lastpay": "آخر دفعة",
        "remind": "تذكير واتساب", "call": "اتصال", "nodebt": "لا ديون على الزبائن 👍", "search_c": "ابحث بالاسم أو الهاتف",
        "noorders": "لا طلبات مفتوحة الآن", "prep": "قيد التجهيز", "ready": "جاهز", "cancel": "إلغاء",
        "notify": "أبلغ الزبون", "confirm_cancel": "إلغاء هذا الطلب؟", "debtors": "أعلى الديون أولاً",
        "refresh": "تحديث", "offline": "تعذر الاتصال بجهاز المحل"}.items()}
    tabs = [("home", "🏠"), ("items", "🔍")]
    tabs += [(k, i) for k, i in (("low", "📦"), ("customers", "👥"), ("orders", "🛵"), ("ask", "✨")) if c.get(k)]
    nav = "".join(f"<button data-tab='{k}'><span>{i}</span><small>{escape(L[k])}</small></button>" for k, i in tabs)
    return _page(f"""<header><b>{escape(settings.get('shop_name'))}</b>
<span class='muted'>👤 {escape(user['full_name'] or user['username'])} · <a href='/m/logout'>{escape(t("خروج"))}</a></span></header>
<section id='t-home'><div id='cards' class='grid'></div><p class='muted c'><a href='#' id='rf'>↻ {escape(L['refresh'])}</a></p></section>
<section id='t-items'><div class='row'><input id='q' placeholder='{escape(t("امسح أو اكتب اسم الصنف أو الباركود"))}'>
<button id='scan' style='display:none'>📷</button></div><video id='v' playsinline style='width:100%;display:none;border-radius:12px'></video>
<div id='out'></div></section>
<section id='t-low'><div id='lowout'></div></section>
<section id='t-customers'><input id='cq' placeholder='{escape(L["search_c"])}'><p class='muted' id='chint'>{escape(L["debtors"])}</p>
<div id='cout'></div></section>
<section id='t-orders'><div id='oout'></div></section>
<section id='t-ask'><div class='card'><b>✨ {escape(t("اسأل محلك"))}</b>
<div class='row'><input id='aq' placeholder='{escape(t("مثلاً: كم بعت اليوم؟ مين عليه دين؟"))}'><button id='ab'>{escape(t("اسأل"))}</button></div>
<div id='aout'></div></div></section>
<nav>{nav}</nav>
<script>
const C={_js(c)},L={_js(L)},CUR={_js(cur)};
const $=id=>document.getElementById(id);
const el=(tag,cls,txt)=>{{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}};
const money=v=>(+v).toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}})+' '+CUR;
async function api(name,q){{try{{const r=await fetch('/m/api/'+name+(q!==undefined?'?q='+encodeURIComponent(q):''));
 if(r.status===401){{location.reload();return null}}return await r.json()}}catch(e){{return {{error:L.offline}}}}}}
async function post(name,body){{try{{const r=await fetch('/m/api/'+name,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});return await r.json()}}catch(e){{return {{error:L.offline}}}}}}
function err(box,j){{if(j&&j.error){{box.innerHTML='';box.appendChild(el('div','card bad','⚠ '+j.error));return true}}return false}}
// ---------- التنقل
const loaded={{}};
function show(tab){{document.querySelectorAll('section').forEach(s=>s.style.display=s.id==='t-'+tab?'':'none');
 document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.tab===tab));
 if(location.hash!=='#'+tab)history.replaceState(null,'','#'+tab);
 ({{home:loadHome,low:loadLow,customers:()=>loadCust(''),orders:loadOrders}}[tab]||(()=>{{}}))();
 if(tab==='items')$('q').focus(); if(tab==='ask')$('aq').focus();}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>show(b.dataset.tab));
// ---------- الرئيسية
async function loadHome(){{const j=await api('home');const box=$('cards');if(err(box,j))return;box.innerHTML='';
 j.cards.forEach(k=>{{const d=el('div','card kpi '+(k.tone||''));d.appendChild(el('div','ic',k.icon));d.appendChild(el('div','muted',k.label));
  d.appendChild(el('div','big',k.value));if(k.tab){{d.style.cursor='pointer';d.onclick=()=>show(k.tab)}}box.appendChild(d)}});}}
$('rf').onclick=e=>{{e.preventDefault();loadHome()}};
// ---------- الأصناف والجرد
const q=$('q'),out=$('out');
async function find(v){{if(!v)return;const j=await api('find',v);if(err(out,j))return;out.innerHTML='';
 if(!j.length){{out.appendChild(el('div','card muted',L.none));return}}
 j.forEach(p=>{{const c=el('div','card');c.appendChild(el('b','',p.name));c.appendChild(el('div','big',money(p.price)));
  c.appendChild(el('div','muted',L.stock+': '+p.qty+' '+p.unit+(p.expiry?(' • '+L.exp+': '+p.expiry):'')+(p.wholesale?(' • '+L.whole+': '+money(p.wholesale)):'')+(p.barcode?' • '+p.barcode:'')));
  if(C.count){{const r=el('div','row');const inp=el('input');inp.type='number';inp.step='any';inp.inputMode='decimal';inp.placeholder=L.count;
   const b=el('button','',L.save);const res=el('div','muted');r.appendChild(inp);r.appendChild(b);c.appendChild(r);c.appendChild(res);
   b.onclick=async()=>{{const k=await post('count',{{product_id:p.id,counted:+inp.value}});res.textContent=k.error?('⚠ '+k.error):('✓ '+L.saved+' — '+L.diff+': '+k.diff)}}}}
  out.appendChild(c)}})}}
q.addEventListener('keydown',e=>{{if(e.key==='Enter'){{find(q.value.trim());q.select()}}}});
window.onNativeScan=v=>{{if(v){{show('items');q.value=v;find(v)}}}};
if(window.AndroidBridge){{const b=$('scan');b.style.display='';b.onclick=()=>AndroidBridge.scan()}}
else if('BarcodeDetector' in window&&navigator.mediaDevices){{const b=$('scan');b.style.display='';
 b.onclick=async()=>{{const v=$('v');v.style.display='';const s=await navigator.mediaDevices.getUserMedia({{video:{{facingMode:'environment'}}}});
  v.srcObject=s;await v.play();const d=new BarcodeDetector();const tick=async()=>{{const c=await d.detect(v).catch(()=>[]);
  if(c.length){{s.getTracks().forEach(t=>t.stop());v.style.display='none';q.value=c[0].rawValue;find(q.value)}}else requestAnimationFrame(tick)}};tick()}}}}
// ---------- النواقص
async function loadLow(){{const box=$('lowout');const j=await api('low');if(err(box,j))return;box.innerHTML='';
 if(!j.length){{box.appendChild(el('div','card good',L.nolow));return}}
 j.forEach(p=>{{const c=el('div','card line');const a=el('div');a.appendChild(el('b','',p.name));
  a.appendChild(el('div','muted',L.min+': '+p.min+' • '+L.need+': '+p.need+' '+p.unit));c.appendChild(a);
  c.appendChild(el('div','big '+(p.qty<=0?'bad':'warn'),String(p.qty)));c.onclick=()=>{{show('items');q.value=p.barcode||p.name;find(q.value)}};box.appendChild(c)}})}}
// ---------- الزبائن والديون
let ct;$('cq').addEventListener('input',()=>{{clearTimeout(ct);ct=setTimeout(()=>loadCust($('cq').value.trim()),300)}});
async function loadCust(v){{const box=$('cout');$('chint').style.display=v?'none':'';const j=await api('customers',v);if(err(box,j))return;box.innerHTML='';
 if(!j.length){{box.appendChild(el('div','card good',L.nodebt));return}}
 j.forEach(k=>{{const c=el('div','card');const top=el('div','line');const a=el('div');a.appendChild(el('b','',k.name));
  a.appendChild(el('div','muted',(k.phone||'')+(k.last_payment?' • '+L.lastpay+': '+k.last_payment:'')));top.appendChild(a);
  top.appendChild(el('div','big '+(k.balance>0?'bad':'good'),money(k.balance)));c.appendChild(top);
  const r=el('div','row');if(k.wa){{const w=el('a','btn wa','💬 '+L.remind);w.href=k.wa;w.target='_blank';r.appendChild(w)}}
  if(k.phone){{const t=el('a','btn ghost','📞 '+L.call);t.href='tel:'+k.phone;r.appendChild(t)}}
  if(r.children.length)c.appendChild(r);box.appendChild(c)}})}}
// ---------- الطلبات
async function loadOrders(){{const box=$('oout');const j=await api('orders');if(err(box,j))return;box.innerHTML='';
 if(!j.length){{box.appendChild(el('div','card muted',L.noorders));return}}
 j.forEach(o=>{{const c=el('div','card');const top=el('div','line');const a=el('div');a.appendChild(el('b','',o.number+' — '+o.customer));
  a.appendChild(el('div','muted',o.created+' • '+o.fulfilment+(o.address?' • '+o.address:'')));top.appendChild(a);
  top.appendChild(el('span','pill '+o.status,o.status_label));c.appendChild(top);
  o.items.forEach(i=>c.appendChild(el('div','',i)));c.appendChild(el('div','big',money(o.total)));
  const r=el('div','row');const act=(st,lbl,cls)=>{{const b=el('button',cls||'',lbl);b.onclick=async()=>{{
   if(st==='cancelled'&&!confirm(L.confirm_cancel))return;const k=await post('order',{{id:o.id,status:st}});
   if(k.error){{alert(k.error);return}}if(k.wa&&st!=='cancelled')window.open(k.wa,'_blank');loadOrders()}};r.appendChild(b)}};
  if(o.status==='new')act('preparing','👨‍🍳 '+L.prep);if(o.status!=='ready')act('ready','✅ '+L.ready,'ok');
  act('cancelled',L.cancel,'ghost');if(o.wa){{const w=el('a','btn wa','💬 '+L.notify);w.href=o.wa;w.target='_blank';r.appendChild(w)}}
  c.appendChild(r);box.appendChild(c)}})}}
// ---------- اسأل
if(C.ask){{const aq=$('aq'),ao=$('aout');const go=async()=>{{const v=aq.value.trim();if(!v)return;ao.textContent='…';
 const j=await api('ask',v);ao.innerHTML='';if(err(ao,j))return;ao.appendChild(el('b','',j.title));
 j.lines.forEach(l=>ao.appendChild(el('div','',l)));
 if(j.rows.length){{const tb=el('table');const tr0=el('tr');j.headers.forEach(x=>tr0.appendChild(el('th','',x)));tb.appendChild(tr0);
  j.rows.forEach(rw=>{{const tr=el('tr');rw.forEach(x=>tr.appendChild(el('td','',x)));tb.appendChild(tr)}});ao.appendChild(tb)}}}};
 $('ab').onclick=go;aq.addEventListener('keydown',e=>{{if(e.key==='Enter')go()}});}}
const start=(location.hash||'#home').slice(1);show(document.querySelector('nav button[data-tab="'+start+'"]')?start:'home');
setInterval(()=>{{const on=document.querySelector('nav button.on');if(on&&on.dataset.tab==='orders')loadOrders();
 if(on&&on.dataset.tab==='home')loadHome()}},30000);
</script>""")


def manifest():
    return json.dumps({"name": settings.get("shop_name"), "short_name": "POS", "start_url": "/m", "display": "standalone",
                       "background_color": "#0F172A", "theme_color": "#2563EB"}, ensure_ascii=False)
