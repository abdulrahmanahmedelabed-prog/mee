# -*- coding: utf-8 -*-
"""
إنفوجرافيك البرنامج بنفس هوية الإعلان (خط البرنامج وألوانه)، بثلاثة مقاسات:

    python marketing/infographic/make_infographic.py --phone "0599 123 456"

post.png (1080×1350 منشور فيسبوك/إنستغرام)، story.png (1080×1920 حالة واتساب/ستوري)، flyer_a4.png (A4 للطباعة 300dpi).
اللقطات من marketing/ad/shots (تُحدَّث بـ capture_shots.py).
"""

import argparse
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QGuiApplication, QImage, QLinearGradient,  # noqa: E402
                           QPainter, QPainterPath, QPixmap, QRadialGradient)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SHOTS = os.path.join(ROOT, "marketing", "ad", "shots")
FONT = "IBM Plex Sans Arabic"
NAVY, NAVY2 = QColor("#0B1224"), QColor("#1E3A8A")
WHITE, MUTED = QColor("#FFFFFF"), QColor("#CBD5E1")
GREEN, AMBER = QColor("#22C55E"), QColor("#F59E0B")

STATS = [("30", "إجراء تدقيق مالي\nعلى كل العمليات"), ("0.02", "ثانية لحفظ الفاتورة\nمع 20 كاشيراً معاً"),
         ("3", "سنوات من البيانات\nوكل تقرير في ثانية")]
FEATURES = [
    ("🧾", "#3B82F6", "بيع سريع", "باركود • ميزان • كرتونة وحبّة"),
    ("📲", "#8B5CF6", "كل طرق الدفع", "نقدي • بطاقة • محافظ وتطبيقات بنوك"),
    ("📒", "#F59E0B", "دفتر ديون ذكي", "حد دين • شيكات • تذكير واتساب"),
    ("💰", "#22C55E", "ربحك الحقيقي", "يومي • شهري • سنوي • ميزانية"),
    ("🔎", "#EF4444", "مدقق مالي داخلي", "يكشف العجز والتلاعب برأي ودرجة"),
    ("🤖", "#06B6D4", "مستشار ذكي", "ينبّهك قبل النفاد والخسارة"),
    ("📱", "#EC4899", "محلك في جيبك", "تطبيق جوال • متجر أونلاين"),
    ("📶", "#64748B", "بدون إنترنت", "البيع لا يتوقف أبداً"),
]


def font(px, bold=True):
    f = QFont(FONT)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(QFont.Bold if bold else QFont.Normal)
    return f


def text(p, rect, s, px, color, align=Qt.AlignCenter, bold=True):
    flags = int(align | Qt.TextWordWrap)
    size = px
    while size > 8:
        br = QFontMetrics(font(size, bold)).boundingRect(rect.toRect(), flags, s)
        if br.height() <= rect.height() and br.width() <= rect.width():
            break
        size *= 0.95
    p.setFont(font(size, bold))
    p.setPen(color)
    p.drawText(rect, flags, s)


def rounded_shadow(p, r, radius, alpha=26, depth=6):
    for i in range(depth):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, alpha))
        p.drawRoundedRect(r.adjusted(-i * 2, -i * 2 + 8, i * 2, i * 2 + 12), radius + i * 2, radius + i * 2)


def shot(p, name, crop, target, radius):
    pm = QPixmap(os.path.join(SHOTS, name))
    rounded_shadow(p, target, radius)
    path = QPainterPath()
    path.addRoundedRect(target, radius, radius)
    p.save()
    p.setClipPath(path)
    p.drawPixmap(target, pm, QRectF(*crop))
    p.restore()


def background(p, W, H):
    g = QLinearGradient(0, 0, W * 0.3, H)
    g.setColorAt(0, NAVY)
    g.setColorAt(1, NAVY2)
    p.fillRect(0, 0, W, H, g)
    for cx, cy, r, col in ((0.1, 0.12, 0.7, "#2563EB"), (0.95, 0.6, 0.7, "#16A34A"), (0.4, 1.0, 0.6, "#7C3AED")):
        rg = QRadialGradient(QPointF(cx * W, cy * H), r * max(W, H) * 0.6)
        c = QColor(col)
        c.setAlpha(60)
        rg.setColorAt(0, c)
        c.setAlpha(0)
        rg.setColorAt(1, c)
        p.fillRect(0, 0, W, H, rg)


def draw(W, H, name, phone, out):
    img = QImage(W, H, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    p.setLayoutDirection(Qt.RightToLeft)
    background(p, W, H)
    s = W / 1080
    tall = H / W
    m = 56 * s
    y = 60 * s

    # الشعار والاسم
    tile = QRectF(W - m - 110 * s, y, 110 * s, 110 * s)
    g = QLinearGradient(tile.topLeft(), tile.bottomRight())
    g.setColorAt(0, QColor("#3B82F6"))
    g.setColorAt(1, GREEN)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(tile, 28 * s, 28 * s)
    text(p, tile, "POS", 40 * s, WHITE)
    text(p, QRectF(m, y + 4 * s, W - 2 * m - 140 * s, 60 * s), name, 50 * s, WHITE, Qt.AlignRight | Qt.AlignVCenter)
    text(p, QRectF(m, y + 64 * s, W - 2 * m - 140 * s, 44 * s), "للدكاكين والسوبرماركت والمحلات — يعمل بدون إنترنت",
         28 * s, MUTED, Qt.AlignRight | Qt.AlignVCenter, bold=False)
    y += 150 * s

    # العنوان
    head_h = (150 if tall > 1.5 else 120) * s
    text(p, QRectF(m, y, W - 2 * m, head_h), "كل حسابات محلك… في برنامج واحد", (74 if tall > 1.5 else 64) * s, WHITE)
    y += head_h + 10 * s

    # توزيع المساحة: المزايا بارتفاع مريح أولاً، وما يبقى للقطة البرنامج
    features = FEATURES if tall > 1.5 else FEATURES[:6]
    gap = 20 * s
    sh = (170 if tall > 1.5 else 140) * s
    footer_h = 190 * s
    rows = (len(features) + 1) // 2
    fh_want = (130 if tall > 1.5 else 108) * s
    shot_h = H - y - 40 * s - sh - 34 * s - rows * fh_want - (rows - 1) * gap - footer_h - 30 * s
    shot_h = max(120 * s, min(shot_h, H * 0.3))
    sw = shot_h * 1140 / 806
    if sw > W - 2 * m:
        sw = W - 2 * m
        shot_h = sw * 806 / 1140
    shot(p, "dashboard.png", (0, 80, 1140, 806), QRectF((W - sw) / 2, y, sw, shot_h), 22 * s)
    y += shot_h + 40 * s

    # أرقام
    cw = (W - 2 * m - 2 * gap) / 3
    for i, (num, label) in enumerate(STATS):
        r = QRectF(W - m - (i + 1) * cw - i * gap, y, cw, sh)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRoundedRect(r, 26 * s, 26 * s)
        text(p, QRectF(r.x(), r.y() + 10 * s, r.width(), sh * 0.45), num, 64 * s, AMBER)
        text(p, QRectF(r.x() + 10 * s, r.y() + sh * 0.5, r.width() - 20 * s, sh * 0.44), label, 24 * s, MUTED, bold=False)
    y += sh + 34 * s

    # المزايا
    cols = 2
    avail = H - y - footer_h - 30 * s
    fh = min(150 * s, (avail - (rows - 1) * gap) / rows)
    fw = (W - 2 * m - gap) / cols
    for i, (icon, color, title_, sub) in enumerate(features):
        r_, c_ = divmod(i, cols)
        r = QRectF(W - m - (c_ + 1) * fw - c_ * gap, y + r_ * (fh + gap), fw, fh)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(r, 24 * s, 24 * s)
        ic = min(fh - 36 * s, 84 * s)
        ir = QRectF(r.right() - 20 * s - ic, r.center().y() - ic / 2, ic, ic)
        col = QColor(color)
        col.setAlpha(60)
        p.setBrush(col)
        p.drawRoundedRect(ir, ic * 0.28, ic * 0.28)
        text(p, ir, icon, ic * 0.5, WHITE)
        tx = QRectF(r.x() + 18 * s, r.y() + 10 * s, r.width() - ic - 54 * s, r.height() * 0.5)
        text(p, tx, title_, 34 * s, WHITE, Qt.AlignRight | Qt.AlignBottom)
        text(p, QRectF(tx.x(), r.center().y() + 4 * s, tx.width(), r.height() * 0.42), sub, 23 * s, MUTED,
             Qt.AlignRight | Qt.AlignTop, bold=False)

    # الدعوة
    fy = H - footer_h - 10 * s
    bw, bh = W - 2 * m, 104 * s
    br = QRectF(m, fy, bw, bh)
    p.setBrush(GREEN)
    p.drawRoundedRect(br, bh / 2, bh / 2)
    text(p, br.adjusted(20 * s, 0, -20 * s, 0), "جرّبه مجاناً 30 يوماً بكل المزايا", 44 * s, WHITE)
    contact = f"واتساب: {phone}" if phone else "تركيب وتدريب لموظفيك • دعم بالعربي"
    text(p, QRectF(m, fy + bh + 14 * s, bw, 60 * s), contact, 34 * s, AMBER if phone else MUTED, bold=bool(phone))
    p.end()
    img.save(out)
    print("✓", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="برنامج المحاسبة ونقاط البيع")
    ap.add_argument("--phone", default="")
    ap.add_argument("--out", default=HERE)
    a = ap.parse_args()
    QGuiApplication(sys.argv)
    fd = os.path.join(ROOT, "ui", "fonts")
    for f in os.listdir(fd):
        if f.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fd, f))
    draw(1080, 1350, a.name, a.phone, os.path.join(a.out, "post.png"))
    draw(1080, 1920, a.name, a.phone, os.path.join(a.out, "story.png"))
    draw(2480, 3508, a.name, a.phone, os.path.join(a.out, "flyer_a4.png"))


if __name__ == "__main__":
    main()
