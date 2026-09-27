# -*- coding: utf-8 -*-
"""
الطلبات الأونلاين (المتجر الإلكتروني البسيط):

- صفحة عامة /shop على خادم البرنامج: الزبون يتصفح الأصناف المتوفرة وأسعارها، يضعها في سلة، ويرسل الطلب
  (استلام من المحل أو توصيل) — الدفع عند الاستلام، فلا حاجة لبوابة دفع.
- الطلب يظهر فوراً في شاشة «الطلبات الأونلاين» في البرنامج، ويُحوَّل لفاتورة في نقطة البيع بضغطة.
- للوصول من الإنترنت (خارج شبكة المحل) يلزم نفق آمن مثل Cloudflare Tunnel أو Tailscale Funnel (انظر الدليل).
الأسعار والكميات يعيد الخادم حسابها بنفسه؛ لا يُعتمد على ما يرسله المتصفح.
"""

import json
import time
from html import escape

from core import db, settings, audit
from core.utils import money, qty, fmt_qty

STATUS = {"new": "جديد", "preparing": "قيد التجهيز", "ready": "جاهز", "done": "مكتمل", "cancelled": "ملغى"}
FULFILMENT = {"pickup": "استلام من المحل", "delivery": "توصيل"}
MAX_ITEMS = 60
_RATE = {}   # ip -> [أوقات الطلبات] للحد من الإساءة


class OrderError(ValueError):
    pass


# ---------------------------------------------------------------------------
# الكتالوج
# ---------------------------------------------------------------------------

def catalog():
    rows = db.query("""SELECT id, name, category, sale_price, unit, quantity, is_weighted FROM products
                       WHERE is_active=1 AND sale_price > 0 AND quantity > 0 ORDER BY category, name""")
    return [{"id": r["id"], "name": r["name"], "category": r["category"] or "", "price": money(r["sale_price"]),
             "unit": r["unit"] or "", "weighted": bool(r["is_weighted"])} for r in rows]


# ---------------------------------------------------------------------------
# إنشاء الطلب (من الصفحة العامة)
# ---------------------------------------------------------------------------

def create_order(data, source_ip=""):
    if not settings.get_bool("online_store_enabled"):
        raise OrderError("المتجر الإلكتروني غير مفعّل حالياً")
    now = time.time()
    hits = [t for t in _RATE.get(source_ip, []) if now - t < 3600]
    if len(hits) >= 10:
        raise OrderError("طلبات كثيرة من نفس الجهاز، حاول لاحقاً")
    name = (data.get("name") or "").strip()[:80]
    phone = "".join(ch for ch in (data.get("phone") or "") if ch.isdigit() or ch == "+")[:20]
    fulfilment = data.get("fulfilment") if data.get("fulfilment") in FULFILMENT else "pickup"
    address = (data.get("address") or "").strip()[:200]
    if not name or len(phone) < 7:
        raise OrderError("الاسم ورقم الهاتف مطلوبان")
    if fulfilment == "delivery":
        if not settings.get_bool("online_store_delivery"):
            raise OrderError("التوصيل غير متاح حالياً")
        if not address:
            raise OrderError("العنوان مطلوب للتوصيل")
    raw = data.get("items") or []
    if not isinstance(raw, list) or not raw or len(raw) > MAX_ITEMS:
        raise OrderError("السلة فارغة")
    items = []
    for it in raw:
        try:
            pid, q = int(it["product_id"]), qty(float(it["quantity"]))
        except (KeyError, TypeError, ValueError):
            raise OrderError("طلب غير صالح")
        if q <= 0 or q > 1000:
            raise OrderError("كمية غير صحيحة")
        p = db.query_one("SELECT * FROM products WHERE id=? AND is_active=1", (pid,))
        if not p or p["sale_price"] <= 0:
            raise OrderError("صنف غير متوفر")
        if not p["is_weighted"]:
            q = float(int(q))
        items.append({"product_id": p["id"], "name": p["name"], "quantity": q, "unit_price": money(p["sale_price"])})
    total = money(sum(i["quantity"] * i["unit_price"] for i in items))
    fee = settings.get_float("online_store_delivery_fee", 0) if fulfilment == "delivery" else 0.0
    if total < settings.get_float("online_store_min_order", 0):
        raise OrderError(f"أقل قيمة للطلب {settings.get_float('online_store_min_order', 0):g}")
    with db.tx() as conn:
        number = db.next_number(conn, "online_order", "WEB")
        cur = conn.execute("""INSERT INTO online_orders(order_number, customer_name, phone, address, fulfilment, note,
                                                        items, total, status, source_ip, created_at, updated_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)""",
                           (number, name, phone, address, fulfilment, (data.get("note") or "").strip()[:300],
                            json.dumps(items, ensure_ascii=False), money(total + fee), source_ip, db.now(), db.now()))
        oid = cur.lastrowid
    _RATE[source_ip] = hits + [now]
    return {"id": oid, "order_number": number, "total": money(total + fee), "delivery_fee": money(fee)}


# ---------------------------------------------------------------------------
# إدارة الطلبات (من البرنامج)
# ---------------------------------------------------------------------------

def list_orders(status=None, limit=300):
    sql = "SELECT * FROM online_orders"
    params = []
    if status == "open":
        sql += " WHERE status IN ('new','preparing','ready')"
    elif status:
        sql += " WHERE status=?"
        params.append(status)
    rows = []
    for r in db.query(sql + " ORDER BY id DESC LIMIT ?", params + [limit]):
        d = dict(r)
        d["items"] = json.loads(r["items"])
        rows.append(d)
    return rows


def get_order(order_id):
    r = db.query_one("SELECT * FROM online_orders WHERE id=?", (order_id,))
    if not r:
        return None
    d = dict(r)
    d["items"] = json.loads(r["items"])
    return d


def set_status(order_id, status, invoice_id=None):
    if status not in STATUS:
        raise ValueError("حالة غير معروفة")
    with db.tx() as conn:
        conn.execute("UPDATE online_orders SET status=?, updated_at=?, invoice_id=COALESCE(?, invoice_id) WHERE id=?",
                     (status, db.now(), invoice_id, order_id))
        audit.log("طلب أونلاين", f"#{order_id} ← {STATUS[status]}", conn)


def new_count():
    return int(db.scalar("SELECT COUNT(*) FROM online_orders WHERE status='new'") or 0)


def status_message(order):
    shop = settings.get("shop_name")
    s = order["status"]
    if s == "preparing":
        body = "طلبك قيد التجهيز الآن."
    elif s == "ready":
        body = "طلبك جاهز للاستلام ✅" if order["fulfilment"] == "pickup" else "طلبك جاهز وسيخرج للتوصيل قريباً 🛵"
    elif s == "done":
        body = "شكراً لطلبك، نتمنى أن تكون راضياً 🌷"
    elif s == "cancelled":
        body = "نعتذر، تم إلغاء الطلب. تواصل معنا لأي استفسار."
    else:
        body = "استلمنا طلبك وسنتواصل معك قريباً."
    return f"مرحباً {order['customer_name']}\nطلب رقم {order['order_number']} من {shop}\n{body}\nالمجموع: {order['total']:,.2f}"


# ---------------------------------------------------------------------------
# الصفحة العامة
# ---------------------------------------------------------------------------

def store_page():
    from core import i18n
    rtl = i18n.is_rtl()
    t = i18n.tr
    cur = settings.get("currency_symbol") or ""
    products = catalog()
    cats = sorted({p["category"] for p in products if p["category"]})
    data = json.dumps(products, ensure_ascii=False).replace("</", "<\\/")
    delivery = settings.get_bool("online_store_delivery")
    fee = settings.get_float("online_store_delivery_fee", 0)
    labels = {k: t(v) for k, v in {
        "search": "ابحث عن صنف...", "all": "الكل", "add": "أضف", "cart": "السلة", "total": "المجموع",
        "name": "الاسم", "phone": "رقم الهاتف", "address": "العنوان", "note": "ملاحظات", "send": "إرسال الطلب",
        "pickup": "استلام من المحل", "delivery": "توصيل", "empty": "السلة فارغة", "fee": "رسوم التوصيل",
        "ok": "تم استلام طلبك رقم", "pay": "الدفع عند الاستلام", "err": "تعذر إرسال الطلب"}.items()}
    cat_btns = "".join(f"<button class='cat' data-c='{escape(c)}'>{escape(c)}</button>" for c in cats)
    closed = "" if settings.get_bool("online_store_enabled") else \
        f"<div class='closed'>{escape(t('المتجر الإلكتروني غير مفعّل حالياً'))}</div>"
    return f"""<!doctype html><html lang='{'ar' if rtl else 'en'}' dir='{'rtl' if rtl else 'ltr'}'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(settings.get('shop_name'))}</title>
<style>
:root{{--bg:#F8FAFC;--card:#fff;--text:#0F172A;--muted:#64748B;--line:#E2E8F0;--accent:#16A34A}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0B1220;--card:#131C2E;--text:#E2E8F0;--muted:#94A3B8;--line:#23324A;--accent:#4ADE80}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Tahoma,system-ui,sans-serif}}
header{{padding:16px;background:var(--card);border-bottom:1px solid var(--line)}}header h1{{margin:0;font-size:20px}}
header p{{margin:4px 0 0;color:var(--muted)}}main{{max-width:900px;margin:0 auto;padding:12px 16px 140px}}
input,textarea,select{{width:100%;padding:11px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text);font-size:16px}}
.cats{{display:flex;gap:6px;overflow-x:auto;padding:10px 0}}.cat{{flex:none;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:20px;padding:6px 12px}}
.cat.on{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}}
.p{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px;display:flex;flex-direction:column;gap:6px}}
.p b{{font-size:14px}}.p span{{color:var(--accent);font-weight:bold}}button.add{{border:0;background:var(--accent);color:#fff;border-radius:8px;padding:8px}}
.bar{{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);padding:12px 16px}}
.bar button{{width:100%;border:0;background:var(--accent);color:#fff;border-radius:10px;padding:13px;font-size:17px}}
dialog{{border:0;border-radius:14px;padding:16px;width:min(520px,94vw);background:var(--card);color:var(--text)}}
.row{{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)}}
.q{{display:flex;gap:6px;align-items:center}}.q button{{width:32px;height:32px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--text)}}
label{{display:block;margin-top:8px;color:var(--muted);font-size:13px}}.closed{{background:#FEE2E2;color:#991B1B;padding:10px;border-radius:10px;margin:10px 0}}
</style></head><body>
<header><h1>🏪 {escape(settings.get('shop_name'))}</h1><p>{escape(t(settings.get('online_store_message') or ''))} • {escape(settings.get('shop_phone') or '')}</p></header>
<main>{closed}<input id='s' placeholder='{labels["search"]}'><div class='cats'><button class='cat on' data-c=''>{labels["all"]}</button>{cat_btns}</div>
<div class='grid' id='g'></div></main>
<div class='bar'><button id='open'>🛒 {labels["cart"]} — <span id='sum'>0.00</span> {escape(cur)}</button></div>
<dialog id='d'><h3>🛒 {labels["cart"]}</h3><div id='lines'></div>
<p><b>{labels["total"]}: <span id='sum2'>0.00</span> {escape(cur)}</b> <small id='feeLine'></small></p>
<label>{labels["name"]}</label><input id='n' autocomplete='name'>
<label>{labels["phone"]}</label><input id='ph' type='tel' autocomplete='tel'>
<label><select id='f'><option value='pickup'>{labels["pickup"]}</option>{f"<option value='delivery'>{labels['delivery']}</option>" if delivery else ""}</select></label>
<label>{labels["address"]}</label><input id='a' autocomplete='street-address'>
<label>{labels["note"]}</label><textarea id='no' rows='2'></textarea>
<p style='color:var(--muted)'>💵 {labels["pay"]}</p>
<div class='bar' style='position:static;padding:0;border:0'><button id='send'>{labels["send"]}</button></div>
<p id='msg'></p></dialog>
<script>
const P={data};const cart={{}};const fee={fee};let cat='';
const g=document.getElementById('g'),s=document.getElementById('s');
function money(v){{return v.toFixed(2)}}
function render(){{const q=s.value.trim();g.innerHTML='';
 P.filter(p=>(!cat||p.category===cat)&&(!q||p.name.includes(q))).forEach(p=>{{const d=document.createElement('div');d.className='p';
  d.innerHTML='<b></b><span>'+money(p.price)+' {escape(cur)}</span><small></small><button class="add">+ {labels["add"]}</button>';
  d.querySelector('b').textContent=p.name;d.querySelector('small').textContent=p.unit;
  d.querySelector('button').onclick=()=>{{cart[p.id]=(cart[p.id]||0)+1;totals();}};g.appendChild(d);}});}}
function total(){{return Object.entries(cart).reduce((t,[id,q])=>t+P.find(p=>p.id==id).price*q,0)}}
function totals(){{const t=total();const f=document.getElementById('f');const extra=(f&&f.value==='delivery')?fee:0;
 document.getElementById('sum').textContent=money(t);document.getElementById('sum2').textContent=money(t+extra);
 document.getElementById('feeLine').textContent=extra?('+ {labels["fee"]} '+money(extra)):'';lines();}}
function lines(){{const L=document.getElementById('lines');L.innerHTML='';const ids=Object.keys(cart);
 if(!ids.length){{L.textContent='{labels["empty"]}';return}}
 ids.forEach(id=>{{const p=P.find(x=>x.id==id);const r=document.createElement('div');r.className='row';
  r.innerHTML='<span></span><span class="q"><button>−</button><b>'+cart[id]+'</b><button>+</button></span>';
  r.querySelector('span').textContent=p.name;const [m,pl]=r.querySelectorAll('button');
  m.onclick=()=>{{cart[id]--;if(cart[id]<=0)delete cart[id];totals()}};pl.onclick=()=>{{cart[id]++;totals()}};L.appendChild(r);}});}}
document.querySelectorAll('.cat').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.cat').forEach(x=>x.classList.remove('on'));b.classList.add('on');cat=b.dataset.c;render()}});
s.oninput=render;document.getElementById('open').onclick=()=>{{lines();document.getElementById('d').showModal()}};
document.getElementById('f').onchange=totals;
document.getElementById('send').onclick=async()=>{{const msg=document.getElementById('msg');
 const body={{name:n.value,phone:ph.value,address:a.value,note:no.value,fulfilment:f.value,
  items:Object.entries(cart).map(([id,q])=>({{product_id:+id,quantity:q}}))}};
 try{{const r=await fetch('/shop/order',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  const j=await r.json();if(j.error)throw new Error(j.error);
  msg.textContent='✅ {labels["ok"]} '+j.order_number;for(const k in cart)delete cart[k];totals();}}
 catch(e){{msg.textContent='⚠ {labels["err"]}: '+e.message}}}};
render();
</script></body></html>"""
