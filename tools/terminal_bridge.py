# -*- coding: utf-8 -*-
"""
جسر جهاز الدفع — مثال مرجعي لبروتوكول ShopPOS Terminal Bridge v1 (انظر core/payments.py).

يشغَّل على جهاز الكاشير المتصل به جهاز البنك:
    python tools/terminal_bridge.py            (المنفذ الافتراضي 9900، ويعمل كمحاكي)

لربط بنك حقيقي: عدّل الدالة process_sale فقط لتستدعي مكتبة البنك أو بروتوكول الجهاز (ECR عبر منفذ COM أو TCP
حسب مواصفات البنك)، وأرجع النتيجة بنفس الشكل. البرنامج نفسه لا يحتاج أي تعديل.
"""

import json
import os
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TERMINAL_NAME = "محاكي الجسر"


def process_sale(amount, currency, reference):
    """
    ← هنا يوضع ربط البنك الحقيقي. مثال: إرسال رسالة البيع للجهاز عبر منفذ COM وانتظار الرد.
    يجب أن ترجع: approved, auth_code, rrn, card (مخفية مثل ****1234), message
    """
    time.sleep(0.2)
    if f"{amount:.2f}".endswith(".13"):
        return {"approved": False, "message": "مرفوضة: رصيد غير كافٍ"}
    return {"approved": True, "auth_code": f"{secrets.randbelow(10**6):06d}", "rrn": secrets.token_hex(6).upper(),
            "card": "****" + f"{secrets.randbelow(10**4):04d}", "message": "موافقة"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._send({"ok": True, "terminal": TERMINAL_NAME})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/sale":
            self.send_error(404)
            return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or b"{}")
            self._send(process_sale(float(req["amount"]), req.get("currency", ""), req.get("reference", "")))
        except (KeyError, ValueError) as e:
            self._send({"approved": False, "message": f"طلب غير صالح: {e}"})


def serve(port=9900, host="127.0.0.1"):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("BRIDGE_PORT", 9900))
    print(f"Terminal bridge on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    serve(port).serve_forever()
