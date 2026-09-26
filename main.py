# -*- coding: utf-8 -*-
"""
برنامج المحاسبة ونقاط البيع للمحلات الصغيرة والسوبرماركت - النسخة 3.0
يعمل محلياً بدون إنترنت، على جهاز واحد أو عدة أجهزة كاشير عبر شبكة المحل.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core import db, auth, backup, config, remote


def excepthook(exc_type, exc, tb):
    """أي خطأ غير متوقع يظهر برسالة ويُسجّل في ملف بدل إغلاق البرنامج فجأة"""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        os.makedirs(db.DATA_DIR, exist_ok=True)
        with open(os.path.join(db.DATA_DIR, "errors.log"), "a", encoding="utf-8") as f:
            f.write(f"\n[{db.now()}]\n{text}")
    except OSError:
        pass
    if not QApplication.instance():
        return
    if isinstance(exc, remote.ConnectionFailed):
        QMessageBox.warning(None, "انقطع الاتصال", f"{exc}\n\nلم تُحفظ العملية الأخيرة. أعد المحاولة بعد عودة الاتصال.")
    elif isinstance(exc, remote.RemoteError):
        QMessageBox.warning(None, "الجهاز الرئيسي", str(exc))
    else:
        QMessageBox.critical(None, "خطأ غير متوقع", f"حدث خطأ ولم يتأثر حفظ البيانات:\n{exc}\n\n(التفاصيل في data/errors.log)")


def connect_as_client(app):
    """نقطة بيع فرعية: الاتصال بالجهاز الرئيسي، مع إمكانية تعديل الإعدادات إن فشل"""
    from ui.dialogs import NetworkDialog
    while True:
        cfg = config.load()
        if cfg["mode"] != config.MODE_CLIENT:
            return False
        client = remote.install_client(cfg["server_host"], cfg["server_port"], cfg["link_code"], cfg["terminal_name"])
        try:
            client.ping()
            return True
        except remote.ConnectionFailed as e:
            remote.uninstall_client()
            box = QMessageBox(QMessageBox.Warning, "تعذر الاتصال", str(e))
            retry = box.addButton("إعادة المحاولة", QMessageBox.AcceptRole)
            settings_btn = box.addButton("إعدادات الاتصال", QMessageBox.ActionRole)
            box.addButton("خروج", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is retry:
                continue
            if box.clickedButton() is settings_btn:
                NetworkDialog().exec()
                config.reset_cache()
                continue
            sys.exit(0)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Shop Accounting")
    app.setLayoutDirection(Qt.RightToLeft)
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))  # أرقام لاتينية وفاصلة عشرية نقطة
    font = QFont()
    font.setFamilies(["Segoe UI", "Tahoma", "Noto Sans Arabic", "Noto Naskh Arabic"])
    font.setPointSize(10)
    app.setFont(font)
    from ui.style import STYLE_SHEET
    app.setStyleSheet(STYLE_SHEET)
    sys.excepthook = excepthook

    mode = config.load()["mode"]
    if mode == config.MODE_CLIENT:
        connect_as_client(app)
    else:
        db.init_db()
        if mode == config.MODE_SERVER:
            try:
                remote.start_server()
            except OSError as e:
                QMessageBox.warning(None, "الخادم", f"تعذر تشغيل خدمة الشبكة على المنفذ {config.get('server_port')}:\n{e}\n"
                                                     "ستعمل نقطة البيع على هذا الجهاز فقط.")
        try:
            backup.auto_daily_backup()
        except Exception:
            pass

    from ui.dialogs import LoginDialog, ChangePasswordDialog
    if LoginDialog().exec() != QDialog.Accepted:
        return 0
    if auth.current_user().get("must_change_password"):
        ChangePasswordDialog(None, forced=True).exec()

    from ui.main_window import MainWindow
    window = MainWindow()
    window.showMaximized()
    code = app.exec()
    remote.stop_server()
    return code


if __name__ == "__main__":
    sys.exit(main())
