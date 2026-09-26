# -*- coding: utf-8 -*-
"""
سياق التنفيذ: المستخدم الحالي ونقطة البيع (الجهاز) الحالية.

- على الجهاز العادي: قيمة عامة واحدة.
- على الخادم: كل طلب قادم من جهاز كاشير آخر يُنفَّذ بسياقه الخاص (مستخدمه وجهازه) داخل خيط منفصل.
"""

import threading
from contextlib import contextmanager

_local = threading.local()
_global = {"user": None, "terminal": None}


def user():
    if getattr(_local, "active", False):
        return _local.user
    return _global["user"]


def set_user(u):
    _global["user"] = dict(u) if u else None


def terminal():
    if getattr(_local, "active", False):
        return _local.terminal
    if _global["terminal"] is None:
        from core import config
        _global["terminal"] = config.get("terminal_name")
    return _global["terminal"]


def set_terminal(name):
    _global["terminal"] = name


@contextmanager
def request(user_row, terminal_name):
    """تنفيذ طلب بسياق مستخدم وجهاز محددين (يُستخدم في الخادم)"""
    _local.active = True
    _local.user = dict(user_row) if user_row else None
    _local.terminal = terminal_name
    try:
        yield
    finally:
        _local.active = False
        _local.user = None
        _local.terminal = None
