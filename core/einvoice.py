# -*- coding: utf-8 -*-
"""
رمز QR للفاتورة الإلكترونية على الإيصال (صيغة TLV المعتمدة للفواتير الضريبية المبسطة في السعودية — المرحلة الأولى):
اسم البائع، الرقم الضريبي، وقت الفاتورة، الإجمالي شامل الضريبة، قيمة الضريبة — مشفرة Base64 داخل الرمز.
ملاحظة: المرحلة الثانية (الربط مع منصة الهيئة وتوقيع الفواتير) تحتاج تكاملاً خاصاً بكل دولة.
"""

import base64
import struct
import zlib


def tlv_base64(seller, vat_number, timestamp, total, vat):
    out = b""
    for tag, value in enumerate((seller, vat_number, timestamp, f"{total:.2f}", f"{vat:.2f}"), start=1):
        b = str(value).encode("utf-8")
        if len(b) > 255:
            b = b[:255]
        out += bytes([tag, len(b)]) + b
    return base64.b64encode(out).decode("ascii")


def decode_tlv(b64):
    raw, i, out = base64.b64decode(b64), 0, {}
    while i < len(raw):
        tag, n = raw[i], raw[i + 1]
        out[tag] = raw[i + 2:i + 2 + n].decode("utf-8")
        i += 2 + n
    return out


def _png(matrix, scale=4):
    size = len(matrix) * scale
    rows = []
    for r in matrix:
        line = bytes(0 if cell else 255 for cell in r for _ in range(scale))
        rows.extend([b"\x00" + line] * scale)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def qr_data_uri(text):
    """صورة QR كـ data URI (تعمل في الطباعة وملفات PDF)، أو None إن لم تتوفر مكتبة qrcode"""
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(text)
    q.make(fit=True)
    return "data:image/png;base64," + base64.b64encode(_png(q.get_matrix())).decode("ascii")


def invoice_qr(inv):
    from core import settings
    ts = (inv["created_at"] or "").replace(" ", "T")
    return qr_data_uri(tlv_base64(settings.get("shop_name"), settings.get("tax_number") or "", ts,
                                  inv["total"], inv["tax"]))
