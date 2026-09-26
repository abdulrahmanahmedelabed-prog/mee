# -*- coding: utf-8 -*-
"""الطباعة: فواتير حرارية 58/80مم، تقارير A4، وملصقات أسعار بالباركود"""

from PySide6.QtCore import QSizeF, QRectF, Qt, QMarginsF
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout, QPainter, QFont, QColor
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog, QPrinterInfo

from core import settings, barcode
from core.utils import money


def available_printers():
    return [p.printerName() for p in QPrinterInfo.availablePrinters()]


def _make_printer(width_mm=None):
    printer = QPrinter(QPrinter.HighResolution)
    name = settings.get("printer_name")
    if name and name in available_printers():
        printer.setPrinterName(name)
    if width_mm and width_mm < 150:
        # ورق حراري: عرض ثابت وطول كبير (الطابعة تقص حسب المحتوى)
        printer.setPageSize(QPageSize(QSizeF(width_mm, 297), QPageSize.Millimeter, "Receipt"))
        printer.setPageMargins(QMarginsF(2, 2, 2, 2), QPageLayout.Millimeter)
    else:
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
    return printer


def _doc(html, printer):
    doc = QTextDocument()
    doc.setHtml(html)
    doc.setPageSize(printer.pageRect(QPrinter.Point).size())
    return doc


def print_html(parent, html, width_mm=None, preview=False, ask=False):
    """طباعة مباشرة على الطابعة المحددة، أو معاينة. إذا لم توجد طابعة تُفتح المعاينة (ويمكن الحفظ PDF منها)"""
    if width_mm is None:
        width_mm = int(settings.get_float("receipt_width_mm", 80))
    printer = _make_printer(width_mm)
    no_printer = not available_printers()
    if preview or no_printer:
        dlg = QPrintPreviewDialog(printer, parent)
        dlg.setWindowTitle("معاينة الطباعة")
        dlg.paintRequested.connect(lambda pr: _doc(html, pr).print_(pr))
        dlg.resize(700, 800)
        dlg.exec()
        return
    if ask:
        d = QPrintDialog(printer, parent)
        if d.exec() != QPrintDialog.Accepted:
            return
    _doc(html, printer).print_(printer)


def save_pdf(html, path, width_mm=None):
    printer = _make_printer(width_mm)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    _doc(html, printer).print_(printer)
    return path


# ---------------- ملصقات الأسعار ----------------

def draw_barcode(painter, rect: QRectF, code: str):
    try:
        bits = barcode.ean13_bits(code) if barcode.is_valid_ean13(code) else barcode.code128_bits(code)
    except ValueError:
        bits = barcode.code128_bits(code)
    unit = rect.width() / len(bits)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("black"))
    for i, b in enumerate(bits):
        if b == "1":
            painter.drawRect(QRectF(rect.x() + i * unit, rect.y(), unit + 0.05, rect.height()))


def render_labels(printer, items, label_w=50, label_h=30):
    """items: قائمة (اسم، سعر، باركود) - ملصق واحد لكل صفحة (مناسب لطابعات الملصقات)"""
    printer.setPageSize(QPageSize(QSizeF(label_w, label_h), QPageSize.Millimeter, "Label"))
    printer.setPageMargins(QMarginsF(1, 1, 1, 1), QPageLayout.Millimeter)
    painter = QPainter(printer)
    sym = settings.get("currency_symbol")
    shop = settings.get("shop_name")
    for idx, (name, price, code) in enumerate(items):
        if idx:
            printer.newPage()
        r = painter.viewport()
        W, H = r.width(), r.height()
        painter.setLayoutDirection(Qt.RightToLeft)
        f = QFont("Tahoma")
        f.setPixelSize(int(H * 0.09))
        painter.setFont(f)
        painter.setPen(QColor("black"))
        painter.drawText(QRectF(0, 0, W, H * 0.12), Qt.AlignCenter, shop)
        f.setPixelSize(int(H * 0.12))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(0, H * 0.12, W, H * 0.16), Qt.AlignCenter | Qt.TextWordWrap, name)
        f.setPixelSize(int(H * 0.2))
        painter.setFont(f)
        painter.drawText(QRectF(0, H * 0.28, W, H * 0.24), Qt.AlignCenter, f"{money(price):,.2f} {sym}")
        if code:
            draw_barcode(painter, QRectF(W * 0.08, H * 0.55, W * 0.84, H * 0.3), code)
            f.setBold(False)
            f.setPixelSize(int(H * 0.08))
            painter.setFont(f)
            painter.drawText(QRectF(0, H * 0.86, W, H * 0.12), Qt.AlignCenter, code)
    painter.end()


def print_labels(parent, items):
    printer = QPrinter(QPrinter.HighResolution)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle("ملصقات الأسعار")
    dlg.paintRequested.connect(lambda pr: render_labels(pr, items))
    dlg.resize(600, 700)
    dlg.exec()
