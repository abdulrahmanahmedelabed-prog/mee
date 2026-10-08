# -*- coding: utf-8 -*-
"""
طباعة الجداول الكبيرة بسرعة: رسم مباشر للصفحات (QPainter) بدل تنسيق HTML.
دفتر يومية بثمانية آلاف سطر يصبح PDF في ثوانٍ، ويُجهَّز في الخلفية (ui/jobs.py) دون تعطيل العمل.

يعمل في خيط خلفي: Qt يسمح بالرسم على QPrinter وQImage خارج خيط الواجهة.
"""

import base64

from PySide6.QtCore import QRectF, Qt, QMarginsF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize, QPainter, QPen
from PySide6.QtPrintSupport import QPrinter

from core import i18n, settings, db

BLUE = QColor("#2563EB")
HEAD_BG = QColor("#EEF2F7")
SHADE = QColor("#F6F8FB")
LINE = QColor("#D0D5DD")
MUTED = QColor("#475467")


class Cancelled(Exception):
    pass


class TableReport:
    """تقرير جدولي جاهز للرسم. rows: قوائم نصوص؛ numeric: أرقام الأعمدة الرقمية؛ shade: لكل صف True لتظليله"""

    def __init__(self, title, subtitle, headers, rows, numeric=None, shade=None, landscape=False):
        self.title, self.subtitle = title, subtitle
        self.headers = [str(h) for h in headers]
        self.rows = rows
        self.numeric = set(numeric or ())
        self.shade = shade
        self.landscape = landscape

    @classmethod
    def from_table(cls, table, title, subtitle=""):
        """من جدول الواجهة كما هو معروض (بنفس الترتيب والتلوين)"""
        from ui.widgets import RAW_BG
        cols = table.columnCount()
        headers = [i18n.tr(table.horizontalHeaderItem(c).text()) for c in range(cols)]
        rows, shade, numeric = [], [], set()
        for r in range(table.rowCount()):
            row = []
            for c in range(cols):
                it = table.item(r, c)
                row.append(i18n.tr(it.text()) if it else "")
                if it and r < 50 and (it.textAlignment() & Qt.AlignLeft) and it.text():
                    numeric.add(c)
            first = table.item(r, 0)
            shade.append(bool(first and first.data(RAW_BG)))
            rows.append(row)
        return cls(i18n.tr(title), i18n.tr(subtitle), headers, rows, numeric, shade, landscape=cols >= 8)


def _font_family():
    from PySide6.QtGui import QFontDatabase
    fams = QFontDatabase.families()
    for f in ("IBM Plex Sans Arabic", "Tahoma", "Segoe UI", "DejaVu Sans"):
        if f in fams:
            return f
    return QFont().family()


def make_pdf_printer(path, landscape=False):
    p = QPrinter(QPrinter.HighResolution)
    p.setOutputFormat(QPrinter.PdfFormat)
    p.setOutputFileName(path)
    _page(p, landscape)
    return p


def _page(printer, landscape=False):
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    printer.setPageMargins(QMarginsF(10, 10, 10, 12), QPageLayout.Millimeter)


def render(report, printer, progress=None, cancelled=None):
    """يرسم التقرير على الطابعة (أو PDF). يرجع عدد الصفحات"""
    rtl = i18n.is_rtl()
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(i18n.tr("تعذر فتح الطابعة أو ملف PDF"))
    try:
        return _render(report, printer, painter, rtl, progress, cancelled)
    finally:
        painter.end()


def _render(rep, printer, p, rtl, progress, cancelled):
    page = printer.pageRect(QPrinter.DevicePixel)
    W, H = page.width(), page.height()
    mm = printer.resolution() / 25.4
    fam = _font_family()
    f_body = QFont(fam)
    f_body.setPointSizeF(8.6)
    f_bold = QFont(f_body)
    f_bold.setBold(True)
    f_title = QFont(fam)
    f_title.setPointSizeF(15)
    f_title.setBold(True)
    f_sub = QFont(fam)
    f_sub.setPointSizeF(9)
    fm = QFontMetricsF(f_body, printer)
    fmb = QFontMetricsF(f_bold, printer)
    row_h = fm.height() * 1.55
    pad = 1.6 * mm
    ncol = len(rep.headers)

    # ---- عرض الأعمدة حسب المحتوى (عيّنة من الصفوف) ثم ملاءمة عرض الصفحة
    sample = rep.rows[:300] + rep.rows[-100:]
    want = [fmb.horizontalAdvance(h) + 2 * pad for h in rep.headers]
    for row in sample:
        for c in range(min(ncol, len(row))):
            want[c] = max(want[c], fm.horizontalAdvance(str(row[c])) + 2 * pad)
    want = [min(w, W * 0.45) for w in want]
    total = sum(want)
    if total > W:                    # تقليص الأعمدة النصية الطويلة فقط؛ التاريخ والمرجع والأرقام تبقى كاملة
        for _ in range(6):
            excess = sum(want) - W
            if excess <= 0.5:
                break
            avg = W / ncol
            flex = [c for c in range(ncol) if c not in rep.numeric and want[c] > avg] or \
                   [c for c in range(ncol) if want[c] > avg] or list(range(ncol))
            room = sum(want[c] - min(want[c], avg) for c in flex) or sum(want[c] for c in flex)
            for c in flex:
                share = (want[c] - min(want[c], avg)) if room else want[c]
                want[c] -= min(excess * share / room, want[c] - 8 * mm)
    else:                            # توزيع الفراغ على الأعمدة النصية
        extra = W - total
        flex = [c for c in range(ncol) if c not in rep.numeric] or list(range(ncol))
        for c in flex:
            want[c] += extra / len(flex)
    xs, x = [], (W if rtl else 0)
    for w in want:
        if rtl:
            xs.append((x - w, w))
            x -= w
        else:
            xs.append((x, w))
            x += w

    # ---- رأس الصفحة الأولى: الشعار واسم المحل وبياناته ثم العنوان
    s = settings.get
    info = [x for x in (s("branch_name"), s("shop_address"),
                        (i18n.tr("هاتف: ") + s("shop_phone")) if s("shop_phone") else "",
                        (i18n.tr("الرقم الضريبي: ") + s("tax_number")) if s("tax_number") else "") if x]
    logo = None
    from core import branding
    b64 = branding.logo_b64()
    if b64:
        img = QImage()
        if img.loadFromData(base64.b64decode(b64)):
            logo = img
    head1 = 26 * mm + (8 * mm if rep.subtitle else 0)
    head_n = 9 * mm
    foot = 7 * mm
    first_rows = max(1, int((H - head1 - foot - row_h) // row_h))
    other_rows = max(1, int((H - head_n - foot - row_h) // row_h))
    n = len(rep.rows)
    pages = 1 if n <= first_rows else 1 + -(-(n - first_rows) // other_rows)
    align_text = (Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignVCenter
    align_num = (Qt.AlignLeft if rtl else Qt.AlignRight) | Qt.AlignVCenter
    printed = db.now()[:16]
    shop = s("shop_name") or ""
    p.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)

    def text(rect, flags, t, font, color=None):
        p.setFont(font)
        p.setPen(color or QColor("#101828"))
        p.drawText(rect, flags, t)

    def header_row(y):
        p.fillRect(QRectF(0, y, W, row_h), HEAD_BG)
        for c, (cx, cw) in enumerate(xs):
            t = fmb.elidedText(rep.headers[c], Qt.ElideRight, cw - 2 * pad)
            text(QRectF(cx + pad, y, cw - 2 * pad, row_h), Qt.AlignCenter, t, f_bold)
        p.setPen(QPen(LINE, 0.25 * mm))
        p.drawLine(0, int(y + row_h), W, int(y + row_h))
        return y + row_h

    idx = 0
    for pg in range(pages):
        if cancelled and cancelled():
            raise Cancelled()
        if pg:
            printer.newPage()
        if pg == 0:
            lw = 0
            if logo is not None:
                lh = 18 * mm
                lw = lh * logo.width() / max(1, logo.height())
                lx = 0 if rtl else W - lw
                p.drawImage(QRectF(lx, 0, lw, lh), logo)
            tx = QRectF(0 if not rtl else lw + 3 * mm, 0, W - lw - 3 * mm, 10 * mm)
            text(tx, align_text, shop, f_title)
            text(QRectF(tx.x(), 10 * mm, tx.width(), 7 * mm), align_text, " • ".join(info), f_sub, MUTED)
            p.setPen(QPen(BLUE, 0.6 * mm))
            p.drawLine(0, int(19.5 * mm), W, int(19.5 * mm))
            text(QRectF(0, 20.5 * mm, W, 7 * mm), Qt.AlignCenter, rep.title, f_bold)
            if rep.subtitle:
                text(QRectF(0, 27 * mm, W, 6 * mm), Qt.AlignCenter, rep.subtitle, f_sub, MUTED)
            y, capacity = head1, first_rows
        else:
            text(QRectF(0, 0, W, 7 * mm), align_text, f"{shop} — {rep.title}", f_bold)
            text(QRectF(0, 0, W, 7 * mm), align_num, rep.subtitle, f_sub, MUTED)
            y, capacity = head_n, other_rows
        y = header_row(y)
        p.setFont(f_body)
        for _ in range(capacity):
            if idx >= n:
                break
            row = rep.rows[idx]
            if rep.shade and idx < len(rep.shade) and rep.shade[idx]:
                p.fillRect(QRectF(0, y, W, row_h), SHADE)
            p.setPen(QColor("#101828"))
            for c, (cx, cw) in enumerate(xs):
                v = str(row[c]) if c < len(row) else ""
                if not v:
                    continue
                t = fm.elidedText(v, Qt.ElideRight, cw - 2 * pad)
                p.drawText(QRectF(cx + pad, y, cw - 2 * pad, row_h), align_num if c in rep.numeric else align_text, t)
            y += row_h
            p.setPen(QPen(LINE, 0.12 * mm))
            p.drawLine(0, int(y), W, int(y))
            idx += 1
        foot_t = i18n.tr("صفحة {0} من {1}").format(pg + 1, pages)
        text(QRectF(0, H - foot, W, foot), Qt.AlignCenter, foot_t, f_sub, MUTED)
        text(QRectF(0, H - foot, W, foot), align_text, printed, f_sub, MUTED)
        if progress:
            progress(pg + 1, pages)
    return pages
