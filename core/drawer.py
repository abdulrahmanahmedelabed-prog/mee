# -*- coding: utf-8 -*-
"""
فتح درج النقود بأمر ESC/POS القياسي (ESC p 0 25 250).
الدرج عادةً موصول بالطابعة الحرارية (منفذ RJ11)، فيُرسل الأمر إلى الطابعة:
- printer: طابعة ويندوز مثبتة (يحتاج pywin32) أو CUPS على لينكس/ماك
- network: طابعة شبكة (Ethernet) على المنفذ 9100
- serial : منفذ COM / USB-Serial
الإعدادات من ملف إعدادات الجهاز لأن لكل كاشير درجه.
"""

import socket
import subprocess
import sys

from core import config

KICK = b"\x1b\x70\x00\x19\xfa"
MODES = {"none": "لا يوجد درج", "printer": "عبر الطابعة الحرارية المثبتة", "network": "طابعة شبكة (IP)",
         "serial": "منفذ COM مباشر"}


class DrawerError(Exception):
    pass


def open_drawer(mode=None):
    mode = mode or config.get("drawer_mode", "none")
    if mode == "none":
        return False
    try:
        if mode == "network":
            host = config.get("drawer_host")
            if not host:
                raise DrawerError("أدخل عنوان IP للطابعة في الإعدادات")
            with socket.create_connection((host, int(config.get("drawer_port") or 9100)), timeout=3) as s:
                s.sendall(KICK)
        elif mode == "serial":
            port = config.get("drawer_serial") or "COM1"
            try:
                import serial  # pyserial (اختياري)
                with serial.Serial(port, 9600, timeout=2) as ser:
                    ser.write(KICK)
            except ImportError:
                path = rf"\\.\{port}" if sys.platform.startswith("win") else port
                with open(path, "wb", buffering=0) as f:
                    f.write(KICK)
        elif mode == "printer":
            printer = config.get("drawer_printer") or config.get("printer_name")
            if sys.platform.startswith("win"):
                try:
                    import win32print
                except ImportError:
                    raise DrawerError("يلزم تثبيت الحزمة pywin32:  pip install pywin32")
                printer = printer or win32print.GetDefaultPrinter()
                h = win32print.OpenPrinter(printer)
                try:
                    win32print.StartDocPrinter(h, 1, ("Drawer", None, "RAW"))
                    win32print.StartPagePrinter(h)
                    win32print.WritePrinter(h, KICK)
                    win32print.EndPagePrinter(h)
                    win32print.EndDocPrinter(h)
                finally:
                    win32print.ClosePrinter(h)
            else:
                cmd = ["lp", "-o", "raw"] + (["-d", printer] if printer else [])
                subprocess.run(cmd, input=KICK, check=True, timeout=5, capture_output=True)
        else:
            raise DrawerError("نوع اتصال غير معروف")
    except DrawerError:
        raise
    except Exception as e:
        raise DrawerError(f"تعذر فتح الدرج: {e}")
    return True
