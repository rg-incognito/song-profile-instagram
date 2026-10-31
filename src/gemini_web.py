"""Generate images through the Gemini web app (gemini.google.com) in a dedicated Chrome profile.

Uses the user's Gemini subscription (no API image quota needed). Chrome runs with its own profile in
chrome_profile/ and a local remote-debugging port; Playwright attaches over CDP. The first run opens the
window and waits for the user to sign in to Google there (once; the profile keeps the session).

    python src/gemini_web.py --login                       # open the window, sign in once
    python src/gemini_web.py --prompt "..." --ref img.png --out work/x.png
"""
import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / 'chrome_profile'
PORT = 9333
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
APP = 'https://gemini.google.com/app'
DEBUG_DIR = ROOT / 'work' / 'web_debug'

EDITOR = 'div.ql-editor[contenteditable="true"]'


def _port_open():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def ensure_chrome():
    if _port_open():
        return
    PROFILE.mkdir(exist_ok=True)
    subprocess.Popen([CHROME, f'--remote-debugging-port={PORT}', '--remote-debugging-address=127.0.0.1',
                      f'--user-data-dir={PROFILE}', '--no-first-run', '--no-default-browser-check',
                      '--window-size=1300,1000', APP])
    for _ in range(60):
        if _port_open():
            return
        time.sleep(0.5)
    raise RuntimeError('Chrome debug port did not open')


def _page(browser):
    ctx = browser.contexts[0]
    for p in ctx.pages:
        if 'gemini.google.com' in p.url:
            return ctx, p
    return ctx, ctx.new_page()


def _signed_in(page):
    try:
        page.wait_for_selector(EDITOR, timeout=15000)
    except PWTimeout:
        return False
    return page.locator('a:has-text("Sign in"), button:has-text("Sign in")').count() == 0


def _wait_login(page, timeout_s=600):
    print('\n>>> Sign in to your Google account in the Chrome window that just opened (one time only).'
          '\n>>> Waiting up to 10 minutes...', flush=True)
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            if 'gemini.google.com/app' in page.url and _signed_in(page):
                print('>>> Signed in.', flush=True)
                return
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError('Not signed in to Gemini in the pipeline Chrome profile')


def _shot(page, name):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(DEBUG_DIR / f'{int(time.time())}_{name}.png'))
    except Exception:
        pass


def _attach(page, ref):
    """Attach a reference image: Upload and tools -> Upload files (file chooser handled by Playwright)."""
    page.get_by_role('button', name='Upload and tools').click()
    page.wait_for_timeout(1000)
    inp = page.locator('input[type="file"][accept^="image/"]')
    if inp.count():
        inp.first.set_input_files(str(ref))
        page.keyboard.press('Escape')
    else:
        with page.expect_file_chooser(timeout=15000) as fc:
            page.locator('[data-test-id="local-images-files-uploader-button"]').click()
        fc.value.set_files(str(ref))
    # wait for the thumbnail preview to finish uploading
    page.wait_for_timeout(1500)
    for _ in range(60):
        if page.locator('[class*="uploading"], mat-progress-spinner, [role="progressbar"]').count() == 0:
            break
        page.wait_for_timeout(500)


def _select_create_image(page):
    """Turn on the 'Create image' tool so the prompt always goes to the image model."""
    try:
        page.get_by_role('button', name='Upload and tools').click()
        page.wait_for_timeout(1000)
        page.locator('.cdk-overlay-container button:has-text("Create image")').first.click(timeout=5000)
        page.wait_for_timeout(800)
    except Exception as e:
        print(f'  [web] could not select Create image tool ({e.__class__.__name__}); relying on prompt', flush=True)
        page.keyboard.press('Escape')


def _response_images(page):
    return page.locator('model-response generated-image img, model-response single-image img, '
                        'model-response img.image')


def generate(prompt, out_path, ref=None, timeout_s=300):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_chrome()
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
        ctx, page = _page(browser)
        page.bring_to_front()
        page.goto(APP, wait_until='domcontentloaded')
        if not _signed_in(page):
            _wait_login(page)
            page.goto(APP, wait_until='domcontentloaded')
            page.wait_for_selector(EDITOR, timeout=30000)
        for label in ('Got it', 'No thanks', 'Dismiss'):
            b = page.get_by_role('button', name=label)
            if b.count():
                b.first.click()
                page.wait_for_timeout(300)
        if ref:
            _attach(page, ref)
        _select_create_image(page)
        ed = page.locator(EDITOR)
        ed.click()
        ed.fill(prompt)
        page.wait_for_timeout(500)
        before = _response_images(page).count()
        page.keyboard.press('Enter')
        _shot(page, 'sent')

        # wait for the generated image to appear and fully load
        end = time.time() + timeout_s
        img = None
        while time.time() < end:
            imgs = _response_images(page)
            if imgs.count() > before:
                cand = imgs.last
                try:
                    if cand.evaluate('e => e.complete && e.naturalWidth > 256'):
                        img = cand
                        break
                except Exception:
                    pass
            page.wait_for_timeout(2000)
        if img is None:
            _shot(page, 'timeout')
            txt = page.locator('model-response').last.inner_text() if page.locator('model-response').count() else ''
            raise RuntimeError(f'No image within {timeout_s}s. Gemini said: {txt[:300]!r}')
        page.wait_for_timeout(1500)
        _shot(page, 'done')

        # full-size download via the image's own download button
        img.hover()
        page.wait_for_timeout(500)
        btn = page.locator('button[aria-label*="Download" i], button[data-test-id*="download" i]').last
        try:
            with page.expect_download(timeout=90000) as dl:
                btn.click()
            dl.value.save_as(str(out_path))
        except Exception as e:  # fall back to the displayed image bytes
            print(f'  [web] download button failed ({e.__class__.__name__}); saving displayed image', flush=True)
            src = img.get_attribute('src')
            data = page.evaluate("""async (src) => { const r = await fetch(src); const b = await r.arrayBuffer();
                                   return Array.from(new Uint8Array(b)); }""", src)
            out_path.write_bytes(bytes(data))
        browser.close()  # detaches CDP only; Chrome keeps running with the session
    return out_path


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--login', action='store_true')
    ap.add_argument('--prompt')
    ap.add_argument('--ref')
    ap.add_argument('--out', default=str(ROOT / 'work' / 'web_test.png'))
    a = ap.parse_args()
    if a.login:
        ensure_chrome()
        with sync_playwright() as pw:
            b = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
            _, p = _page(b)
            if 'gemini.google.com' not in p.url:
                p.goto(APP)
            if not _signed_in(p):
                _wait_login(p)
            print('Logged in OK')
            b.close()
        sys.exit(0)
    print(generate(a.prompt, a.out, a.ref))
