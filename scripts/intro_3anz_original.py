#!/usr/bin/env python3
"""Genera la intro "3anz Original" (estilo plataforma de streaming, ciencia ficcion).

Uso:
    python3 scripts/intro_3anz_original.py [salida.mp4]

Salida por defecto: intro/3anz_original_intro.mp4 (1920x1080, 30 fps, ~6 s, con sonido).
Solo necesita Python 3 con Pillow y numpy, y ffmpeg en el PATH.
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
DUR = 6.0
SR = 48000

# Paleta sci-fi: negro azulado + cian
BG_TOP = np.array([2, 4, 10], dtype=np.float32)
BG_GLOW = np.array([10, 40, 70], dtype=np.float32)
ACCENT = (80, 220, 255)
WHITE = (240, 246, 255)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_THIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def ramp(t, a, b):
    return ease((t - a) / (b - a))


def background():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.55)) ** 2 + ((yy - H / 2) / (H * 0.6)) ** 2)
    g = np.clip(1 - d, 0, 1)[..., None] ** 2
    img = BG_TOP + (BG_GLOW - BG_TOP) * g
    return img


def spaced_text(draw, center, text, font, spacing, fill):
    widths = [draw.textlength(c, font=font) for c in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = center[0] - total / 2
    for c, w in zip(text, widths):
        draw.text((x, center[1]), c, font=font, fill=fill, anchor="lm")
        x += w + spacing
    return total


def text_layer(t):
    """Capa RGBA con el logo segun el instante t."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cy = H / 2 - 40

    # "3anz": aparece con un ligero zoom hacia atras
    a_logo = ramp(t, 1.1, 2.3)
    if a_logo > 0:
        scale = 1.08 - 0.08 * a_logo
        font = ImageFont.truetype(FONT_BOLD, int(230 * scale))
        spaced_text(d, (W / 2, cy), "3anz", font, int(18 * scale),
                    WHITE + (int(255 * a_logo),))

    # Linea fina que se abre desde el centro
    a_line = ramp(t, 0.5, 1.6)
    if a_line > 0:
        half = 420 * a_line
        y = cy + 150
        d.rectangle([W / 2 - half, y - 1, W / 2 + half, y + 1],
                    fill=ACCENT + (int(230 * min(1, a_line * 1.5)),))

    # "ORIGINAL" con mucho espaciado
    a_orig = ramp(t, 2.1, 3.0)
    if a_orig > 0:
        font = ImageFont.truetype(FONT_THIN, 54)
        spacing = int(40 - 14 * a_orig)
        spaced_text(d, (W / 2, cy + 215), "ORIGINAL", font, spacing,
                    ACCENT + (int(255 * a_orig),))
    return layer


def sweep_mask(t):
    """Barrido de luz diagonal que cruza el logo."""
    p = ramp(t, 2.6, 3.7)
    if p <= 0 or p >= 1:
        return None
    xx = np.arange(W, dtype=np.float32)[None, :]
    yy = np.arange(H, dtype=np.float32)[:, None]
    pos = -400 + p * (W + 800)
    band = np.exp(-(((xx + (yy - H / 2) * 0.35) - pos) / 90) ** 2)
    return band


def render_frame(i, bg):
    t = i / FPS
    layer = text_layer(t)
    glow = layer.filter(ImageFilter.GaussianBlur(18))

    img = bg.copy()
    for lyr, strength in ((glow, 0.9), (layer, 1.0)):
        arr = np.asarray(lyr, dtype=np.float32)
        a = arr[..., 3:4] / 255 * strength
        img = img * (1 - a) + arr[..., :3] * a

    band = sweep_mask(t)
    if band is not None:
        txt_a = np.asarray(layer, dtype=np.float32)[..., 3] / 255
        img += (band * txt_a)[..., None] * 140

    # Fundido de entrada / salida
    fade = ramp(t, 0.0, 0.6) * (1 - ramp(t, DUR - 1.0, DUR))
    img *= fade

    # Grano de pelicula
    img += np.random.normal(0, 1.5, (H, W, 1))
    return np.clip(img, 0, 255).astype(np.uint8)


def make_audio(path):
    n = int(DUR * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)

    # Dron grave de fondo
    drone = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.5 * t)) * 0.12
    env = np.clip(t / 1.0, 0, 1) * np.clip((DUR - t) / 1.2, 0, 1)
    out += drone * env

    # Whoosh: ruido filtrado que sube hasta el impacto
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, n)
    k = 400
    noise = np.convolve(noise, np.ones(k) / k, mode="same") * 12
    w_env = np.exp(-((t - 1.1) / 0.35) ** 2)
    out += noise * w_env * 0.35

    # Impacto (boom) al aparecer el logo
    tb = np.clip(t - 1.15, 0, None)
    freq = 40 + 80 * np.exp(-tb * 8)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    boom = np.sin(phase) * np.exp(-tb * 2.2) * (t >= 1.15)
    out += boom * 0.8

    # Brillo agudo con el barrido de luz
    ts = np.clip(t - 2.7, 0, None)
    shimmer = np.sin(2 * np.pi * 1760 * t) * np.sin(2 * np.pi * 2637 * t)
    out += shimmer * np.exp(-ts * 2.5) * (t >= 2.7) * 0.06

    out /= max(1e-9, np.abs(out).max()) / 0.9
    stereo = np.stack([out, out], axis=1)
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def main():
    root = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "intro" / "3anz_original_intro.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    wav = out.with_suffix(".wav")
    make_audio(wav)

    np.random.seed(7)
    bg = background()
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(wav),
        "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(DUR * FPS)):
        proc.stdin.write(render_frame(i, bg).tobytes())
    proc.stdin.close()
    proc.wait()
    wav.unlink()
    if proc.returncode != 0:
        sys.exit(proc.returncode)
    print(f"Intro generada: {out}")


if __name__ == "__main__":
    main()
