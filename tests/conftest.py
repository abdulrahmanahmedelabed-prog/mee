import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import db, auth, settings, config, context  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.set_db_path(str(tmp_path / "test.db"))
    config.reset_cache()
    context.set_terminal(None)
    settings._cache.clear()
    db.init_db()
    settings.set_many({"require_shift": "0"})   # قاعدة الوردية الإلزامية لها اختبارها الخاص (test_accounting_rules)
    auth.login("admin", "admin")
    yield
    auth.logout()
    settings._cache.clear()


def pytest_sessionfinish(session, exitstatus):
    """إغلاق كل نوافذ Qt المتبقية قبل خروج بايثون: حذفها بعد QApplication يسبب انهياراً عند الخروج على ويندوز"""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    from core import remote
    try:
        remote.stop_server()
    except Exception:  # noqa: BLE001
        pass
    for w in QApplication.topLevelWidgets():
        w.close()
        w.deleteLater()
    for _ in range(3):
        app.processEvents()
