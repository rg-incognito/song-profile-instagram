"""Shared Gemini REST client (no SDK). Key from .env GEMINI_API_KEY, sent as a header, never in a URL."""
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://generativelanguage.googleapis.com'


def load_env():
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()


def api_key():
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('GEMINI_API_KEY missing in .env')
    return key


def _headers():
    return {'x-goog-api-key': api_key()}


def list_models():
    out, token = [], None
    while True:
        r = requests.get(f'{BASE}/v1beta/models', headers=_headers(),
                         params={'pageSize': 1000, **({'pageToken': token} if token else {})}, timeout=60)
        r.raise_for_status()
        j = r.json()
        out += j.get('models', [])
        token = j.get('nextPageToken')
        if not token:
            return out


_DEAD = set()  # models with no/exhausted quota or 404 in this process: skipped on later calls

# ------------------------------------------------------------------ model ranking (best -> weakest)
_RANK_EXCLUDE = ('image', 'tts', 'customtools', 'computer-use', 'robotics', 'transcribe', 'embedding',
                 'banana', 'live', 'audio', 'research', 'antigravity', 'omni', 'gemma', 'learnlm', 'aqa')
_STATIC = ['gemini-3.1-pro-preview', 'gemini-2.5-pro', 'gemini-3.5-flash', 'gemini-3-flash-preview',
           'gemini-2.5-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-flash-lite']
_RANKED = None


def _tier(name):
    if '-pro' in name:
        return 3
    if '-flash-lite' in name or '-lite' in name:
        return 1
    if '-flash' in name:
        return 2
    return 0


def _ver(name):
    m = re.search(r'gemini-(\d+(?:\.\d+)?)', name)
    return float(m.group(1)) if m else 0.0


def rank_key(name):
    """Higher is better: tier (pro > flash > flash-lite), then version, then stable over preview/exp."""
    stable = 0 if ('preview' in name or 'exp' in name) else 1
    return (_tier(name), _ver(name), stable, -len(name))


def ranked_models():
    """Every usable Gemini text/vision/audio model on this key, best first, weakest last.
    generate() walks this list and drops a model as soon as its quota is gone, so each call
    automatically uses the best model that still has quota."""
    global _RANKED
    if _RANKED is None:
        try:
            names = [m['name'].split('/', 1)[1] for m in list_models()
                     if 'generateContent' in m.get('supportedGenerationMethods', [])]
        except Exception as e:
            print(f'  [gemini] list_models failed ({e.__class__.__name__}); static model ranking')
            names = list(_STATIC)
        names = [n for n in names if n.startswith('gemini-') and _tier(n) > 0
                 and 'latest' not in n and not any(x in n for x in _RANK_EXCLUDE)]
        _RANKED = sorted(set(names), key=rank_key, reverse=True) or list(_STATIC)
    return list(_RANKED)


def generate(models, payload, timeout=300):
    """POST generateContent, trying each model in order on 429/500/503/404. Returns the raw JSON response."""
    last = None
    for i, model in enumerate(models):
        if model in _DEAD and model != models[-1]:
            continue
        for attempt in range(3):
            try:
                r = requests.post(f'{BASE}/v1beta/models/{model}:generateContent', headers=_headers(),
                                  json=payload, timeout=timeout)
            except requests.RequestException as e:  # timeout / connection reset: retry, then next model
                last = f'{model}: {e.__class__.__name__}'
                time.sleep(5 * (attempt + 1))
                continue
            if r.ok:
                return r.json()
            last = f"{model}: {r.status_code} {' '.join(r.text.split())[:300]}"
            if r.status_code == 429:
                m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                if 'limit: 0' in r.text or 'PerDay' in r.text or (m and int(m.group(1)) > 60):
                    _DEAD.add(model)
                    break  # no quota / daily quota exhausted for this model: waiting won't help, next model
            if r.status_code in (429, 500, 503):
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 404:
                _DEAD.add(model)
            break  # 400/404 etc: next model
        nxt = next((m for m in models[i + 1:] if m not in _DEAD), None)
        print(f"  [gemini] {model} unavailable ({last.split(': ', 1)[-1][:60]}) -> {nxt or 'no models left'}")
    raise RuntimeError(f'All Gemini models failed. Last: {last}')


def text_of(resp):
    parts = resp['candidates'][0]['content']['parts']
    return ''.join(p.get('text', '') for p in parts if not p.get('thought')).strip()


def parse_json(text):
    m = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find('{'), text.find('[')) if i >= 0], default=0)
    return json.JSONDecoder().raw_decode(text[start:])[0]  # ignore trailing text / a repeated object


def upload_file(path, mime):
    """Gemini Files API resumable upload. Returns {'uri','mimeType'} once ACTIVE."""
    path = Path(path)
    size = path.stat().st_size
    r = requests.post(f'{BASE}/upload/v1beta/files', headers={
        **_headers(), 'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
        'X-Goog-Upload-Header-Content-Length': str(size), 'X-Goog-Upload-Header-Content-Type': mime,
        'Content-Type': 'application/json'}, json={'file': {'display_name': path.name}}, timeout=60)
    r.raise_for_status()
    url = r.headers['X-Goog-Upload-URL']
    r = requests.post(url, headers={'X-Goog-Upload-Offset': '0', 'X-Goog-Upload-Command': 'upload, finalize',
                                    'Content-Length': str(size)}, data=path.read_bytes(), timeout=600)
    r.raise_for_status()
    f = r.json()['file']
    while f.get('state') == 'PROCESSING':
        time.sleep(2)
        f = requests.get(f"{BASE}/v1beta/{f['name']}", headers=_headers(), timeout=60).json()
    if f.get('state') == 'FAILED':
        raise RuntimeError(f'Gemini file processing failed: {f}')
    return {'uri': f['uri'], 'mimeType': f.get('mimeType', mime)}
