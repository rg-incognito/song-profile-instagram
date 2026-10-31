"""Instagram reel publishing via the Instagram Graph API, resumable local-file upload (no public hosting needed).

Flow (https://developers.facebook.com/docs/instagram-platform/content-publishing/resumable-uploads):
  1. POST graph.facebook.com/{v}/{ig-user-id}/media  media_type=REELS upload_type=resumable caption share_to_feed
     -> {"id": container_id, "uri": "https://rupload.facebook.com/ig-api-upload/{v}/{container_id}"}
  2. POST that uri with headers Authorization: OAuth <token>, offset: 0, file_size: <bytes>, body = mp4 bytes
  3. GET  /{container_id}?fields=status_code,status  until FINISHED (ERROR/EXPIRED -> fail)
  4. POST /{ig-user-id}/media_publish creation_id=<container_id>  -> {"id": media_id}

Credentials from .env: IG_USER_ID, IG_ACCESS_TOKEN. Optional: IG_API_VERSION (default v26.0),
IG_GRAPH_HOST (default graph.facebook.com; set graph.instagram.com for an Instagram-Login token).
The token is never printed or logged (it is scrubbed from any error text).
"""
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402,F401  (loads .env into os.environ)

DEFAULT_VERSION = 'v26.0'


class InstagramError(RuntimeError):
    pass


def credentials():
    uid = os.environ.get('IG_USER_ID', '').strip()
    tok = os.environ.get('IG_ACCESS_TOKEN', '').strip()
    return (uid, tok) if uid and tok else (None, None)


def is_configured():
    return credentials()[0] is not None


def _cfg():
    version = os.environ.get('IG_API_VERSION', '').strip() or DEFAULT_VERSION
    host = os.environ.get('IG_GRAPH_HOST', '').strip()
    if not host:
        tok = os.environ.get('IG_ACCESS_TOKEN', '')
        # Instagram-Login (business) tokens start with "IG"; Facebook-Login tokens with "EAA".
        host = 'graph.instagram.com' if tok.startswith('IG') else 'graph.facebook.com'
    return version, host


def _scrub(text, token):
    return str(text).replace(token, '<token>') if token else str(text)


def _check(r, token, what):
    try:
        j = r.json()
    except ValueError:
        j = {}
    if not r.ok or (isinstance(j, dict) and 'error' in j):
        raise InstagramError(_scrub(f'{what} failed: HTTP {r.status_code} {r.text[:500]}', token))
    return j


def publish_reel(video_path, caption, share_to_feed=True, poll_interval=10, poll_timeout=900, log=print):
    """Upload + publish a local MP4 as a Reel. Returns the published media id, or None if not configured."""
    uid, token = credentials()
    if not uid:
        log('  [instagram] IG_USER_ID / IG_ACCESS_TOKEN not set in .env -> skipping publish '
            '(see docs/INSTAGRAM_SETUP.md)')
        return None
    video_path = Path(video_path)
    size = video_path.stat().st_size
    version, host = _cfg()
    graph = f'https://{host}/{version}'
    auth = {'Authorization': f'OAuth {token}'}

    # 1. create resumable container
    r = requests.post(f'{graph}/{uid}/media', headers=auth, timeout=60, data={
        'media_type': 'REELS', 'upload_type': 'resumable', 'caption': caption,
        'share_to_feed': 'true' if share_to_feed else 'false'})
    j = _check(r, token, 'create container')
    cid = j['id']
    uri = j.get('uri') or f'https://rupload.facebook.com/ig-api-upload/{version}/{cid}'
    log(f'  [instagram] container {cid} created, uploading {size / 1e6:.1f} MB')

    # 2. upload bytes (resume from bytes_transferred on retry)
    offset, data = 0, video_path.read_bytes()
    for attempt in range(4):
        try:
            r = requests.post(uri, headers={**auth, 'offset': str(offset), 'file_size': str(size),
                                            'Content-Type': 'application/octet-stream'},
                              data=data[offset:], timeout=900)
            j = _check(r, token, 'upload')
            if j.get('success', True):
                break
            raise InstagramError(_scrub(f'upload not successful: {j}', token))
        except (requests.RequestException, InstagramError) as e:
            if attempt == 3:
                raise InstagramError(_scrub(e, token)) from None
            time.sleep(5 * (attempt + 1))
            try:  # find out how much arrived, resume from there
                s = requests.get(f'{graph}/{cid}', headers=auth, params={'fields': 'video_status'}, timeout=60).json()
                offset = int(s.get('video_status', {}).get('uploading_phase', {}).get('bytes_transferred', 0))
            except Exception:
                offset = 0
            log(f'  [instagram] upload retry {attempt + 1} from offset {offset}')

    # 3. poll processing status
    deadline = time.time() + poll_timeout
    while True:
        r = requests.get(f'{graph}/{cid}', headers=auth, params={'fields': 'status_code,status'}, timeout=60)
        j = _check(r, token, 'status')
        code = j.get('status_code')
        if code == 'FINISHED':
            break
        if code in ('ERROR', 'EXPIRED'):
            raise InstagramError(_scrub(f'container {cid} {code}: {j.get("status")}', token))
        if time.time() > deadline:
            raise InstagramError(f'container {cid} still {code} after {poll_timeout}s')
        log(f'  [instagram] processing... ({code})')
        time.sleep(poll_interval)

    # 4. publish
    r = requests.post(f'{graph}/{uid}/media_publish', headers=auth, data={'creation_id': cid}, timeout=120)
    media_id = _check(r, token, 'media_publish')['id']
    log(f'  [instagram] published reel media id {media_id}')
    return media_id


def check_token():
    """Sanity check credentials: returns the IG account username (without exposing the token)."""
    uid, token = credentials()
    if not uid:
        return None
    version, host = _cfg()
    r = requests.get(f'https://{host}/{version}/{uid}', headers={'Authorization': f'OAuth {token}'},
                     params={'fields': 'id,username'}, timeout=30)
    return _check(r, token, 'token check').get('username')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Publish a local MP4 as an Instagram Reel')
    ap.add_argument('video', nargs='?')
    ap.add_argument('--caption-file')
    ap.add_argument('--check', action='store_true', help='only verify credentials')
    a = ap.parse_args()
    if a.check or not a.video:
        if not is_configured():
            print('IG_USER_ID / IG_ACCESS_TOKEN not set -> publishing disabled (see docs/INSTAGRAM_SETUP.md)')
        else:
            print('credentials OK for @' + str(check_token()))
        sys.exit(0)
    cap = Path(a.caption_file).read_text(encoding='utf-8') if a.caption_file else ''
    print(publish_reel(a.video, cap))
