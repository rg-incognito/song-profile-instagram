"""Automated QA of a rendered reel. A failed QA blocks posting.

Technical (ffprobe/ffmpeg): 1440x2560, 60 fps, h264 yuv420p video, aac <=48 kHz audio, duration 29.5-30.5 s,
audio not silent, plus Instagram Reels upload spec: moov atom first (auto-fixed by lossless remux),
video bitrate <= 25 Mbps, file <= 300 MB.
Visual (Gemini vision on 3 frames): lyric text legible, not overlapping faces, not garbled/misspelled.

run_qa(video_path, segment=None, work_dir=None) -> {"ok": bool, "checks": {...}, "problems": [...]}
"""
import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

VISION_MODELS = ['gemini-3.5-flash', 'gemini-3.1-pro-preview', 'gemini-3-flash-preview', 'gemini-2.5-flash']
EXPECT = {'width': 1440, 'height': 2560, 'fps': 60.0, 'vcodec': 'h264', 'acodec': 'aac'}
DUR_RANGE = (29.5, 30.5)
SILENCE_DB = -45.0   # mean_volume below this = effectively silent


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _fps(rate):
    n, _, d = rate.partition('/')
    return float(n) / float(d or 1) if float(d or 1) else 0.0


def volume(path):
    err = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-vn', '-af', 'volumedetect',
                          '-f', 'null', '-'], capture_output=True, text=True).stderr
    mean = re.search(r'mean_volume:\s*(-?[\d.]+|-inf) dB', err)
    peak = re.search(r'max_volume:\s*(-?[\d.]+|-inf) dB', err)
    f = lambda m: float('-inf') if not m or m.group(1) == '-inf' else float(m.group(1))  # noqa: E731
    return f(mean), f(peak)


def moov_first(path):
    """True if the 'moov' atom precedes 'mdat' (fast-start), which the Instagram Reels spec requires."""
    with open(path, 'rb') as f:
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                return False
            size, kind = int.from_bytes(hdr[:4], 'big'), hdr[4:8]
            if kind == b'moov':
                return True
            if kind == b'mdat':
                return False
            if size == 1:
                size = int.from_bytes(f.read(8), 'big') - 8
            elif size == 0:
                return False
            f.seek(size - 8, 1)


def ensure_faststart(path, log=print):
    """Lossless remux with +faststart if needed (Instagram requires moov atom at the front)."""
    path = Path(path)
    if moov_first(path):
        return False
    tmp = path.with_name(path.stem + '.faststart' + path.suffix)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path), '-map', '0', '-c', 'copy',
                    '-movflags', '+faststart', str(tmp)], check=True)
    tmp.replace(path)
    log(f'  [qa] remuxed {path.name} with +faststart')
    return True


def technical_checks(path):
    checks, problems = {}, []
    info = probe(path)
    v = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    a = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    if not v:
        return {'video': 'missing'}, ['no video stream']
    checks['resolution'] = f"{v['width']}x{v['height']}"
    if (v['width'], v['height']) != (EXPECT['width'], EXPECT['height']):
        problems.append(f"resolution {checks['resolution']} != 1440x2560")
    fps = _fps(v.get('avg_frame_rate') or v.get('r_frame_rate', '0/1'))
    checks['fps'] = round(fps, 3)
    if abs(fps - EXPECT['fps']) > 0.1:
        problems.append(f'fps {fps:.2f} != 60')
    checks['vcodec'] = v['codec_name']
    if v['codec_name'] != EXPECT['vcodec']:
        problems.append(f"video codec {v['codec_name']} != h264")
    checks['pix_fmt'] = v.get('pix_fmt')
    if v.get('pix_fmt') not in ('yuv420p', 'yuvj420p'):
        problems.append(f"pix_fmt {v.get('pix_fmt')} is not 4:2:0 (Instagram requires yuv420p)")
    checks['faststart'] = moov_first(path)
    if not checks['faststart']:
        problems.append('moov atom not at start (needs -movflags +faststart)')
    if not a:
        problems.append('no audio stream')
    else:
        checks['acodec'] = a['codec_name']
        if a['codec_name'] != EXPECT['acodec']:
            problems.append(f"audio codec {a['codec_name']} != aac")
        checks['sample_rate'] = int(a.get('sample_rate', 0))
        if checks['sample_rate'] > 48000:
            problems.append(f"audio sample rate {checks['sample_rate']} > 48 kHz")
    dur = float(info['format'].get('duration', 0))
    checks['duration'] = round(dur, 3)
    if not DUR_RANGE[0] <= dur <= DUR_RANGE[1]:
        problems.append(f'duration {dur:.2f}s outside {DUR_RANGE}')
    if a:
        mean, peak = volume(path)
        checks['mean_volume_db'], checks['max_volume_db'] = mean, peak
        if mean < SILENCE_DB:
            problems.append(f'audio silent/too quiet (mean {mean} dB)')
    checks['size_mb'] = round(int(info['format'].get('size', 0)) / 1e6, 2)
    if checks['size_mb'] > 300:
        problems.append(f"file {checks['size_mb']} MB > 300 MB Instagram limit")
    vbr = int(v.get('bit_rate') or info['format'].get('bit_rate') or 0)
    checks['video_mbps'] = round(vbr / 1e6, 2)
    if vbr > 25_000_000:
        problems.append(f'video bitrate {vbr / 1e6:.1f} Mbps > 25 Mbps Instagram limit')
    return checks, problems


def _frame_times(segment, duration):
    lines = (segment or {}).get('lines') or []
    if len(lines) >= 3:
        picks = [lines[0], lines[len(lines) // 2], lines[-1]]
        return [round((l['start'] + l['end']) / 2, 2) for l in picks], [l['text'] for l in picks]
    return [round(duration * f, 2) for f in (0.2, 0.5, 0.8)], [None] * 3


def extract_frame(video, t, out_png):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(t), '-i', str(video),
                    '-frames:v', '1', '-vf', 'scale=720:-2', str(out_png)], check=True)
    return out_png


VISION_PROMPT = """You are a strict QA reviewer for an Instagram lyric reel (9:16, painterly illustration,
one line of handwritten-style lyric text near the top). You get {n} frames.{expected}
For EACH frame judge:
- legible: the lyric text is clearly readable (good contrast, not cut off at the edges, not too small)
- overlaps_face: the text overlaps a person's face or head
- garbled: text has garbled / malformed / AI-artifact letters, or differs from the expected line (IMPORTANT
  style notes: ALL CAPS with lowercase 'i' is INTENTIONAL, e.g. "ZiDDi", "KAHiN", "HAi" - never flag this;
  the handwritten font makes lowercase 'i' look tall and thin like 'I' - that is correct rendering, NOT an
  error). Also flag any stray text or watermark baked into the illustration itself.
Return JSON: {{"frames": [{{"index": 0, "text_seen": "...", "legible": true, "overlaps_face": false,
"garbled": false, "notes": "..."}}], "pass": true}}"""


def vision_checks(video, segment, work_dir):
    dur = float(probe(video)['format'].get('duration', 30))
    times, expected = _frame_times(segment, dur)
    work_dir = Path(work_dir or tempfile.mkdtemp())
    parts = []
    for i, t in enumerate(times):
        png = extract_frame(video, t, work_dir / f'qa_frame_{i}.png')
        parts.append({'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(png.read_bytes()).decode()}})
    exp = '' if not any(expected) else '\nExpected lyric line per frame: ' + json.dumps(expected, ensure_ascii=False)
    payload = {'contents': [{'role': 'user', 'parts': [{'text': VISION_PROMPT.format(n=len(parts), expected=exp)}]
                             + parts}],
               'generationConfig': {'temperature': 0.1, 'responseMimeType': 'application/json'}}
    res = gemini.parse_json(gemini.text_of(gemini.generate(gemini.ranked_models(), payload, timeout=180)))
    problems = []
    for f in res.get('frames', []):
        i = f.get('index', '?')
        tt = times[i] if isinstance(i, int) and i < len(times) else '?'
        if not f.get('legible', False):
            problems.append(f'frame {i} (t={tt}s): lyric text not legible - {f.get("notes", "")}')
        if f.get('overlaps_face'):
            problems.append(f'frame {i} (t={tt}s): text overlaps a face')
        if f.get('garbled'):
            problems.append(f'frame {i} (t={tt}s): garbled/wrong text "{f.get("text_seen", "")}" - {f.get("notes", "")}')
    if not res.get('frames'):
        problems.append('vision QA returned no frame verdicts')
    return {'frame_times': times, 'frames': res.get('frames', [])}, problems


def run_qa(video_path, segment=None, work_dir=None, vision=True, log=print):
    ensure_faststart(video_path, log)
    checks, problems = technical_checks(video_path)
    if vision:
        try:
            checks['vision'], vp = vision_checks(video_path, segment, work_dir)
            problems += vp
        except Exception as e:  # fail closed: if we can't verify, we don't post
            checks['vision'] = f'error: {e}'
            problems.append(f'vision QA could not run: {e}')
    ok = not problems
    log(f"  [qa] {'PASS' if ok else 'FAIL'} {checks.get('resolution')} {checks.get('fps')}fps "
        f"{checks.get('vcodec')}/{checks.get('acodec')} {checks.get('duration')}s "
        f"mean {checks.get('mean_volume_db')}dB")
    for p in problems:
        log(f'  [qa]   - {p}')
    return {'ok': ok, 'checks': checks, 'problems': problems}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='QA a rendered reel')
    ap.add_argument('video')
    ap.add_argument('--segment', help='segment.json for expected lyric lines')
    ap.add_argument('--no-vision', action='store_true')
    a = ap.parse_args()
    seg = json.loads(Path(a.segment).read_text(encoding='utf-8')) if a.segment else None
    sys.stdout.reconfigure(encoding='utf-8')
    r = run_qa(a.video, seg, Path(a.video).parent, vision=not a.no_vision)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if r['ok'] else 1)
