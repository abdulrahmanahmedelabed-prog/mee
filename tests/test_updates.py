# -*- coding: utf-8 -*-
"""التحديث بضغطة: قراءة إصدار GitHub، التنزيل والتحقق من البصمة والحجم، ومعاملات التثبيت الصامت"""
import hashlib
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core import updates

PAYLOAD = b"MZ" + os.urandom(300_000)


def _release(digest=True, version="v99.1"):
    asset = {"name": "ShopAccounting-Setup.exe", "size": len(PAYLOAD),
             "browser_download_url": "https://github.com/o/r/releases/download/v99.1/ShopAccounting-Setup.exe"}
    if digest:
        asset["digest"] = "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()
    return {"tag_name": version, "html_url": "https://github.com/o/r/releases/tag/v99.1", "name": "v99.1",
            "body": "- ميزة جديدة", "assets": [asset, {"name": "ShopAccounting-Portable.zip", "size": 1}]}


class _Resp(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self._url = url

    def geturl(self):
        return self._url


def _opener(data):
    return lambda req, timeout=None: _Resp(data, req.full_url)


def test_reads_github_release_with_setup_asset():
    info = updates.newer_than(_release(), "10.6")
    assert info["version"] == "99.1" and info["setup_url"].endswith("/ShopAccounting-Setup.exe")
    assert info["sha256"] == hashlib.sha256(PAYLOAD).hexdigest() and info["setup_size"] == len(PAYLOAD)
    assert updates.newer_than(_release(version="v10.6"), "10.6") is None
    bad = _release()
    bad["assets"][0]["browser_download_url"] = "http://evil/x.exe"
    assert updates.newer_than(bad, "10.6")["setup_url"] == ""


def test_download_verifies_hash_and_size(tmp_path):
    info = updates.newer_than(_release(), "10.6")
    seen = []
    path = updates.download(info, str(tmp_path), progress=lambda d, t: seen.append((d, t)), opener=_opener(PAYLOAD))
    assert open(path, "rb").read() == PAYLOAD and seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    with pytest.raises(updates.UpdateError):                        # ملف معدّل: بصمة لا تطابق
        updates.download(info, str(tmp_path / "x"), opener=_opener(PAYLOAD[:-1] + b"!"))
    with pytest.raises(updates.UpdateError):                        # تنزيل ناقص
        updates.download(info, str(tmp_path / "y"), opener=_opener(PAYLOAD[:1000]))
    assert not [f for f in os.listdir(tmp_path / "x") if f.endswith(".exe")]
    with pytest.raises(updates.Cancelled):
        updates.download(info, str(tmp_path / "z"), cancelled=lambda: True, opener=_opener(PAYLOAD))
    assert os.listdir(tmp_path / "z") == []                        # لا بقايا ملفات


def test_untrusted_hosts_and_args():
    info = {"version": "99", "setup_url": "https://example.com/Setup.exe"}
    with pytest.raises(updates.UpdateError):
        updates.download(info)
    assert updates._trusted("https://objects.githubusercontent.com/x") and not updates._trusted("http://github.com/x")
    args = updates.installer_args("en")
    assert "/SILENT" in args and "/RELAUNCH=1" in args and "/LANG=english" in args
    assert not updates.can_self_update()                            # ليس نسخة ويندوز مثبّتة
    with pytest.raises(updates.UpdateError):
        updates.check(url="https://127.0.0.1:9/none.json", timeout=1, raise_errors=True)


def test_update_dialog_portable_falls_back_to_page():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ui.update_dialog import UpdateDialog
    d = UpdateDialog(None, updates.newer_than(_release(), "10.6"))
    assert not d.auto and "صفحة التحميل" in d.go_btn.text()
    d.close()
