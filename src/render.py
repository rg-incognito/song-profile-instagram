"""Render the final reel: slow keyframed camera move over the still image + handwritten lyric overlay + audio.

Everything here is measured from reference/reel.mp4 (see fonts/README.md and the constants below):

* Output 1440x2560 @ 60 fps, H.264 high / yuv420p, AAC 192k.
* Camera: one continuous, piecewise-linear "Ken Burns" move. The reference changes direction roughly at every
  lyric change (4 segments in 15.6 s): zoom-in + diagonal drift, slow pan right, faster zoom-in, zoom-out.
  Velocities are constant inside a segment (no easing), position/scale are continuous across keyframes.
  The view never leaves the image (scale 1.0 == image exactly covers the frame).
* Lyrics: one line at a time, not affected by the zoom (fixed overlay), cap-top ~y515 / baseline ~y563 of 2560,
  centre x ~= 0.511 W, pinkish cream colour. Each line fades in over 0.85 s with alpha = u**1.3 and is cut
  (no fade-out) at its end time.

Frames are rendered in Python (cv2.warpAffine, subpixel-exact bilinear sampling of a 2x Lanczos-upscaled
cover image ~= bicubic quality at 3.5x the speed; Pillow fallback) and piped as raw RGB to ffmpeg -> perfectly
smooth zoom without zoompan's integer-pixel jitter. ~11 fps on a 4-thread laptop CPU (30 s reel ~2:45 min)
with x264 preset "faster" CRF 16 (preset "slow" = ~2x slower for ~same visual quality at CRF 16).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:  # cv2 is much faster; Pillow fallback keeps the module dependency-light
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "fonts" / "ShadowsIntoLight-Regular.ttf"

OUT_W, OUT_H = 1440, 2560

# ---- text (all px values are for a 1440x2560 frame; scaled if the output size differs) ----
TEXT_COLOR = (214, 188, 172)      # chosen so that after 4:2:0 encoding strokes read ~(225,186,177) like the reference
CAP_HEIGHT = 44.0                 # average letter height in the reference (U 31 .. B 57, H 49)
TEXT_BASELINE_Y = 567.5           # puts ink centre at y~543 like the reference lines
TEXT_CENTER_X = 0.511             # reference lines are centred at x 730..758 (mean 740)
LETTER_GAP = 13.5                 # ink-to-ink gap between letters (reference: 11-18 px, mean 13.5)
WORD_GAP = 61.0                   # ink-to-ink gap between words (reference: 55-70 px, mean 61)
MAX_TEXT_W = 1300.0               # shrink long lines to fit (or wrap, see render_text_block)
LINE_SPACING = 1.9                # baseline-to-baseline distance for wrapped lines, in cap heights
FADE_IN = 0.85                    # seconds (reference: 48-53 frames @60fps)
FADE_GAMMA = 1.3                  # alpha = u**1.3 (fitted to the reference fade curve)
JITTER = True                     # hand-drawn irregularity: per-glyph scale / baseline / rotation
SS = 4                            # supersampling for text rendering
STROKE_ADD = 0.5                  # px added to the font's ~3.3 px stroke (reference strokes ~4.2 px)
# Letter ink widths measured on the reference lines (px at cap height 44). The reference hand is narrower than
# Shadows Into Light, so each glyph is condensed horizontally to these widths (others: DEFAULT_CONDENSE).
WIDTH_TARGETS = {"A": 24, "B": 31, "D": 23, "E": 32, "G": 28, "H": 24, "i": 9, "J": 31, "K": 22, "L": 22,
                 "M": 31, "N": 23, "O": 27, "P": 20, "R": 27, "S": 28, "T": 33, "U": 27, "Z": 42}
DEFAULT_CONDENSE = 0.78

# ---- camera moves measured from the reference (dz in %/s of scale, vx/vy in px/s of a 1440-wide frame) ----
MOVES = [
    (+1.07, -15.5, -12.5),   # 0.0-4.4 s : zoom-in, drift up-left
    (+0.27, +27.0, 0.0),     # 4.4-8.5 s : slow pan right
    (+2.07, +0.8, -4.6),     # 8.5-12.4 s: faster zoom-in, slight drift up
    (-2.20, -4.5, +10.5),    # 12.4-15.6 s: zoom-out, drift down
]
# The reference's first frame is already ~6 % inside the artwork (its camera later travels 34 px left of the
# first frame's edge), so we start at the same zoom to leave room for the measured pans.
START_ZOOM = 1.06
MAX_ZOOM = 1.20                       # never punch in further than this (keeps the subject in frame)
MIN_SEG, MAX_SEG = 1.8, 6.0
CAMERA_KEY_DELAY = 0.10               # reference camera turns ~0.1 s after the next line starts fading in

# ---- post-processing: film grain + bloom glow ----
GRAIN_STRENGTH = float(os.environ.get("RENDER_GRAIN", "7"))   # gaussian noise stddev; 0 = off
BLOOM_ALPHA    = float(os.environ.get("RENDER_BLOOM", "0.18")) # bloom mix strength; 0 = off
BLOOM_THRESH   = 160   # only pixels brighter than this contribute to bloom highlights


# ----------------------------------------------------------------------------------------------- text
def _font(size_px: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), max(4, int(round(size_px))))


def _font_size_for_cap(cap: float) -> float:
    f = _font(400)
    bb = f.getbbox("H", anchor="ls")
    return 400.0 * cap / (bb[3] - bb[1])


def render_text_block(text: str, scale: float = 1.0) -> tuple[Image.Image, float]:
    """Like render_text_layer, but lines that would have to shrink below ~85 % are wrapped onto two lines
    (same size as normal lines, second line below the first). Returns (RGBA, first-line baseline offset)."""
    probe, _ = render_text_layer(text, scale=scale, jitter=False, fit=False)
    words = text.split()
    if probe.width <= MAX_TEXT_W * scale / 0.85 or len(words) < 2:
        return render_text_layer(text, scale=scale)
    best = None
    for i in range(1, len(words)):  # most balanced split
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa = render_text_layer(a, scale=scale, jitter=False, fit=False)[0].width
        wb = render_text_layer(b, scale=scale, jitter=False, fit=False)[0].width
        if best is None or max(wa, wb) < best[0]:
            best = (max(wa, wb), a, b)
    (la, ba), (lb, bb_) = render_text_layer(best[1], scale=scale), render_text_layer(best[2], scale=scale)
    gap = LINE_SPACING * CAP_HEIGHT * scale
    W = max(la.width, lb.width)
    top_b = ba + gap - bb_  # y of second layer's top relative to first layer's top
    H = int(math.ceil(max(la.height, top_b + lb.height)))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(la, ((W - la.width) // 2, 0))
    out.alpha_composite(lb, ((W - lb.width) // 2, int(round(top_b))))
    return out, ba


def render_text_layer(text: str, scale: float = 1.0, color=TEXT_COLOR, cap: float = CAP_HEIGHT,
                      letter_gap: float = LETTER_GAP, word_gap: float = WORD_GAP,
                      jitter: bool = JITTER, fit: bool = True) -> tuple[Image.Image, float]:
    """Return (RGBA image tightly cropped around the ink, baseline offset from the top of the image)."""
    cap *= scale
    word_gap *= scale
    size = _font_size_for_cap(cap)
    base_size = size
    letter_gap *= scale
    rng = np.random.default_rng(zlib.crc32(text.encode("utf-8")))
    words = [w for w in text.strip().split() if w]

    def build(size: float, word_gap: float):
        # glyphs are placed by INK bounds: constant ink-to-ink gap between letters and between words,
        # exactly how the reference handwriting is spaced (letter gap 11-18 px, word gap 55-70 px).
        f = _font(size * SS)
        lg = letter_gap * size / base_size * SS
        glyphs = []  # (x_pen, char, (scale, dy, rot), bbox)
        x_ink = 0.0
        for wi, w in enumerate(words):
            if wi:
                x_ink += (word_gap * SS) - lg
            for c in w:
                bb = f.getbbox(c, anchor="ls")
                j = (rng.uniform(0.93, 1.09), rng.normal(0, 0.9), rng.normal(0, 1.6)) if jitter else (1.0, 0.0, 0.0)
                gw = max(1, bb[2] - bb[0])
                tgt = WIDTH_TARGETS.get(c)
                sx = (tgt * (cap / CAP_HEIGHT) * (size / base_size) * SS / gw) if tgt else DEFAULT_CONDENSE
                sx = float(min(1.15, max(0.55, sx)))
                sc = j[0]
                pen = x_ink - bb[0] * sc * sx
                glyphs.append((pen, c, j + (sx,), bb))
                x_ink = pen + bb[2] * sc * sx + lg
        return f, glyphs

    f, glyphs = build(size, word_gap)
    ink_w = (max(g[0] + g[3][2] * g[2][0] * g[2][3] for g in glyphs) - min(g[0] + g[3][0] * g[2][0] * g[2][3] for g in glyphs)) / SS
    if fit and ink_w > MAX_TEXT_W * scale:
        k = MAX_TEXT_W * scale / ink_w
        size *= k
        word_gap *= k
        rng = np.random.default_rng(zlib.crc32(text.encode("utf-8")))
        f, glyphs = build(size, word_gap)
        ink_w = (max(g[0] + g[3][2] * g[2][0] * g[2][3] for g in glyphs) - min(g[0] + g[3][0] * g[2][0] * g[2][3] for g in glyphs)) / SS

    pad = int(size * SS)
    stroke_w = max(0, int(round(STROKE_ADD / 2 * SS * scale)))
    W = int(ink_w * SS + 2 * pad)
    H = int(size * SS * 2.2)
    base = int(H * 0.62)
    mask = Image.new("L", (W, H), 0)
    for (x, c, (sc, dy, rot, sx), bb) in glyphs:
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        if gw <= 0 or gh <= 0:
            continue
        m = int(size * SS * 0.25)
        g = Image.new("L", (gw + 2 * m, gh + 2 * m), 0)
        ImageDraw.Draw(g).text((m - bb[0], m - bb[1]), c, font=f, fill=255, anchor="ls",
                               stroke_width=stroke_w, stroke_fill=255)
        if sc != 1.0 or sx != 1.0 or rot != 0.0:
            g = g.resize((max(1, int(round(g.width * sc * sx))), max(1, int(round(g.height * sc)))), Image.BICUBIC)
            g = g.rotate(rot, resample=Image.BICUBIC, expand=False)
        # where (m - bb[0], m - bb[1]) (the glyph origin) landed after scaling
        ox, oy = (m - bb[0]) * sc * sx, (m - bb[1]) * sc
        px = int(round(pad + x - ox))
        py = int(round(base + dy * SS * scale - oy))
        region = mask.crop((px, py, px + g.width, py + g.height))
        mask.paste(Image.fromarray(np.maximum(np.asarray(region), np.asarray(g))), (px, py))
    mask = mask.resize((W // SS, H // SS), Image.LANCZOS)
    a = np.asarray(mask)
    ys, xs = np.nonzero(a > 2)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    mask = mask.crop((x0, y0, x1, y1))
    rgba = Image.new("RGBA", mask.size, tuple(color) + (0,))
    rgba.putalpha(mask)
    return rgba, base / SS - y0


# ---------------------------------------------------------------------------------------------- camera
def camera_keytimes(segment: dict, duration: float) -> list[float]:
    """Camera changes direction near each lyric change (reference: ~0.1 s after the next line starts)."""
    starts = sorted(float(l["start"]) + CAMERA_KEY_DELAY for l in segment.get("lines", []))
    cand = [s for s in starts if MIN_SEG <= s <= duration - MIN_SEG]
    keys = [0.0]
    for s in cand:
        if s - keys[-1] >= MIN_SEG:
            keys.append(s)
    keys.append(duration)
    if keys[-1] - keys[-2] < MIN_SEG and len(keys) > 2:
        keys.pop(-2)
    out = [keys[0]]
    for a, b in zip(keys, keys[1:]):  # split segments that are too long
        n = max(1, math.ceil((b - a) / MAX_SEG))
        out += [a + (b - a) * (i + 1) / n for i in range(n)]
    return out


def camera_path(segment: dict, duration: float, fps: int, out_w: int, out_h: int):
    """Return arrays s (zoom, >=1), cx, cy (view centre in output-frame px at zoom 1) for every frame."""
    keys = camera_keytimes(segment, duration)
    k = out_w / 1440.0
    z0 = START_ZOOM
    s, cx, cy = z0, out_w / 2, out_h / 2
    seg_states = []  # (t0, s0, cx0, cy0, ds, vx, vy)

    def inside(s_, cx_, cy_):
        hw, hh = out_w / 2 / s_, out_h / 2 / s_
        return 1.0 <= s_ <= MAX_ZOOM and hw - 1e-6 <= cx_ <= out_w - hw + 1e-6 and hh - 1e-6 <= cy_ <= out_h - hh + 1e-6

    for i, (t0, t1) in enumerate(zip(keys, keys[1:])):
        dz, vx, vy = MOVES[i % len(MOVES)]
        dt = t1 - t0
        best = None
        for zsign in (1, -1):
            for sx in (1, -1, 0.5, -0.5, 0):
                for sy in (1, -1, 0.5, -0.5, 0):
                    ds_ = zsign * dz / 100.0 * z0             # MOVES are relative to the first frame
                    vx_, vy_ = sx * vx * k / z0, sy * vy * k / z0
                    ok = all(inside(s + ds_ * dt * u, cx + vx_ * dt * u, cy + vy_ * dt * u)
                             for u in (0.25, 0.5, 0.75, 1.0))
                    if ok:
                        best = (ds_, vx_, vy_)
                        break
                if best:
                    break
            if best:
                break
        if best is None:  # cannot keep the move inside the frame -> slow zoom towards START_ZOOM, drift to centre
            ds_ = (z0 - s) / dt * 0.5
            best = (ds_, (out_w / 2 - cx) / dt * 0.5, (out_h / 2 - cy) / dt * 0.5)
        seg_states.append((t0, s, cx, cy) + best)
        s, cx, cy = s + best[0] * dt, cx + best[1] * dt, cy + best[2] * dt

    n = int(round(duration * fps))
    t = np.arange(n) / fps
    S = np.empty(n); CX = np.empty(n); CY = np.empty(n)
    idx = np.searchsorted([st[0] for st in seg_states], t, side="right") - 1
    for j, (t0, s0, cx0, cy0, ds_, vx_, vy_) in enumerate(seg_states):
        m = idx == j
        S[m] = s0 + ds_ * (t[m] - t0)
        CX[m] = cx0 + vx_ * (t[m] - t0)
        CY[m] = cy0 + vy_ * (t[m] - t0)
    S = np.maximum(S, 1.0)
    hw, hh = out_w / 2 / S, out_h / 2 / S
    CX = np.clip(CX, hw, out_w - hw)
    CY = np.clip(CY, hh, out_h - hh)
    return S, CX, CY, keys


# ---------------------------------------------------------------------------------------------- image
def load_cover(image_path: str, out_w: int, out_h: int) -> np.ndarray:
    """Centre-crop/resize the image so it exactly covers the output frame (zoom 1.0 == full image)."""
    im = Image.open(image_path).convert("RGB")
    sc = max(out_w / im.width, out_h / im.height)
    nw, nh = max(out_w, round(im.width * sc)), max(out_h, round(im.height * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    l, t = (nw - out_w) // 2, (nh - out_h) // 2
    return np.ascontiguousarray(np.asarray(im.crop((l, t, l + out_w, t + out_h))))


UPSAMPLE = 2  # sampling source is the cover image Lanczos-upscaled 2x; bilinear on it ~= bicubic on 1x, 3.5x faster


def prepare_source(cover: np.ndarray, k: int = UPSAMPLE) -> np.ndarray:
    if k == 1:
        return cover
    h, w = cover.shape[:2]
    if cv2 is not None:
        return cv2.resize(cover, (w * k, h * k), interpolation=cv2.INTER_LANCZOS4)
    return np.asarray(Image.fromarray(cover).resize((w * k, h * k), Image.LANCZOS))


def warp(src: np.ndarray, s: float, cx: float, cy: float, out_w: int, out_h: int, k: int = UPSAMPLE,
         cubic: bool = False) -> np.ndarray:
    """Sample the output frame for zoom s centred at (cx, cy) (1x cover coordinates), subpixel exact."""
    a = 1.0 / s
    # output pixel centre u+.5 -> 1x coord x = cx + (u + .5 - W/2) * a ; -> k-x pixel index k*x - .5
    tx = k * (cx - (out_w / 2) * a + 0.5 * a) - 0.5
    ty = k * (cy - (out_h / 2) * a + 0.5 * a) - 0.5
    if cv2 is not None:
        M = np.array([[a * k, 0, tx], [0, a * k, ty]], dtype=np.float64)
        flags = cv2.INTER_CUBIC if cubic else cv2.INTER_LINEAR
        return cv2.warpAffine(src, M, (out_w, out_h), flags=flags | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REFLECT)
    im = Image.fromarray(src)  # Pillow: coefficients map output pixel corner coords to input corner coords
    return np.asarray(im.transform((out_w, out_h), Image.AFFINE, (a * k, 0, tx + 0.5, 0, a * k, ty + 0.5),
                                   resample=Image.BICUBIC if cubic else Image.BILINEAR))


# ---------------------------------------------------------------------------------------------- post-processing
def _bloom(frame: np.ndarray, alpha: float, thresh: int) -> np.ndarray:
    """Soft bloom glow: extract highlights, blur them, mix back in.

    Done at 1/4 resolution for speed (blur radius scales accordingly).
    alpha=0.18 and thresh=160 gives a barely-visible warm halation around bright areas.
    """
    if alpha <= 0:
        return frame
    h, w = frame.shape[:2]
    # downsample 4x
    small_h, small_w = max(1, h // 4), max(1, w // 4)
    if cv2 is not None:
        small = cv2.resize(frame, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
    else:
        small = np.asarray(Image.fromarray(frame).resize((small_w, small_h), Image.BILINEAR))
    # extract highlights (clamp negatives to zero)
    hi = np.clip(small.astype(np.int16) - thresh, 0, 255).astype(np.uint8)
    # blur the highlights
    if cv2 is not None:
        hi = cv2.GaussianBlur(hi, (31, 31), 0)
    else:
        hi = np.asarray(Image.fromarray(hi).filter(__import__('PIL').ImageFilter.GaussianBlur(radius=8)))
    # upsample back
    if cv2 is not None:
        hi_full = cv2.resize(hi, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        hi_full = np.asarray(Image.fromarray(hi).resize((w, h), Image.BILINEAR))
    return np.clip(frame.astype(np.float32) + hi_full.astype(np.float32) * alpha, 0, 255).astype(np.uint8)


def _grain(frame: np.ndarray, strength: float, rng: np.random.Generator) -> np.ndarray:
    """Add Gaussian film grain. Per-frame random seed → natural flicker."""
    if strength <= 0:
        return frame
    noise = rng.standard_normal(frame.shape).astype(np.float32) * strength
    return np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------------------------- main
def _line_windows(segment: dict, duration: float):
    lines = sorted(segment.get("lines", []), key=lambda l: float(l["start"]))
    out = []
    for i, l in enumerate(lines):
        st = max(0.0, float(l["start"]))
        en = min(duration, float(l["end"]))
        if i + 1 < len(lines):
            en = min(en, float(lines[i + 1]["start"]))
        if en - st > 0.05 and str(l.get("text", "")).strip():
            out.append((st, en, str(l["text"]).strip()))
    return out


def _encoder_args(encoder: str, crf: int, preset: str) -> list[str]:
    if encoder == "amf":  # AMD hardware encoder: ~4x faster, slightly lower efficiency -> lower QP
        q = max(10, crf - 2)
        return ["-c:v", "h264_amf", "-profile:v", "high", "-quality", "quality", "-rc", "vbr_peak",
                "-qp_i", str(q), "-qp_p", str(q + 2), "-qp_b", str(q + 4),
                "-maxrate", "11M", "-bufsize", "22M"]
    return ["-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf),
            "-maxrate", "11M", "-bufsize", "22M"]


def render_video(image_path, segment, out_path, fps: int = 60, crf: int = 16, preset: str = "faster",
                 size=(OUT_W, OUT_H), verbose: bool = True, encoder: str | None = None,
                 interp: str = "linear", max_frames: int | None = None):
    """Render the reel. encoder: 'x264' (default, env RENDER_ENCODER overrides) or 'amf' (AMD GPU)."""
    encoder = (encoder or os.environ.get("RENDER_ENCODER") or "x264").lower()
    preset = os.environ.get("RENDER_PRESET", preset)
    t_start = time.time()
    if isinstance(segment, (str, Path)):
        segment = json.loads(Path(segment).read_text(encoding="utf-8"))
    out_w, out_h = size
    scale = out_w / 1440.0
    duration = float(segment.get("duration") or 30.0)
    n_frames = int(round(duration * fps))
    if max_frames:
        n_frames = min(n_frames, max_frames)
        duration = n_frames / fps

    if not Path(image_path).exists() and (ROOT / image_path).exists():
        image_path = ROOT / image_path
    cover = load_cover(str(image_path), out_w, out_h)
    src = prepare_source(cover)
    S, CX, CY, keys = camera_path(segment, duration, fps, out_w, out_h)

    # pre-render one RGBA layer per line
    layers = []
    for st, en, text in _line_windows(segment, duration):
        rgba, base_off = render_text_block(text, scale=scale)
        a = np.asarray(rgba).astype(np.float32)
        x0 = int(round(out_w * TEXT_CENTER_X - rgba.width / 2))
        y0 = int(round(TEXT_BASELINE_Y * scale - base_off))
        x0 = max(0, min(out_w - rgba.width, x0))
        layers.append(dict(st=st, en=en, text=text, x0=x0, y0=y0,
                           rgb=a[..., :3], alpha=a[..., 3:4] / 255.0))

    # place the lyric band where it never covers the characters (Gemini zone + pixel check along the camera path)
    if layers and segment.get("text_y") is None and os.environ.get("LYRIC_PLACEMENT", "auto") != "off":
        import placement
        box_w = max(L["rgb"].shape[1] for L in layers)
        box_h = max(L["rgb"].shape[0] for L in layers)
        bx0 = min(L["x0"] for L in layers)
        zone = placement.gemini_zone(image_path)
        yc, rep = placement.choose_text_y(cover, S, CX, CY, box_w, box_h, bx0, zone)
        segment["text_y"] = yc
        try:
            Path(out_path).with_suffix(".placement.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
        except Exception:
            pass
    if layers and segment.get("text_y") is not None:
        yc = float(segment["text_y"])  # centre of the lyric box in output px
        for L in layers:
            h = L["rgb"].shape[0]
            L["y0"] = int(round(min(out_h - h, max(0, yc - h / 2))))
        if verbose:
            print(f"[render] lyric box centre y={yc:.0f}", flush=True)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio = segment.get("audio_path")
    if audio and not Path(audio).exists() and (ROOT / audio).exists():
        audio = str(ROOT / audio)
    if not audio or not Path(audio).exists():
        print(f"[render] WARNING: audio not found ({audio!r}) -> silent video", flush=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{out_w}x{out_h}",
           "-r", str(fps), "-i", "-"]
    if audio and Path(audio).exists():
        cmd += ["-i", str(audio)]
    cmd += ["-map", "0:v:0"]
    if audio and Path(audio).exists():
        cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-af", f"apad,atrim=0:{duration:.3f}"]
    cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p",
            *_encoder_args(encoder, crf, preset),
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-r", str(fps), "-t", f"{duration:.3f}", "-movflags", "+faststart",
            str(out_path)]

    grain_rng = np.random.default_rng()  # unseeded — different grain every render

    def make_frame(i: int) -> bytes:
        t = i / fps
        frame = warp(src, S[i], CX[i], CY[i], out_w, out_h, cubic=(interp == "cubic"))
        # bloom glow — applied before text so text stays sharp above the glow
        frame = _bloom(frame, BLOOM_ALPHA, BLOOM_THRESH)
        for L in layers:
            if L["st"] <= t < L["en"]:
                op = min(1.0, (t - L["st"]) / FADE_IN) ** FADE_GAMMA
                if op <= 0:
                    continue
                h, w = L["alpha"].shape[:2]
                y0, x0 = L["y0"], L["x0"]
                roi = frame[y0:y0 + h, x0:x0 + w].astype(np.float32)
                al = L["alpha"] * op
                frame[y0:y0 + h, x0:x0 + w] = (roi * (1 - al) + L["rgb"] * al + 0.5).astype(np.uint8)
        # film grain — applied last so it sits on top of everything
        frame = _grain(frame, GRAIN_STRENGTH, grain_rng)
        return frame.tobytes()

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    # frames are produced by a small thread pool (cv2 releases the GIL) while the main thread feeds ffmpeg
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    try:
        with ThreadPoolExecutor(max_workers=3) as ex:
            q = deque()
            nxt = 0
            for i in range(n_frames):
                while nxt < n_frames and len(q) < 6:
                    q.append(ex.submit(make_frame, nxt)); nxt += 1
                proc.stdin.write(q.popleft().result())
                if verbose and i % (fps * 5) == 0:
                    print(f"[render] frame {i}/{n_frames}  {time.time() - t_start:.1f}s", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with code {rc}")
    if verbose:
        el = time.time() - t_start
        print(f"[render] done {out_path} ({n_frames} frames in {el:.1f}s, {n_frames / el:.1f} fps); "
              f"camera keys {[round(k, 2) for k in keys]}", flush=True)
    return str(out_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a lyric reel from an image + segment json")
    ap.add_argument("--image", required=True)
    ap.add_argument("--segment", required=True, help="segment JSON file (see SPEC.md)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--preset", default="faster", help="x264 preset (slow = ~2x render time, ~same quality at CRF 16)")
    ap.add_argument("--encoder", choices=["x264", "amf"], default=None)
    ap.add_argument("--interp", choices=["cubic", "linear"], default="linear",
                    help="interpolation on the 2x-upsampled source (linear is ~bicubic quality, much faster)")
    ap.add_argument("--max-frames", type=int, default=None, help="render only the first N frames (testing)")
    a = ap.parse_args(argv)
    render_video(a.image, a.segment, a.out, fps=a.fps, crf=a.crf, preset=a.preset, encoder=a.encoder,
                 interp=a.interp, max_frames=a.max_frames)


if __name__ == "__main__":
    main()
