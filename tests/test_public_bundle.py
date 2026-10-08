# -*- coding: utf-8 -*-
"""المستودع العام: صفحة وأدلة وروابط تحميل فقط — لا كود ولا أدلة المزوّد الداخلية"""
import os

from tools import build_public


def test_public_bundle_has_no_source(tmp_path):
    out = build_public.build(str(tmp_path / "pub"))
    files = list(build_public._walk(out))
    assert "index.html" in files and "README.md" in files and "media/ad.mp4" in files
    assert not [f for f in files if f.endswith((".py", ".kt", ".java", ".iss", ".bat", ".json", ".yml", ".pem"))]
    assert not [f for f in files if os.path.basename(f).startswith(("05_", "06_", "07_"))]
    readme = open(os.path.join(out, "README.md"), encoding="utf-8").read()
    assert "## للمطوّر" not in readme and "prog/mee" not in readme and "shopping/releases/latest" in readme
    site = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    assert "prog/mee" not in site and "shopping/releases/latest/download/ShopAccounting-Setup.exe" in site
