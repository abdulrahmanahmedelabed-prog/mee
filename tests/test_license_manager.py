# -*- coding: utf-8 -*-
"""نافذة المطوّر لإصدار مفاتيح التفعيل: إنشاء المفاتيح، إصدار مفتاح صالح، رمز استعادة، والسجل"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core import license as lic  # noqa: E402
from tools import license_tool as lt  # noqa: E402


def test_license_manager_issues_valid_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(lt, "PUBKEY_FILE", str(tmp_path / "license_pubkey.py"))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    key_dir = str(tmp_path / "keys")
    assert lt.pubkey_status(key_dir) == (False, "none")
    assert lt.init_keys(key_dir, bits=1024) is True
    assert lt.pubkey_status(key_dir) == (True, "ok")
    assert lt.init_keys(key_dir) is False            # لا يستبدل مفتاحاً موجوداً أبداً

    from tools.license_manager import LicenseManager
    QApplication.instance() or QApplication([])
    w = LicenseManager(key_dir)
    w.machine.setText("abcd1234ef567890")
    w.shop.setText("بقالة التجربة")
    w.issue()
    pub = lt.load_private(os.path.join(key_dir, "private_key.json"))
    data = lic.parse_key(w.key_out.toPlainText(), {"n": pub["n"], "e": pub["e"]})
    assert data["machine"] == "ABCD-1234-EF56-7890" and data["shop"] == "بقالة التجربة" and data["plan"] == "pro"
    assert "الترخيص والتفعيل" in w.message() and w.last_key in w.message()
    assert w.log_table.rowCount() == 1

    w.machine.setText("123")                          # رمز ناقص: لا يصدر شيئاً جديداً
    w.issue()
    assert w.log_table.rowCount() == 1

    w.reset_machine.setText("ABCD-1234-EF56-7890")
    w.make_reset()
    r = lic.parse_key(w.reset_out.toPlainText(), {"n": pub["n"], "e": pub["e"]}, prefix=lic.RESET_PREFIX)
    assert r["type"] == "reset" and r["machine"] == "ABCD-1234-EF56-7890"
