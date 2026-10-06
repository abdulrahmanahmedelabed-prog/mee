# -*- coding: utf-8 -*-
"""
الترجمة (واجهة إنجليزية للأسواق العالمية).

الكود مكتوب بالعربية، والترجمة تتم وقت العرض فقط: tr("نص عربي") ← النص الإنجليزي.
البيانات المحفوظة (طرق الدفع، الوحدات، أسباب حركة المخزون) تبقى كما هي، فلا يتأثر أي منطق محاسبي.

- نصوص ثابتة: تطابق تام من i18n/en.json
- نصوص f-string: قوالب مثل "الرصيد: {0}" ← "Balance: {0}" (والقيم داخلها تُترجم أيضاً إن كانت نصوصاً معروفة)
- نص من عدة أسطر: كل سطر على حدة
- ما لا يُعرف من البيانات (أسماء أصناف وفئات وعملاء قصيرة): الاسم الإنجليزي الذي كتبه صاحب المحل،
  وإلا ترجمة تلقائية بالقاموس (core/product_names.py)
"""

import json
import os
import re
import sys

ARABIC = re.compile(r"[؀-ۿ]")
_LANG = "ar"
_EXACT = {}
_TEMPLATES = []      # (regex, english, first_literal)
_CACHE = {}
LANGUAGES = {"ar": "العربية", "en": "English"}


def _catalog_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.join(base, "i18n")


def set_language(lang):
    global _LANG
    _LANG = lang if lang in LANGUAGES else "ar"
    _EXACT.clear()
    _TEMPLATES.clear()
    _CACHE.clear()
    if _LANG == "ar":
        return
    with open(os.path.join(_catalog_dir(), f"{_LANG}.json"), encoding="utf-8") as f:
        cat = json.load(f)
    _EXACT.update(cat["exact"])
    templates = dict(cat["templates"])
    for k, v in list(cat["exact"].items()):
        if "   " in k and "   " in v:          # عناوين القائمة الجانبية بدون الأيقونة
            _EXACT.setdefault(k.split("   ")[-1].strip(), v.split("   ")[-1].strip())
        if "%d" in k or "%s" in k:               # نصوص تُنسَّق بـ %
            templates[re.sub(r"%[ds]", "{0}", k)] = re.sub(r"%[ds]", "{0}", v)
    for ar, en in sorted(templates.items(), key=lambda kv: -len(kv[0])):
        parts = re.split(r"(\{\d+\})", ar)
        pattern, literals = "", []
        for p in parts:
            if re.fullmatch(r"\{\d+\}", p):
                pattern += "(.*?)"
            else:
                lit = p.replace("{{", "{").replace("}}", "}")
                pattern += re.escape(lit)
                if lit.strip():
                    literals.append(lit)
        if not literals:
            continue
        _TEMPLATES.append((re.compile("^" + pattern + "$", re.S), en, max(literals, key=len)))


def language():
    return _LANG


def is_rtl():
    return _LANG == "ar"


def tr(text):
    if _LANG == "ar" or not isinstance(text, str) or not text or not ARABIC.search(text):
        return text
    hit = _CACHE.get(text)
    if hit is not None:
        return hit
    out = _translate(text)
    if len(_CACHE) > 20000:
        _CACHE.clear()
    _CACHE[text] = out
    return out


def _translate(text):
    if text in _EXACT:
        return _EXACT[text]
    stripped = text.strip()
    if stripped != text and stripped in _EXACT:
        return text.replace(stripped, _EXACT[stripped])
    if stripped.endswith(":") and stripped[:-1].strip() in _EXACT:
        return text.replace(stripped, _EXACT[stripped[:-1].strip()] + ":")
    for rx, en, lit in _TEMPLATES:
        if lit in text:
            m = rx.match(text)
            if m:
                vals = [tr(g) for g in m.groups()]
                try:
                    return en.format(*vals)
                except (IndexError, KeyError, ValueError):
                    pass
    if "\n" in text:
        return "\n".join(tr(line) for line in text.split("\n"))
    # بادئة بلا حروف عربية (أيقونة، رقم): نترجم الباقي
    m = re.match(r"^([^؀-ۿ]+)(.+)$", text, re.S)
    if m:
        rest = tr(m.group(2))
        if rest != m.group(2):
            return m.group(1) + rest
    # أجزاء عربية داخل نص مركّب («الإجمالي: 50 ₪»): نترجم فقط إن عُرفت كل الأجزاء،
    # وإلا فالنص بيانات (اسم صنف أو عميل) ويبقى كما هو
    runs = re.findall(_RUN, text)
    if runs and all(r.strip() in _EXACT for r in runs):
        return re.sub(_RUN, lambda mm: mm.group(0).replace(mm.group(0).strip(), _EXACT[mm.group(0).strip()]), text)
    try:
        from core import product_names
        out = product_names.english(text)
    except Exception:
        out = None
    return out or text


def clear_cache():
    """بعد تغيير اسم إنجليزي لصنف"""
    _CACHE.clear()


_RUN = r"[؀-ۿ][؀-ۿً-ٟ0-9% ()/،\-]*[؀-ۿ)]|[؀-ۿ]"


def tr_html(html):
    """ترجمة مستند HTML (فاتورة/تقرير): النص بين الوسوم، مع قلب اتجاه الصفحة"""
    if _LANG == "ar" or not html:
        return html
    html = re.sub(r">([^<>]+)<", lambda m: ">" + tr(m.group(1)) + "<", html)
    html = html.replace("dir='rtl'", "dir='ltr'").replace('dir="rtl"', 'dir="ltr"')
    html = html.replace("direction: rtl", "direction: ltr").replace("lang='ar'", "lang='en'")
    html = html.replace("text-align: left", "text-align: __R__").replace("text-align: right", "text-align: left")
    html = html.replace("text-align:right", "text-align:left").replace("text-align: __R__", "text-align: right")
    return html


def _init_from_env():
    lang = os.environ.get("SHOP_LANG")
    if lang:
        set_language(lang)


_init_from_env()
