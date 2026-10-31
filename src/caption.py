"""Instagram caption + hashtags via Gemini, in the reference account's short aesthetic style.

Example output:
    Mere naam tu 🤍
    by Ajay-Atul
    .
    .
    .
    #merenaamtu #digitalart #love #hindisongs #lyrics #reels #aesthetic
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

MODELS = ['gemini-3.5-flash', 'gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash']

PROMPT = """You write Instagram captions for an aesthetic Hindi/Bollywood song-lyrics reel account
(painterly digital-art couple illustration + one handwritten lyric line on screen).

Song: {song}
Lyric lines shown in the reel (for context only, do NOT reproduce them all): {lines}

Write the caption in EXACTLY this shape (no extra text, no quotes, no markdown):
line 1: a short title-case snippet (2-5 words) of the song's most iconic phrase or title, Roman-script Hinglish,
        followed by ONE soft emoji from: 🤍 🤎 ❤️ 🥀 ✨ 🌙
line 2: "by <credit>" where credit is the singer/composer's well-known name (an @handle only if you are certain it is
        their real official Instagram handle; otherwise the plain name)
lines 3-5: a single "." on each line (spacer)
line 6: 5 to 8 hashtags separated by single spaces: first the song name squashed lowercase (e.g. #merenaamtu),
        then a mix from #digitalart #love #hindisongs #lyrics #reels #aesthetic #bollywood #lyricsvideo #arijitsingh
        (artist tag only if relevant), all lowercase, no duplicates.
Keep it short. Never include more than one lyric phrase.

Return JSON: {{"caption": "<the caption with \\n line breaks>"}}"""


def _slug_tag(title):
    return '#' + re.sub(r'[^a-z0-9]', '', title.lower())


def fallback_caption(song):
    title = song.get('title', 'Song')
    artist = song.get('artist') or 'Unknown'
    tags = [_slug_tag(title), '#digitalart', '#love', '#hindisongs', '#lyrics', '#reels', '#aesthetic']
    return f"{title} 🤍\nby {artist}\n.\n.\n.\n" + ' '.join(dict.fromkeys(tags))


def _clean(caption, song):
    lines = [l.rstrip() for l in caption.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        raise ValueError('caption too short')
    tag_line = next((l for l in reversed(lines) if l.lstrip().startswith('#')), None)
    if not tag_line:
        raise ValueError('no hashtags')
    tags = list(dict.fromkeys(t.lower() for t in re.findall(r'#\w+', tag_line)))
    if len(tags) < 5:
        tags += [t for t in ['#digitalart', '#love', '#hindisongs', '#lyrics', '#reels', '#aesthetic']
                 if t not in tags]
    tags = tags[:8]
    head = [l for l in lines if not l.lstrip().startswith('#') and l.strip() != '.'][:2]
    out = '\n'.join(head + ['.', '.', '.', ' '.join(tags)])
    if len(out) > 2200:  # Instagram caption hard limit
        raise ValueError('caption too long')
    return out


def make_caption(song, segment=None):
    lines = [l['text'] for l in (segment or {}).get('lines', [])][:8]
    song_desc = json.dumps({k: song.get(k) for k in ('title', 'artist', 'film', 'year', 'mood')}, ensure_ascii=False)
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': PROMPT.format(song=song_desc, lines=' / '.join(lines) or '-')}]}],
        'generationConfig': {'temperature': 0.8, 'responseMimeType': 'application/json'},
    }
    try:
        resp = gemini.generate(MODELS, payload, timeout=120)
        return _clean(gemini.parse_json(gemini.text_of(resp))['caption'], song)
    except Exception as e:  # never let the caption kill a reel
        print(f'  [caption] Gemini failed ({e}); using fallback caption')
        return fallback_caption(song)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Generate an Instagram caption for a song')
    ap.add_argument('--title', default='Mere Naam Tu')
    ap.add_argument('--artist', default='Abhay Jodhpurkar')
    ap.add_argument('--film', default='Zero')
    ap.add_argument('--segment', help='path to segment.json (optional)')
    a = ap.parse_args()
    seg = json.loads(Path(a.segment).read_text(encoding='utf-8')) if a.segment else {
        'lines': [{'text': 'MERE NAAM TU', 'start': 0, 'end': 3}, {'text': 'TU HAi TOH MAiN HOON', 'start': 3, 'end': 6}]}
    sys.stdout.reconfigure(encoding='utf-8')
    print(make_caption({'title': a.title, 'artist': a.artist, 'film': a.film, 'year': 2018, 'mood': 'romantic'}, seg))
