# -*- coding: utf-8 -*-
"""تجميع الفروع: قراءة نسخة كل فرع وجمعها، دون المساس بقاعدة هذا الجهاز"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import db, products, sales, settings, backup, branches, reports  # noqa: E402


def item(pid, q, price):
    return {"product_id": pid, "product_name": "x", "quantity": q, "unit_price": price}


def test_consolidated_report_reads_branch_backups(tmp_path):
    settings.set_many({"shop_name": "سوبرماركت النور", "branch_name": "الفرع الرئيسي"})
    a = products.add_product("أرز", "100", "مواد", 8, 10, 100, 5)
    sales.create_sale([item(a, 3, 10)])
    # «فرع» آخر: نسخة من هذه القاعدة باسم فرع آخر وبيع إضافي
    shared = tmp_path / "drive"
    shared.mkdir()
    main_db = db.DB_PATH
    branch_path = backup.create_backup(str(shared), tag="branch")
    db.set_db_path(branch_path)
    settings._cache.clear()
    settings.set_many({"branch_name": "فرع الجامعة"})
    sales.create_sale([item(a, 5, 10)])
    db.set_db_path(main_db)
    settings._cache.clear()
    settings.set_many({"branches_dir": str(shared)})

    t = db.today()
    rows = branches.consolidated(t, t)
    names = [r["branch"] for r in rows]
    assert names == ["الفرع الرئيسي (هذا الجهاز)", "فرع الجامعة", "المجموع"]
    here, other, total = rows
    assert here["net_sales"] == reports.profit_and_loss(t, t)["net_sales"] == 30
    assert other["net_sales"] == 80 and other["invoice_count"] == 2
    assert total["net_sales"] == 110 and total["invoice_count"] == 3
    # القراءة من ملف الفرع لا تغيّر هذا الجهاز
    assert db.scalar("SELECT COUNT(*) FROM invoices") == 1


def test_imported_branch_file(tmp_path):
    settings.set_many({"shop_name": "محل", "branch_name": "أ"})
    path = backup.create_backup(str(tmp_path), tag="x")
    db.set_db_path(path)
    settings._cache.clear()
    settings.set_many({"branch_name": "ب"})
    main = str(tmp_path / "main.db")
    db.set_db_path(main)
    db.init_db()
    settings._cache.clear()
    settings.set_many({"shop_name": "محل", "branch_name": "أ"})
    assert branches.add_branch_file(path) == "ب"
    t = db.today()
    assert [r["branch"] for r in branches.consolidated(t, t)][1] == "ب"
