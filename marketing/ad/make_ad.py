# -*- coding: utf-8 -*-
"""
صانع الفيديو الإعلاني (بدون برامج مونتاج): يرسم المشاهد بـ Qt، ويولّد الموسيقى ومؤثرات صوتية متزامنة مع كل حركة،
ويصدّر MP4 عبر ffmpeg بعلو صوت -14 LUFS (معيار المنصات).

    pip install PySide6 numpy imageio-ffmpeg
    python marketing/ad/make_ad.py --phone "0599 123 456" --name "اسم برنامجك"

الناتج: ad_vertical.mp4 (1080×1920 لريلز/تيك توك/حالة واتساب) و ad_horizontal.mp4 (1920×1080 ليوتيوب/فيسبوك).
لتغيير النصوص عدّل قائمة SCENES، ولتحديث اللقطات شغّل capture_shots.py (أو ضع صوراً بنفس الأسماء في مجلد shots).
"""

import argparse
import math
import os
import subprocess
import sys
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np  # noqa: E402
from PySide6.QtCore import QRectF, Qt, QPointF  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,  # noqa: E402
                           QPen, QPixmap, QRadialGradient)

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
FPS = 30
BPM = 112
BAR = 4 * 60 / BPM  # ثانيتان وربع تقريباً

NAVY, NAVY2 = QColor("#0B1224"), QColor("#1E3A8A")
WHITE, MUTED = QColor("#FFFFFF"), QColor("#CBD5E1")
GREEN, BLUE, AMBER, RED = QColor("#22C55E"), QColor("#3B82F6"), QColor("#F59E0B"), QColor("#EF4444")
HEAD_FONT = BODY_FONT = "IBM Plex Sans Arabic"      # نفس خط البرنامج (مضمَّن في ui/fonts)

# (المدة بالمقاطع الموسيقية، نوع المشهد، بيانات)
SCENES = [
    (2, "hook", {"lines": ["لسّا بتحسب على الورقة؟", "ودفتر الديون كل يوم أثقل؟"]}),
    (2, "brand", {}),
    (2, "shot", {"img": "pos.png", "crop": (0, 0, 1140, 886), "title": "بيع بالباركود في ثانية",
                 "sub": "كرتونة وحبّة • ميزان • عروض تلقائية • تنبيه الصلاحية"}),
    (2, "card", {"title": "كل طرق الدفع في شاشة واحدة",
                 "sub": "نقدي • بطاقة • محافظ إلكترونية وتطبيقات بنوك برمز QR"}),
    (2, "shot", {"img": "customers.png", "crop": (0, 80, 1140, 806), "title": "دفتر الديون… صار ذكي",
                 "sub": "رصيد كل زبون • حد دين • تذكير واتساب بضغطة"}),
    (2, "shot", {"img": "dashboard.png", "crop": (0, 80, 1140, 720), "title": "اعرف ربحك الحقيقي كل يوم",
                 "sub": "المبيعات • الربح • الصندوق • المخزون — بنظرة واحدة"}),
    (2, "shot", {"img": "audit.png", "crop": (0, 80, 1140, 806), "title": "مدقق مالي داخل برنامجك",
                 "sub": "37 فحصاً لكل العمليات • يكشف العجز والتلاعب • رأي ودرجة"}),
    (2, "shot", {"img": "smart_ask.png", "crop": (0, 80, 1140, 806), "title": "اسأل محلك… بلهجتك",
                 "sub": "كم ربحت؟ مين عليه دين؟ شو رح يخلص؟ — الجواب فوراً وبدون إنترنت"}),
    (2, "shot", {"img": "seasons.png", "crop": (0, 80, 1140, 806), "title": "جاهز لرمضان قبل الكل",
                 "sub": "تقويم هجري • كم تطلب من كل صنف • ومتى تطلب"}),
    (2, "phones", {"title": "محلك في جيبك",
                   "sub": "لوحة المالك • متجر أونلاين بلا عمولة • جرد بالكاميرا"}),
    (2, "grid", {"title": "وكمان…", "items": ["تنبؤ بالمبيعات والسيولة", "حاسبة الزكاة", "تقرير لكل الفروع",
                                             "رواتب وأقساط", "وضع داكن وشعار محلك", "عربي و English"]}),
    (3, "cta", {}),
]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def font(family, px, bold=True):
    f = QFont(family)
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


class Renderer:
    def __init__(self, w, h, name, phone):
        self.W, self.H, self.name, self.phone = w, h, name, phone
        self.portrait = h > w
        self.s = min(w, h) / 1080  # معامل الحجم
        self.img = {}
        for f in os.listdir(SHOTS):
            if f.endswith(".png"):
                self.img[f] = QPixmap(os.path.join(SHOTS, f))

    # ------------------------------------------------------------------ أدوات
    def text(self, p, rect, txt, fam, px, color, align=Qt.AlignCenter, alpha=1.0, bold=True):
        p.save()
        p.setOpacity(p.opacity() * alpha)
        size = px * self.s
        flags = int(align | Qt.TextWordWrap)
        while size > 12:
            f = font(fam, size, bold)
            br = QFontMetrics(f).boundingRect(rect.toRect(), flags, txt)
            if br.height() <= rect.height() and br.width() <= rect.width():
                break
            size *= 0.94
        p.setFont(font(fam, size, bold))
        p.setPen(color)
        p.drawText(rect, flags, txt)
        p.restore()

    def card_img(self, p, pm, crop, target, radius=22, zoom=1.0):
        """صورة بإطار دائري وظل؛ zoom لتأثير كين بيرنز"""
        x, y, w, h = crop
        src = QRectF(x, y, w, h)
        if zoom != 1.0:
            cw, ch = w / zoom, h / zoom
            src = QRectF(x + (w - cw) / 2, y + (h - ch) / 2, cw, ch)
        p.save()
        for i in range(6):  # ظل ناعم
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 22))
            p.drawRoundedRect(target.adjusted(-i * 3, -i * 3 + 10, i * 3, i * 3 + 14), radius + i * 3, radius + i * 3)
        path = QPainterPath()
        path.addRoundedRect(target, radius, radius)
        p.setClipPath(path)
        p.drawPixmap(target, pm, src)
        p.restore()

    def fit(self, cw, ch, box):
        k = min(box.width() / cw, box.height() / ch)
        w, h = cw * k, ch * k
        return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)

    def background(self, p, t):
        g = QLinearGradient(0, 0, self.W * 0.3, self.H)
        g.setColorAt(0, NAVY)
        g.setColorAt(1, NAVY2)
        p.fillRect(0, 0, self.W, self.H, g)
        for i, (cx, cy, r, col) in enumerate(((0.15, 0.2, 0.55, "#2563EB"), (0.9, 0.75, 0.6, "#16A34A"),
                                              (0.5, 1.0, 0.5, "#7C3AED"))):
            x = (cx + 0.06 * math.sin(t * 0.4 + i * 2)) * self.W
            y = (cy + 0.05 * math.cos(t * 0.33 + i)) * self.H
            rad = r * max(self.W, self.H) * 0.6
            rg = QRadialGradient(QPointF(x, y), rad)
            c = QColor(col)
            c.setAlpha(70)
            rg.setColorAt(0, c)
            c.setAlpha(0)
            rg.setColorAt(1, c)
            p.fillRect(0, 0, self.W, self.H, rg)

    def layout(self):
        """مناطق النص والصورة حسب اتجاه الفيديو"""
        W, H, s = self.W, self.H, self.s
        if self.portrait:
            return (QRectF(50, 150 * s, W - 100, 210 * s), QRectF(80, 370 * s, W - 160, 150 * s),
                    QRectF(40, 580 * s, W - 80, H - 580 * s - 200 * s), Qt.AlignHCenter | Qt.AlignVCenter)
        return (QRectF(W * 0.56, H * 0.30, W * 0.40, 170 * s), QRectF(W * 0.56, H * 0.30 + 190 * s, W * 0.40, 220 * s),
                QRectF(W * 0.04, H * 0.08, W * 0.50, H * 0.84), Qt.AlignRight | Qt.AlignVCenter)

    def titles(self, p, t, d):
        tr, sr, _, al = self.layout()
        a = ease(t / 0.5)
        p.save()
        p.translate(0, (1 - a) * 40 * self.s)
        self.text(p, tr, d["title"], HEAD_FONT, 70 if self.portrait else 64, WHITE, al, a)
        p.restore()
        b = ease((t - 0.35) / 0.5)
        p.save()
        p.translate(0, (1 - b) * 30 * self.s)
        self.text(p, sr, d["sub"], BODY_FONT, 38 if self.portrait else 33, MUTED, al, b, bold=False)
        p.restore()

    def footer(self, p):
        self.text(p, QRectF(0, self.H - 120 * self.s, self.W, 80 * self.s), self.name, BODY_FONT, 30, MUTED,
                  Qt.AlignCenter, 0.8)

    def phone_frame(self, p, pm, rect, angle=0.0):
        p.save()
        p.translate(rect.center())
        p.rotate(angle)
        r = QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height())
        rad = rect.width() * 0.12
        for i in range(6):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 25))
            p.drawRoundedRect(r.adjusted(-i * 3, -i * 3 + 14, i * 3, i * 3 + 18), rad, rad)
        p.setBrush(QColor("#111827"))
        p.drawRoundedRect(r, rad, rad)
        inner = r.adjusted(rect.width() * 0.04, rect.width() * 0.04, -rect.width() * 0.04, -rect.width() * 0.04)
        path = QPainterPath()
        path.addRoundedRect(inner, rad * 0.75, rad * 0.75)
        p.setClipPath(path)
        src_h = pm.width() * inner.height() / inner.width()
        p.drawPixmap(inner, pm, QRectF(0, 0, pm.width(), min(src_h, pm.height())))
        p.restore()

    # ------------------------------------------------------------------ المشاهد
    def scene_hook(self, p, t, dur, d):
        W, H, s = self.W, self.H, self.s
        for i, line in enumerate(d["lines"]):
            a = ease((t - 0.2 - i * 1.3) / 0.6)
            col = WHITE if i == 0 else AMBER
            y = H / 2 - 330 * s + i * 340 * s if self.portrait else H / 2 - 230 * s + i * 230 * s
            p.save()
            p.translate(0, (1 - a) * 50 * s)
            self.text(p, QRectF(60, y, W - 120, 300 * s if self.portrait else 200 * s), line, HEAD_FONT, 88, col,
                      Qt.AlignCenter, a)
            p.restore()

    def scene_brand(self, p, t, dur, d):
        W, H, s = self.W, self.H, self.s
        a = ease(t / 0.6)
        size = 190 * s * (0.6 + 0.4 * a)
        c = QPointF(W / 2, H / 2 - 230 * s)
        p.save()
        p.setOpacity(a)
        g = QLinearGradient(c.x() - size, c.y() - size, c.x() + size, c.y() + size)
        g.setColorAt(0, BLUE)
        g.setColorAt(1, GREEN)
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(c.x() - size / 2, c.y() - size / 2, size, size), size * 0.24, size * 0.24)
        self.text(p, QRectF(c.x() - size / 2, c.y() - size / 2, size, size), "POS", "DejaVu Sans", 64 * (size / (190 * s)),
                  WHITE)
        p.restore()
        b = ease((t - 0.4) / 0.6)
        self.text(p, QRectF(40, H / 2 - 60 * s, W - 80, 200 * s), self.name, HEAD_FONT, 72, WHITE, Qt.AlignCenter, b)
        c2 = ease((t - 0.9) / 0.6)
        self.text(p, QRectF(40, H / 2 + 150 * s, W - 80, 140 * s), "للدكاكين والسوبرماركت والمحلات الصغيرة",
                  BODY_FONT, 40, MUTED, Qt.AlignCenter, c2, bold=False)

    def scene_shot(self, p, t, dur, d):
        _, _, ir, _ = self.layout()
        pm = self.img[d["img"]]
        x, y, w, h = d["crop"]
        a = ease((t - 0.15) / 0.6)
        crop, zoom = d["crop"], 1.0 + 0.06 * (t / dur)
        target = self.fit(w, h, ir)
        if self.portrait:  # تكبير الصورة مع حركة أفقية بطيئة من اليمين لليسار
            k = min(ir.height() * 0.9 / h, ir.width() / (0.62 * w))
            vis = min(w, ir.width() / k)
            pan = 0.5 - 0.5 * math.cos(math.pi * min(1, max(0, (t - 0.6) / (dur - 1.2))))
            crop = (x + (w - vis) * (1 - pan), y, vis, h)
            target = QRectF(ir.center().x() - vis * k / 2, ir.center().y() - h * k / 2, vis * k, h * k)
            zoom = 1.0
        p.save()
        p.setOpacity(a)
        p.translate(0, (1 - a) * 80 * self.s)
        self.card_img(p, pm, crop, target, 22 * self.s, zoom=zoom)
        p.restore()
        self.titles(p, t, d)

    def scene_card(self, p, t, dur, d):
        _, _, ir, _ = self.layout()
        pay, term = self.img["payment.png"], self.img["wallet_pay.png"]
        a = ease((t - 0.15) / 0.6)
        box = QRectF(ir.x(), ir.y(), ir.width() * 0.62, ir.height())
        tgt = self.fit(pay.width(), pay.height(), box.adjusted(0, 0, 0, -ir.height() * 0.05))
        tgt.moveCenter(QPointF(ir.center().x() + ir.width() * 0.12, ir.center().y()))
        p.save()
        p.setOpacity(a)
        p.translate(0, (1 - a) * 80 * self.s)
        self.card_img(p, pay, (0, 0, pay.width(), pay.height()), tgt, 22 * self.s)
        p.restore()
        b = ease((t - 1.0) / 0.5)
        th = tgt.height() * 0.78
        tw = th * term.width() / term.height()
        tt = QRectF(ir.center().x() - ir.width() * 0.47, tgt.bottom() - th - ir.height() * 0.02, tw, th)
        p.save()
        p.setOpacity(b)
        p.translate(-(1 - b) * 120 * self.s, 0)
        self.card_img(p, term, (0, 0, term.width(), term.height()), tt, 20 * self.s)
        p.restore()
        # ختم «موافقة»
        c = ease((t - 2.2) / 0.35)
        if c > 0:
            p.save()
            r = 60 * self.s * (1.6 - 0.6 * c)
            ctr = QPointF(tt.left() + 10 * self.s, tt.top() + 10 * self.s)
            p.setOpacity(c)
            p.setBrush(GREEN)
            p.setPen(QPen(WHITE, 6 * self.s))
            p.drawEllipse(ctr, r, r)
            self.text(p, QRectF(ctr.x() - r, ctr.y() - r, 2 * r, 2 * r), "✓", "DejaVu Sans", 70 * (r / (60 * self.s)), WHITE)
            p.restore()
        self.titles(p, t, d)

    def scene_phones(self, p, t, dur, d):
        _, _, ir, _ = self.layout()
        names = ["phone_staff.png", "phone_owner.png", "phone_shop.png"]
        ph = ir.height() * (0.86 if self.portrait else 0.8)
        pw = ph * 0.47
        offs = [-0.95, 0, 0.95]
        angs = [-7, 0, 7]
        order = [0, 2, 1]  # الأوسط فوق
        for k in order:
            a = ease((t - 0.2 - abs(offs[k]) * 0.35) / 0.6)
            cx = ir.center().x() + offs[k] * pw * (0.9 if self.portrait else 0.8) * a
            cy = ir.center().y() + (0 if k == 1 else ph * 0.05) + (1 - a) * 200 * self.s
            sc = 1.0 if k == 1 else 0.9
            rect = QRectF(cx - pw * sc / 2, cy - ph * sc / 2, pw * sc, ph * sc)
            p.save()
            p.setOpacity(min(1, a * 1.5))
            self.phone_frame(p, self.img[names[k]], rect, angs[k] * a)
            p.restore()
        self.titles(p, t, d)

    def scene_grid(self, p, t, dur, d):
        W, H, s = self.W, self.H, self.s
        a = ease(t / 0.5)
        self.text(p, QRectF(40, (380 if self.portrait else 90) * s, W - 80, 150 * s), d["title"], HEAD_FONT, 76, WHITE,
                  Qt.AlignCenter, a)
        cols = 2 if self.portrait else 3
        rows = math.ceil(len(d["items"]) / cols)
        gw = W - 140 if self.portrait else W * 0.8
        gh = 230 * s
        gap = 30 * s
        top = (590 if self.portrait else 290) * s
        left = (W - gw) / 2
        cw = (gw - gap * (cols - 1)) / cols
        colors = [BLUE, GREEN, QColor("#8B5CF6"), AMBER, QColor("#06B6D4"), QColor("#EC4899")]
        for i, item in enumerate(d["items"]):
            r, c = divmod(i, cols)
            b = ease((t - 0.3 - i * 0.22) / 0.45)
            x = W - left - (c + 1) * cw - c * gap  # من اليمين لليسار
            rect = QRectF(x, top + r * (gh + gap), cw, gh)
            p.save()
            p.setOpacity(b)
            p.translate(rect.center())
            p.scale(0.85 + 0.15 * b, 0.85 + 0.15 * b)
            p.translate(-rect.center())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 28))
            p.drawRoundedRect(rect, 28 * s, 28 * s)
            p.setBrush(colors[i % len(colors)])
            p.drawRoundedRect(QRectF(rect.right() - 16 * s, rect.top() + 30 * s, 8 * s, rect.height() - 60 * s), 4, 4)
            self.text(p, rect.adjusted(30 * s, 10, -40 * s, -10), item, HEAD_FONT, 44, WHITE)
            p.restore()
        _ = rows

    def scene_cta(self, p, t, dur, d):
        W, H, s = self.W, self.H, self.s
        a = ease(t / 0.5)
        p.save()
        p.translate(0, (1 - a) * 40 * s)
        self.text(p, QRectF(40, H / 2 - 420 * s, W - 80, 180 * s), "أول شهر ماكس مجاناً", HEAD_FONT, 110, WHITE, Qt.AlignCenter, a)
        p.restore()
        b = ease((t - 0.3) / 0.5)
        pulse = 1 + 0.04 * math.sin(t * 6) * (b >= 1)
        bw, bh = min(W - 160, 820 * s) * pulse, 170 * s * pulse
        br = QRectF(W / 2 - bw / 2, H / 2 - 200 * s, bw, bh)
        p.save()
        p.setOpacity(b)
        p.setPen(Qt.NoPen)
        p.setBrush(GREEN)
        p.drawRoundedRect(br, bh / 2, bh / 2)
        self.text(p, br, "ثم مجاني للأبد", HEAD_FONT, 64, WHITE)
        p.restore()
        c = ease((t - 0.8) / 0.5)
        self.text(p, QRectF(40, H / 2 + 20 * s, W - 80, 120 * s), "البيع لا يتوقف أبداً • تركيب وتدريب • دعم بالعربي", BODY_FONT,
                  42, MUTED, Qt.AlignCenter, c, bold=False)
        e = ease((t - 1.3) / 0.5)
        contact = f"واتساب: {self.phone}" if self.phone else "راسلنا على واتساب الآن"
        self.text(p, QRectF(40, H / 2 + 170 * s, W - 80, 140 * s), contact, HEAD_FONT, 60, AMBER, Qt.AlignCenter, e)
        self.text(p, QRectF(40, H / 2 + 330 * s, W - 80, 120 * s), self.name, BODY_FONT, 36, WHITE, Qt.AlignCenter, e)
        if getattr(self, "company", ""):
            self.text(p, QRectF(40, H / 2 + 420 * s, W - 80, 100 * s), self.company, BODY_FONT, 32, MUTED, Qt.AlignCenter, e,
                      bold=False)

    # ------------------------------------------------------------------ الإطار
    def frame(self, t):
        img = QImage(self.W, self.H, QImage.Format_RGB888)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.background(p, t)
        start = 0.0
        for bars, kind, d in SCENES:
            dur = bars * BAR
            if start <= t < start + dur:
                lt = t - start
                fade = min(1.0, (dur - lt) / 0.3)
                p.setOpacity(max(0.0, fade))
                getattr(self, "scene_" + kind)(p, lt, dur, d)
                p.setOpacity(1.0)
                if kind not in ("brand", "cta", "hook"):
                    self.footer(p)
                break
            start += dur
        p.end()
        return img


def total_duration():
    return sum(b for b, _, _ in SCENES) * BAR


# ---------------------------------------------------------------------- الموسيقى
def note(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def make_music(path, dur, sr=44100):
    N = int(dur * sr)
    out = np.zeros(N)
    beat = 60 / BPM
    prog = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
    tt = np.arange(N) / sr
    drums_from = SCENES[0][0] * BAR
    nbars = int(math.ceil(dur / BAR))
    for b in range(nbars):
        chord = prog[b % 4]
        s0 = int(b * BAR * sr)
        s1 = min(N, int((b + 1) * BAR * sr))
        seg = tt[s0:s1] - b * BAR
        env = np.minimum(1, seg / 0.25) * np.exp(-seg * 0.25)
        pad = sum(np.sin(2 * np.pi * note(n) * seg) + 0.3 * np.sin(4 * np.pi * note(n) * seg) for n in chord)
        out[s0:s1] += 0.045 * pad * env
        for k in range(8):  # أربيجيو ثُمنيات
            n = chord[[0, 1, 2, 1][k % 4]] + 12 + (12 if k % 4 == 2 else 0)
            a0 = s0 + int(k * beat / 2 * sr)
            L = min(N - a0, int(0.35 * sr))
            if L <= 0:
                continue
            x = np.arange(L) / sr
            out[a0:a0 + L] += 0.09 * (np.sin(2 * np.pi * note(n) * x) + 0.25 * np.sin(4 * np.pi * note(n) * x)) * np.exp(-x * 9)
        if b * BAR >= drums_from - 0.01:
            for k in range(4):
                a0 = s0 + int(k * beat * sr)
                L = min(N - a0, int(0.3 * sr))
                x = np.arange(L) / sr
                f = 45 + 80 * np.exp(-x * 30)
                out[a0:a0 + L] += 0.5 * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-x * 12)
                bl = min(N - a0, int(beat * sr))
                xb = np.arange(bl) / sr
                out[a0:a0 + bl] += 0.14 * np.tanh(2 * np.sin(2 * np.pi * note(chord[0] - 24) * xb)) * np.exp(-xb * 3)
                h0 = a0 + int(beat / 2 * sr)
                hl = min(N - h0, int(0.05 * sr))
                if hl > 0:
                    nz = np.diff(np.random.default_rng(k + b).standard_normal(hl + 1))
                    out[h0:h0 + hl] += 0.035 * nz * np.exp(-np.arange(hl) / sr * 60)
    fade_in = np.minimum(1, tt / 0.8)
    fade_out = np.clip((dur - tt) / 2.5, 0, 1)
    out *= fade_in * fade_out
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.7
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------- المؤثرات الصوتية
PENTA = [880.0, 1046.5, 1174.7, 1318.5, 1568.0, 1760.0]   # سلّم لا الصغير الخماسي (نفس مقام الموسيقى)


def cue_sheet(portrait):
    """توقيت كل صوت مطابق لتوقيت حركة العنصر في دوال المشاهد، وموضعه يمين/يسار حسب مكانه على الشاشة.
    [(ثانية، الصوت، pan، تعديل dB، معامل إضافي)]"""
    txt = 0.0 if portrait else 0.5          # في الأفقي: النص يميناً والصورة يساراً
    img = 0.0 if portrait else -0.45
    c = []
    start = 0.0
    for idx, (bars, kind, d) in enumerate(SCENES):
        S, D = start, bars * BAR
        if kind == "hook":
            for i in range(len(d["lines"])):
                t = S + 0.2 + i * 1.3
                c += [(t - 0.06, "whoosh_up", 0.0, -2),
                      (t + 0.1, "impact", 0.0, -8) if i == 0 else (t + 0.1, "thump", 0.0, -2)]
                if i:
                    c.append((t + 0.14, "tick", 0.0))
        elif kind == "brand":
            c += [(S - 1.25, "riser", 0.0), (S, "impact", 0.0), (S + 0.12, "shimmer", 0.0),
                  (S + 0.38, "whoosh_text", 0.0), (S + 0.88, "tick", 0.0, -3)]
        elif kind in ("shot", "card", "phones"):
            c += [(S - 0.02, "whoosh_text", txt), (S + 0.33, "tick", txt, -3)]
            if kind == "shot":
                c += [(S + 0.12, "whoosh_img", img), (S + 0.32, "thump", img, -9)]
                if portrait:
                    c.append((S + 0.6, "drift", 0.0, 0, D - 1.2))
            elif kind == "card":
                wal = -0.25 if portrait else -0.75
                c += [(S + 0.12, "whoosh_img", img + 0.1), (S + 0.32, "thump", img + 0.1, -9),
                      (S + 0.98, "swipe", wal), (S + 1.15, "thump", wal, -12),
                      (S + 2.2, "pop", wal, -3, 1318.5), (S + 2.22, "success", wal)]
            else:
                side = 0.5 if portrait else 0.3
                c += [(S + 0.18, "whoosh_up", img), (S + 0.5, "swipe", img - side), (S + 0.55, "swipe", img + side)]
        elif kind == "grid":
            cols = 2 if portrait else 3
            c.append((S - 0.02, "whoosh_text", 0.0))
            for i in range(len(d["items"])):
                col = i % cols
                pan = (0.3 - 0.6 * col) if portrait else (0.5 - 0.5 * col)
                c.append((S + 0.3 + i * 0.22, "pop", pan, 0, PENTA[i % len(PENTA)]))
        elif kind == "cta":
            c += [(S, "impact", 0.0, -7), (S + 0.02, "whoosh_text", 0.0), (S + 0.3, "pop", 0.0, 0, 1046.5),
                  (S + 0.33, "chime", 0.0), (S + 0.8, "tick", 0.0), (S + 1.3, "ping", 0.0), (S + 1.36, "shimmer", 0.0, -3)]
        # انتقال: صوت يتصاعد حتى لحظة القطع (إلا قبل الشعار: يسبقه riser)
        if idx < len(SCENES) - 1 and SCENES[idx + 1][1] != "brand":
            c.append((S + D - 0.45, "transition", 0.0))
        start += D
    return c


def make_audio(music_path, out_path, portrait):
    import sfx
    dur = total_duration()
    m = sfx.read_wav_mono(music_path)
    n = int(dur * sfx.SR)
    m = np.pad(m, (0, max(0, n - len(m))))[:n]
    effects = sfx.render(cue_sheet(portrait), dur)
    music = np.vstack([m, m]) * 0.75
    sfx.write_wav(out_path, sfx.duck(music, effects) + effects)


def load_fonts():
    from PySide6.QtGui import QFontDatabase
    d = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ui", "fonts")
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(d, f))


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def render(w, h, out, name, phone, music, still_dir=None):
    r = Renderer(w, h, name, phone)
    dur = total_duration()
    n = int(dur * FPS)
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(FPS), "-i", "-", "-i", music, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        img = r.frame(i / FPS)
        proc.stdin.write(bytes(img.constBits())[: w * h * 3])
        if still_dir and i % (FPS * 2) == 0:
            img.save(os.path.join(still_dir, f"{os.path.basename(out)}_{i // FPS:02d}s.jpg"), quality=80)
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed")
    print("✓", out, f"{dur:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="برنامج المحاسبة ونقاط البيع")
    ap.add_argument("--phone", default="", help="رقم واتساب يظهر في آخر الإعلان")
    ap.add_argument("--company", default="", help="اسم الشركة تحت اسم البرنامج في آخر الإعلان")
    ap.add_argument("--out", default=HERE)
    ap.add_argument("--only", choices=["vertical", "horizontal"])
    ap.add_argument("--stills", help="مجلد لحفظ لقطات للمراجعة")
    ap.add_argument("--preview", help="ثوانٍ مفصولة بفواصل: يحفظ إطارات فقط بدون فيديو، مثل 2,10,16")
    a = ap.parse_args()
    Renderer.company = a.company
    QGuiApplication(sys.argv)
    load_fonts()
    sys.path.insert(0, HERE)
    if a.preview:
        for w, h, tag in ((1080, 1920, "v"), (1920, 1080, "h")):
            r = Renderer(w, h, a.name, a.phone)
            for sec in a.preview.split(","):
                r.frame(float(sec)).save(os.path.join(a.out, f"preview_{tag}_{float(sec):04.1f}.jpg"), quality=80)
        return
    music = os.path.join(a.out, "music.wav")
    make_music(music, total_duration())
    for w, h, name in ((1080, 1920, "vertical"), (1920, 1080, "horizontal")):
        if a.only and a.only != name:
            continue
        mix = os.path.join(a.out, f"mix_{name}.wav")
        make_audio(music, mix, h > w)
        render(w, h, os.path.join(a.out, f"ad_{name}.mp4"), a.name, a.phone, mix, a.stills)


if __name__ == "__main__":
    main()
