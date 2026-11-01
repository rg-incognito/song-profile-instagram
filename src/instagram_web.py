"""Post finished reels to Instagram through instagram.com in the pipeline Chrome profile (same window as Gemini).

No Graph API / Business account needed: the user logs in once in that Chrome window, the profile keeps the
session. Uploads are locked to IG_EXPECTED_USERNAME (.env) so a reel never lands on the wrong account.

    python src/instagram_web.py --login                       # open instagram.com, log in once
    python src/instagram_web.py --whoami
    python src/instagram_web.py --post output/x.mp4 --caption-file output/x.txt [--dry-run]
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402  (loads .env)
import gemini_web  # noqa: E402

ROOT = gemini.ROOT
HOME = 'https://www.instagram.com/'
DEBUG_DIR = ROOT / 'work' / 'ig_debug'
NEW_POST = 'svg[aria-label="New post"], svg[aria-label="Create"]'
DIALOG = 'div[role="dialog"]'


def expected_username():
    return os.environ.get('IG_EXPECTED_USERNAME', '').strip().lstrip('@').lower()


def _shot(page, name):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(DEBUG_DIR / f'{int(time.time())}_{name}.png'))
    except Exception:
        pass


def _page(browser):
    ctx = browser.contexts[0]
    for p in ctx.pages:
        if 'instagram.com' in p.url:
            return p
    return ctx.new_page()


def _logged_in(page):
    try:
        page.wait_for_selector(f'{NEW_POST}, input[name="username"], input[name="email"]', timeout=20000)
    except PWTimeout:
        pass
    return page.locator(NEW_POST).count() > 0


def _dismiss(page):
    for label in ('Not now', 'Not Now', 'Cancel', 'Decline optional cookies', 'OK'):
        b = page.locator(f'{DIALOG} button:text-is("{label}"), {DIALOG} div[role="button"]:text-is("{label}")')
        if b.count():
            try:
                b.first.click(timeout=2000)
                page.wait_for_timeout(500)
            except Exception:
                pass


def whoami(page):
    """Username of the logged-in account (from the sidebar 'Profile' link)."""
    hrefs = page.eval_on_selector_all(
        'a[href^="/"]', 'els => els.filter(e => /profile/i.test(e.innerText) || e.querySelector("img[alt*=profile i]"))'
                        '.map(e => e.getAttribute("href"))')
    for h in hrefs:
        m = re.fullmatch(r'/([A-Za-z0-9._]+)/', h or '')
        if m and m.group(1) not in ('explore', 'reels', 'direct', 'accounts'):
            return m.group(1).lower()
    return ''


def _open(pw, login_wait_s=0):
    gemini_web.ensure_chrome()
    b = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{gemini_web.PORT}')
    page = _page(b)
    page.bring_to_front()
    page.goto(HOME, wait_until='domcontentloaded')
    end = time.time() + login_wait_s
    while not _logged_in(page):
        if time.time() > end:
            raise RuntimeError('Not logged in to Instagram in the pipeline Chrome (python src/instagram_web.py --login)')
        print('>>> Log in to Instagram in the pipeline Chrome window...', flush=True)
        time.sleep(5)  # never reload here: the user may be typing
        if '/accounts/onetap' in page.url:  # "Save your login info?" page after a successful login
            page.goto(HOME, wait_until='domcontentloaded')
    _dismiss(page)
    return b, page


def _click_text(page, scope, texts, timeout=15000):
    """Click the first visible button/role=button in scope whose text matches one of texts."""
    end = time.time() + timeout / 1000
    while time.time() < end:
        for t in texts:
            loc = page.locator(f'{scope} [role="button"]:text-is("{t}"), {scope} button:text-is("{t}")')
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    el.click()
                    return t
        page.wait_for_timeout(400)
    raise RuntimeError(f'button {texts} not found')


def post_reel(mp4, caption, dry_run=False, log=print, timeout_s=900):
    """Upload mp4 as a reel with caption. Returns the reel URL (or 'shared'). dry_run stops before Share."""
    mp4 = Path(mp4).resolve()
    with sync_playwright() as pw:
        b, page = _open(pw)
        try:
            user = whoami(page)
            exp = expected_username()
            if exp and user != exp:
                raise RuntimeError(f'refusing to post: logged in as @{user or "?"}, expected @{exp}')
            log(f'  [instagram] posting as @{user}')

            # 1. Create -> Post
            page.locator(NEW_POST).first.click()
            page.wait_for_timeout(1500)
            sub = page.locator('svg[aria-label="Post"]')  # Create opens a menu: Post / Live video / Ad
            if page.locator(f'{DIALOG} input[type="file"]').count() == 0 and sub.count():
                sub.first.click()
                page.wait_for_selector(f'{DIALOG} input[type="file"]', state='attached', timeout=20000)

            # 2. file
            page.locator(f'{DIALOG} input[type="file"]').first.set_input_files(str(mp4))
            log('  [instagram] file selected')

            # 3. "Video posts are now shared as reels" -> OK
            try:
                page.locator(f'{DIALOG} button:text-is("OK"), {DIALOG} [role="button"]:text-is("OK")') \
                    .first.click(timeout=8000)
            except PWTimeout:
                pass

            # 4. crop: keep the original 9:16
            page.wait_for_selector(f'{DIALOG} :text-is("Next")', timeout=120000)
            page.wait_for_timeout(1500)
            try:
                page.locator('svg[aria-label="Select crop"], svg[aria-label="Select Crop"]').first.click(timeout=5000)
                page.wait_for_timeout(600)
                page.locator(f'{DIALOG} :text-is("Original")').first.click(timeout=5000)
                page.wait_for_timeout(600)
            except Exception as e:
                log(f'  [instagram] crop menu not found ({e.__class__.__name__}); keeping default')
            _shot(page, 'crop')
            _click_text(page, DIALOG, ['Next'])        # crop -> edit
            page.wait_for_timeout(2500)
            _click_text(page, DIALOG, ['Next'])        # edit -> caption
            page.wait_for_timeout(2000)

            # 5. caption
            box = page.locator(f'{DIALOG} div[contenteditable="true"][role="textbox"], '
                               f'{DIALOG} div[aria-label^="Write a caption"]').first
            box.click()
            for i, line in enumerate(caption.strip().split('\n')):
                if i:
                    page.keyboard.press('Shift+Enter')
                if line:
                    page.keyboard.insert_text(line)
            page.wait_for_timeout(800)
            try:  # close the #hashtag suggestion list by clicking the dialog title
                page.locator(f'{DIALOG} :text-is("New reel"), {DIALOG} :text-is("Create new post")').first \
                    .click(timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(500)
            _shot(page, 'caption')
            if dry_run:
                log('  [instagram] dry run: stopping before Share (closing the dialog)')
                page.keyboard.press('Escape')
                page.wait_for_timeout(800)
                try:
                    _click_text(page, DIALOG, ['Discard'], timeout=4000)
                except Exception:
                    pass
                return 'dry-run'

            # 6. share and wait for confirmation
            _click_text(page, DIALOG, ['Share'])
            log('  [instagram] sharing...')
            end = time.time() + timeout_s
            while time.time() < end:
                if page.locator(f'{DIALOG} :text-matches("(reel|post) has been shared|Reel shared", "i")').count():
                    break
                err = page.locator(f'{DIALOG} :text-matches("couldn.t be shared|something went wrong|try again", "i")')
                if err.count():
                    _shot(page, 'error')
                    raise RuntimeError('Instagram: ' + err.first.inner_text()[:200])
                page.wait_for_timeout(2000)
            else:
                _shot(page, 'timeout')
                raise RuntimeError(f'Instagram: no "shared" confirmation within {timeout_s}s')
            _shot(page, 'shared')
            page.keyboard.press('Escape')
            log('  [instagram] reel shared')
            return f'https://www.instagram.com/{user}/reels/'
        finally:
            b.close()  # detaches CDP; Chrome keeps running


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--login', action='store_true')
    ap.add_argument('--whoami', action='store_true')
    ap.add_argument('--post')
    ap.add_argument('--caption-file')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.login or a.whoami:
        with sync_playwright() as pw:
            b, p = _open(pw, login_wait_s=900 if a.login else 0)
            print('logged in as @' + whoami(p))
            b.close()
    if a.post:
        cap = Path(a.caption_file).read_text(encoding='utf-8') if a.caption_file else ''
        print(post_reel(a.post, cap, dry_run=a.dry_run))
