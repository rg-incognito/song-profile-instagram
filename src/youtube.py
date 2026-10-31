"""Upload finished reels to the YouTube channel as Shorts (YouTube Data API v3).

One-time auth (pick the NEW channel in the browser when asked):
    python src/youtube.py --auth
Upload by hand:
    python src/youtube.py --upload output/<id>.mp4 --title "..."   (metadata normally comes from make_metadata)

Config: yt_client_secret.json (OAuth desktop client, same Google Cloud project as shortGen) and yt_token.json
(created by --auth). Both gitignored. Env YT_PRIVACY = public (default) | unlisted | private.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402  (loads .env)

ROOT = gemini.ROOT
SECRET = ROOT / 'yt_client_secret.json'
TOKEN = ROOT / 'yt_token.json'
SCOPES = ['https://www.googleapis.com/auth/youtube']


def is_configured():
    return TOKEN.exists()


def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent select_account')
    TOKEN.write_text(creds.to_json(), encoding='utf-8')
    ch = channel()
    print(f"Authorised channel: {ch.get('title')} ({ch.get('handle')})")


def _svc():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN.read_text(encoding='utf-8-sig')), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding='utf-8')
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def channel():
    items = _svc().channels().list(part='snippet', mine=True).execute().get('items') or []
    if not items:
        return {}
    sn = items[0]['snippet']
    return {'id': items[0]['id'], 'title': sn.get('title'), 'handle': sn.get('customUrl')}


# ------------------------------------------------------------------------------------------ metadata
def make_metadata(song, segment, ig_caption=''):
    """Gemini writes a Shorts title/description/tags; template fallback if quota is gone."""
    title_s, artist = song.get('title', ''), song.get('artist', '')
    first = next((l['text'] for l in segment.get('lines', []) if l.get('text')), '')
    prompt = f"""Write YouTube Shorts metadata for a 30-second aesthetic lyric reel: a hand-drawn illustration of a
couple with the Hinglish lyrics of "{title_s}" by {artist} ({song.get('film') or 'single'}) appearing line by line.
Mood: {song.get('mood')}. First lyric line on screen: "{first.title()}".
Rules: title <= 70 chars, song name + an emotional hook, 1-2 emojis max, end with #shorts; no clickbait lies.
description: 2 short lines (feeling + "Song: <title> - <artist>"), a credit line "All rights to the original
artists and label.", then 6-10 hashtags (#hindisongs #lyrics #<song> #love #aesthetic #shorts ...).
tags: 10-15 plain tags (song, artist, film, hindi lyrics, romantic songs, lyrics status, aesthetic).
Return JSON only: {{"title": "...", "description": "...", "tags": ["..."]}}"""
    payload = {'contents': [{'parts': [{'text': prompt}]}],
               'generationConfig': {'temperature': 0.8, 'responseMimeType': 'application/json'}}
    try:
        m = gemini.parse_json(gemini.text_of(gemini.generate(gemini.ranked_models(), payload, timeout=120)))
        assert m.get('title') and m.get('description')
    except Exception as e:
        print(f'  [youtube] metadata via Gemini failed ({str(e)[:100]}); template used', flush=True)
        slug = ''.join(c for c in title_s.lower() if c.isalnum())
        m = {'title': f'{title_s} 🤍 lyrics #shorts',
             'description': f'{first.title()}...\nSong: {title_s} - {artist}\nAll rights to the original artists '
                            f'and label.\n\n#{slug} #hindisongs #lyrics #love #aesthetic #shorts',
             'tags': [title_s, artist, f'{title_s} lyrics', 'hindi songs', 'romantic songs', 'lyrics status',
                      'aesthetic lyrics', 'bollywood songs']}
    if '#shorts' not in m['title'].lower() and '#shorts' not in m['description'].lower():
        m['description'] += ' #shorts'
    m['title'] = m['title'][:100]
    m['tags'] = [t for t in m.get('tags', []) if isinstance(t, str)][:20]
    return m


# ------------------------------------------------------------------------------------------ upload
def upload_short(mp4, meta, privacy=None, log=print):
    from googleapiclient.http import MediaFileUpload
    privacy = privacy or os.environ.get('YT_PRIVACY', 'public')
    body = {'snippet': {'title': meta['title'], 'description': meta['description'], 'tags': meta.get('tags', []),
                        'categoryId': '10',  # Music
                        'defaultLanguage': 'hi', 'defaultAudioLanguage': 'hi'},
            'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': False,
                       'containsSyntheticMedia': True}}  # AI-generated artwork: honest disclosure
    req = _svc().videos().insert(part='snippet,status', body=body,
                                 media_body=MediaFileUpload(str(mp4), mimetype='video/mp4', resumable=True,
                                                            chunksize=8 * 1024 * 1024))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log(f'    YT upload {int(status.progress() * 100)}%')
    vid = resp['id']
    log(f'  [youtube] uploaded ({privacy}): https://youtube.com/shorts/{vid}')
    return vid


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--auth', action='store_true')
    ap.add_argument('--whoami', action='store_true')
    ap.add_argument('--upload')
    ap.add_argument('--title')
    ap.add_argument('--privacy')
    a = ap.parse_args()
    if a.auth:
        auth()
    if a.whoami:
        print(channel())
    if a.upload:
        meta = {'title': a.title or Path(a.upload).stem, 'description': '#shorts', 'tags': []}
        upload_short(a.upload, meta, a.privacy)
