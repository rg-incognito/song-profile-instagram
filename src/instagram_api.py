"""Post reels to Instagram via the official Graph API (legal, no browser automation).

Flow:
  1. Upload mp4 to a temporary public URL (via file.io free service, auto-deletes after 1 download)
  2. Create a media container  POST /{ig-user-id}/media  media_type=REELS
  3. Poll until container status == FINISHED
  4. Publish                   POST /{ig-user-id}/media_publish

Credentials from .env:
  IG_USER_ID       — Instagram business account ID (17841466854855377)
  IG_ACCESS_TOKEN  — User token with instagram_content_publish + pages_* permissions

    python src/instagram_api.py --post output/x.mp4 --caption-file output/x.txt [--dry-run]
    python src/instagram_api.py --whoami
    python src/instagram_api.py --refresh-token   # extend token lifetime
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402  (loads .env)

ROOT = gemini.ROOT
GRAPH = 'https://graph.facebook.com/v21.0'


def _creds():
    uid = os.environ.get('IG_USER_ID', '').strip()
    tok = os.environ.get('IG_ACCESS_TOKEN', '').strip()
    if not uid or not tok:
        raise RuntimeError('IG_USER_ID or IG_ACCESS_TOKEN missing from .env')
    return uid, tok


def whoami(log=print):
    uid, tok = _creds()
    r = requests.get(f'{GRAPH}/{uid}', params={'fields': 'id,username,name', 'access_token': tok}, timeout=30)
    r.raise_for_status()
    d = r.json()
    log(f'  [ig-api] @{d.get("username")} (id={d.get("id")}, name={d.get("name")})')
    return d


def _upload_to_fileio(mp4: Path, log=print) -> str:
    """Upload to file.io — free, no account, file auto-deletes after first download."""
    log(f'  [ig-api] uploading {mp4.name} ({mp4.stat().st_size // 1024 // 1024} MB) to file.io...')
    with mp4.open('rb') as f:
        r = requests.post('https://file.io/', files={'file': (mp4.name, f, 'video/mp4')},
                          data={'expires': '1d', 'autoDelete': 'true'}, timeout=300)
    r.raise_for_status()
    d = r.json()
    if not d.get('success'):
        raise RuntimeError(f'file.io upload failed: {d}')
    url = d['link']
    log(f'  [ig-api] video URL: {url}')
    return url


def _create_container(ig_user_id: str, token: str, video_url: str, caption: str, log=print) -> str:
    log('  [ig-api] creating reel container...')
    r = requests.post(f'{GRAPH}/{ig_user_id}/media', params={
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': token,
    }, timeout=60)
    r.raise_for_status()
    container_id = r.json()['id']
    log(f'  [ig-api] container id: {container_id}')
    return container_id


def _wait_for_container(ig_user_id: str, token: str, container_id: str,
                        timeout_s=300, log=print) -> None:
    log('  [ig-api] waiting for container to process...')
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f'{GRAPH}/{container_id}',
                         params={'fields': 'status_code,status', 'access_token': token}, timeout=30)
        r.raise_for_status()
        d = r.json()
        status = d.get('status_code', '')
        log(f'  [ig-api] container status: {status}')
        if status == 'FINISHED':
            return
        if status == 'ERROR':
            raise RuntimeError(f'container processing error: {d}')
        time.sleep(10)
    raise RuntimeError(f'container not FINISHED within {timeout_s}s')


def _publish(ig_user_id: str, token: str, container_id: str, log=print) -> str:
    log('  [ig-api] publishing reel...')
    r = requests.post(f'{GRAPH}/{ig_user_id}/media_publish', params={
        'creation_id': container_id,
        'access_token': token,
    }, timeout=60)
    r.raise_for_status()
    media_id = r.json()['id']
    log(f'  [ig-api] published, media_id: {media_id}')
    return media_id


def post_reel(mp4, caption, dry_run=False, log=print):
    """Upload mp4 as a reel with caption. Returns the reel URL (or 'dry-run')."""
    mp4 = Path(mp4).resolve()
    uid, tok = _creds()

    video_url = _upload_to_fileio(mp4, log)
    container_id = _create_container(uid, tok, video_url, caption.strip(), log)

    if dry_run:
        log('  [ig-api] dry-run: container created, stopping before publish')
        return 'dry-run'

    _wait_for_container(uid, tok, container_id, log=log)
    media_id = _publish(uid, tok, container_id, log)
    return f'https://www.instagram.com/p/{media_id}/'


def refresh_token(log=print):
    """Exchange the short-lived token for a 60-day long-lived token and update .env."""
    _, tok = _creds()
    app_id = os.environ.get('IG_APP_ID', '').strip()
    app_secret = os.environ.get('IG_APP_SECRET', '').strip()
    if not app_id or not app_secret:
        log('  [ig-api] IG_APP_ID and IG_APP_SECRET required in .env to refresh token')
        return
    r = requests.get(f'{GRAPH}/oauth/access_token', params={
        'grant_type': 'fb_exchange_token',
        'client_id': app_id,
        'client_secret': app_secret,
        'fb_exchange_token': tok,
    }, timeout=30)
    r.raise_for_status()
    new_tok = r.json()['access_token']
    env_path = ROOT / '.env'
    text = env_path.read_text(encoding='utf-8')
    import re
    text = re.sub(r'^IG_ACCESS_TOKEN=.*$', f'IG_ACCESS_TOKEN={new_tok}', text, flags=re.MULTILINE)
    env_path.write_text(text, encoding='utf-8')
    log(f'  [ig-api] token refreshed and saved to .env (valid ~60 days)')
    return new_tok


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--whoami', action='store_true')
    ap.add_argument('--post')
    ap.add_argument('--caption-file')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--refresh-token', action='store_true')
    a = ap.parse_args()

    if a.whoami:
        whoami()
    if getattr(a, 'refresh_token'):
        refresh_token()
    if a.post:
        cap = Path(a.caption_file).read_text(encoding='utf-8') if a.caption_file else ''
        print(post_reel(a.post, cap, dry_run=a.dry_run))
