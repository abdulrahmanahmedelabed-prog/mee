# -*- coding: utf-8 -*-
"""
برنامج المحاسبة ونقاط البيع للمحلات الصغيرة والسوبرماركت.
يعمل محلياً بدون إنترنت، على جهاز واحد أو عدة أجهزة كاشير عبر شبكة المحل.
التشغيل بـ --demo يفتح «نسخة التدريب»: بيانات سوبرماركت تجريبية في مجلد منفصل لا يمس بيانات المحل.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEMO = "--demo" in sys.argv
if DEMO:
    _base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    os.environ["SHOP_DATA_DIR"] = os.environ.get("SHOP_DEMO_DIR") or os.path.join(_base, "demo_data")

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


def prepare_demo():
    """نسخة التدريب: تُملأ بالبيانات التجريبية أول مرة، والدخول admin/admin أو cashier/1234 بدون تغيير كلمة المرور"""
    if not db.scalar("SELECT COUNT(*) FROM invoices"):
        from tools import demo_data
        progress = None
        if QApplication.instance():
            from PySide6.QtWidgets import QProgressDialog
            dlg = QProgressDialog("تجهيز نسخة التدريب: سوبرماركت كامل بمبيعات 3 سنوات (مرة واحدة فقط)...",
                                  None, 0, 100)
            dlg.setWindowTitle("نسخة التدريب")
            dlg.setMinimumDuration(0)
            dlg.setMinimumWidth(460)
            dlg.show()

            def progress(frac, day):
                dlg.setValue(int(frac * 100))
                if day:
                    dlg.setLabelText(f"تجهيز نسخة التدريب (مرة واحدة فقط)...\nالمبيعات حتى {day}")
                QApplication.processEvents()
        demo_data.main(progress)
    with db.tx() as conn:
        conn.execute("UPDATE users SET must_change_password=0")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Shop Accounting")
    from ui import i18n_qt
    i18n_qt.apply_language(os.environ.get("SHOP_LANG") or config.load().get("language") or "ar", app)
    app.setLayoutDirection(i18n_qt.direction())
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))  # أرقام لاتينية وفاصلة عشرية نقطة
    from ui.style import load_fonts
    family = load_fonts()              # الخط العربي الحديث المضمَّن مع البرنامج
    font = QFont()
    font.setFamilies([f for f in (family, "Segoe UI", "Tahoma", "Noto Sans Arabic") if f])
    font.setPointSize(10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    from ui import theme
    theme.apply(app)                   # فاتح / داكن / تلقائي، بألوان ثابتة لا يغيّرها إعداد ويندوز
    sys.excepthook = excepthook

    mode = config.load()["mode"]
    if mode == config.MODE_CLIENT:
        connect_as_client(app)
    else:
        db.init_db()
        try:                                          # فحص سلامة ملف البيانات عند كل تشغيل
            state = db.get_connection().execute("PRAGMA quick_check").fetchone()[0]
        except Exception as e:
            state = str(e)
        if state != "ok":
            QMessageBox.critical(None, "تنبيه مهم", "فحص سلامة ملف البيانات وجد مشكلة:\n" + str(state) +
                                 "\n\nاسترجع آخر نسخة احتياطية سليمة من الإعدادات ← النسخ الاحتياطي، وتواصل مع الدعم.")
        if DEMO:
            prepare_demo()
        if mode == config.MODE_SERVER or str(config.get("owner_web")) == "1":
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
    if not LoginDialog.run_login():
        return 0
    if auth.current_user().get("must_change_password"):
        ChangePasswordDialog(None, forced=True).exec()
    from ui.setup_wizard import SetupWizard, needs_setup
    if auth.has_permission("settings") and needs_setup():
        SetupWizard().exec()
        i18n_qt.apply_language(config.load().get("language") or "ar", app)   # إن اختار الإنجليزية في المعالج
        theme.apply(app)

    from ui.main_window import MainWindow
    window = MainWindow()
    if DEMO:
        window.training = True
        window.update_header()
    window.showMaximized()
    code = app.exec()
    remote.stop_server()
    return code


if __name__ == "__main__":
    sys.exit(main())
