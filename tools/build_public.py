# -*- coding: utf-8 -*-
"""
تجهيز محتوى المستودع العام (abdulrahmanahmedelabed-prog/shopping): صفحة البرنامج، الأدلة، الصور، الفيديو
وروابط التحميل — بدون أي كود مصدري. الكود يبقى في المستودع الخاص.
    python tools/build_public.py OUT_DIR
ينشره تلقائياً سير العمل .github/workflows/public.yml (يحتاج السر PUBLIC_REPO_TOKEN).
"""

import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_REPO = "abdulrahmanahmedelabed-prog/shopping"
# أدلة المزوّد الداخلية (التسويق، البناء والترخيص، التفعيل) لا تُنشر
PRIVATE_DOCS = ("05_", "06_", "07_")
NOTICE = ("\n---\n\n© الحسن للبرمجيات والإعلان — جميع الحقوق محفوظة. هذا المستودع للتحميل والأدلة وصفحة البرنامج فقط.\n"
          "© Al-Hassan Software & Advertising — all rights reserved. This repository hosts downloads, guides and the "
          "product website only.\n")


def _public_text(text):
    text = text.replace("abdulrahmanahmedelabed-prog/mee", PUBLIC_REPO)
    return text.replace("abdulrahmanahmedelabed-prog.github.io/mee/", "abdulrahmanahmedelabed-prog.github.io/shopping/")


def _readme():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    text = text.split("\n## للمطوّر", 1)[0].rstrip()
    if text.endswith("---"):
        text = text[:-3].rstrip()
    lines = [ln for ln in text.splitlines()
             if "actions/workflows" not in ln and not any(f"docs/{p}" in ln for p in PRIVATE_DOCS)]
    return _public_text("\n".join(lines)) + "\n" + NOTICE


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def build(out):
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(out):                      # تنظيف كل شيء عدا .git
        if name == ".git":
            continue
        p = os.path.join(out, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(_readme())
    docs = os.path.join(ROOT, "docs")
    for name in sorted(os.listdir(docs)):
        src = os.path.join(docs, name)
        if name.endswith(".md") and not name.startswith(PRIVATE_DOCS):
            with open(src, encoding="utf-8") as f:
                text = _public_text(f.read())
            with open(_mk(os.path.join(out, "docs", name)), "w", encoding="utf-8") as f:
                f.write(text)
        elif name.endswith(".png"):
            _copy(src, os.path.join(out, "docs", name))
    for name in sorted(os.listdir(os.path.join(docs, "en"))):
        if name.endswith(".md"):
            with open(os.path.join(docs, "en", name), encoding="utf-8") as f:
                text = _public_text(f.read())
            with open(_mk(os.path.join(out, "docs", "en", name)), "w", encoding="utf-8") as f:
                f.write(text)
    for rel in ("marketing/ad/ad_horizontal.mp4", "marketing/ad/ad_vertical.mp4", "marketing/infographic/post.png",
                "marketing/infographic/story.png", "marketing/infographic/flyer_a4.png"):
        if os.path.exists(os.path.join(ROOT, rel)):
            _copy(os.path.join(ROOT, rel), os.path.join(out, rel))

    # صفحة البرنامج في جذر المستودع (GitHub Pages من الفرع الرئيسي)
    with open(os.path.join(docs, "site", "index.html"), encoding="utf-8") as f:
        html = _public_text(f.read())
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    for name in os.listdir(docs):
        if name.endswith(".png"):
            _copy(os.path.join(docs, name), os.path.join(out, "img", name))
    fonts = os.path.join(ROOT, "ui", "fonts")
    for name in ("IBMPlexSansArabic_400Regular.ttf", "IBMPlexSansArabic_700Bold.ttf", "OFL.txt"):
        _copy(os.path.join(fonts, name), os.path.join(out, "fonts", name))
    _copy(os.path.join(ROOT, "marketing", "ad", "ad_horizontal.mp4"), os.path.join(out, "media", "ad.mp4"))
    open(os.path.join(out, ".nojekyll"), "w").close()

    missing = [m for m in sorted(set(re.findall(r"img/[a-z_]+\.png", html))) if not os.path.exists(os.path.join(out, m))]
    if missing:
        raise SystemExit("missing site images: " + ", ".join(missing))
    leaked = [p for p in _walk(out) if p.endswith((".py", ".kt", ".java", ".iss", ".bat", ".json", ".yml"))]
    if leaked:
        raise SystemExit("source files must not be published: " + ", ".join(leaked))
    return out


def _mk(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _walk(out):
    for d, dirs, files in os.walk(out):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in files:
            yield os.path.relpath(os.path.join(d, f), out).replace(os.sep, "/")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = build(sys.argv[1])
    print("public bundle:", path, sum(1 for _ in _walk(path)), "files")
