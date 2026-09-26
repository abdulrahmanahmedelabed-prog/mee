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
    auth.login("admin", "admin")
    yield
    auth.logout()
    settings._cache.clear()
