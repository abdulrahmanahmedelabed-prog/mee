# -*- coding: utf-8 -*-
"""الباركود: التحقق من EAN-13، توليد باركود داخلي، وقراءة باركود الميزان"""

from core import settings


def ean13_check_digit(first12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def is_valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13_check_digit(code[:12]) == code[12]


def internal_barcode(product_id: int) -> str:
    """باركود داخلي للمنتجات التي بلا باركود (يبدأ بـ 299 حتى لا يتعارض مع الميزان ولا مع باركود المصانع)"""
    body = f"299{product_id:09d}"
    return body + ean13_check_digit(body)


def parse_scale_barcode(code: str):
    """
    باركود الميزان الشائع (EAN-13):  PP CCCCC VVVVV K
      PP    = بادئة الميزان (20-29 افتراضياً)
      CCCCC = رمز الصنف (PLU) المسجّل في بطاقة المنتج
      VVVVV = الوزن بالغرام أو السعر بالأغورة (حسب الإعداد)
      K     = رقم التحقق
    يرجع: (plu, value, mode) أو None
    """
    if not settings.get_bool("scale_enabled"):
        return None
    code = code.strip()
    if len(code) != 13 or not code.isdigit():
        return None
    prefixes = [p.strip() for p in settings.get("scale_prefixes", "").split(",") if p.strip()]
    prefix = next((p for p in prefixes if code.startswith(p)), None)
    if not prefix or code.startswith("299"):
        return None
    code_len = int(settings.get_float("scale_code_length", 5))
    start = len(prefix)
    plu = code[start:start + code_len].lstrip("0") or "0"
    raw_value = code[start + code_len:12]
    if not raw_value:
        return None
    mode = settings.get("scale_mode", "weight")
    value = int(raw_value) / (1000.0 if mode == "weight" else 100.0)
    return plu, value, mode


# ---------------- رسم باركود EAN-13 (لطباعة ملصقات الأسعار) ----------------

_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
_G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
_R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_bits(code: str) -> str:
    """تحويل رقم EAN-13 إلى سلسلة أشرطة (1 = أسود) - 95 وحدة"""
    if len(code) == 12:
        code += ean13_check_digit(code)
    if not is_valid_ean13(code):
        raise ValueError("باركود EAN-13 غير صالح")
    first, left, right = int(code[0]), code[1:7], code[7:]
    bits = "101"
    for i, d in enumerate(left):
        bits += (_L if _PARITY[first][i] == "L" else _G)[int(d)]
    bits += "01010"
    for d in right:
        bits += _R[int(d)]
    bits += "101"
    return bits


def code128_bits(text: str) -> str:
    """ترميز Code128-B لأي باركود غير رقمي/غير قياسي"""
    patterns = [
        "11011001100", "11001101100", "11001100110", "10010011000", "10010001100", "10001001100", "10011001000",
        "10011000100", "10001100100", "11001001000", "11001000100", "11000100100", "10110011100", "10011011100",
        "10011001110", "10111001100", "10011101100", "10011100110", "11001110010", "11001011100", "11001001110",
        "11011100100", "11001110100", "11101101110", "11101001100", "11100101100", "11100100110", "11101100100",
        "11100110100", "11100110010", "11011011000", "11011000110", "11000110110", "10100011000", "10001011000",
        "10001000110", "10110001000", "10001101000", "10001100010", "11010001000", "11000101000", "11000100010",
        "10110111000", "10110001110", "10001101110", "10111011000", "10111000110", "10001110110", "11101110110",
        "11010001110", "11000101110", "11011101000", "11011100010", "11011101110", "11101011000", "11101000110",
        "11100010110", "11101101000", "11101100010", "11100011010", "11101111010", "11001000010", "11110001010",
        "10100110000", "10100001100", "10010110000", "10010000110", "10000101100", "10000100110", "10110010000",
        "10110000100", "10011010000", "10011000010", "10000110100", "10000110010", "11000010010", "11001010000",
        "11110111010", "11000010100", "10001111010", "10100111100", "10010111100", "10010011110", "10111100100",
        "10011110100", "10011110010", "11110100100", "11110010100", "11110010010", "11011011110", "11011110110",
        "11110110110", "10101111000", "10100011110", "10001011110", "10111101000", "10111100010", "11110101000",
        "11110100010", "10111011110", "10111101110", "11101011110", "11110101110", "11010000100", "11010010000",
        "11010011100", "1100011101011",
    ]
    start_b = 104
    values = [start_b] + [ord(ch) - 32 for ch in text if 32 <= ord(ch) < 128]
    checksum = (values[0] + sum(v * (i + 1) for i, v in enumerate(values[1:]))) % 103
    values.append(checksum)
    return "".join(patterns[v] for v in values) + patterns[106]
