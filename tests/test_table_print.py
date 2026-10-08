# -*- coding: utf-8 -*-
"""الطباعة السريعة للجداول الكبيرة دون تعطيل العمل: صفحات صحيحة، إلغاء، ودفتر اليومية كاملاً"""
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core import products, sales


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _in_thread(fn):
    out = {}

    def run():
        try:
            out["v"] = fn()
        except Exception as e:  # noqa: BLE001
            out["e"] = e
    t = threading.Thread(target=run)
    t.start()
    t.join(60)
    if "e" in out:
        raise out["e"]
    return out["v"]


def test_big_table_renders_page_by_page(app, tmp_path):
    from ui import table_print as T
    rows = [[f"2026-01-{i % 28 + 1:02d}", f"REF-{i}", "بيان طويل " * 6, "حساب", f"{i:,.2f}", ""] for i in range(3000)]
    rep = T.TableReport("دفتر اليومية", "اختبار", ["التاريخ", "المرجع", "البيان", "الحساب", "مدين", "دائن"], rows, {4, 5},
                        [i % 2 == 0 for i in range(3000)])
    path = str(tmp_path / "big.pdf")
    seen = []
    pages = T.render(rep, T.make_pdf_printer(path), lambda i, n: seen.append((i, n)))
    assert pages > 50 and seen[-1] == (pages, pages) and os.path.getsize(path) > 50_000
    with pytest.raises(T.Cancelled):
        T.render(rep, T.make_pdf_printer(str(tmp_path / "c.pdf")), None, lambda: True)


def test_journal_report_prints_whole_period(app, tmp_path):
    from core import db
    from ui import table_print as T
    from ui.accounting_screen import _JournalReport
    pid = products.add_product("أرز", "tp1", "", 3, 5, 500, 0)
    for _ in range(5):
        sales.create_sale([{"product_id": pid, "product_name": "أرز", "quantity": 1, "unit_price": 5}])
    rep = _JournalReport("2000-01-01", db.today(), False, "كل الفترة")
    _in_thread(lambda: rep.rows)                       # البيانات تُجهَّز في خيط خلفي (بلا Qt)
    pages = T.render(rep, T.make_pdf_printer(str(tmp_path / "j.pdf")))
    assert pages >= 1 and len(rep.rows) >= 5 * 3 and len(rep.shade) == len(rep.rows)


def test_pairing_dialog_and_assistant(app):
    from core import assistant
    from ui.pair_dialog import PairDialog, APK_URL
    d = PairDialog()
    assert d.pair_qr.pixmap() is not None and not d.pair_qr.pixmap().isNull()
    assert d.addr.text().endswith("/m") and APK_URL.endswith("ShopPOS-android.apk")
    d.close()
    d.deleteLater()
    r = assistant.answer("كيف اربط الجوال؟")
    assert r["intent"] == "pair" and r["action"][0] == "pair"


def test_job_bar_draws_between_events_and_keeps_ui_responsive(app, tmp_path):
    """الرسم يتم على خيط الواجهة بين الأحداث: المؤقتات تعمل أثناء التجهيز، والنتيجة ملف كامل"""
    import time
    from PySide6.QtCore import QTimer
    from ui import jobs, table_print as T
    bar = jobs.JobBar()
    rows = [[str(i), "نص " * 8, f"{i:.2f}"] for i in range(6000)]
    rep = T.TableReport("اختبار", "", ["#", "البيان", "المبلغ"], rows, {2})
    path = str(tmp_path / "bar.pdf")
    bar.submit("اختبار", lambda: T.render_iter(rep, T.make_pdf_printer(path)), prepare=lambda: rep.rows, path=path,
               report=rep)
    ticks = []
    t = QTimer()
    t.timeout.connect(lambda: ticks.append(1))
    t.start(20)
    end = time.time() + 60
    while (bar.current is not None or bar.queue) and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    t.stop()
    assert bar.current is None and bar.last.count > 50 and os.path.getsize(path) > 50_000
    assert len(ticks) >= 3                              # الواجهة لم تتجمد أثناء الرسم
    assert bar._path() == path and bar.print_btn.isVisibleTo(bar)
    bar.deleteLater()
    app.processEvents()
