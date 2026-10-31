"""Where do the lyrics go? Keep them off the characters for the WHOLE clip, including during the camera move.

1. Gemini (vision) looks at the illustration and says where the empty background is and where a lyric line
   would sit best (fraction of image height). It also flags anything that is not plain background.
2. A pixel check builds a "not background" mask (characters, props, rain...) and, for every candidate y, maps
   the lyric box back through the camera path (zoom + pan of every frame) to make sure it never touches the
   mask. The candidate closest to Gemini's suggestion with zero overlap wins; the reference reel's y is the
   tie-breaker / fallback.

choose_text_y(cover, S, CX, CY, box_w, box_h, x0, gemini_hint) -> (centre_y_px, report)
gemini_zone(image_path) -> dict (cached next to the image as <image>.placement.json)
"""
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

REF_Y = 543.0          # reference reel lyric centre (1440x2560)
MARGIN = 40            # px of clear background required around the lyric box (output px)
Y_MIN, Y_MAX = 200, 2360


# ------------------------------------------------------------------------------------- Gemini
def gemini_zone(image_path):
    image_path = Path(image_path)
    cache = image_path.with_suffix('.placement.json')
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding='utf-8'))
        except Exception:
            pass
    im = Image.open(image_path).convert('RGB')
    im.thumbnail((720, 1280))
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=90)
    prompt = """This is a 9:16 illustration for an Instagram lyric reel. One short line of song lyrics
(small handwritten white text, about 4% of the image height tall, up to ~90% of the width) will be placed on it.
The camera slowly zooms in up to ~15% and pans slightly during the video, so leave a safety margin.
Find where the line can go WITHOUT touching or covering any character, face, hair, hands, body, object,
rain streak cluster or detailed scenery - only over plain, empty background.
Return JSON only:
{"empty_bands": [{"top": <0-1>, "bottom": <0-1>}],      // horizontal bands of plain empty background, full width
 "best_y": <0-1>,              // vertical centre for the lyric line; prefer the upper empty area
 "subject_top": <0-1>,         // highest point of any character/object
 "busy": <true if there is no clean place at all>,
 "reason": "<short>"}
All values are fractions of the image height (0 = top, 1 = bottom)."""
    payload = {'contents': [{'parts': [{'text': prompt}, {'inlineData': {
        'mimeType': 'image/jpeg', 'data': base64.b64encode(buf.getvalue()).decode()}}]}],
        'generationConfig': {'temperature': 0.2, 'responseMimeType': 'application/json'}}
    try:
        zone = gemini.parse_json(gemini.text_of(gemini.generate(gemini.ranked_models(), payload, timeout=120)))
    except Exception as e:
        print(f'  [placement] Gemini zone unavailable ({str(e)[:120]}); pixel check only', flush=True)
        return {}
    try:
        cache.write_text(json.dumps(zone, indent=2), encoding='utf-8')
    except Exception:
        pass
    return zone


# ------------------------------------------------------------------------------------- pixels
def subject_mask(cover: np.ndarray) -> np.ndarray:
    """True where the image is NOT plain background (cover = HxWx3 uint8 at output size)."""
    img = cover.astype(np.float32)
    if cv2 is not None:
        img = cv2.GaussianBlur(img, (0, 0), 3)  # kill paper grain
    # background colour = dominant colour among the outer border + top band (robust median)
    h, w = img.shape[:2]
    sample = np.concatenate([img[:h // 8].reshape(-1, 3), img[:, :w // 20].reshape(-1, 3),
                             img[:, -w // 20:].reshape(-1, 3)])
    q = (sample // 12).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2], return_counts=True)
    k = keys[counts.argmax()]
    sel = (q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]) == k
    bg = np.median(sample[sel], axis=0)
    dist = np.sqrt(((img - bg) ** 2).sum(-1))
    mask = (dist > 28).astype(np.uint8)
    if cv2 is not None:
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))   # drop specks of grain
        mask = cv2.dilate(mask, np.ones((2 * MARGIN + 1, 2 * MARGIN + 1), np.uint8))
    return mask.astype(bool)


def _overlap_along_path(integral, S, CX, CY, x0, x1, y0, y1, out_w, out_h, step=6):
    """Max covered fraction of the lyric rect (output px) over the camera path."""
    H, W = integral.shape[0] - 1, integral.shape[1] - 1
    worst = 0.0
    for i in range(0, len(S), step):
        s, cx, cy = S[i], CX[i], CY[i]
        ax0 = int(np.clip(cx + (x0 - out_w / 2) / s, 0, W)); ax1 = int(np.clip(cx + (x1 - out_w / 2) / s, 0, W))
        ay0 = int(np.clip(cy + (y0 - out_h / 2) / s, 0, H)); ay1 = int(np.clip(cy + (y1 - out_h / 2) / s, 0, H))
        area = max(1, (ax1 - ax0) * (ay1 - ay0))
        cov = integral[ay1, ax1] - integral[ay0, ax1] - integral[ay1, ax0] + integral[ay0, ax0]
        worst = max(worst, cov / area)
        if worst > 0.5:
            break
    return worst


def choose_text_y(cover, S, CX, CY, box_w, box_h, x0, zone=None):
    out_h, out_w = cover.shape[:2]
    mask = subject_mask(cover)
    integral = np.pad(mask.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    zone = zone or {}
    pref = REF_Y
    try:
        if zone.get('best_y') is not None:
            pref = float(zone['best_y']) * out_h
    except (TypeError, ValueError):
        pass
    x1 = x0 + box_w
    best = None
    for yc in range(Y_MIN + box_h // 2, Y_MAX - box_h // 2, 8):
        y0, y1 = yc - box_h / 2, yc + box_h / 2
        ov = _overlap_along_path(integral, S, CX, CY, x0, x1, y0, y1, out_w, out_h)
        # zero overlap dominates; then closeness to Gemini's spot; slight pull towards the reference height
        cost = ov * 1e6 + abs(yc - pref) + 0.25 * abs(yc - REF_Y)
        if best is None or cost < best[0]:
            best = (cost, yc, ov)
    _, yc, ov = best
    report = {'text_center_y': yc, 'overlap': round(float(ov), 4), 'gemini_best_y_px': round(pref),
              'gemini': zone, 'clean': bool(ov == 0)}
    if ov > 0:
        print(f'  [placement] WARNING: no fully clean spot; least overlap {ov:.1%} at y={yc}', flush=True)
    else:
        print(f'  [placement] lyrics at y={yc} (Gemini suggested {pref:.0f}); clear of characters for whole clip',
              flush=True)
    return yc, report
