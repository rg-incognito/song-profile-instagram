"""Instagram reel analytics: scrape view/like counts and report best-performing post times.

fetch_views(url) -> {'views': int|None, 'likes': int|None}
update_history_views(history_path) -> updated list
best_times(history) -> analysis dict
"""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path


def _parse_count(text):
    """'1.2M' -> 1200000, '45K' -> 45000, '1,234' -> 1234, None on failure."""
    if not text:
        return None
    text = text.strip().replace(',', '').replace(' ', '')
    m = re.match(r'^([\d.]+)([KkMmBb]?)$', text)
    if not m:
        return None
    n, suffix = float(m.group(1)), m.group(2).upper()
    return int(n * {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}.get(suffix, 1))


def fetch_views(url, timeout_s=30):
    """Visit an Instagram reel URL and return {'views': int|None, 'likes': int|None, 'url': url}."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gemini_web  # re-use the already-running Chrome profile
        from playwright.sync_api import sync_playwright

        gemini_web.ensure_chrome()
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9333')
            ctx = browser.contexts[0]
            page = ctx.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=timeout_s * 1000)
                page.wait_for_timeout(4000)

                # view count — Instagram shows it as "X views" or "X plays" near the reel
                views = None
                for sel in [
                    'span[class*="view"]', 'span[class*="play"]',
                    'section span span', 'div[class*="metric"] span',
                    'span:has-text("views")', 'span:has-text("plays")',
                ]:
                    try:
                        els = page.locator(sel).all()
                        for el in els:
                            t = (el.inner_text() or '').strip()
                            if re.search(r'\d', t):
                                v = _parse_count(re.sub(r'[^\d.KkMmBb]', '', t))
                                if v and v > 0:
                                    views = v
                                    break
                        if views:
                            break
                    except Exception:
                        pass

                # like count
                likes = None
                for sel in ['section span[aria-label*="like" i]', 'button[type="button"] span span']:
                    try:
                        els = page.locator(sel).all()
                        for el in els:
                            t = (el.inner_text() or '').strip()
                            if re.search(r'\d', t):
                                v = _parse_count(re.sub(r'[^\d.KkMmBb]', '', t))
                                if v is not None:
                                    likes = v
                                    break
                        if likes is not None:
                            break
                    except Exception:
                        pass

                return {'views': views, 'likes': likes, 'url': url}
            finally:
                page.close()
    except Exception as e:
        return {'views': None, 'likes': None, 'url': url, 'error': str(e)[:200]}


def update_history_views(history_path):
    """Read history.json, fetch views for every posted entry that has an ig_url, save back."""
    history_path = Path(history_path)
    history = json.loads(history_path.read_text(encoding='utf-8'))
    changed = False
    for entry in history:
        if not isinstance(entry, dict):
            continue
        url = entry.get('ig_url')
        if not url or not entry.get('posted'):
            continue
        # only re-check if no views yet, or last check was >6h ago
        last = entry.get('views_checked_at')
        if entry.get('views') and last:
            age_h = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
            if age_h < 6:
                continue
        result = fetch_views(url)
        if result.get('views') is not None:
            entry['views'] = result['views']
        if result.get('likes') is not None:
            entry['likes'] = result['likes']
        entry['views_checked_at'] = datetime.now().isoformat(timespec='minutes')
        changed = True
        time.sleep(2)
    if changed:
        history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding='utf-8')
    return history


def best_times(history):
    """Analyse posting hours vs views. Returns sorted list of (hour_IST, avg_views, count)."""
    from collections import defaultdict
    slots = defaultdict(list)
    for entry in history:
        if not isinstance(entry, dict):
            continue
        views = entry.get('views')
        posted_at = entry.get('posted_at') or entry.get('created')
        if not views or not posted_at:
            continue
        try:
            dt = datetime.fromisoformat(posted_at)
            # created is local time (assumed IST already); just use the hour
            slots[dt.hour].append(views)
        except Exception:
            pass
    result = []
    for hour, v_list in sorted(slots.items()):
        result.append({
            'hour_ist': hour,
            'avg_views': int(sum(v_list) / len(v_list)),
            'max_views': max(v_list),
            'count': len(v_list),
        })
    result.sort(key=lambda x: x['avg_views'], reverse=True)
    return result


def summary_text(history):
    """Return a Telegram-ready summary of recent reel performance."""
    lines = ['📊 *Reel Analytics*\n']
    posted = [e for e in history if isinstance(e, dict) and e.get('posted') and e.get('ig_url')]
    if not posted:
        return 'No posted reels with Instagram URLs tracked yet.'

    # recent 10
    recent = posted[-10:]
    for e in reversed(recent):
        song = e.get('song', {})
        title = song.get('title', e.get('run_id', '?'))
        views = e.get('views')
        likes = e.get('likes')
        posted_at = (e.get('posted_at') or e.get('created') or '')[:16]
        v_str = f"{views:,}" if views else '—'
        l_str = f"{likes:,}" if likes else '—'
        lines.append(f"*{title}* ({posted_at})\n👁 {v_str} views · ❤️ {l_str} likes")

    # best hours
    bt = best_times(history)
    if bt:
        lines.append('\n📅 *Best posting hours (IST by avg views):*')
        for b in bt[:3]:
            lines.append(f"  {b['hour_ist']:02d}:00 — avg {b['avg_views']:,} views ({b['count']} reels)")

    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    root = Path(__file__).resolve().parent.parent
    h = json.loads((root / 'history.json').read_text(encoding='utf-8'))
    if '--update' in sys.argv:
        h = update_history_views(root / 'history.json')
    print(summary_text(h))
