# -*- coding: utf-8 -*-
"""
تشغيل الجهاز الرئيسي كخادم فقط بدون واجهة (اختياري، لجهاز في المكتب الخلفي).
الاستخدام:  python tools/server_headless.py [مجلد البيانات] [المنفذ]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if len(sys.argv) > 1:
    os.environ["SHOP_DATA_DIR"] = sys.argv[1]

from core import db, config, remote, backup  # noqa: E402


def main():
    db.init_db()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None
    host, port = remote.start_server(port=port)
    print(f"READY {config.local_ip()}:{port} link_code={config.get('link_code')}", flush=True)
    last_backup_day = None
    try:
        while True:
            time.sleep(60)
            day = time.strftime("%Y%m%d")
            if day != last_backup_day:
                try:
                    backup.auto_daily_backup()
                except Exception:
                    pass
                last_backup_day = day
    except KeyboardInterrupt:
        remote.stop_server()


if __name__ == "__main__":
    main()
