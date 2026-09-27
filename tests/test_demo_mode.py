# -*- coding: utf-8 -*-
"""نسخة التدريب (--demo): بيانات تجريبية في مجلد منفصل، والدخول بدون فرض تغيير كلمة المرور"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_demo_mode_prepares_separate_training_data(tmp_path):
    code = ("import sys; sys.argv=['main.py','--demo']; import main; from core import db, auth;"
            "db.init_db(); main.prepare_demo(); main.prepare_demo();"
            "print(db.DATA_DIR); print(db.scalar('SELECT COUNT(*) FROM invoices') > 20);"
            "print(db.scalar('SELECT COUNT(*) FROM users WHERE must_change_password=1'));"
            "print(bool(auth.authenticate('cashier','1234')))")
    env = dict(os.environ, SHOP_DEMO_DIR=str(tmp_path / "demo"), SHOP_DATA_DIR=str(tmp_path / "real"),
               QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()[-4:]
    assert lines == [str(tmp_path / "demo"), "True", "0", "True"]
    assert not (tmp_path / "real").exists()
