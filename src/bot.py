"""Telegram trigger: control the reel pipeline from the bot chat.

Run on the PC (keep it running):  python src/bot.py     (or double-click start_bot.bat)

Commands (only accepted from your own chat = TELEGRAM_CHAT_ID):
  /reel                 make 1 reel, Gemini picks the song
  /reel <song name>     make 1 reel of that song
  /reels <n>            make n reels (max 5)
  /unlisted <song?>     like /reel but YouTube upload is unlisted (review before public)
  /noyt <song?>         like /reel but skip YouTube (Telegram only)
  /status               what's running / queued
  /stop                 stop the current job (queue cleared)
  /log                  last lines of today's log
  /help
Finished reels arrive in this chat automatically (sent by make_reel.py).
"""
import ctypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import telegram as tg  # noqa: E402  (loads .env)
import moments  # noqa: E402

ROOT = tg.ROOT
OFFSET_FILE = ROOT / 'logs' / 'bot_offset.txt'
WARP = r'C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe'
MAX_BATCH = 5
HELP = '\n'.join([
    '🎵 Reel bot commands',
    '/reel - 1 reel, Gemini picks the song',
    '/reel <song> - 1 reel of that song',
    '/reel payal - 1 reel of that couple moment (see /moments)',
    '/reel payal <song> - that moment with that song',
    '/moments - list all couple moments',
    '/reels 3 - several reels (max 5)',
    '/unlisted <song?> - YouTube upload unlisted',
    '/noyt <song?> - skip YouTube',
    '/noig <song?> - skip Instagram auto-post',
    '/status - running / queue',
    '/stop - stop current job',
    '/log - recent log',
    '/schedule - daily auto-reel times',
    '/pause /resume - pause / resume the daily auto-reels',
])

# ------------------------------------------------------------------------------------------- daily schedule
# Gemini free quota resets at midnight Pacific (~13:30 IST), so the day's reels start after that.
SCHEDULE = [t.strip() for t in os.environ.get('DAILY_REEL_TIMES', '08:00,11:00,14:00,17:00,20:00,22:30').split(',') if t.strip()]
SCHED_FILE = ROOT / 'logs' / 'schedule_state.json'


def _sched_state():
    import json
    try:
        return json.loads(SCHED_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'paused': False, 'done': {}}


def _sched_save(st):
    import json
    SCHED_FILE.write_text(json.dumps(st, indent=2), encoding='utf-8')


def scheduler():
    """Enqueue one reel per slot per day. A slot missed because the PC was off runs as soon as the bot starts
    (same day only), so the day still gets its reels."""
    while True:
        try:
            st = _sched_state()
            today = datetime.now().strftime('%Y-%m-%d')
            st['done'] = {k: v for k, v in st.get('done', {}).items() if v == today}  # forget older days
            if not st.get('paused'):
                now = datetime.now().strftime('%H:%M')
                for slot in SCHEDULE:
                    if now >= slot and st['done'].get(slot) != today:
                        st['done'][slot] = today
                        _sched_save(st)
                        enqueue(f'daily reel ({slot})', [])
            _sched_save(st)
        except Exception as e:
            print(f'[bot] scheduler error: {e}', flush=True)
        time.sleep(30)

queue = deque()          # items: (label, argv, env_overrides)
current = {'proc': None, 'label': None, 'started': None}
lock = threading.Lock()


def say(text):
    try:
        tg._call('sendMessage', data={'chat_id': tg.chat_id(), 'text': text[:4000]})
    except Exception as e:
        print(f'[bot] send failed: {e}', flush=True)


def ensure_warp():
    """api.telegram.org is throttled by the ISP without WARP."""
    if not Path(WARP).exists():
        return
    try:
        st = subprocess.run([WARP, 'status'], capture_output=True, text=True, timeout=20).stdout
        if 'Connected' not in st:
            print('[bot] WARP disconnected -> connecting', flush=True)
            subprocess.run([WARP, 'connect'], capture_output=True, timeout=30)
            time.sleep(5)
    except Exception as e:
        print(f'[bot] warp check failed: {e}', flush=True)


# ------------------------------------------------------------------------------------------- console window
WINDOW_NAME = 'Reel Bot'


class Tee:
    """Everything printed appears in the window and in logs/bot_console.log. The file comes first, and a console
    problem never stops the bot."""

    def __init__(self, stream, path):
        self.stream, self.path = stream, path

    def write(self, text):
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(text)
        except OSError:
            pass
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:
            pass
        return len(text)

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass


def setup_console():
    (ROOT / 'logs').mkdir(exist_ok=True)
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding='utf-8', errors='replace')
    path = ROOT / 'logs' / 'bot_console.log'
    sys.stdout, sys.stderr = Tee(sys.stdout, path), Tee(sys.stderr, path)
    # Enlarge the scroll buffer so you can scroll back through the full log.
    try:
        import ctypes.wintypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        # CONSOLE_SCREEN_BUFFER_INFO: dwSize (SHORT x, SHORT y), plus 10 more SHORTs/DWORDs
        class COORD(ctypes.Structure):
            _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]
        class SMALL_RECT(ctypes.Structure):
            _fields_ = [('Left', ctypes.c_short), ('Top', ctypes.c_short),
                        ('Right', ctypes.c_short), ('Bottom', ctypes.c_short)]
        class CSBI(ctypes.Structure):
            _fields_ = [('dwSize', COORD), ('dwCursorPosition', COORD),
                        ('wAttributes', ctypes.c_ushort), ('srWindow', SMALL_RECT),
                        ('dwMaximumWindowSize', COORD)]
        info = CSBI()
        if k.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
            new_size = COORD(info.dwSize.X, 9000)  # 9000 lines scroll buffer
            k.SetConsoleScreenBufferSize(h, new_size)
    except Exception:
        pass


def set_title(text):
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(text)
    except Exception:
        pass


def next_slot():
    st = _sched_state()
    if st.get('paused'):
        return 'daily reels paused'
    today = datetime.now().strftime('%Y-%m-%d')
    left = [s for s in SCHEDULE if st.get('done', {}).get(s) != today]
    return f'next reel {left[0]}' if left else f'next reel tomorrow {SCHEDULE[0]}'


def title_text():
    with lock:
        label, started, step, waiting = current['label'], current['started'], current.get('step'), len(queue)
    if not label:
        return f'{WINDOW_NAME} - idle - {next_slot()}'
    mins = int((time.time() - started) / 60) if started else 0
    more = f' - {waiting} queued' if waiting else ''
    return f'{WINDOW_NAME} - WORKING {mins}m - {step or "starting"} - {label}{more}'


def title_loop():
    while True:
        set_title(title_text())
        time.sleep(5)


def _warp_state():
    if not Path(WARP).exists():
        return 'not installed'
    try:
        out = subprocess.run([WARP, 'status'], capture_output=True, text=True, timeout=20).stdout
        return 'connected' if 'Connected' in out else 'NOT connected'
    except Exception as e:
        return f'unknown ({e.__class__.__name__})'


def _chrome_state():
    with socket.socket() as c:
        c.settimeout(1)
        up = c.connect_ex(('127.0.0.1', 9333)) == 0
    return 'running (port 9333)' if up else 'not running, opens when a reel needs it'


def banner():
    print('\n'.join([
        '',
        '=' * 74,
        f' REEL BOT - @lafzonmeitu - started {datetime.now():%d %b %H:%M}',
        ' This window is the bot. Closing it stops the daily reels until the next restart.',
        '-' * 74,
        f' Telegram   : listening for commands from your chat only',
        f' Chrome     : {_chrome_state()} - Gemini images, Instagram posting',
        f' WARP       : {_warp_state()} - needed for Telegram',
        f' Schedule   : {", ".join(SCHEDULE)} - {next_slot()}',
        r' Logs       : logs\bot_console.log, logs\bot_job_<time>.log',
        '=' * 74,
        '',
    ]), flush=True)


# ------------------------------------------------------------------------------------------- jobs
def _pump(p, log_path):
    """Copy the job's output line by line to its log file and the window. Keeps draining whatever happens,
    otherwise a full pipe would freeze the reel."""
    with open(log_path, 'w', encoding='utf-8') as lf:
        for line in p.stdout:
            line = line.rstrip('\r\n')
            lf.write(line + '\n')
            lf.flush()
            m = re.search(r'-> (\w+)', line)
            if m and line[:2].isdigit():
                with lock:
                    current['step'] = m.group(1)
            print(line, flush=True)


def run_job(argv, env, log_path, on_start=None):
    p = subprocess.Popen([sys.executable, '-u', str(ROOT / 'make_reel.py'), *argv], cwd=str(ROOT),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                         encoding='utf-8', errors='replace')
    if on_start:
        on_start(p)
    t = threading.Thread(target=_pump, args=(p, log_path), daemon=True)
    t.start()
    rc = p.wait()
    t.join(5)  # a browser started by the job can hold the pipe open forever; the job itself has ended
    return rc


def _worker_loop():
    while True:
        with lock:
            job = queue.popleft() if queue else None
        if job is None:
            time.sleep(2)
            continue
        label, argv, env_over = job
        env = {**os.environ, **env_over, 'PYTHONIOENCODING': 'utf-8'}
        say(f'▶️ Starting: {label}\n(≈8-10 min per reel; the video will arrive here)')
        log_path = ROOT / 'logs' / f'bot_job_{datetime.now():%Y%m%d_%H%M%S}.log'
        t0 = time.time()
        print(f"\n{'=' * 74}\n START {datetime.now():%H:%M:%S}  {label}\n log: {log_path.name}\n{'=' * 74}", flush=True)

        def started(p):
            with lock:
                current.update(proc=p, label=label, started=t0, step=None)

        rc = run_job(argv, env, log_path, started)
        with lock:
            stopped = current.get('stopped')
            current.update(proc=None, label=None, started=None, stopped=False, step=None)
        result = 'STOPPED' if stopped else 'DONE' if rc == 0 else f'PROBLEMS (exit {rc})'
        print(f"{'=' * 74}\n {result} {datetime.now():%H:%M:%S}  {label}  ({(time.time() - t0) / 60:.0f} min)\n"
              f" {next_slot()}\n{'=' * 74}\n", flush=True)
        tail = _tail(log_path, 12, only=('=== ', 'OK', 'FAILED', 'QA-FAIL', 'quota', 'youtube', 'telegram',
                                                'instagram'))
        mins = (time.time() - t0) / 60
        if stopped:
            say(f'⏹ Stopped: {label}')
        elif rc == 0:
            say(f'✅ Done: {label} ({mins:.0f} min)\n{tail}')
        else:
            say(f'⚠️ Finished with problems: {label} ({mins:.0f} min)\n{tail}')


def worker():
    """Never let the job thread die: a crash used to leave the bot answering but running nothing."""
    import traceback
    while True:
        try:
            _worker_loop()
        except Exception as e:
            print('[bot] worker crashed: ' + traceback.format_exc(), flush=True)
            with lock:
                current.update(proc=None, label=None, started=None, stopped=False)
            say(f'⚠️ Job runner error ({e.__class__.__name__}: {str(e)[:200]}) - recovered, send the command again.')
            time.sleep(5)


def _tail(path, n, only=None):
    try:
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return ''
    if only:
        lines = [l for l in lines if any(k in l for k in only)]
    return '\n'.join(l[-300:] for l in lines[-n:])


def enqueue(label, argv, env_over=None):
    with lock:
        queue.append((label, argv, env_over or {}))
        pos = len(queue) + (1 if current['proc'] else 0)
    if pos > 1:
        say(f'🕒 Queued: {label} (position {pos})')


# ------------------------------------------------------------------------------------------- commands
def handle(text):
    text = (text or '').strip()
    if not text.startswith('/'):
        say('Send /reel, /reel <song>, /reels 3, /status or /help')
        return
    cmd, _, arg = text.partition(' ')
    cmd = cmd.split('@')[0].lower()
    arg = arg.strip()
    song_args = []
    first, _, rest = arg.partition(' ')
    mo = moments.find(first)
    if mo:
        song_args += ['--moment', mo['key']]
        arg = rest.strip()
    if arg:
        song_args += ['--song', arg]
    if mo:
        arg = f"{mo['name']}{' / ' + arg if arg else ''}" 
    if cmd in ('/start', '/help'):
        say(HELP)
    elif cmd == '/reel':
        enqueue(f"reel{' - ' + arg if arg else ' (Gemini picks the song)'}", song_args)
    elif cmd == '/reels':
        try:
            n = max(1, min(MAX_BATCH, int(arg or '1')))
        except ValueError:
            return say('Usage: /reels 3')
        enqueue(f'{n} reels', ['--count', str(n)])
    elif cmd == '/unlisted':
        enqueue(f"reel (YouTube unlisted){' - ' + arg if arg else ''}", song_args, {'YT_PRIVACY': 'unlisted'})
    elif cmd == '/noyt':
        enqueue(f"reel (no YouTube){' - ' + arg if arg else ''}", song_args + ['--no-youtube'])
    elif cmd == '/noig':
        enqueue(f"reel (no Instagram){' - ' + arg if arg else ''}", song_args + ['--no-instagram'])
    elif cmd == '/moments':
        say('Couple moments (/reel <word>):\n' + moments.help_text())
    elif cmd == '/status':
        with lock:
            cur, q = current['label'], [j[0] for j in queue]
            st = current['started']
        msg = f"Running: {cur} ({(time.time() - st) / 60:.0f} min)" if cur else 'Idle'
        if q:
            msg += '\nQueue:\n' + '\n'.join(f'{i + 1}. {l}' for i, l in enumerate(q))
        say(msg)
    elif cmd == '/stop':
        with lock:
            queue.clear()
            p = current['proc']
            if p:
                current['stopped'] = True
        if p:
            subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True)
        else:
            say('Nothing running.')
    elif cmd == '/schedule':
        st = _sched_state()
        today = datetime.now().strftime('%Y-%m-%d')
        lines = [f"{s}  {'✅ done today' if st.get('done', {}).get(s) == today else '⏳ pending'}" for s in SCHEDULE]
        say(('⏸ PAUSED\n' if st.get('paused') else '') + 'Daily auto-reels:\n' + '\n'.join(lines))
    elif cmd in ('/pause', '/resume'):
        st = _sched_state()
        st['paused'] = cmd == '/pause'
        _sched_save(st)
        say('⏸ Daily auto-reels paused.' if st['paused'] else '▶️ Daily auto-reels resumed.')
    elif cmd == '/log':
        logs = sorted((ROOT / 'logs').glob('2*.log'))
        say(_tail(logs[-1], 25) if logs else 'No log yet.')
    else:
        say('Unknown command. /help')


# ------------------------------------------------------------------------------------------- main loop
def main():
    setup_console()
    ensure_warp()
    me = tg.chat_id()  # your chat only
    offset = int(OFFSET_FILE.read_text()) if OFFSET_FILE.exists() else 0
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=title_loop, daemon=True).start()
    try:
        tg._call('setMyCommands', data={'commands': (
            '[{"command":"reel","description":"Make a reel (optional: song name)"},'
            '{"command":"reels","description":"Make N reels"},'
            '{"command":"moments","description":"List couple moments"},'
            '{"command":"unlisted","description":"Reel, YouTube unlisted"},'
            '{"command":"noyt","description":"Reel, skip YouTube"},'
            '{"command":"noig","description":"Reel, skip Instagram"},'
            '{"command":"status","description":"What is running"},'
            '{"command":"stop","description":"Stop current job"},'
            '{"command":"log","description":"Recent log"},'
            '{"command":"schedule","description":"Daily auto-reel times"},'
            '{"command":"pause","description":"Pause daily auto-reels"},'
            '{"command":"resume","description":"Resume daily auto-reels"}]')})
    except Exception:
        pass
    say('🤖 Reel bot online. /help for commands.')
    banner()
    print('[bot] listening...', flush=True)
    fails = 0
    while True:
        try:
            updates = tg._call('getUpdates', timeout=70, params={'offset': offset, 'timeout': 50})
            fails = 0
        except Exception as e:
            fails += 1
            print(f'[bot] poll error: {str(e)[:120]}', flush=True)
            if fails % 3 == 0:
                ensure_warp()
            time.sleep(min(60, 5 * fails))
            continue
        for u in updates:
            offset = u['update_id'] + 1
            OFFSET_FILE.write_text(str(offset))
            msg = u.get('message') or {}
            if str((msg.get('chat') or {}).get('id')) != str(me):
                continue  # ignore everyone else
            print(f"[bot] {datetime.now():%H:%M:%S} <- {msg.get('text')!r}", flush=True)
            try:
                handle(msg.get('text'))
            except Exception as e:
                say(f'Error: {e}')


if __name__ == '__main__':
    main()
