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


def _page(body):
    from core import i18n
    return i18n.tr_html(f"""<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='mobile-web-app-capable' content='yes'>
<meta name='apple-mobile-web-app-capable' content='yes'><link rel='manifest' href='/m/manifest.json'>
<title>{escape(settings.get('shop_name'))}</title><style>
:root{{--bg:#F1F5F9;--card:#fff;--text:#0F172A;--muted:#64748B;--line:#E2E8F0;--accent:#2563EB}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0B1220;--card:#131C2E;--text:#E2E8F0;--muted:#94A3B8;--line:#23324A;--accent:#60A5FA}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Tahoma,system-ui,sans-serif}}
main{{max-width:560px;margin:0 auto;padding:14px 16px 40px}}h2{{font-size:18px}}
input{{width:100%;padding:13px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text);font-size:17px}}
button{{border:0;background:var(--accent);color:#fff;border-radius:10px;padding:12px 14px;font-size:16px}}
.row{{display:flex;gap:8px;margin:8px 0}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:8px 0}}
.muted{{color:var(--muted);font-size:13px}}.big{{font-size:24px;font-weight:bold;color:var(--accent)}}
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
    from core import i18n
    t = i18n.tr
    from core import plans
    can_count = auth.has_permission("inventory", user) and plans.has("mobile")
    can_q = can_ask(user)
    cur = settings.get("currency_symbol") or ""
    L = {k: t(v) for k, v in {"price": "السعر", "stock": "المتوفر", "exp": "أقرب صلاحية", "whole": "سعر الجملة",
                              "count": "الكمية الفعلية على الرف:", "save": "حفظ الجرد", "saved": "تم الحفظ",
                              "none": "لا يوجد منتج بهذا الاسم", "diff": "الفرق"}.items()}
    return _page(f"""<div class='row'><input id='q' placeholder='{escape(t("امسح أو اكتب اسم الصنف أو الباركود"))}' autofocus>
<button id='scan' style='display:none'>📷</button></div><video id='v' playsinline style='width:100%;display:none;border-radius:12px'></video>
<div id='out'></div>
<div class='card' id='askbox' style='display:none'><b>✨ {escape(t("اسأل محلك"))}</b>
<div class='row'><input id='aq' placeholder='{escape(t("مثلاً: كم بعت اليوم؟ مين عليه دين؟"))}'><button id='ab'>{escape(t("اسأل"))}</button></div>
<div id='aout'></div></div><p class='muted'>👤 {escape(user['full_name'] or user['username'])} — <a href='/m/logout'>خروج</a></p>
<script>
const CAN={json.dumps(can_count)};const L={_js(L)};const CUR={_js(cur)};
const q=document.getElementById('q'),out=document.getElementById('out');
async function find(v){{if(!v)return;const r=await fetch('/m/api/find?q='+encodeURIComponent(v));const j=await r.json();
 out.innerHTML='';if(!j.length){{out.textContent=L.none;return}}
 j.forEach(p=>{{const c=document.createElement('div');c.className='card';
  c.innerHTML='<b></b><div class="big">'+p.price.toFixed(2)+' '+CUR+'</div><div class="muted"></div>'+
   (CAN?'<div class="row"><input type="number" step="any" inputmode="decimal" placeholder="'+L.count+'"><button>'+L.save+'</button></div><div class="res muted"></div>':'');
  c.querySelector('b').textContent=p.name;
  c.querySelector('.muted').textContent=L.stock+': '+p.qty+' '+p.unit+(p.expiry?(' • '+L.exp+': '+p.expiry):'')+(p.wholesale?(' • '+L.whole+': '+p.wholesale.toFixed(2)):'')+' • '+p.barcode;
  if(CAN){{const inp=c.querySelector('input');c.querySelector('button').onclick=async()=>{{
   const r=await fetch('/m/api/count',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{product_id:p.id,counted:+inp.value}})}});
   const k=await r.json();c.querySelector('.res').textContent=k.error?('⚠ '+k.error):('✓ '+L.saved+' — '+L.diff+': '+k.diff);}}}}
  out.appendChild(c);}});}}
q.addEventListener('keydown',e=>{{if(e.key==='Enter'){{find(q.value.trim());q.select()}}}});
if({json.dumps(can_q)}){{const box=document.getElementById('askbox'),aq=document.getElementById('aq'),ao=document.getElementById('aout');
 box.style.display='';const go=async()=>{{const v=aq.value.trim();if(!v)return;ao.textContent='…';
  const r=await fetch('/m/api/ask?q='+encodeURIComponent(v));const j=await r.json();ao.innerHTML='';
  if(j.error){{ao.textContent='⚠ '+j.error;return}}
  const h=document.createElement('div');h.innerHTML='<b></b>';h.querySelector('b').textContent=j.title;ao.appendChild(h);
  j.lines.forEach(l=>{{const d=document.createElement('div');d.textContent=l;ao.appendChild(d)}});
  if(j.rows.length){{const tb=document.createElement('table');tb.style.width='100%';tb.style.fontSize='13px';
   const tr0=document.createElement('tr');j.headers.forEach(x=>{{const th=document.createElement('th');th.textContent=x;th.style.textAlign='start';tr0.appendChild(th)}});tb.appendChild(tr0);
   j.rows.forEach(rw=>{{const tr=document.createElement('tr');rw.forEach(x=>{{const td=document.createElement('td');td.textContent=x;tr.appendChild(td)}});tb.appendChild(tr)}});ao.appendChild(tb)}}}};
 document.getElementById('ab').onclick=go;aq.addEventListener('keydown',e=>{{if(e.key==='Enter')go()}});
 if(location.hash==='#ask')aq.focus();}}
window.onNativeScan=v=>{{if(v){{q.value=v;find(v)}}}};
if(window.AndroidBridge){{const b=document.getElementById('scan');b.style.display='';b.onclick=()=>AndroidBridge.scan();}}
else if('BarcodeDetector' in window && navigator.mediaDevices){{const b=document.getElementById('scan');b.style.display='';
 b.onclick=async()=>{{const v=document.getElementById('v');v.style.display='';
  const s=await navigator.mediaDevices.getUserMedia({{video:{{facingMode:'environment'}}}});v.srcObject=s;await v.play();
  const d=new BarcodeDetector();const tick=async()=>{{const c=await d.detect(v).catch(()=>[]);
   if(c.length){{s.getTracks().forEach(t=>t.stop());v.style.display='none';q.value=c[0].rawValue;find(q.value)}}else requestAnimationFrame(tick)}};tick();}}}}
</script>""")


def manifest():
    return json.dumps({"name": settings.get("shop_name"), "short_name": "POS", "start_url": "/m", "display": "standalone",
                       "background_color": "#0F172A", "theme_color": "#2563EB"}, ensure_ascii=False)
