"""Audio stage: pick a song, download official audio, let Gemini choose a ~30 s hook and transcribe timed Hinglish lyrics.

Functions for the orchestrator:
    pick_song(history, hint=None) -> song dict
    download_audio(song, cache_dir='songs_cache') -> path to cached full-song WAV
    select_segment(audio_path, song, run_dir, duration=30.0) -> segment dict (also run_dir/segment.json, run_dir/clip.m4a)

CLI:  python src/song.py --song "Mere Naam Tu" --out work/test_audio
      python src/song.py --out work/test_audio2            (Gemini picks a song)
"""
import argparse
import json
import random
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402

ROOT = gemini.ROOT

# ----------------------------------------------------------------------------------------------- models
_MODEL_CACHE = {}
_EXCLUDE = ('image', 'tts', 'customtools', 'computer-use', 'robotics', 'transcribe', 'embedding',
            'banana', 'live', 'audio', 'research', 'antigravity')


def _version(name):
    m = re.search(r'gemini-(\d+(?:\.\d+)?)', name)
    return float(m.group(1)) if m else 0.0


def pick_models(kind='pro'):
    """Best -> weakest models (shared ranking in gemini.ranked_models). kind='flash' starts at flash tier
    for cheap text tasks (keeps scarce pro quota for audio/lyrics), still falling down to flash-lite."""
    order = gemini.ranked_models()
    if kind == 'flash':
        order = [m for m in order if '-pro' not in m] + [m for m in order if '-pro' in m]
    return order


_NUM, _STR, _INT, _BOOL = {'type': 'NUMBER'}, {'type': 'STRING'}, {'type': 'INTEGER'}, {'type': 'BOOLEAN'}


def _obj(props, required=None):
    return {'type': 'OBJECT', 'properties': props, 'required': required or list(props)}


SCHEMA_LINES = _obj({'lines': {'type': 'ARRAY', 'items': _obj({'text': _STR, 'start': _NUM, 'end': _NUM})}})
SCHEMA_ALIGN = _obj({'snippets': {'type': 'ARRAY', 'items': _obj({'i': _INT, 'words': _STR})},
                     'lines': {'type': 'ARRAY', 'items': _obj({'text': _STR, 'first': _INT, 'last': _INT,
                                                               'starts_mid': _BOOL})}})


def _ask(models, parts, temperature=None, timeout=600, schema=None, meta=None):
    """generateContent -> parsed JSON (structured output when `schema` given; one retry on malformed JSON)."""
    cfg = {'responseMimeType': 'application/json'}
    if schema:
        cfg['responseSchema'] = schema
    if temperature is not None:
        cfg['temperature'] = temperature
    for attempt in range(2):
        resp = gemini.generate(models, {'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': cfg},
                               timeout=timeout)
        if meta is not None:
            meta['model'] = resp.get('modelVersion')
        try:
            return gemini.parse_json(gemini.text_of(resp))
        except (ValueError, KeyError, IndexError) as e:  # malformed / truncated JSON: ask once more
            print(f'  [song] bad JSON from {resp.get("modelVersion")}: {str(e)[:80]}; retrying')
    raise RuntimeError('Gemini kept returning malformed JSON')


# ----------------------------------------------------------------------------------------------- helpers
def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:80] or 'song'


def song_slug(song):
    return slugify(f"{song.get('title', '')} {song.get('artist', '')}")


def format_line(text):
    """'Thoda sa ziddi hoon!' -> 'THODA SA ZiDDi HOON' (uppercase, every i lowercase, no punctuation but ')."""
    text = text.replace('’', "'").replace('`', "'")
    text = re.sub(r"[^\w\s']", ' ', text, flags=re.U)
    text = re.sub(r'_', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip().upper()
    return text.replace('I', 'i')


def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', **kw)
    if r.returncode != 0:
        raise RuntimeError(f'command failed ({cmd[0]} {cmd[1] if len(cmd) > 1 else ""}): {r.stderr[-800:]}')
    return r.stdout


def probe_duration(path):
    return float(_run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)]))


def _mp3(src, dst, start=None, dur=None):
    """Compressed copy for Gemini upload (full song or a window)."""
    cmd = ['ffmpeg', '-v', 'error', '-y']
    if start is not None:
        cmd += ['-ss', f'{max(0.0, start):.3f}', '-t', f'{dur:.3f}']
    cmd += ['-i', str(src), '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '192k', str(dst)]
    _run(cmd)
    return dst


def _ts(sec):
    return f'{int(sec // 60)}:{sec % 60:05.2f}'


# ----------------------------------------------------------------------------------------------- 1. pick_song
REFERENCE_VIBE = ('"Mere Naam Tu" (Abhay Jodhpurkar, music Ajay-Atul, film Zero 2018) - soft, tender, emotional '
                  'romantic Hindi song, the kind used on aesthetic couple-illustration lyric reels on Instagram')


def _history_titles(history):
    out = []
    for h in history or []:
        s = h.get('song', h) if isinstance(h, dict) else {}
        if isinstance(s, dict) and s.get('title'):
            out.append(f"{s['title']} - {s.get('artist', '')}".strip(' -'))
        elif isinstance(h, str):
            out.append(h)
    return out


def _norm_title(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())


INDIE_ARTISTS = ('Prateek Kuhad, Anuv Jain, The Local Train, Aditya Rikhari, Lucky Ali, Ritviz, Kaavish, '
                 'When Chai Met Toast, Osho Jain, Faheem Abdullah, Rauhan Malik, Raghav Meattle, Zaeden, '
                 'Bharat Chauhan, Siddhant Bhosle, Kavya Trehan, Tanzeel Khan, Ankur Tewari, Arpit Bala, '
                 'Shashwat Sachdev, Sanam, Vilen, Dhruv Sharma, Nikhita Gandhi, Jasleen Royal, Mitraz, Kushagra, '
                 'Sajjad Ali, Ali Sethi, Hasan Raheem, Asim Azhar, Shae Gill')
BOLLY_ARTISTS = ('Arijit Singh, Jubin Nautiyal, Darshan Raval, Shreya Ghoshal, Vishal Mishra, Armaan Malik, '
                 'Atif Aslam, KK, Sonu Nigam, Mohit Chauhan, Javed Ali, Shilpa Rao, Sachet-Parampara, Pritam, '
                 'Amit Trivedi, A.R. Rahman, Vishal-Shekhar, Shankar-Ehsaan-Loy, Sachin-Jigar, Tanishk Bagchi, '
                 'Kumar Sanu / Udit Narayan / Alka Yagnik 90s classics, Kishore Kumar / Lata classics')


def pick_song(history, hint=None, moment=None, source=None, rng=None):
    """Return song dict {title, artist, film, year, mood, youtube_query, moment, source}. Avoids titles in history.

    moment: a dict from moments.py - the song must fit that couple moment (mood + scene). If a song `hint` is
    given without a moment, Gemini picks the moment that fits the song best.
    source: 'bollywood' | 'indie' (default: 50/50 at random)."""
    import moments as moments_mod
    rng = rng or random.Random()
    used = _history_titles(history)
    source = source or rng.choice(['bollywood', 'indie'])
    schema = ('Return ONLY JSON: {"title": str (song title as commonly written in Roman script), '
              '"artist": str (main singer(s)), "composer": str|null, "film": str|null (film/album, null for '
              'independent singles), "year": int|null, "mood": str (3-6 words), '
              '"is_indie": bool (independent / non-film release), '
              '"youtube_query": str (precise YouTube search for the OFFICIAL AUDIO or official lyric/full song '
              'upload of the ORIGINAL studio version, e.g. "Mere Naam Tu Zero Abhay Jodhpurkar Ajay-Atul official '
              'audio" - include title, film or album, singer and the words "official audio")'
              + (', "moment": str (the key of the moment below that fits this song best)' if hint and not moment
                 else '') + '}')
    if hint:
        extra = ''
        if moment:
            extra = f'\nThe reel will show this couple moment: "{moment["name"]}".'
        else:
            extra = ('\nAlso choose which illustrated couple moment fits this song best. Moments (key: '
                     'description | mood):\n' + '\n'.join(f"{m['key']}: {m['name']} | {m['mood']}"
                                                          for m in moments_mod.MOMENTS))
        prompt = (f'The user wants a reel with this song: "{hint}". Identify the exact song (most popular '
                  f'original studio version) and fill in its details.{extra}\n{schema}')
    else:
        avoid = '\n'.join(f'- {t}' for t in used[-300:]) or '(none)'
        if source == 'indie':
            pool = (f'an INDEPENDENT (non-film) Hindi / Urdu / Hindustani indie-pop song, e.g. by {INDIE_ARTISTS} '
                    '(or another indie artist) - loved on Instagram reels, a soft memorable sung hook')
        else:
            pool = (f'a Hindi FILM (Bollywood) song, any era (2020s, 2010s, 2000s, 90s classics), e.g. by '
                    f'{BOLLY_ARTISTS} - hugely popular and loved on Instagram reels, a memorable sung hook')
        moment = moment or moments_mod.pick(history, rng)
        prompt = (
            'You curate songs for an Instagram page that posts 30-second lyric reels over painterly couple '
            f'illustrations. Reference vibe: {REFERENCE_VIBE}.\n'
            f'THIS reel\'s illustration shows: "{moment["name"]}" - {moment["scene"]}\n'
            f'Song mood needed: {moment["mood"]}.\n'
            f'Pick ONE song that is {pool}. The song must FIT this exact moment and mood - its feeling and its '
            'lyrics should match the picture (someone watching should feel "this song is exactly this moment"). '
            'Hindi/Urdu lyrics; not a rap, not a dance/party number. Vary eras and artists, do not always pick '
            'the most famous one.\n'
            f'Do NOT pick any of these already-used songs:\n{avoid}\n{schema}')
    banned = {_norm_title(t.split(' - ')[0]) for t in used}
    for attempt in range(4):
        song = _ask(pick_models('flash'), [{'text': prompt}], temperature=None if hint else 1.0)
        if isinstance(song, list):
            song = song[0]
        if hint or _norm_title(song.get('title')) not in banned:
            break
        prompt += f'\n(You picked "{song.get("title")}" which is already used. Pick a different one.)'
    if not moment:
        moment = moments_mod.find(song.get('moment')) or moments_mod.pick(history, rng)
    out = {'title': song.get('title', hint or '').strip(), 'artist': (song.get('artist') or '').strip(),
           'film': song.get('film') or None, 'year': song.get('year') if isinstance(song.get('year'), int) else None,
           'mood': song.get('mood') or 'romantic', 'youtube_query': (song.get('youtube_query') or '').strip(),
           'moment': moment['key'], 'source': 'indie' if song.get('is_indie') else 'bollywood'}
    if song.get('composer'):
        out['composer'] = song['composer']
    if not out['youtube_query']:
        out['youtube_query'] = f"{out['title']} {out['film'] or ''} {out['artist']} official audio".strip()
    return out


# ----------------------------------------------------------------------------------------------- 2. download_audio
OFFICIAL_CHANNELS = ('t-series', 'tseries', 'zee music', 'sony music', 'yrf', 'yash raj', 'tips', 'saregama',
                     'times music', 'speed records', 'universal music', 'warner music', 'eros now', 'shemaroo',
                     'venus', 'aditya music', 'lahari', 'jiosaavn', 'saavn', 'merchant records', 'vyrl',
                     'hitz music', 'pen music', 'desi music factory', 'white hill', 'junglee music',
                     'excel', 'red chillies', 'dharma', 'unisys', 'think music', 'coke studio', 'believe',
                     'svf', 'ishtar', 'saga music', 'amara muzik', 'blive', 'times music hindi')
BAD_WORDS = ('live', 'cover', 'slowed', 'reverb', '8d', 'remix', 'lofi', 'lo-fi', 'lo fi', 'mashup', 'unplugged',
             'acoustic', 'reprise', 'karaoke', 'instrumental', 'sped up', 'speed up', 'nightcore', 'reaction',
             'jukebox', 'teaser', 'trailer', 'status', 'whatsapp', 'ringtone', '1 hour', 'loop', 'female version',
             'male version', 'piano', 'guitar', 'flute', 'tutorial', 'chords', 'dance', 'choreography', 'shorts',
             'bass boosted', 'concert', 'tribute', 'medley', 'version', 'edit', 'meaning', 'trending reels')


def _yt_search(query, n=12):
    out = _run([sys.executable, '-m', 'yt_dlp', '--flat-playlist', '-J', '--no-warnings', f'ytsearch{n}:{query}'],
               timeout=180)
    return json.loads(out).get('entries') or []


def _score(e, song, extra_ok=''):
    title = (e.get('title') or '').lower()
    chan = (e.get('channel') or e.get('uploader') or '').lower()
    dur = e.get('duration') or 0
    if not (120 <= dur <= 480):
        return None
    if e.get('live_status') in ('is_live', 'is_upcoming', 'was_live'):
        return None
    allowed = (song.get('title', '') + ' ' + extra_ok).lower()
    for w in BAD_WORDS:
        if re.search(rf'(?<![a-z]){re.escape(w)}(?![a-z])', title) and w not in allowed:
            return None
    s = 0.0
    tw = [w for w in re.findall(r'[a-z0-9]+', song.get('title', '').lower()) if len(w) > 1]
    hit = sum(w in title for w in tw) / max(1, len(tw))
    if hit < 0.6:
        return None
    s += 4 * hit
    if any(c in chan for c in OFFICIAL_CHANNELS):
        s += 6
    artist_words = [w for w in re.findall(r'[a-z]+', song.get('artist', '').lower()) if len(w) > 3]
    if artist_words and any(w in chan for w in artist_words):
        s += 4  # artist's own channel
    if 'official audio' in title or '(audio)' in title or 'audio song' in title or 'full audio' in title:
        s += 5
    elif 'audio' in title:
        s += 3
    if 'lyric' in title:
        s += 3
    if 'full song' in title:
        s += 1.5
    if 'video' in title:
        s += 0.5
    if 'topic' in chan:  # YouTube Music auto-generated = clean studio audio
        s += 5
    s += min(2.0, (e.get('view_count') or 0) / 5e7)
    return s


def download_audio(song, cache_dir='songs_cache'):
    """Download the official audio for `song` (cached by slug). Returns path to a 44.1 kHz stereo WAV."""
    cache = Path(cache_dir)
    if not cache.is_absolute():
        cache = ROOT / cache
    cache.mkdir(parents=True, exist_ok=True)
    slug = song_slug(song)
    wav, meta_path = cache / f'{slug}.wav', cache / f'{slug}.json'
    if wav.exists() and wav.stat().st_size > 1_000_000:
        return str(wav)

    queries = [song.get('youtube_query') or '',
               f"{song['title']} {song.get('artist', '')} official audio",
               f"{song['title']} {song.get('film') or ''} {song.get('artist', '')} full song"]
    cands = {}
    for q in [q for q in queries if q.strip()]:
        try:
            for e in _yt_search(q):
                sc = _score(e, song)
                if sc is not None and e.get('id'):
                    cands[e['id']] = (max(sc, cands.get(e['id'], (-1,))[0]), e)
        except Exception as ex:
            print(f'  [song] search failed for {q!r}: {ex}')
        if len(cands) >= 3 and max(c[0] for c in cands.values()) >= 12:
            break
    if not cands:
        raise RuntimeError(f"No acceptable YouTube upload found for {song['title']}")
    ranked = sorted(cands.values(), key=lambda c: -c[0])
    for sc, e in ranked[:4]:
        url = f"https://www.youtube.com/watch?v={e['id']}"
        print(f"  [song] downloading [{sc:.1f}] {e.get('title')} | {e.get('channel')} | {e.get('duration')}s")
        tmp_tpl = str(cache / f'{slug}.src.%(ext)s')
        try:
            _run([sys.executable, '-m', 'yt_dlp', '-f', 'bestaudio/best', '--no-playlist', '--no-warnings',
                  '-o', tmp_tpl, url], timeout=600)
        except Exception as ex:
            print(f'  [song] download failed: {str(ex)[-300:]}')
            continue
        srcs = [p for p in cache.glob(f'{slug}.src.*') if not p.name.endswith('.part')]
        if not srcs:
            continue
        src = srcs[0]
        _run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le',
              str(wav)])
        for p in cache.glob(f'{slug}.src.*'):
            p.unlink(missing_ok=True)
        d = probe_duration(wav)
        if not (120 <= d <= 480):
            print(f'  [song] rejected: duration {d:.0f}s')
            wav.unlink(missing_ok=True)
            continue
        meta_path.write_text(json.dumps({'song': song, 'youtube_id': e['id'], 'youtube_title': e.get('title'),
                                         'channel': e.get('channel'), 'duration': d}, indent=2, ensure_ascii=False),
                             encoding='utf-8')
        return str(wav)
    raise RuntimeError(f"All downloads failed for {song['title']}")


# ----------------------------------------------------------------------------------------------- 3. select_segment
STYLE_RULES = (
    'Lyric line rules (these lines are shown one at a time as on-screen captions in an Instagram lyric reel):\n'
    '- Roman-script Hinglish exactly as SUNG (no translation, no Devanagari). Use the standard popular spellings '
    'used on Instagram/YouTube lyric videos: "hoon" (not "hun"/"hu"), "main" (I), "mein" (in), "tera/teri/tere", '
    '"dil", "hai", "hain", "bhi", "kya", "kyun", "nahi", "mujhe", "tujhe", "pyaar", "yaar", "zara", "zindagi", '
    '"ishq", "saath", "baat", "raat", "aankhein", "dhadkan", "sa", "ka", "ki", "ke".\n'
    '- One phrase per line, the way a lyric video would break it: usually 3-6 words (roughly 2-5 s of singing), never more than 7. Split a '
    'long sung phrase at its natural breath/musical break.\n'
    '- Repeated phrases that are sung again get their own new line each time.\n'
    '- Do not write vocalisations like "ooh", "aa", "hmm" unless they are a clearly sung hook; skip pure '
    'instrumental parts (no line there).\n'
    '- No punctuation except apostrophes. No speaker labels, no notes.\n')


def _moment_hint(song):
    try:
        import moments as moments_mod
        m = moments_mod.BY_KEY.get(song.get('moment'))
    except Exception:
        m = None
    if not m:
        return ''
    return (f'The reel\'s illustration shows: "{m["name"]}" ({m["mood"]}). Among the strong, recognisable '
            'parts, prefer the one whose lyrics fit this moment best (e.g. for a sulking/fight picture, lines '
            'about manana / naraazgi; for a sleeping-on-lap picture, calm tender lines). Still never pick a weak '
            'or obscure part just for the words.\n')


def _pass1_window(full_mp3_uri, song, total, duration):
    prompt = (
        f'This is the full audio of the song "{song["title"]}" by {song.get("artist")}'
        f'{" from " + song["film"] if song.get("film") else ""} (total length {_ts(total)} = {total:.1f} s).\n'
        'Listen to the whole track, then choose the single best '
        f'{duration:.0f}-second portion for an Instagram lyric reel: the most iconic, emotional, recognisable part '
        '(usually the hook / mukhda / chorus or the most-quoted lines), with the singer singing almost the WHOLE '
        f'{duration:.0f} s (no instrumental stretch longer than ~3 s inside the window, no dialogue, no long intro).\n'
        'The window must START at the beginning of a sung phrase - never mid-word.\n'
        'All times are seconds from the start of THIS audio file, as precise as you can (decimals).\n'
        'Avoid the very end of the track (outro / fade-out) and the intro.\n'
        + _moment_hint(song) +
        'Return ONLY compact JSON: {"best_start": float (onset of the first sung word of the chosen window), '
        '"alternatives": [float] (2 other good window starts, same rules), '
        '"best_first_words": str, "lyrics_preview": [str] (at most 12 lines sung in the chosen window, Roman '
        'Hinglish), "why": str (one sentence)}')
    return _ask(pick_models('pro'), [{'fileData': {'fileUri': full_mp3_uri, 'mimeType': 'audio/mp3'}},
                                     {'text': prompt}])


def _pass_transcribe(clip_uri, song, clip_len, preview=None, draft=None, insist=False):
    ctx = f'Song: "{song["title"]}" by {song.get("artist")}' + (f' (film/album: {song["film"]})' if song.get('film') else '')
    if draft is None:
        task = (f'{ctx}.\nThis audio clip is {clip_len:.2f} s long and is an excerpt of that song. Transcribe '
                'every sung lyric line in the clip with precise timestamps.')
        if insist:
            task += (' Go through the WHOLE clip from 0 s to the end: there is singing in most of it, and every '
                     'sung line (including repeats of the chorus) must be listed.')
        if preview:
            task += ('\nA rough guess of the lyrics in this area (may be wrong or incomplete - trust the AUDIO): '
                     + ' / '.join(map(str, preview)))
    else:
        task = (f'{ctx}.\nThis audio clip is {clip_len:.2f} s long. Below is a DRAFT transcription with timestamps. '
                'Listen carefully to the clip and return the corrected full list: fix misheard words and spellings, '
                'add missing sung lines, remove lines that are not actually sung in this clip, and correct the '
                'times so each start is exactly when the first syllable of the line is sung and each end is when '
                'its last syllable finishes. Keep lines that are already right unchanged.\nDRAFT:\n'
                + '\n'.join(f'{l["start"]:.2f}-{l["end"]:.2f}  {l["text"]}' for l in draft))
    prompt = (task + '\n\n' + STYLE_RULES +
              '\nTiming: seconds from the start of THIS clip (0.00 = clip start), two decimals. "start" = onset of '
              'the first sung syllable of the line, "end" = when its last syllable ends. Lines in order, no '
              f'overlaps, all within 0..{clip_len:.2f}. Include lines that are only partly inside the clip.\n'
              'Return ONLY JSON: {"lines": [{"text": str, "start": float, "end": float}]}')
    try:
        j = _ask(pick_models('pro'), [{'fileData': {'fileUri': clip_uri, 'mimeType': 'audio/mp3'}},
                                      {'text': prompt}], schema=SCHEMA_LINES)
    except RuntimeError as e:
        print(f'  [song] transcription failed: {e}')
        return []
    raw = json.dumps(j, ensure_ascii=False)
    if isinstance(j, dict):
        lines = j.get('lines') or next((v for v in j.values() if isinstance(v, list)), [])
    else:
        lines = j
    out = []
    for l in lines or []:
        try:
            t = l.get('text') or l.get('line') or l.get('lyrics')
            out.append({'text': str(t).strip(), 'start': float(l['start']), 'end': float(l['end'])})
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    if not out:
        print(f'  [song] transcription returned no lines: {raw[:300]!r}')
    return out


def _rms_profile(path, start, dur, hop=0.02):
    """Short-time RMS (dB) of the source around a region; None if numpy missing."""
    try:
        import numpy as np
    except ImportError:
        return None
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0, start):.3f}', '-t', f'{dur:.3f}', '-i', str(path),
                          '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(16000 * hop)
    if len(a) < n * 4:
        return None
    frames = a[:len(a) // n * n].reshape(-1, n)
    return 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-6), hop


def _vocal_env(path, start, dur, hop=0.01):
    """Rough lead-vocal energy envelope (dB, `hop` s frames): centre-channel spectral subtraction
    (mid power - side power) in the 250-4000 Hz band. Returns (env, hop) or None without numpy."""
    try:
        import numpy as np
    except ImportError:
        return None
    sr = 16000
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0, start):.3f}', '-t', f'{dur:.3f}', '-i', str(path),
                          '-ac', '2', '-ar', str(sr), '-f', 's16le', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, 2) / 32768.0
    if len(a) < sr:
        return None
    mid, side = (a[:, 0] + a[:, 1]) / 2, (a[:, 0] - a[:, 1]) / 2
    n, h = 1024, int(sr * hop)
    win = np.hanning(n).astype(np.float32)
    idx = np.arange(0, len(mid) - n, h)[:, None] + np.arange(n)[None, :]
    f = np.fft.rfftfreq(n, 1 / sr)
    band = (f >= 250) & (f <= 4000)
    pm = (np.abs(np.fft.rfft(mid[idx] * win, axis=1))[:, band] ** 2)
    ps = (np.abs(np.fft.rfft(side[idx] * win, axis=1))[:, band] ** 2)
    v = np.maximum(pm - 1.5 * ps, 0).sum(axis=1)
    env = 10 * np.log10(v + 1e-9)
    env = np.convolve(env, np.ones(5) / 5, mode='same')
    return env, hop


def phrase_onsets(path, start, dur, min_strength=6.0):
    """Candidate sung-phrase onsets (s relative to `start`) as [(t, strength_dB)], strongest dips first.
    An onset = end of a dip in the vocal envelope followed by a rise (a breath/pause then singing)."""
    r = _vocal_env(path, start, dur)
    if r is None:
        return []
    import numpy as np
    env, hop = r
    pre_n, post_n = int(0.25 / hop), int(0.25 / hop)
    m = len(env)
    floor = np.percentile(env, 5)
    s = np.full(m, -99.0)
    for i in range(pre_n, m - post_n):
        pre = env[i - pre_n:i].min()
        post = np.median(env[i:i + post_n])
        local = np.percentile(env[max(0, i - 150):i + 150], 85)
        # rise out of a dip, capped by how deep the dip is relative to the local singing level
        s[i] = min(post - pre, local - pre) - 0.15 * max(0.0, floor - pre)
    out, used = [], np.zeros(m, bool)
    for i in np.argsort(-s):
        if s[i] < min_strength:
            break
        if used[max(0, i - int(0.6 / hop)):i + int(0.6 / hop)].any():
            continue
        used[i] = True
        out.append((round(i * hop, 2), round(float(s[i]), 1)))
    return sorted(out)


def _snap_start(path, t, search=0.6):
    """Move a cut point to the quietest 20 ms frame within +-search s (avoids cutting mid-syllable)."""
    prof = _rms_profile(path, t - search, 2 * search)
    if prof is None:
        return t
    db, hop = prof
    i = int(db.argmin())
    return max(0.0, t - search + i * hop)


def clean_lines(lines, duration, min_len=0.6, hold=1.2, bridge=2.5, lead=0.15):
    """Format text, sort, clamp to 0..duration, fix overlaps, extend display ends.

    A line stays on screen after its last sung word for up to `hold` s, or until the next line if the gap is
    shorter than `bridge` s (the reference reel keeps a line visible until the next one replaces it).
    Each line appears `lead` s before its first sung syllable (the reference shows captions ~0.2 s early).
    """
    ls = []
    for l in sorted(lines, key=lambda x: x['start']):
        text = format_line(l['text'])
        if not text:
            continue
        s, e = max(0.0, l['start'] - lead), min(duration, l['end'])
        if e - s < 0.25 or s >= duration - 0.5:
            continue
        if ls and text == ls[-1]['text'] and s - ls[-1]['end'] < 0.3:  # duplicated fragment
            ls[-1]['end'] = max(ls[-1]['end'], e)
            continue
        ls.append({'text': text, 'start': round(s, 2), 'end': round(e, 2)})
    for i, l in enumerate(ls):
        nxt = ls[i + 1]['start'] if i + 1 < len(ls) else duration
        if l['end'] > nxt:  # overlap -> cut at next start
            l['end'] = nxt
        gap = nxt - l['end']
        l['end'] = nxt if gap <= bridge else l['end'] + hold
        l['end'] = round(min(l['end'], duration), 2)
    ls = [l for l in ls if l['end'] - l['start'] >= min_len * 0.5]
    # validation
    for i, l in enumerate(ls):
        assert 0 <= l['start'] < l['end'] <= duration + 1e-6, l
        if i:
            assert ls[i - 1]['end'] <= l['start'] + 1e-6, (ls[i - 1], l)
    return ls


def _snippet_bounds(audio_path, src_start, duration, strong=8.0, weak=3.0, min_len=0.6, max_len=3.0, max_n=48):
    """Cut points at acoustic phrase onsets: all strong onsets, then weaker ones to split snippets > max_len."""
    on = phrase_onsets(audio_path, src_start, duration, min_strength=weak)
    on = [(t, st) for t, st in on if min_len <= t <= duration - min_len]
    b = [0.0, float(duration)]

    def fits(t):
        return all(abs(t - x) >= min_len for x in b)

    for t, st in sorted(on, key=lambda x: -x[1]):
        if st >= strong and fits(t) and len(b) < max_n:
            b.append(t)
    changed = True
    while changed and len(b) < max_n:
        changed = False
        b.sort()
        for x0, x1 in zip(b, b[1:]):
            if x1 - x0 > max_len:
                inside = [(t, st) for t, st in on if x0 + min_len <= t <= x1 - min_len]
                if inside:
                    b.append(max(inside, key=lambda x: x[1])[0])
                    changed = True
                    break
    return [round(float(x), 2) for x in sorted(b)]


def _align_snippets(audio_path, src_start, duration, song, draft, run_dir):
    import base64
    b = _snippet_bounds(audio_path, src_start, duration)
    if len(b) < 3:
        return None
    parts = []
    for k in range(len(b) - 1):
        mp3 = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{src_start + b[k]:.3f}', '-t', f'{b[k + 1] - b[k]:.3f}',
                              '-i', str(audio_path), '-ac', '1', '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '128k',
                              '-f', 'mp3', '-'], capture_output=True).stdout
        parts += [{'text': f'Snippet {k} ({b[k]:.2f}-{b[k + 1]:.2f} s):'},
                  {'inlineData': {'mimeType': 'audio/mp3', 'data': base64.b64encode(mp3).decode()}}]
    prompt = (
        f'Above are {len(b) - 1} consecutive snippets (in order, no gaps) cut from a {duration:.0f} s excerpt of the '
        f'song "{song["title"]}" by {song.get("artist")}. Snippets were cut at pauses/breaths, so a sung line usually '
        'starts at the beginning of a snippet, and one line may span several snippets.\n'
        'DRAFT lyric lines for this excerpt (from a full-clip transcription; timing unreliable, wording may have '
        'errors, and it may MISS lines - e.g. repeated chorus lines - so listen to every snippet yourself):\n' + '\n'.join(f'- {l["text"]}' for l in draft) + '\n\n'
        'Task: 1) For every snippet, write the words actually sung in it (Roman Hinglish; "" if none / only music). '
        '2) Give the final lyric lines for the excerpt in order (fix wording using what you hear; keep the draft '
        'line splitting unless clearly wrong; drop lines not sung; include a line that is cut off at the start or '
        'end of the excerpt), and for each the index of the snippet where its FIRST word is sung ("first") and '
        'where its LAST word is sung ("last"). If the first word starts clearly later than the beginning of its '
        'snippet (e.g. the snippet begins with the end of the previous line), set "starts_mid": true.\n\n'
        + STYLE_RULES +
        '\nReturn ONLY JSON: {"snippets": [{"i": int, "words": str}], '
        '"lines": [{"text": str, "first": int, "last": int, "starts_mid": bool}]}')
    meta = {}
    j = _ask(pick_models('pro'), parts + [{'text': prompt}], schema=SCHEMA_ALIGN, meta=meta)
    if not isinstance(j, dict):
        return None
    (run_dir / '_pass3.json').write_text(json.dumps({'bounds': b, 'model': meta.get('model'), **j}, indent=2,
                                                    ensure_ascii=False), encoding='utf-8')
    n = len(b) - 1
    draft_starts = [l['start'] for l in draft]
    glines = [l for l in j.get('lines', []) if isinstance(l, dict) and str(l.get('text', '')).strip()]
    # Map lines -> snippets by matching words ourselves (the per-snippet transcriptions are reliable, the
    # model's own first/last indices are often off by one); fall back to its indices when words don't match.
    words = {}
    for sn in j.get('snippets', []):
        try:
            words[int(sn['i'])] = str(sn.get('words', ''))
        except (KeyError, TypeError, ValueError):
            pass
    stoks = [(_norm_tok(w), k, pos, len(words[k].split())) for k in sorted(words) if 0 <= k < n
             for pos, w in enumerate(words[k].split()) if _norm_tok(w)]
    ltoks = [(_norm_tok(w), i, pos) for i, l in enumerate(glines) for pos, w in enumerate(str(l['text']).split())
             if _norm_tok(w)]
    import difflib
    sm = difflib.SequenceMatcher(None, [t[0] for t in stoks], [t[0] for t in ltoks], autojunk=False)
    hit = {}  # line token index -> snippet token index
    for blk in sm.get_matching_blocks():
        for d in range(blk.size):
            hit[blk.b + d] = blk.a + d
    out, prev_start = [], -1.0
    for i, l in enumerate(glines):
        idx = [k for k, t in enumerate(ltoks) if t[1] == i and k in hit]
        f = la = None
        start = None
        if idx and len(idx) >= max(1, 0.5 * sum(1 for t in ltoks if t[1] == i)):
            first_tok, last_tok = stoks[hit[idx[0]]], stoks[hit[idx[-1]]]
            f, la = first_tok[1], last_tok[1]
            lead_words = ltoks[idx[0]][2]  # line words before the first matched one
            pos = max(0, first_tok[2] - lead_words)
            start = b[f] + (b[f + 1] - b[f]) * pos / max(1, first_tok[3]) if pos else b[f]
        else:
            try:
                f, la = int(l['first']), int(l['last'])
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= f < n):
                continue
            la = max(f, min(la, n - 1))
            start = b[f]
            if l.get('starts_mid'):
                inside = [t for t in draft_starts if b[f] < t < b[f + 1]]
                start = inside[0] if inside else b[f] + 0.4 * (b[f + 1] - b[f])
        if start <= prev_start:  # out of order / same snippet as previous line: squeeze after it
            start = prev_start + 0.5 * max(0.3, b[min(n, f + 1)] - prev_start)
        out.append({'text': str(l['text']).strip(), 'start': round(start, 2), 'end': round(b[min(n, la + 1)], 2)})
        prev_start = start
    for i in range(len(out) - 1):
        out[i]['end'] = min(out[i]['end'], out[i + 1]['start'])
    print(f'  [song] pass3 ({meta.get("model")}): {n} snippets -> {len(out)} aligned lines')
    return out


def _norm_tok(w):
    """Spelling-tolerant token for matching Hinglish words ('Ulajhan' ~ 'uljhan', 'hoon' ~ 'hun')."""
    w = re.sub(r'[^a-z]', '', w.lower())
    w = re.sub(r'(.)\1+', r'\1', w).replace('h', '').replace('w', 'v').replace('z', 'j')
    w = w[0] + re.sub(r'[aeiou]', '', w[1:]) if len(w) > 2 else w  # consonant skeleton after the first letter
    return w


def _best_window(abs_lines, hint, duration, lead=0.5, limit=None):
    """Pick the window start (a line onset minus `lead`) near `hint` that maximises sung coverage.
    `limit` = (lo, hi): the window must stay inside the transcribed region."""
    best = None
    for l in abs_lines:
        if not (hint - 4.0 <= l['start'] <= hint + 8.0):
            continue
        if limit and not (limit[0] <= l['start'] - lead and l['start'] - lead + duration <= limit[1] + 1.0):
            continue
        w0, w1 = l['start'] - lead, l['start'] - lead + duration
        cover = sum(max(0.0, min(w1, x['end']) - max(w0, x['start'])) for x in abs_lines)
        cut = any(x['start'] < w1 - 0.3 < x['end'] - 0.8 for x in abs_lines)  # a line chopped near the end
        score = cover - 0.25 * abs(l['start'] - hint) - (0.5 if cut else 0)
        if best is None or score > best[0]:
            best = (score, l['start'], cover)
    return best


def select_segment(audio_path, song, run_dir, duration=30.0, refine=True, source_start=None):
    """Choose + transcribe the reel segment.

    pass 1: full song -> Gemini picks the hook (rough start).
    pass 2: padded ~45 s window -> Gemini transcribes lines (wording good, timestamps often 1-2 s off).
    pass 3: the window is cut into snippets at acoustic phrase onsets; Gemini labels which snippet each line
            starts/ends in -> line starts land on real vocal onsets (typically within ~0.1 s).
    Then the 30 s window is placed just before a line start, cut, faded and loudness-normalised.
    `source_start` (s) forces the window start and skips pass 1. `refine=False` skips pass 3.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = Path(audio_path)
    total = probe_duration(audio_path)
    print(f"  [song] models: {pick_models('pro')}")

    # ---- pass 1: choose the window on the full song
    p1 = {}
    if source_start is None:
        full_mp3 = _mp3(audio_path, run_dir / '_full.mp3')
        full = gemini.upload_file(full_mp3, 'audio/mp3')
        p1 = _pass1_window(full['uri'], song, total, duration)
        if isinstance(p1, list):
            p1 = p1[0]
        (run_dir / '_pass1.json').write_text(json.dumps(p1, indent=2, ensure_ascii=False), encoding='utf-8')
        cands = [p1.get('best_start', p1.get('start'))] + list(p1.get('alternatives') or [])
        cands = [float(c) for c in cands if isinstance(c, (int, float))]
        lo, hi = min(15.0, 0.08 * total), max(0.0, total - duration - 12.0)
        ok = [c for c in cands if lo <= c <= hi]
        hint = ok[0] if ok else (cands[0] if cands else total * 0.35)
        print(f"  [song] pass1 hook ~{_ts(hint)}; why: {str(p1.get('why', ''))[:140]}")
    else:
        hint = float(source_start) + 0.5
    hint = min(max(0.0, hint), max(0.0, total - duration))

    # ---- pass 2: transcribe a padded window (more after than before, so the window can slide)
    w0 = max(0.0, hint - 6.0)
    wlen = min(total - w0, (hint - w0) + duration + 10.0)
    win_mp3 = _mp3(audio_path, run_dir / '_window.mp3', w0, wlen)
    win = gemini.upload_file(win_mp3, 'audio/mp3')
    lines = _pass_transcribe(win['uri'], song, wlen, preview=p1.get('lyrics_preview'))
    sung = sum(max(0.0, l['end'] - l['start']) for l in lines)
    if sung < 0.35 * wlen:  # weak models sometimes transcribe only a couple of lines: try once more
        print(f'  [song] pass2 covered only {sung:.0f}/{wlen:.0f} s; retrying')
        again = _pass_transcribe(win['uri'], song, wlen, preview=p1.get('lyrics_preview'), insist=True)
        if sum(max(0.0, l['end'] - l['start']) for l in again) > sung:
            lines = again
    if not lines:
        raise RuntimeError('Gemini returned no lyric lines')
    (run_dir / '_pass2.json').write_text(json.dumps({'offset': w0, 'lines': lines}, indent=2, ensure_ascii=False),
                                         encoding='utf-8')
    lines = sorted(lines, key=lambda x: x['start'])

    # ---- pass 3: snippet alignment over the whole padded window
    aligned = None
    if refine:
        try:
            aligned = _align_snippets(audio_path, w0, wlen, song, lines, run_dir)
            if not aligned or not (0.6 * len(lines) <= len(aligned) <= 1.6 * len(lines) + 1):
                print(f'  [song] pass3 rejected ({len(aligned or [])} vs {len(lines)} lines)')
                aligned = None
        except Exception as ex:
            print(f'  [song] pass3 failed, keeping pass2 timing: {str(ex)[:200]}')
    if aligned is None:  # fallback: pass-2 times, each start snapped to a strong acoustic onset within 1 s
        on = phrase_onsets(audio_path, w0, wlen, min_strength=8.0)
        aligned = []
        for l in lines:
            near = [t for t, st in on if abs(t - l['start']) <= 1.0]
            st = min(near, key=lambda t: abs(t - l['start'])) if near else l['start']
            aligned.append({**l, 'start': st})
    abs_lines = [{**l, 'start': l['start'] + w0, 'end': l['end'] + w0} for l in aligned]

    # ---- window: start ~0.5 s before a (now accurate) line onset, near Gemini's hook, maximising sung time
    if source_start is not None:
        src_start = float(source_start)
    else:
        best = _best_window(abs_lines, hint, duration, limit=(w0, w0 + wlen))
        first = best[1] if best else min(abs_lines, key=lambda x: abs(x['start'] - hint))['start']
        src_start = _snap_start(audio_path, max(0.0, first - 0.5), search=0.25)
        if not (0.15 <= first - src_start <= 0.9):
            src_start = max(0.0, first - 0.5)
        if best:
            print(f'  [song] window coverage {best[2]:.1f}/{duration:.0f} s sung')
    src_start = round(min(src_start, max(0.0, total - duration)), 3)
    if source_start is None and (src_start < w0 - 0.01 or src_start + duration > w0 + wlen + 1.0):
        # Gemini's hook guess pointed at an instrumental part and the only sung lines lie at the edge of the
        # transcribed region: re-transcribe around the chosen start so the whole 30 s has lyrics.
        print(f'  [song] window {_ts(src_start)} leaves the transcribed region; re-transcribing there')
        return select_segment(audio_path, song, run_dir, duration, refine, source_start=src_start)
    src_end = src_start + duration
    rel = [{**l, 'start': l['start'] - src_start, 'end': l['end'] - src_start} for l in abs_lines
           if l['end'] - src_start > 0.3 and l['start'] - src_start < duration - 0.5]
    print(f'  [song] source window {_ts(src_start)} - {_ts(src_end)}, {len(rel)} lines')

    # ---- final clip: exact duration, fades, loudnorm, AAC 192k 44.1k
    clip = run_dir / 'clip.m4a'
    af = (f'afade=t=in:st=0:d=0.3,afade=t=out:st={duration - 1.5:.3f}:d=1.5,'
          'loudnorm=I=-14:TP=-1:LRA=11,aresample=44100')
    _run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{src_start:.3f}', '-t', f'{duration:.3f}', '-i', str(audio_path),
          '-af', af, '-ac', '2', '-ar', '44100', '-c:a', 'aac', '-b:a', '192k', '-t', f'{duration:.3f}', str(clip)])

    seg_lines = clean_lines(rel, duration)
    try:
        rel_audio = str(clip.relative_to(ROOT)).replace('\\', '/')
    except ValueError:
        rel_audio = str(clip)
    segment = {'audio_path': rel_audio, 'duration': float(duration), 'source_start': src_start,
               'source_end': round(src_end, 3), 'lines': seg_lines}
    (run_dir / 'segment.json').write_text(json.dumps(segment, indent=2, ensure_ascii=False), encoding='utf-8')
    for tmp in ('_full.mp3', '_window.mp3'):
        (run_dir / tmp).unlink(missing_ok=True)
    return segment


# ----------------------------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description='Pick/download a song and build a 30 s segment with timed lyrics')
    ap.add_argument('--song', help='song name hint (omit: Gemini picks)')
    ap.add_argument('--out', default='work/test_audio')
    ap.add_argument('--duration', type=float, default=30.0)
    ap.add_argument('--history', default=str(ROOT / 'history.json'))
    ap.add_argument('--no-refine', action='store_true', help='skip the 3rd Gemini correction pass')
    ap.add_argument('--start', type=float, help='force source start (s), skips Gemini window choice')
    a = ap.parse_args()
    hist = []
    if Path(a.history).exists():
        try:
            hist = json.loads(Path(a.history).read_text(encoding='utf-8'))
        except Exception:
            hist = []
    song = pick_song(hist, a.song)
    print('song:', json.dumps(song, ensure_ascii=False))
    path = download_audio(song)
    print('audio:', path)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'song.json').write_text(json.dumps(song, indent=2, ensure_ascii=False), encoding='utf-8')
    seg = select_segment(path, song, out, a.duration, refine=not a.no_refine, source_start=a.start)
    print(json.dumps(seg, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
