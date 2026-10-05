# -*- coding: utf-8 -*-
"""
تجميع الفروع: تقرير واحد لكل فروع المحل (أو محلات المالك المتعددة).

كل فرع يعمل بنسخته المستقلة، ويرسل نسخته الاحتياطية تلقائياً إلى مجلد مشترك (Google Drive / OneDrive / فلاشة)
من إعداد «نسخة ثانية» في النسخ الاحتياطي. الجهاز الرئيسي يقرأ أحدث نسخة لكل فرع من هذا المجلد (للقراءة فقط)،
ويحسب لها نفس تقرير الأرباح والخسائر، ويجمع الفروع في جدول واحد.
"""

import glob
import os
import shutil
import sqlite3
from datetime import datetime

from core import db, settings
from core.utils import money

FIELDS = ("invoice_count", "net_sales", "gross_profit", "expenses", "net_profit", "inventory", "receivables",
          "payables")


def import_dir():
    d = os.path.join(db.DATA_DIR, "branches")
    os.makedirs(d, exist_ok=True)
    return d


def _identity(path):
    """اسم الفرع من داخل الملف: اسم الفرع إن وُجد وإلا اسم المحل"""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            vals = dict(conn.execute("SELECT key, value FROM settings WHERE key IN ('shop_name','branch_name')").fetchall())
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    name = (vals.get("branch_name") or "").strip() or (vals.get("shop_name") or "").strip()
    return name or os.path.splitext(os.path.basename(path))[0]


def add_branch_file(path):
    """استيراد ملف فرع يدوياً (نسخة احتياطية أُرسلت بالواتساب أو على فلاشة)"""
    name = _identity(path)
    if not name:
        raise ValueError("الملف ليس نسخة احتياطية صالحة من البرنامج")
    dest = os.path.join(import_dir(), f"branch_{datetime.now():%Y%m%d_%H%M%S}.db")
    shutil.copy2(path, dest)
    return name


def sources():
    """أحدث ملف لكل فرع: {اسم الفرع: (المسار، تاريخ التعديل)} — من المجلد المشترك ومن الملفات المستوردة"""
    here = os.path.abspath(db.DB_PATH)
    own = _identity(here)
    files = glob.glob(os.path.join(import_dir(), "*.db"))          # (مجلد cache الفرعي لا يدخل: ليس *.db في الجذر)
    shared = settings.get("branches_dir")
    if shared and os.path.isdir(shared):
        files += glob.glob(os.path.join(shared, "**", "*.db"), recursive=True)
    out = {}
    for f in files:
        if os.path.abspath(f) == here:
            continue
        name = _identity(f)
        if not name or name == own:
            continue
        mtime = os.path.getmtime(f)
        if name not in out or mtime > out[name][1]:
            out[name] = (f, mtime)
    return out


def _readable_copy(path, mtime):
    """نسخة محلية مرقّاة من ملف الفرع (لا نكتب أبداً في الملف الأصلي في المجلد المشترك)"""
    cache = os.path.join(import_dir(), "cache")
    os.makedirs(cache, exist_ok=True)
    key = abs(hash(os.path.abspath(path))) % 10 ** 12
    copy = os.path.join(cache, f"{key}.db")
    if not os.path.exists(copy) or os.path.getmtime(copy) < mtime:
        shutil.copy2(path, copy)
        os.utime(copy, None)
        db.upgrade_file(copy)
    return copy


def _summary(date_from, date_to):
    from core import reports
    pl = reports.profit_and_loss(date_from, date_to)
    return {"invoice_count": pl["invoice_count"], "net_sales": pl["net_sales"], "gross_profit": pl["gross_profit"],
            "expenses": pl["expenses"], "net_profit": pl["net_profit"],
            "inventory": money(db.scalar("SELECT SUM(quantity * cost_price) FROM products WHERE quantity > 0")),
            "receivables": money(db.scalar("SELECT SUM(amount) FROM customer_transactions")),
            "payables": money(db.scalar("SELECT SUM(amount) FROM supplier_transactions"))}


def consolidated(date_from, date_to):
    """[{branch, updated, ...الأرقام}] لهذا الفرع ثم بقية الفروع، وصف المجموع في النهاية"""
    rows = [dict(_summary(date_from, date_to), branch=(_identity(db.DB_PATH) or "هذا الفرع") + " (هذا الجهاز)",
                 updated=datetime.now().strftime("%Y-%m-%d %H:%M"), path=None)]
    for name, (path, mtime) in sorted(sources().items()):
        try:
            with db.reading(_readable_copy(path, mtime)):
                s = _summary(date_from, date_to)
        except sqlite3.Error as e:
            rows.append({"branch": name, "updated": "", "error": str(e), "path": path, **{k: 0 for k in FIELDS}})
            continue
        rows.append(dict(s, branch=name, updated=datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"), path=path))
    total = {k: money(sum(r.get(k) or 0 for r in rows)) if k != "invoice_count" else sum(r[k] for r in rows)
             for k in FIELDS}
    rows.append(dict(total, branch="المجموع", updated="", path=None))
    return rows
