# -*- coding: utf-8 -*-
"""النسخ الاحتياطي والاستعادة (يومي تلقائي + عند الإغلاق + يدوي)"""

import glob
import os
import sqlite3
from datetime import datetime

from core import db, settings


def backup_dir():
    d = settings.get("backup_dir") or os.path.join(db.DATA_DIR, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def create_backup(target_dir=None, tag="manual"):
    """نسخة آمنة حتى أثناء عمل البرنامج (باستخدام SQLite backup API)"""
    target_dir = target_dir or backup_dir()
    os.makedirs(target_dir, exist_ok=True)
    name = f"accounting_{datetime.now():%Y%m%d_%H%M%S}_{tag}.db"
    path = os.path.join(target_dir, name)
    src = db.get_connection()
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    prune()
    mirror_backup(path)
    return path


def mirror_backup(path):
    """نسخة ثانية في مجلد مزامنة سحابي (Google Drive / OneDrive / Dropbox) أو فلاشة.
    برنامج المزامنة يرفعها للسحابة تلقائياً، فتبقى البيانات آمنة حتى لو تعطل الجهاز أو سُرق."""
    mirror = settings.get("backup_mirror_dir")
    if not mirror:
        return None
    try:
        os.makedirs(mirror, exist_ok=True)
        import shutil
        target = os.path.join(mirror, os.path.basename(path))
        shutil.copy2(path, target)
        keep = int(settings.get_float("backup_keep", 30))
        files = sorted(glob.glob(os.path.join(mirror, "accounting_*.db")), reverse=True)
        for f in files[keep:]:
            os.remove(f)
        return target
    except OSError:
        return None  # المجلد غير متاح (فلاشة غير موصولة مثلاً) - لا نوقف البرنامج


def list_backups():
    """[(المسار، الحجم بالبايت، التاريخ نصاً)]"""
    files = sorted(glob.glob(os.path.join(backup_dir(), "accounting_*.db")), reverse=True)
    return [(f, os.path.getsize(f), datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")) for f in files]


def prune():
    keep = int(settings.get_float("backup_keep", 30))
    for f, _, _ in list_backups()[keep:]:
        try:
            os.remove(f)
        except OSError:
            pass


def auto_daily_backup():
    """نسخة واحدة يومياً عند أول تشغيل في اليوم"""
    today = datetime.now().strftime("%Y%m%d")
    if not any(os.path.basename(f).startswith(f"accounting_{today}") for f, _, _ in list_backups()):
        return create_backup(tag="auto")
    return None


def validate_backup(path):
    try:
        conn = sqlite3.connect(path)
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        return ok and {"products", "invoices"} <= tables
    except sqlite3.Error:
        return False


def restore_backup(path):
    """استعادة نسخة: تُحفظ نسخة من الوضع الحالي أولاً للأمان"""
    if not validate_backup(path):
        raise ValueError("الملف ليس نسخة احتياطية صالحة")
    create_backup(tag="before_restore")
    src = sqlite3.connect(path)
    dst = db.get_connection()
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    db.init_db()  # ترقية النسخة إن كانت قديمة
    return True
