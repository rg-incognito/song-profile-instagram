"""Image agent: Gemini scene prompt + Nano Banana (Gemini image model) -> 1440x2560 PNG in the reference style.

generate_image(song, out_path, seed_hint=None) -> out_path
CLI: python src/image_gen.py --title "Mere Naam Tu" --mood "tender romantic" --out work/test_image/image.png
"""
import argparse
import base64
import io
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

ROOT = gemini.ROOT
REF_FRAME = ROOT / 'reference' / 'frames' / 'f_01.png'
OUT_W, OUT_H = 1440, 2560

TEXT_MODEL_PREFS = ['gemini-3.8-flash', 'gemini-3.5-flash', 'gemini-3.1-pro-preview', 'gemini-3-flash-preview',
                    'gemini-flash-latest', 'gemini-2.5-flash']
IMAGE_MODEL_PREFS = ['gemini-3-pro-image', 'gemini-3-pro-image-preview', 'nano-banana-pro-preview',
                     'gemini-3.1-flash-image', 'gemini-3.1-flash-image-preview', 'gemini-2.5-flash-image']
VISION_MODEL_PREFS = ['gemini-3.8-flash', 'gemini-3.5-flash', 'gemini-3-flash-preview', 'gemini-flash-latest',
                      'gemini-2.5-flash']

POSES = [
    'hug from behind, his arms wrapped around her waist, her hands resting on his',
    'foreheads touching, eyes hidden under hair, hands clasped between them',
    'walking away side by side holding hands, seen from behind / three-quarter back',
    'sitting close together on a terrace ledge, her head on his shoulder',
    'sharing one umbrella in light rain, standing shoulder to shoulder',
    'tight embrace, her face buried in his chest, his chin resting on her head',
    'she rides piggyback on him, arms around his neck, both heads turned away',
    'slow dance, her hands on his shoulders, faces turned down and hidden by hair',
    'sitting back to back on the floor, heads tilted toward each other',
    'he kisses the top of her head while she leans into his chest',
    'lying in grass seen from above, heads touching, hair covering faces',
    'she holds his face in her hands, both faces turned away from the viewer',
]
PALETTES = {
    'deep maroon': '#560006',
    'midnight navy': '#0E1A33',
    'bottle green': '#0F2E1F',
    'burnt orange': '#7A2E0B',
    'plum': '#3D1430',
    'deep teal': '#0B3036',
    'oxblood brown': '#3A1410',
}

STYLE_PROMPT = """Create a NEW illustration in exactly the same art style as the attached reference image \
(the reference is ONLY a style guide: do NOT copy its characters, pose or composition; ignore any text in it).

SCENE: {scene}
BACKGROUND: one solid, flat, deep {palette_name} colour (around {palette_hex}), uniform, with only a very subtle \
paper / canvas grain texture. No environment details, no gradient, no vignette, no props in the background \
except what the scene strictly needs (drawn in the same flat way, low contrast).

STYLE (locked, match the reference precisely):
- flat painterly digital illustration, like a modern Indian / Korean webtoon poster; soft matte paper grain over everything
- warm caramel / golden-brown skin with simple 2-3 tone cel shadows, no gradients, no airbrush, no glossy highlights
- hair is a dark near-black mass with fine painterly strands at the edges
- clothes are big flat colour shapes (off-white, cream, black, muted tones) with soft folds and the same paper texture
- faces are HIDDEN: hair falls over the eyes, or faces are turned away / buried / in profile with NO eyes, no eyebrows, \
no detailed facial features (at most a simple nose/lip silhouette edge)
- muted, warm, cinematic colour; low saturation except the rich background

COMPOSITION (critical):
- vertical 9:16 portrait poster
- the couple occupies ONLY the lower 60-65% of the frame, shown large (head-and-torso / mid shot), \
and is cropped by the bottom edge of the image
- the TOP 35% of the image is completely EMPTY plain background colour: no heads, no hair, no objects, nothing
- the tops of their heads start at roughly 35-40% down from the top edge

ABSOLUTELY NO text, letters, words, numbers, captions, logos, signatures or watermarks anywhere."""


_model_cache = {}
_dead = set()  # models that returned a hard quota 429 this process


def _gen(models, payload, timeout=300):
    """Like gemini.generate but fails fast: a quota-exhausted model is skipped at once (and remembered),
    a transient 429/5xx gets one short retry."""
    import requests
    last = None
    for model in [m for m in models if m not in _dead]:
        for attempt in range(2):
            t = time.time()
            try:
                r = requests.post(f'{gemini.BASE}/v1beta/models/{model}:generateContent',
                                  headers=gemini._headers(), json=payload, timeout=timeout)
            except requests.RequestException as e:
                last = f'{model}: {e}'
                continue
            if r.ok:
                print(f'  [image_gen] {model} ok in {time.time() - t:.0f}s', flush=True)
                return r.json(), model
            last = f'{model}: {r.status_code} {r.text[:200]}'
            if r.status_code == 429 and 'limit: 0' in r.text:  # no quota at all on this tier: never retry
                _dead.add(model)
                _model_cache.setdefault('zero_quota', []).append(model)
                break
            if r.status_code in (429, 500, 503) and attempt == 0:
                time.sleep(8)
                continue
            break
        print(f'  [image_gen] skip {last[:160]!r}', flush=True)
    raise RuntimeError(f'All models failed. Last: {last}')


def _available():
    if 'names' not in _model_cache:
        try:
            _model_cache['names'] = {m['name'].split('/', 1)[1] for m in gemini.list_models()}
        except Exception as e:  # network hiccup: just use prefs as-is
            print(f'  [image_gen] list_models failed ({e}); using static fallback list')
            _model_cache['names'] = None
    return _model_cache['names']


def pick(prefs):
    names = _available()
    if not names:
        return list(prefs)
    chosen = [m for m in prefs if m in names]
    return chosen or list(prefs)


def _b64(img: Image.Image, fmt='PNG'):
    buf = io.BytesIO()
    img.save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode()


def reference_image():
    """f_01 with the lyric line painted out (copy a clean background band over it), downsized."""
    im = Image.open(REF_FRAME).convert('RGB')
    w, h = im.size
    y0, y1 = int(h * 0.185), int(h * 0.245)  # lyric band (~y 470-630 on 2560)
    band = im.crop((0, int(h * 0.06), w, int(h * 0.06) + (y1 - y0)))
    im.paste(band, (0, y0))
    return im.resize((w // 2, h // 2), Image.LANCZOS)


# ---------------------------------------------------------------- step 1: scene
def write_scene(song, seed_hint=None):
    rng = random.Random(seed_hint)
    poses = rng.sample(POSES, 4)
    palette_names = list(PALETTES)
    prompt = f"""You art-direct a single illustration for an Instagram lyric reel of the song \
"{song.get('title')}" by {song.get('artist') or 'unknown'} (film: {song.get('film') or '-'}), mood: "{song.get('mood')}".
The illustration always shows one young Indian couple (faces hidden: hair over eyes / turned away), \
large mid-shot, cropped by the bottom edge, on a plain solid dark background.
Pick ONE intimate moment that fits this song's mood. Some ideas (you may use one or invent a similar one): {poses}.
Pick a background colour from {palette_names} that suits the mood (deep maroon is the classic default for \
romance/longing; vary it when another fits better). Describe clothing in simple muted flat colours that contrast \
with the background.
Return JSON only: {{"scene": "<2-3 sentences: pose, body positions, clothes, hair, small details; faces hidden; \
no background scenery>", "palette": "<one of the palette names>"}}"""
    payload = {'contents': [{'parts': [{'text': prompt}]}],
               'generationConfig': {'temperature': 1.1, 'responseMimeType': 'application/json'}}
    try:
        data = gemini.parse_json(gemini.text_of(_gen(pick(TEXT_MODEL_PREFS), payload)[0]))
        scene, pal = data['scene'].strip(), data.get('palette', 'deep maroon').strip().lower()
    except Exception as e:
        print(f'  [image_gen] scene writer failed ({e}); using random fallback')
        scene, pal = poses[0] + '. Simple muted clothes, faces hidden by hair.', 'deep maroon'
    if pal not in PALETTES:
        pal = 'deep maroon'
    return scene, pal


# ---------------------------------------------------------------- step 2: image
WEB_WATERMARK_PX = 185  # Gemini web sparkle sits in the bottom ~150 px (bottom-right) at 1K and 2K: cut that strip


def _call_image_web(prompt, ref):
    """Generate through gemini.google.com in the pipeline Chrome profile (src/gemini_web.py)."""
    import tempfile
    import gemini_web
    tmp = Path(tempfile.mkdtemp())
    ref_path = tmp / 'style_reference.png'
    ref.save(ref_path)
    out = gemini_web.generate(prompt, tmp / 'web.png', ref=ref_path)
    im = Image.open(out).convert('RGB')
    w, h = im.size
    im = im.crop((0, 0, w, h - WEB_WATERMARK_PX))  # watermark gone; _fit_9x16 re-crops width
    _model_cache['used'] = f'gemini-web {w}x{h}'
    return im


def _call_image(prompt, ref):
    if os.environ.get('IMAGE_BACKEND', 'web').lower() == 'web':
        return _call_image_web(prompt, ref)
    parts = [{'text': prompt},
             {'inlineData': {'mimeType': 'image/png', 'data': _b64(ref)}}]
    models = pick(IMAGE_MODEL_PREFS)
    last = None
    for size in ('4K', '2K', None):
        img_cfg = {'aspectRatio': '9:16', **({'imageSize': size} if size else {})}
        payload = {'contents': [{'parts': parts}],
                   'generationConfig': {'responseModalities': ['TEXT', 'IMAGE'], 'imageConfig': img_cfg}}
        try:
            resp, used = _gen(models, payload, timeout=400)
        except RuntimeError as e:
            last = e
            continue
        for p in resp.get('candidates', [{}])[0].get('content', {}).get('parts', []):
            d = p.get('inlineData') or p.get('inline_data')
            if d and not p.get('thought'):
                _model_cache['used'] = f'{used} imageSize={size}'
                return Image.open(io.BytesIO(base64.b64decode(d['data']))).convert('RGB')
        last = RuntimeError(f'no image in response: {json.dumps(resp)[:300]}')
    raise RuntimeError(f'image generation failed: {last}')


def _fit_9x16(im):
    w, h = im.size
    target = 9 / 16
    if abs(w / h - target) > 0.005:  # centre-crop width or crop from the top-bottom (keep bottom anchored)
        if w / h > target:
            nw = round(h * target)
            im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = round(w / target)
            im = im.crop((0, h - nh, w, h))
    return im.resize((OUT_W, OUT_H), Image.LANCZOS)


def _add_grain(im, strength=3.0, seed=0):
    """Very subtle paper grain: low-freq blotches + fine noise, luminance only."""
    rng = np.random.default_rng(seed)
    a = np.asarray(im).astype(np.float32)
    fine = rng.normal(0, 1, (OUT_H, OUT_W)).astype(np.float32)
    coarse = Image.fromarray(((rng.normal(0, 1, (OUT_H // 8, OUT_W // 8)) * 40 + 128).clip(0, 255)).astype(np.uint8))
    coarse = np.asarray(coarse.resize((OUT_W, OUT_H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3)),
                        np.float32) - 128
    lum = a.mean(axis=2) / 255.0
    g = (fine * 0.5 + coarse / 40 * 0.7) * strength * (0.25 + 0.75 * lum)  # keep darks clean like the reference
    return Image.fromarray((a + g[..., None]).clip(0, 255).astype(np.uint8))


# ---------------------------------------------------------------- QA
def _pixel_qa(im):
    """Top 30% must be near-uniform background."""
    a = np.asarray(im.resize((180, 320))).astype(np.float32)
    top = a[: int(320 * 0.30)]
    med = np.median(top.reshape(-1, 3), axis=0)
    dev = np.abs(top - med).max(axis=2)
    frac = float((dev > 40).mean())
    return frac < 0.01, f'top30 non-bg fraction={frac:.3f}'


def _vision_qa(im):
    ref = reference_image().resize((360, 640))
    q = """Image 1 is a style REFERENCE. Image 2 is a CANDIDATE. Judge the candidate strictly.
Return JSON: {"has_text": bool (any letters/words/numbers/signature/watermark anywhere in candidate),
"top_empty": bool (top 30% of candidate is plain empty background, nothing intruding),
"faces_hidden": bool (no visible eyes or detailed facial features),
"style_match": int 1-10 (flat painterly look, paper grain, cel-shaded caramel skin, solid deep background vs reference),
"notes": "short"}"""
    payload = {'contents': [{'parts': [{'text': q},
                                       {'inlineData': {'mimeType': 'image/png', 'data': _b64(ref)}},
                                       {'inlineData': {'mimeType': 'image/png',
                                                       'data': _b64(im.resize((360, 640)))}}]}],
               'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json'}}
    try:
        r = gemini.parse_json(gemini.text_of(_gen(pick(VISION_MODEL_PREFS), payload)[0]))
    except Exception as e:
        print(f'  [image_gen] vision QA unavailable ({e}); accepting')
        return True, {'error': str(e)}
    ok = (not r.get('has_text')) and r.get('top_empty') and r.get('faces_hidden') and int(r.get('style_match', 0)) >= 7
    return bool(ok), r


# ---------------------------------------------------------------- main entry
def generate_image(song: dict, out_path, seed_hint=None, max_retries=2, grain=True):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ref = reference_image()
    best = None
    for attempt in range(max_retries + 1):
        seed = None if seed_hint is None else f'{seed_hint}-{attempt}'
        scene, pal = write_scene(song, seed)
        prompt = STYLE_PROMPT.format(scene=scene, palette_name=pal, palette_hex=PALETTES[pal])
        print(flush=True); print(f'  [image_gen] attempt {attempt + 1}: palette={pal} scene={scene}')
        try:
            raw = _call_image(prompt, ref)
        except RuntimeError as e:
            print(f'  [image_gen] {e}', flush=True)
            if all(m in _dead for m in pick(IMAGE_MODEL_PREFS)):
                break  # every image model has zero quota: retrying is pointless
            continue
        print(f'  [image_gen] raw image {raw.size}')
        im = _fit_9x16(raw)
        px_ok, px_note = _pixel_qa(im)
        v_ok, v = _vision_qa(im)
        score = int(v.get('style_match', 5) or 5) + (3 if px_ok else 0) + (5 if v_ok else 0)
        print(f'  [image_gen] QA pixel={px_ok} ({px_note}) vision={v_ok} {v}')
        if best is None or score > best[0]:
            best = (score, im, {'model': _model_cache.get('used'), 'scene': scene, 'palette': pal, 'qa': v, 'pixel': px_note})
        if px_ok and v_ok:
            break
    if best is None:
        zq = _model_cache.get('zero_quota')
        if zq:
            raise RuntimeError(f'image generation impossible: models {zq} have quota limit 0 for this API key '
                               '(Gemini Free Tier has no image-generation quota). Enable billing on the Google AI '
                               'Studio project that owns GEMINI_API_KEY.')
        raise RuntimeError('image generation failed on all attempts')
    im = best[1]
    if grain:
        im = _add_grain(im, seed=abs(hash(str(seed_hint))) % 2**32)
    im.save(out_path)
    out_path.with_suffix('.json').write_text(json.dumps(best[2], indent=2), encoding='utf-8')
    return str(out_path)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--title', required=True)
    ap.add_argument('--artist', default='')
    ap.add_argument('--mood', default='romantic')
    ap.add_argument('--out', required=True)
    ap.add_argument('--seed', default=None)
    ap.add_argument('--retries', type=int, default=2)
    a = ap.parse_args()
    print(generate_image({'title': a.title, 'artist': a.artist, 'mood': a.mood}, a.out, a.seed, a.retries))
