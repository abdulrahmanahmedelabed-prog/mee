# -*- coding: utf-8 -*-
"""
استخراج كل النصوص العربية الظاهرة للمستخدم من الكود (للترجمة).
    python tools/i18n_extract.py            ← يكتب i18n/strings.json ويطبع النصوص غير المترجمة في en.json
النصوص الثابتة تُحفظ كما هي، ونصوص f-string تُحفظ كقوالب: "الرصيد: {0}".
"""

import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARABIC = re.compile(r"[؀-ۿ]")
SKIP_FILES = {"license_tool.py", "i18n_extract.py", "demo_data.py", "product_names.py"}
# كلمات يفهم بها «اسأل محلك» الأسئلة (عامية وفصحى) — مفردات للفهم وليست نصوصاً تظهر للمستخدم
VOCAB_NAMES = {"INTENTS", "NAV", "MONTHS", "_STOP", "PLAN_WORDS", "SALES_WORDS", "NAV_VERBS", "SUPERLATIVE", "LEAST",
               "CONCEPTS", "NUMBER_WORDS", "_PREFIXES", "_SUFFIXES", "CALC_WORDS", "_MATH_PREFIX", "NOTES_WORDS"}
VOCAB_CALLS = {"_has", "norm", "has_concept"}


def _vocab_nodes(tree, filename):
    """عُقد النصوص التي هي مفردات فهم (في core/assistant.py فقط)"""
    out = set()
    if filename != "assistant.py":
        return out
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if (targets and set(targets) & VOCAB_NAMES) or (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in VOCAB_CALLS):
            out.update(id(n) for n in ast.walk(node) if isinstance(n, ast.Constant))
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):          # (مفتاح، [كلمات]) في الحلقات
            out.update(id(n) for n in ast.walk(node.iter) if isinstance(n, ast.Constant))
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "replace" or (
                isinstance(node, ast.Tuple) and len(node.elts) == 2 and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str) and len(e.value) == 1 for e in node.elts)):
            out.update(id(n) for n in ast.walk(node) if isinstance(n, ast.Constant))
    for node in ast.walk(tree):                     # أنماط re وجداول الحروف
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("compile", "search", "maketrans", "sub"):
            out.update(id(n) for n in ast.walk(node) if isinstance(n, ast.Constant))
    return out


def _template(node):
    parts, n = [], 0
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value.replace("{", "{{").replace("}", "}}"))
        else:
            parts.append("{%d}" % n)
            n += 1
    return "".join(parts)


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                out.add(id(first.value))
    return out


def extract():
    exact, templates = set(), set()
    files = glob.glob(os.path.join(ROOT, "core", "*.py")) + glob.glob(os.path.join(ROOT, "ui", "*.py")) + \
        [os.path.join(ROOT, "main.py")]
    for f in files:
        if os.path.basename(f) in SKIP_FILES:
            continue
        tree = ast.parse(open(f, encoding="utf-8").read())
        docs = _docstrings(tree) | _vocab_nodes(tree, os.path.basename(f))
        inside_fstring = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    inside_fstring.add(id(v))
                t = _template(node)
                if ARABIC.search(t) and "SELECT" not in t and "INSERT" not in t:
                    templates.add(t)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                    and id(node) not in inside_fstring and ARABIC.search(node.value):
                v = node.value
                if any(k in v for k in ("SELECT ", "INSERT ", "UPDATE ", "CREATE ", " LIKE ", "QPushButton", "\u0600", "؀")) \
                        or v.endswith(" %") or v == "٫":
                    continue
                exact.add(v)
                if "," in v and "\n" not in v and len(v) < 200:   # قوائم مفصولة بفاصلة (أنواع المصاريف الافتراضية)
                    exact.update(x.strip() for x in v.split(",") if ARABIC.search(x))
    # HTML (الفواتير والتقارير المطبوعة): نترجم النص بين الوسوم فقط
    for group, is_t in ((list(exact), False), (list(templates), True)):
        for v in group:
            if "<" in v and ">" in v:
                (templates if is_t else exact).discard(v)
                for seg in re.split(r"<[^>]*>", v):
                    seg = seg.strip()
                    if not ARABIC.search(seg):
                        continue
                    if is_t and re.search(r"\{\d+\}", seg):
                        n = iter(range(100))
                        templates.add(re.sub(r"\{\d+\}", lambda m: "{%d}" % next(n), seg))
                    else:
                        exact.add(seg.replace("{{", "{").replace("}}", "}") if is_t else seg)
    return sorted(exact), sorted(templates)


def main():
    exact, templates = extract()
    os.makedirs(os.path.join(ROOT, "i18n"), exist_ok=True)
    with open(os.path.join(ROOT, "i18n", "strings.json"), "w", encoding="utf-8") as f:
        json.dump({"exact": exact, "templates": templates}, f, ensure_ascii=False, indent=1)
    en_path = os.path.join(ROOT, "i18n", "en.json")
    en = json.load(open(en_path, encoding="utf-8")) if os.path.exists(en_path) else {"exact": {}, "templates": {}}
    missing_e = [s for s in exact if s not in en["exact"]]
    missing_t = [t for t in templates if t not in en["templates"]]
    print(f"exact: {len(exact)} (missing {len(missing_e)})  templates: {len(templates)} (missing {len(missing_t)})")
    if "--show" in sys.argv:
        json.dump({"exact": missing_e, "templates": missing_t}, sys.stdout, ensure_ascii=False, indent=0)
    return missing_e, missing_t


if __name__ == "__main__":
    main()
