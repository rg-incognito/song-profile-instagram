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
        then a mix from #digitalart #love #hindisongs #lyrics #reels #aesthetic #bollywood #lyricsvideo #hindilovestatus
        #indiancouple #couplegoals #hindilyrics #romanticsongs — pick the most relevant 4-5;
        add an artist tag (e.g. #anuvjain #arijitsingh) only if the artist is very well-known; all lowercase, no duplicates.
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
        tags += [t for t in ['#digitalart', '#love', '#hindisongs', '#lyrics', '#reels', '#aesthetic',
                              '#hindilyrics', '#romanticsongs', '#couplegoals', '#hindilovestatus']
                 if t not in tags][:8 - len(tags)]
    # the song tag is always the full title (Gemini sometimes cuts it short: #waqtki for Waqt Ki Baatein)
    song_tag = _slug_tag(song.get('title', ''))
    if len(song_tag) > 1:
        tags = [song_tag] + [t for t in tags if not song_tag.startswith(t) and not t.startswith(song_tag)]
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
        resp = gemini.generate(gemini.ranked_models(), payload, timeout=120)
        return _clean(gemini.parse_json(gemini.text_of(resp))['caption'], song)
    except Exception as e:  # never let the caption kill a reel
        print(f'  [caption] Gemini failed ({e}); using fallback caption')
        return fallback_caption(song)


COMMENT_PROMPT = """You write the first comment for a reel on an aesthetic Hindi song-lyrics Instagram page.
It helps people searching Instagram find the reel, so it uses the words people actually search, but it must read
like a real, warm human line, not a keyword list.

Song: {song}
Scene in the illustration: {scene}
Lyric lines in the reel: {lines}

Write ONE line, at most 140 characters, in this shape:
<short natural Hinglish feeling line that names the song> <one emoji> <3 to 5 lowercase hashtags>
Allowed hashtags: the song name squashed lowercase, the singer's name squashed lowercase, #hindilovesongs #lovesongs
#romanticsongs #lyricsstatus #songlyrics #hindilyrics #aestheticlyrics #couplegoals #bollywoodsongs #indiemusic.
Keywords to draw from (use what fits): "<song> lyrics", the singer's name, hindi love songs, lyrics status,
romantic songs, couple goals, song lyrics, aesthetic lyrics, and words for the scene.
Rules: no @mentions, no links, no "follow / like / share" requests, no claims about views or trending.
Do not copy more than 4 words of the lyrics. Write something different from a template: every reel's comment must
feel unique.

Return JSON: {{"comment": "..."}}"""


COMMENT_TAGS = {'#hindisongs', '#hindilovesongs', '#lovesongs', '#romanticsongs', '#lyricsstatus', '#songlyrics',
                '#hindilyrics', '#lyrics', '#aestheticlyrics', '#couplegoals', '#bollywoodsongs', '#indiemusic',
                '#hindiindie', '#lovestatus', '#hinglishlyrics', '#digitalart', '#reels',
                '#hindilovestatus', '#indiancouple', '#coupleillustration', '#lyricsvideo', '#hindipop'}


def fallback_comment(song):
    title, artist = song.get('title', 'This song'), song.get('artist') or ''
    who = artist.split(',')[0].strip()
    tag = _slug_tag(title)
    return f"{title} lyrics{' by ' + who if who else ''} 🤍 {tag} #hindisongs #lovesongs #lyricsstatus"


def _clean_comment(text, song):
    text = ' '.join(str(text).split())
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'(?<!\w)@\w+', '', text)
    tags = list(dict.fromkeys(t.lower() for t in re.findall(r'#\w+', text)))
    body = re.sub(r'#\w+', '', text)
    body = ' '.join(body.split())
    if len(body) < 5:
        raise ValueError('comment too short')
    # weak fallback models misspell hashtags: keep only known-good tags + tags built from the song/artist names
    song_tag = _slug_tag(song.get('title', ''))
    artist_tags = [_slug_tag(n) for n in re.split(r'[,&/]', song.get('artist') or '') if n.strip()]
    tags = [t for t in tags if t in COMMENT_TAGS or t in artist_tags]
    tags += [t for t in ('#hindisongs', '#lyricsstatus', '#lovesongs') if len(tags) < 3 and t not in tags]
    tags = list(dict.fromkeys([song_tag] + tags))[:5]
    out = f"{body} {' '.join(tags)}"
    if len(out) > 220:
        raise ValueError('comment too long')
    return out


def make_comment(song, segment=None):
    """One searchable first comment. Never raises: falls back to a template."""
    try:
        import moments
        mo = moments.BY_KEY.get(song.get('moment')) or {}
    except Exception:
        mo = {}
    lines = [l['text'] for l in (segment or {}).get('lines', [])][:6]
    desc = json.dumps({k: song.get(k) for k in ('title', 'artist', 'film', 'mood')}, ensure_ascii=False)
    prompt = COMMENT_PROMPT.format(song=desc, scene=mo.get('name', 'a couple'), lines=' / '.join(lines) or '-')
    payload = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
               'generationConfig': {'temperature': 1.0, 'responseMimeType': 'application/json'}}
    try:
        resp = gemini.generate(gemini.ranked_models(), payload, timeout=120)
        return _clean_comment(gemini.parse_json(gemini.text_of(resp))['comment'], song)
    except Exception as e:
        print(f'  [caption] comment via Gemini failed ({str(e)[:120]}); template used', flush=True)
        return fallback_comment(song)


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
