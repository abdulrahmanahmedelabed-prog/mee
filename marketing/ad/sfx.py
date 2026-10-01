# -*- coding: utf-8 -*-
"""
مؤثرات صوتية مولَّدة بالكامل (بلا ملفات ولا حقوق): whoosh، pop، tick، impact، riser، chime...
ومازج يضعها على الموسيقى بتوقيت كل حركة، مع توزيع ستيريو حسب مكان العنصر وخفض الموسيقى تحتها (ducking).

مبادئ تصميم صوت الموشن المتبعة:
- الصوت يبدأ مع بداية الحركة لا نهايتها (منحنى ease-out: معظم الحركة في أولها).
- لكل نوع حركة صوت ثابت (نص = whoosh خفيف، صورة = swoosh أثقل، ظهور متتابع = pop بنغمات صاعدة من سلّم الموسيقى).
- الأصوات تتبع مكان العنصر على الشاشة (يمين/يسار).
- الموسيقى تنخفض قليلاً تحت المؤثرات، والمجموع يُضبط على -14 LUFS (معيار يوتيوب وإنستغرام وتيك توك).
"""

import math
import wave

import numpy as np

SR = 48000


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _rng(seed):
    return np.random.default_rng(seed)


def band_noise(dur, f0, f1, width=0.6, seed=0):
    """ضجيج أبيض يمر عبر مرشح نطاق يتحرك من f0 إلى f1 (أساس كل أصوات whoosh)"""
    n = int(dur * SR)
    x = _rng(seed).standard_normal(n + 2048)
    frame, hop = 1024, 256
    win = np.hanning(frame)
    out = np.zeros(n + 2048)
    freqs = np.fft.rfftfreq(frame, 1 / SR)
    steps = max(1, (n - frame) // hop + 1)
    for k in range(steps + 4):
        a = k * hop
        seg = x[a:a + frame]
        if len(seg) < frame:
            break
        pos = min(1.0, a / max(1, n))
        fc = f0 * (f1 / f0) ** pos                     # مسح لوغاريتمي
        lf = np.log2(np.maximum(freqs, 1) / fc)
        gain = np.exp(-(lf / width) ** 2)
        out[a:a + frame] += np.fft.irfft(np.fft.rfft(seg * win) * gain, frame) * win
    out = out[:n]
    return out / (np.max(np.abs(out)) + 1e-9)


def env_ad(n, attack, curve=2.0):
    """غلاف: صعود حتى نسبة attack ثم هبوط"""
    t = np.linspace(0, 1, n)
    up = np.clip(t / max(attack, 1e-4), 0, 1) ** curve
    down = np.clip((1 - t) / max(1 - attack, 1e-4), 0, 1) ** curve
    return np.minimum(up, down)


def whoosh(dur=0.45, f0=500, f1=3500, attack=0.35, seed=1, tone=0.15):
    n = int(dur * SR)
    x = band_noise(dur, f0, f1, 0.55, seed) * env_ad(n, attack, 1.6)
    if tone:   # جسم نغمي خفيف يعطي إحساس الحركة (دوبلر)
        t = _t(dur)
        f = f0 * 0.5 * (f1 / f0) ** (t / dur)
        x += tone * np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(n, attack, 2)
    return x


def reverse_whoosh(dur=0.5, seed=7):
    """صوت انتقال يتصاعد حتى لحظة القطع"""
    n = int(dur * SR)
    return band_noise(dur, 400, 5000, 0.5, seed) * env_ad(n, 0.93, 2.4)


def tick(freq=3800, seed=3):
    t = _t(0.03)
    click = _rng(seed).standard_normal(len(t)) * np.exp(-t * 900)
    return 0.6 * click + np.sin(2 * np.pi * freq * t) * np.exp(-t * 160)


def pop(freq=880):
    """فقاعة: نغمة تهبط بسرعة (مثل ظهور بطاقة)"""
    t = _t(0.16)
    f = freq * (0.55 + 0.45 * np.exp(-t * 45))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28)
    click = tick(freq * 3)
    body[: len(click)] += 0.2 * click[: len(body)]
    return body


def thump(f0=110, f1=45, dur=0.22):
    t = _t(dur)
    f = f1 + (f0 - f1) * np.exp(-t * 30)
    return np.tanh(1.8 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14))


def impact(seed=5):
    body = thump(140, 38, 0.6)
    t = _t(0.6)
    crack = band_noise(0.6, 2500, 400, 0.9, seed) * np.exp(-t * 11)
    return 0.9 * body + 0.5 * crack


def riser(dur=1.2, seed=9):
    n = int(dur * SR)
    t = _t(dur)
    noise = band_noise(dur, 250, 7000, 0.5, seed) * (t / dur) ** 2.2
    f = 180 * (6 ** (t / dur))
    tone = 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) ** 2
    x = noise + tone
    x[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
    return x[:n]


def bell(freq, dur=1.2):
    t = _t(dur)
    x = np.zeros(len(t))
    for ratio, amp, decay in ((1, 1.0, 3.5), (2.0, 0.45, 5), (3.01, 0.25, 7), (4.2, 0.12, 9)):
        x += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * decay)
    return x * np.minimum(1, t / 0.004)


def chime(notes=(1046.5, 1568.0), gap=0.09):
    """نغمة نجاح صاعدة (من سلّم الموسيقى)"""
    parts = [bell(f) for f in notes]
    n = int(gap * SR) * (len(notes) - 1) + len(parts[0])
    x = np.zeros(n)
    for i, p in enumerate(parts):
        a = int(i * gap * SR)
        x[a:a + len(p)] += p * (0.8 ** i)
    return x


def ping():
    """إشعار رسالة (مثل وصول رسالة واتساب، بدون تقليد صوت تجاري)"""
    return chime((1318.5, 1760.0), 0.11) * 0.9


def shimmer(dur=0.9, seed=11):
    rng = _rng(seed)
    t = _t(dur)
    x = np.zeros(len(t))
    for _ in range(26):
        a = int(rng.uniform(0, dur * 0.7) * SR)
        f = rng.uniform(2600, 6200)
        L = min(len(t) - a, int(0.25 * SR))
        tt = np.arange(L) / SR
        x[a:a + L] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 18) * rng.uniform(0.3, 1)
    return x * np.exp(-t * 1.5)


def drift(dur):
    """هواء خفيف جداً يرافق حركة الكاميرا البطيئة"""
    n = int(dur * SR)
    return band_noise(dur, 900, 1400, 0.35, 21) * env_ad(n, 0.5, 1.2)


SOUNDS = {
    "whoosh_text": lambda: whoosh(0.42, 700, 4200, 0.3, 1, 0.08),
    "whoosh_img": lambda: whoosh(0.6, 300, 2600, 0.3, 2, 0.2),
    "whoosh_up": lambda: whoosh(0.5, 350, 3000, 0.4, 4, 0.18),
    "swipe": lambda: whoosh(0.28, 900, 5200, 0.25, 6, 0.05),
    "transition": lambda: reverse_whoosh(0.45),
    "tick": lambda: tick(),
    "thump": lambda: thump(),
    "impact": lambda: impact(),
    "riser": lambda: riser(1.25),
    "shimmer": lambda: shimmer(),
    "chime": lambda: chime(),
    "success": lambda: chime((1046.5, 1318.5, 1568.0), 0.075),
    "ping": lambda: ping(),
}
GAIN_DB = {"whoosh_text": -15, "whoosh_img": -12, "whoosh_up": -12, "swipe": -15, "transition": -14, "tick": -22,
           "thump": -11, "impact": -6, "riser": -13, "shimmer": -22, "chime": -17, "success": -15, "ping": -15,
           "pop": -16, "drift": -30}


def _reverb_ir(seconds=0.9, seed=31):
    rng = _rng(seed)
    t = _t(seconds)
    decay = np.exp(-t * 6.5)
    return [rng.standard_normal(len(t)) * decay * 0.02 for _ in range(2)]


_IR = None


def _reverb(x):
    global _IR
    if _IR is None:
        _IR = _reverb_ir()
    n = len(x) + len(_IR[0])
    size = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, size)
    return [np.fft.irfft(X * np.fft.rfft(ir, size), size)[:n] for ir in _IR]


def render(cues, dur):
    """cues: [(ثانية، اسم الصوت، pan من -1 يسار إلى 1 يمين، تعديل dB، تردد اختياري لصوت pop)] ← مصفوفة ستيريو"""
    out = np.zeros((2, int(dur * SR) + SR * 2))
    cache = {}
    for c in cues:
        at, name, pan = c[0], c[1], c[2]
        db = c[3] if len(c) > 3 else 0.0
        if name == "pop":
            x = pop(c[4] if len(c) > 4 else 880)
        elif name == "drift":
            x = drift(c[4])
        else:
            x = cache.setdefault(name, SOUNDS[name]())
        x = x / (np.max(np.abs(x)) + 1e-9) * 10 ** ((GAIN_DB[name] + db) / 20)
        wet = _reverb(x)
        a = int(max(0.0, at) * SR)
        th = (pan + 1) * math.pi / 4                   # توزيع بقدرة ثابتة
        gl, gr = math.cos(th), math.sin(th)
        for ch, g in ((0, gl), (1, gr)):
            seg = x * g * 0.85 + wet[ch][: len(x)] * 0.35
            end = min(out.shape[1], a + len(seg))
            out[ch, a:end] += seg[: end - a]
            tail = wet[ch][len(x):]
            e2 = min(out.shape[1], end + len(tail))
            out[ch, end:e2] += tail[: e2 - end] * 0.35
    return out[:, : int(dur * SR)]


def duck(music, sfx, depth=0.4):
    """خفض الموسيقى تحت المؤثرات (sidechain): هجوم سريع وتحرير بطيء"""
    env = np.max(np.abs(sfx), axis=0)
    hop = int(0.005 * SR)
    blocks = env[: len(env) // hop * hop].reshape(-1, hop).max(axis=1)
    g = np.empty_like(blocks)
    level = 0.0
    rel = math.exp(-hop / (0.18 * SR))
    for i, v in enumerate(blocks):
        level = v if v > level else level * rel
        g[i] = level
    g = 1 - depth * np.clip(g / (np.percentile(blocks, 99) + 1e-9), 0, 1)
    gain = np.repeat(g, hop)
    gain = np.pad(gain, (0, music.shape[1] - len(gain)), constant_values=1.0)[: music.shape[1]]
    return music * gain


def write_wav(path, stereo):
    peak = np.max(np.abs(stereo)) + 1e-9
    x = np.tanh(stereo / peak * 1.1) / math.tanh(1.1) * 0.89      # -1 dBFS مع حد ناعم
    pcm = (x.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def read_wav_mono(path):
    with wave.open(path, "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768
    if ch == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    if sr != SR:
        x = np.interp(np.arange(int(len(x) * SR / sr)) * sr / SR, np.arange(len(x)), x)
    return x
