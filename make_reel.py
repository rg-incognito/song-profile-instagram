"""Song-profile reel pipeline orchestrator.

    python make_reel.py                       # 1 reel, Gemini picks the song
    python make_reel.py --count 3             # batch of 3 (one failure doesn't stop the rest)
    python make_reel.py --song "Tum Hi Ho"    # specific song
    python make_reel.py --post                # also publish to Instagram (needs IG_* in .env, QA must pass)
    python make_reel.py --dry-run --count 5   # only pick songs, nothing else
    python make_reel.py --resume <run_id>     # continue a failed run, reusing work/<run_id>/ artifacts
"""
import argparse
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
os.chdir(ROOT)  # segment audio paths are relative to the project root

HISTORY = ROOT / 'history.json'
WORK = ROOT / 'work'
OUTPUT = ROOT / 'output'
LOGS = ROOT / 'logs'
SEGMENT_SECONDS = 30.0

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

_logfile = None


def log(msg=''):
    line = f'{datetime.now():%H:%M:%S} {msg}'
    print(line, flush=True)
    if _logfile:
        with open(_logfile, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    except Exception as e:
        log(f'WARNING: could not read {path}: {e}')
        return default


def save_json(path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def rel(p):
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def slugify(s):
    import re
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:40] or 'song'


class Step:
    """Context manager: logs start/end with timing, records into the run state."""

    def __init__(self, state, name):
        self.state, self.name = state, name

    def __enter__(self):
        self.t0 = time.time()
        log(f'  -> {self.name}')
        return self

    def __exit__(self, et, ev, tb):
        dt = time.time() - self.t0
        ok = et is None
        self.state.setdefault('steps', {})[self.name] = {'ok': ok, 'seconds': round(dt, 1),
                                                         **({} if ok else {'error': str(ev)[:500]})}
        log(f"  <- {self.name} {'ok' if ok else 'FAILED'} ({dt:.1f}s){'' if ok else ': ' + str(ev)[:300]}")
        return False


def make_one(run_id, history, hint=None, post=False, keep_work=False, vision_qa=True, telegram=True, youtube=True,
             instagram_web_on=True, moment_key=None, force_telegram=False):
    try:  # imported lazily so --dry-run only needs song.py
        import song as song_mod
        import image_gen
        import render
        import caption as caption_mod
        import qa
        import instagram
    except Exception as e:
        log(f'  cannot import pipeline modules: {type(e).__name__}: {e}')
        return {'run_id': run_id or '(none)', 'ok': False, 'error': f'import: {e}'}

    moment = None
    if moment_key:
        import moments as moments_mod
        moment = moments_mod.find(moment_key)
    pre_state, picked = {}, None
    if run_id is None:  # new run: pick the song first so the run id can carry its slug
        try:
            with Step(pre_state, 'pick_song'):
                picked = song_mod.pick_song(history, hint, moment=moment)
        except Exception as e:
            return {'run_id': '(unpicked)', 'ok': False, 'error': f'pick_song: {e}'}
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(picked['title'])}"
        log(f'  run_id: {run_id}')
    run_dir = WORK / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    state_path = run_dir / 'run.json'
    state = load_json(state_path, {'run_id': run_id, 'started': datetime.now().isoformat(timespec='seconds')})
    state.setdefault('steps', {}).update(pre_state.get('steps', {}))
    if picked:
        save_json(run_dir / 'song.json', picked)
    mp4 = OUTPUT / f'{run_id}.mp4'
    txt = OUTPUT / f'{run_id}.txt'
    t_start = time.time()
    try:
        # 1. song
        song_path = run_dir / 'song.json'
        if song_path.exists():
            song = load_json(song_path, None)
            log(f"  reuse song.json: {song['title']} - {song['artist']}")
        else:
            with Step(state, 'pick_song'):
                song = song_mod.pick_song(history, hint, moment=moment)
            save_json(song_path, song)
        log(f"  song: {song['title']} - {song['artist']} ({song.get('film') or 'single'}, {song.get('year')}) "
            f"[{song.get('source', '?')}] moment: {song.get('moment', '-')}")
        state['song'] = song

        # 2-3. audio + segment
        seg_path = run_dir / 'segment.json'
        segment = load_json(seg_path, None) if seg_path.exists() else None
        if segment and Path(segment['audio_path']).exists():
            log(f"  reuse segment.json ({len(segment['lines'])} lines)")
        else:
            with Step(state, 'download_audio'):
                audio = song_mod.download_audio(song)
            with Step(state, 'select_segment'):
                segment = song_mod.select_segment(audio, song, run_dir, SEGMENT_SECONDS)
            save_json(seg_path, segment)
        for l in segment['lines']:
            log(f"     {l['start']:6.2f}-{l['end']:6.2f}  {l['text']}")

        # 4. image
        img = run_dir / 'image.png'
        if img.exists() and img.stat().st_size > 10_000:
            log('  reuse image.png')
        else:
            with Step(state, 'generate_image'):
                image_gen.generate_image(song, img)

        # 5. render
        if mp4.exists() and state.get('steps', {}).get('render_video', {}).get('ok'):
            log(f'  reuse {mp4.name}')
        else:
            with Step(state, 'render_video'):
                render.render_video(str(img), segment, str(mp4))

        # 6. caption
        if txt.exists() and txt.stat().st_size > 0:
            cap = txt.read_text(encoding='utf-8')
            log('  reuse caption')
        else:
            with Step(state, 'make_caption'):
                cap = caption_mod.make_caption(song, segment)
            txt.write_text(cap, encoding='utf-8')
        log('  caption: ' + cap.replace('\n', ' | '))

        # 7. QA
        with Step(state, 'qa'):
            result = qa.run_qa(mp4, segment, run_dir, vision=vision_qa, log=log)
            pj = Path(mp4).with_suffix('.placement.json')
            if pj.exists() and not json.loads(pj.read_text(encoding='utf-8')).get('clean', True):
                result['ok'] = False
                result['problems'].append('lyrics would touch the characters during the camera move '
                                          '(no clean space in this image) - regenerate the image')
        save_json(run_dir / 'qa.json', result)
        state['qa'] = {'ok': result['ok'], 'problems': result['problems']}

        # history: the reel exists now, so this song counts as used
        entry = {'run_id': run_id, 'song': song, 'created': datetime.now().isoformat(timespec='seconds'),
                 'video': rel(mp4), 'qa_ok': result['ok'], 'posted': False}
        disk_hist = load_json(HISTORY, [])
        disk_hist = [h for h in disk_hist if not (isinstance(h, dict) and h.get('run_id') == run_id)] + [entry]
        save_json(HISTORY, disk_hist)

        # 8a. Telegram delivery (user posts to Instagram by hand). Sent even if QA flagged something:
        #     the notes travel with the video so the user decides.
        if force_telegram:
            state.pop('telegram_sent', None)
        if telegram and not state.get('telegram_sent'):
            import telegram as tg
            if tg.enabled():
                try:
                    with Step(state, 'telegram'):
                        tg.send_reel(mp4, cap, title=f"{song.get('title')} - {song.get('artist')}",
                                     problems=result['problems'])
                    state['telegram_sent'] = True
                    save_json(state_path, state)
                except Exception as e:  # never lose the reel over a delivery hiccup
                    log(f'  telegram send failed: {e} (video is still in output/; retry: '
                        f'python src/telegram.py --send {rel(mp4)} --caption-file {rel(txt)})')
                    # text-only fallback so the user gets notified even when the video upload fails
                    try:
                        tg._call('sendMessage', data={'chat_id': tg.chat_id(),
                                                      'text': f'⚠️ Telegram video send failed: {str(e)[:200]}\n'
                                                              f'Video saved: output/{mp4.name}\n'
                                                              f'📋 Retry: /resume {run_id}'})
                    except Exception:
                        pass

        # 8b. YouTube Shorts (public post -> only when QA passed; never twice)
        if youtube:
            import youtube as yt
            if not yt.is_configured():
                log('  youtube: not authorised yet (python src/youtube.py --auth) -> skipped')
            elif state.get('yt_video_id'):
                log(f"  youtube: already uploaded ({state['yt_video_id']})")
            elif not result['ok']:
                log('  youtube: QA not passed -> NOT uploading. Re-run with --resume ' + run_id)
            else:
                try:
                    with Step(state, 'youtube'):
                        meta = yt.make_metadata(song, segment, cap)
                        save_json(run_dir / 'yt_meta.json', meta)
                        state['yt_video_id'] = yt.upload_short(mp4, meta, log=log)
                    save_json(state_path, state)
                    disk_hist = load_json(HISTORY, [])
                    for h in disk_hist:
                        if isinstance(h, dict) and h.get('run_id') == run_id:
                            h['yt_video_id'] = state['yt_video_id']
                    save_json(HISTORY, disk_hist)
                    if telegram:
                        try:
                            import telegram as tg
                            if tg.enabled():
                                tg._call('sendMessage', data={'chat_id': tg.chat_id(), 'text':
                                         f"▶️ Posted on YouTube: https://youtube.com/shorts/{state['yt_video_id']}"})
                        except Exception:
                            pass
                except Exception as e:
                    log(f'  youtube upload failed: {str(e)[:300]}')

        # 8c. Instagram via the pipeline Chrome (instagram.com); only when QA passed; never twice
        if instagram_web_on and os.environ.get('IG_EXPECTED_USERNAME', '').strip():
            import instagram_web as igw
            if state.get('ig_posted'):
                log('  instagram: already posted')
            elif not result['ok']:
                log('  instagram: QA not passed -> NOT posting. Re-run with --resume ' + run_id)
            else:
                try:
                    with Step(state, 'instagram_web'):
                        url = igw.post_reel(mp4, cap, log=log)
                    state['ig_posted'] = True
                    save_json(state_path, state)
                    if os.environ.get('IG_COMMENT', 'on').lower() != 'off':
                        try:  # never let a comment problem touch the posted reel
                            with Step(state, 'instagram_comment'):
                                url = igw.comment_on_latest(cap, caption_mod.make_comment(song, segment),
                                                            log=log) or url
                            state['ig_commented'] = True
                            save_json(state_path, state)
                        except Exception as e:
                            log(f'  instagram comment failed: {str(e)[:300]}')
                    disk_hist = load_json(HISTORY, [])
                    for h in disk_hist:
                        if isinstance(h, dict) and h.get('run_id') == run_id:
                            h['posted'] = True
                            if url:
                                h['ig_url'] = url
                            h['posted_at'] = datetime.now().isoformat(timespec='seconds')
                    save_json(HISTORY, disk_hist)
                    entry['posted'] = True
                    if url:
                        entry['ig_url'] = url
                    entry['posted_at'] = datetime.now().isoformat(timespec='seconds')
                    if telegram:
                        try:
                            import telegram as tg
                            if tg.enabled():
                                tg._call('sendMessage', data={'chat_id': tg.chat_id(),
                                                              'text': f'📸 Posted on Instagram: {url}'})
                        except Exception:
                            pass
                except Exception as e:
                    log(f'  instagram post failed: {str(e)[:300]} (post by hand from Telegram)')

        # 8. publish (Graph API, optional)
        if post:
            if not result['ok']:
                log('  QA FAILED -> not posting. Fix and re-run with --resume ' + run_id)
            elif not instagram.is_configured():
                instagram.publish_reel(mp4, cap, log=log)  # prints the skip message
            elif state.get('media_id'):
                log(f"  already posted (media id {state['media_id']})")
            else:
                with Step(state, 'publish_reel'):
                    media_id = instagram.publish_reel(mp4, cap, log=log)
                state['media_id'] = media_id
                entry.update(posted=True, media_id=media_id)
                disk_hist = load_json(HISTORY, [])
                for h in disk_hist:
                    if isinstance(h, dict) and h.get('run_id') == run_id:
                        h.update(posted=True, media_id=media_id)
                save_json(HISTORY, disk_hist)

        state['done'] = True
        state.pop('error', None)
        state.pop('traceback', None)
        state['seconds'] = round(time.time() - t_start, 1)
        save_json(state_path, state)
        if not keep_work and result['ok']:
            # keep the inputs needed for --resume small: drop the bulky work dir only on a clean success
            shutil.rmtree(run_dir, ignore_errors=True)
        history.append(entry)
        return {'run_id': run_id, 'ok': result['ok'], 'video': str(mp4), 'caption': str(txt),
                'problems': result['problems'], 'posted': bool(state.get('media_id'))}
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
        state['traceback'] = traceback.format_exc()[-4000:]
        save_json(state_path, state)
        log(f'  REEL FAILED: {state["error"][:400]}')
        log(f'  (work kept in {run_dir}; retry with: python make_reel.py --resume {run_id})')
        return {'run_id': run_id, 'ok': False, 'error': state['error']}


def post_only(run_id, telegram=True, youtube=True, instagram_web_on=True, force_telegram=False):
    """Retry the delivery steps (Telegram / YouTube / Instagram) for a reel whose work dir was cleaned up.
    Needs output/<run_id>.mp4 (and optionally .txt). Looks up song + prior state from history.json."""
    mp4 = OUTPUT / f'{run_id}.mp4'
    txt = OUTPUT / f'{run_id}.txt'
    if not mp4.exists():
        log(f'  output/{run_id}.mp4 not found')
        return {'run_id': run_id, 'ok': False, 'error': 'mp4 not found'}
    cap = txt.read_text(encoding='utf-8', errors='replace') if txt.exists() else ''

    hist = load_json(HISTORY, [])
    entry = next((h for h in reversed(hist) if isinstance(h, dict) and h.get('run_id') == run_id), {})
    song = entry.get('song', {})
    t_start = time.time()
    log(f"  song: {song.get('title', '?')} - {song.get('artist', '?')}")

    # Telegram
    if telegram:
        import telegram as tg
        if tg.enabled():
            if not force_telegram and entry.get('telegram_sent'):
                log('  telegram: already sent (use /repost to force)')
            else:
                try:
                    tg.send_reel(mp4, cap, title=f"{song.get('title', run_id)} - {song.get('artist', '')}", problems=[])
                    for h in hist:
                        if isinstance(h, dict) and h.get('run_id') == run_id:
                            h['telegram_sent'] = True
                    save_json(HISTORY, hist)
                    log(f'  telegram: sent ({mp4.stat().st_size / 1e6:.1f} MB)')
                except Exception as e:
                    log(f'  telegram send failed: {str(e)[:300]}')

    # YouTube — skip if already uploaded (yt_video_id in history); no segment = skip silently
    if youtube:
        import youtube as yt
        if entry.get('yt_video_id'):
            log(f"  youtube: already uploaded ({entry['yt_video_id']})")
        elif not yt.is_configured():
            log('  youtube: not authorised -> skipped')
        else:
            log('  youtube: skipped in post-only mode (no segment data for metadata)')

    # Instagram
    if instagram_web_on and os.environ.get('IG_EXPECTED_USERNAME', '').strip():
        import instagram_web as igw
        if entry.get('posted'):
            log('  instagram: already posted')
        else:
            try:
                url = igw.post_reel(mp4, cap, log=log)
                log(f'  instagram posted: {url}')
                for h in hist:
                    if isinstance(h, dict) and h.get('run_id') == run_id:
                        h['posted'] = True
                save_json(HISTORY, hist)
                if telegram:
                    try:
                        import telegram as tg
                        if tg.enabled():
                            tg._call('sendMessage', data={'chat_id': tg.chat_id(),
                                                          'text': f'📸 Posted on Instagram: {url}'})
                    except Exception:
                        pass
            except Exception as e:
                log(f'  instagram post failed: {str(e)[:300]} (post by hand from Telegram)')

    log(f"  post_only done in {time.time() - t_start:.0f}s")
    return {'run_id': run_id, 'ok': True, 'video': str(mp4)}


def dry_run(count, hint):
    import song as song_mod
    history = load_json(HISTORY, [])
    picks = []
    for i in range(count):
        t0 = time.time()
        try:
            s = song_mod.pick_song(history + [{'song': p} for p in picks], hint)
            picks.append(s)
            log(f"[{i + 1}/{count}] <{s.get('moment')}|{s.get('source')}> {s['title']} - {s['artist']} | {s.get('film')} {s.get('year')} | {s.get('mood')} "
                f"| yt: {s['youtube_query']} ({time.time() - t0:.1f}s)")
        except Exception as e:
            log(f'[{i + 1}/{count}] pick_song FAILED: {e}')
    return picks


def main():
    global _logfile
    ap = argparse.ArgumentParser(description='Make Instagram song-lyric reels')
    ap.add_argument('--count', type=int, default=1, help='number of reels to make')
    ap.add_argument('--song', help='song name hint (default: Gemini picks an unused song)')
    ap.add_argument('--moment', help='couple moment key/alias from src/moments.py (default: rotate)')
    ap.add_argument('--post', action='store_true', help='publish to Instagram after QA passes')
    ap.add_argument('--no-instagram', action='store_true', help='do not post to Instagram via Chrome')
    ap.add_argument('--no-youtube', action='store_true', help='do not upload to YouTube')
    ap.add_argument('--no-telegram', action='store_true', help='do not send the reel to the Telegram bot')
    ap.add_argument('--keep-work', action='store_true', help='keep work/<run_id>/ after success')
    ap.add_argument('--resume', metavar='RUN_ID', help='resume a previous run, reusing its work dir')
    ap.add_argument('--dry-run', action='store_true', help='only pick songs (no download/render)')
    ap.add_argument('--no-vision-qa', action='store_true', help='skip the Gemini frame check (ffprobe QA still runs)')
    ap.add_argument('--force-telegram', action='store_true', help='re-send to Telegram even if already sent')
    ap.add_argument('--post-only', action='store_true', help='skip render/QA, only retry delivery for a completed reel')
    a = ap.parse_args()

    LOGS.mkdir(exist_ok=True)
    _logfile = LOGS / f'{datetime.now():%Y%m%d}.log'
    log(f"=== make_reel {' '.join(sys.argv[1:])}")

    if a.dry_run:
        dry_run(a.count, a.song)
        return 0

    # --post-only: retry delivery for a reel that rendered ok but posting failed / work dir was cleaned up
    if getattr(a, 'post_only', False):
        if not a.resume:
            log('--post-only requires --resume <run_id>')
            return 2
        log(f'=== post-only {a.resume}')
        r = post_only(a.resume, not a.no_telegram, not a.no_youtube, not a.no_instagram, a.force_telegram)
        log(f"=== {r['run_id']}: {'OK' if r.get('ok') else 'FAILED'}")
        return 0 if r.get('ok') else 1

    history = load_json(HISTORY, [])
    if a.resume:
        if not (WORK / a.resume).is_dir():
            log(f'no such run: work/{a.resume}')
            return 2
        run_ids = [a.resume]
    else:
        run_ids = None

    results = []
    n = 1 if run_ids else a.count
    for i in range(n):
        log(f'=== reel {i + 1}/{n}' + (f': {run_ids[0]}' if run_ids else ''))
        t0 = time.time()
        r = make_one(run_ids[0] if run_ids else None, history, a.song, a.post, a.keep_work, not a.no_vision_qa,
                      not a.no_telegram, not a.no_youtube, not a.no_instagram, a.moment, a.force_telegram)
        log(f"=== reel {r['run_id']}: {'OK' if r.get('ok') else 'FAILED'} in {time.time() - t0:.0f}s")
        results.append(r)
        if not r.get('ok') and 'quota' in str(r.get('error', '')).lower():
            log('=== Gemini API free-tier quota is used up for today. Stopping the batch instead of using weaker models.')
            log('    It resets at midnight Pacific time (~1:30 PM IST). Then continue with:')
            log(f"    python make_reel.py --resume {r['run_id']}")
            break

    log('=== summary')
    for r in results:
        if r.get('ok'):
            log(f"  OK      {r['run_id']} -> {r['video']}{' (posted)' if r.get('posted') else ''}")
        elif 'error' in r:
            log(f"  FAILED  {r['run_id']}: {r['error'][:200]}")
        else:
            log(f"  QA-FAIL {r['run_id']} -> {r['video']}: {'; '.join(r['problems'])[:300]}")
    return 0 if all(r.get('ok') for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
