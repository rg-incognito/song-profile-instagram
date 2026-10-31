"""Send finished reels to the user's Telegram bot chat so they can post them to Instagram by hand.

The video goes as a *document* (Telegram does not recompress documents -> original 1440x2560 60fps quality),
plus a preview video message and the Instagram caption as its own message (tap to copy).

Config (.env): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (auto-detected and saved the first time, after you send
/start to the bot).
    python src/telegram.py --setup                  # detect chat id (send /start to the bot first)
    python src/telegram.py --send output/x.mp4 --caption-file output/x.txt
"""
import argparse
import html
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402  (loads .env)

ROOT = gemini.ROOT
API = 'https://api.telegram.org/bot{}/{}'
BOT_LIMIT = 50 * 1024 * 1024  # Bot API upload limit


def _token():
    return os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()


def enabled():
    return bool(_token())


def _call(method, timeout=60, **kw):
    last = None
    for attempt in range(3):
        try:
            for fh in (kw.get('files') or {}).values():  # rewind uploads on retry
                if isinstance(fh, tuple) and hasattr(fh[1], 'seek'):
                    fh[1].seek(0)
            r = requests.post(API.format(_token(), method), timeout=(20, timeout), **kw)
            break
        except requests.RequestException as e:  # the URL contains the token: never surface it
            last = str(e).replace(_token(), '<token>')
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f'Telegram {method}: network error: {last[:200]}')
    try:
        j = r.json()
    except ValueError:
        j = {'ok': False, 'description': r.text[:200]}
    if not j.get('ok'):
        raise RuntimeError(f"Telegram {method} failed: {j.get('description')}")  # token never included
    return j['result']


def _save_chat_id(chat_id):
    env = ROOT / '.env'
    text = env.read_text(encoding='utf-8')
    if re.search(r'^TELEGRAM_CHAT_ID=.*$', text, re.M):
        text = re.sub(r'^TELEGRAM_CHAT_ID=.*$', f'TELEGRAM_CHAT_ID={chat_id}', text, flags=re.M)
    else:
        text += f'\nTELEGRAM_CHAT_ID={chat_id}\n'
    env.write_text(text, encoding='utf-8')
    os.environ['TELEGRAM_CHAT_ID'] = str(chat_id)


def chat_id():
    cid = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if cid:
        return cid
    updates = _call('getUpdates', params={'timeout': 0})
    for u in reversed(updates):
        msg = u.get('message') or u.get('edited_message') or {}
        chat = msg.get('chat') or {}
        if chat.get('type') == 'private' and chat.get('id'):
            _save_chat_id(chat['id'])
            return str(chat['id'])
    raise RuntimeError('No chat found: open your bot in Telegram, press Start (send /start), then retry.')


def send_reel(mp4, caption, title=None, problems=None):
    """Send preview + original-quality file + caption. Returns True on success."""
    if not enabled():
        print('  [telegram] TELEGRAM_BOT_TOKEN not set -> skipping', flush=True)
        return False
    mp4 = Path(mp4)
    cid = chat_id()
    size = mp4.stat().st_size
    if size > BOT_LIMIT:
        raise RuntimeError(f'{mp4.name} is {size / 1e6:.1f} MB; Telegram bots can only upload 50 MB')
    head = f'🎬 <b>{html.escape(title or mp4.stem)}</b>'
    if problems:
        head += '\n⚠️ QA notes:\n' + '\n'.join(f'• {html.escape(p[:180])}' for p in problems)
    # 1) playable preview (Telegram may show it compressed in chat)
    with mp4.open('rb') as f:
        _call('sendVideo', timeout=600, data={'chat_id': cid, 'caption': head, 'parse_mode': 'HTML',
                                              'supports_streaming': 'true', 'width': 1440, 'height': 2560},
              files={'video': (mp4.name, f, 'video/mp4')})
    # 2) untouched original file - download THIS one for Instagram
    with mp4.open('rb') as f:
        _call('sendDocument', timeout=600, data={'chat_id': cid, 'disable_content_type_detection': 'true',
                                                 'caption': '⬆️ Original quality file - save this one for Instagram'},
              files={'document': (mp4.name, f, 'video/mp4')})
    # 3) caption, monospace so a tap copies it
    if caption:
        _call('sendMessage', data={'chat_id': cid, 'parse_mode': 'HTML',
                                   'text': f'📋 Instagram caption (tap to copy):\n<code>{html.escape(caption)}</code>'})
    print(f'  [telegram] sent {mp4.name} ({size / 1e6:.1f} MB) to chat', flush=True)
    return True


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--setup', action='store_true')
    ap.add_argument('--send')
    ap.add_argument('--caption-file')
    a = ap.parse_args()
    if a.setup:
        cid = chat_id()
        _call('sendMessage', data={'chat_id': cid, 'text': '✅ Reel bot connected. Finished reels will arrive here.'})
        print('chat id saved; test message sent')
    if a.send:
        cap = Path(a.caption_file).read_text(encoding='utf-8') if a.caption_file else ''
        send_reel(a.send, cap)
