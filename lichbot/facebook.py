import random
import re
import time
from contextlib import contextmanager

from .models import BotError, LoginError, PhotoPage
from .text_utils import extract_months, fold

LOGIN_MSG = "Chua dang nhap Facebook trong Chrome cua bot. Hay dang nhap roi chay lai."
FBID_RE = re.compile(r"fbid=(\d+)")
ALBUM_SELECTOR = 'a[href*="/media/set/"], a[href*="set=a."], a[href*="/albums/"]'

ALBUM_LINKS_JS = """sel => [...document.querySelectorAll(sel)]
    .map(a => ({href: a.href, text: a.innerText || ''}))"""

THUMB_LINKS_JS = """() => [...document.querySelectorAll('a[href*="fbid="]')]
    .filter(a => a.querySelector('img'))
    .map(a => a.href)"""

BIG_LINKS_JS = """() => [...document.querySelectorAll('a[href*="fbid="]')]
    .filter(a => a.querySelector('img') && a.getBoundingClientRect().width > 200)
    .map(a => a.href)"""

IMAGES_JS = """() => [...document.images]
    .map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight}))
    .filter(i => i.src.startsWith('http') && i.w > 300)"""

BIG_IMAGE_READY_JS = "() => [...document.images].some(i => i.naturalWidth > 600)"

EXPAND_JS = r"""() => {
    const norm = s => (s || '').toLowerCase().normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').trim();
    let clicked = 0;
    for (const el of document.querySelectorAll('[role="button"]')) {
        if (/^[.…\s]*(xem them|see more)$/.test(norm(el.innerText))) {
            el.click();
            clicked += 1;
            if (clicked >= 5) break;
        }
    }
    return clicked;
}"""


FEATURED_LINKS_JS = r"""() => {
    const norm = s => (s || '').toLowerCase().normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').trim();
    const wanted = ['dang chu y', 'featured'];
    const head = [...document.querySelectorAll('span, h2, h3, div')]
        .find(e => e.childElementCount === 0 && wanted.includes(norm(e.textContent)));
    if (!head) return [];
    const pick = /\/posts\/|fbid=|\/photo\.php|\/photo\/|\/permalink|\/videos\//;
    let box = head.parentElement;
    for (let i = 0; box && i < 10; i++, box = box.parentElement) {
        const seen = new Set();
        const links = [];
        for (const a of box.querySelectorAll('a[href]')) {
            if (!pick.test(a.href)) continue;
            const key = a.href.split('?')[0];
            if (seen.has(key)) continue;
            seen.add(key);
            links.push(a.href);
        }
        if (links.length) return links;
    }
    return [];
}"""


def pause(low=1.5, high=3.0):
    time.sleep(random.uniform(low, high))


class FacebookSession:
    def __init__(self, page, context, debug_dir):
        self._page = page
        self._ctx = context
        self._debug_dir = debug_dir
        self._photo_cache = {}
        self._list_cache = {}
        self._last_url = None

    def goto(self, url, wait=(5, 7)):
        self._last_url = url
        if any(k[0] == url for k in self._list_cache):
            return
        self._page.goto(url, wait_until="domcontentloaded")
        pause(*wait)

    def require_login(self):
        if self._last_url and any(k[0] == self._last_url for k in self._list_cache):
            return
        if self._page.locator('input[name="pass"]').count():
            raise LoginError(LOGIN_MSG)

    def scroll(self, pixels=900):
        self._page.mouse.wheel(0, pixels)
        pause()

    def album_links(self):
        return self._page.evaluate(ALBUM_LINKS_JS, ALBUM_SELECTOR)

    def thumb_links(self):
        return self._page.evaluate(THUMB_LINKS_JS)

    def big_photo_links(self):
        return self._page.evaluate(BIG_LINKS_JS)

    def gather_photos(self, picker, rounds, limit=None, stable_rounds=0, step=900):
        cache_key = (self._last_url, rounds, limit, stable_rounds)
        if self._last_url and cache_key in self._list_cache:
            return list(self._list_cache[cache_key])

        photos = {}
        stable = 0
        for _ in range(rounds):
            before = len(photos)
            for href in picker():
                match = FBID_RE.search(href)
                if match and match.group(1) not in photos:
                    photos[match.group(1)] = href
            if limit and len(photos) >= limit:
                break
            stable = stable + 1 if len(photos) == before else 0
            if stable_rounds and stable >= stable_rounds:
                break
            self.scroll(step)
        result = list(photos.values())
        if self._last_url:
            self._list_cache[cache_key] = result
        return result

    def featured_links(self):
        return self._page.evaluate(FEATURED_LINKS_JS)

    def expand_captions(self):
        clicked = self._page.evaluate(EXPAND_JS)
        if clicked:
            pause(0.8, 1.5)
        return clicked

    def screenshot(self, name):
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        path = self._debug_dir / name
        try:
            self._page.screenshot(path=str(path), timeout=8000)
        except Exception as err:
            print(f"Bo qua chup man hinh debug ({type(err).__name__})")
        return path

    def _image_loader(self, src):
        def load():
            response = self._ctx.request.get(src)
            if not response.ok:
                raise BotError(f"Khong tai duoc anh (HTTP {response.status})")
            content_type = response.headers.get("content-type", "image/jpeg")
            ext = "png" if "png" in content_type else "webp" if "webp" in content_type else "jpg"
            return response.body(), ext

        return load

    def open_photo(self, href):
        m = FBID_RE.search(href)
        cache_key = m.group(1) if m else href
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]

        page = self._page
        page.goto(href, wait_until="domcontentloaded")
        try:
            page.wait_for_function(BIG_IMAGE_READY_JS, timeout=20000)
        except Exception:
            pass
        pause(2, 3)
        self.expand_captions()
        text = fold(page.inner_text("body"))
        images = page.evaluate(IMAGES_JS)
        if not images:
            self._photo_cache[cache_key] = None
            return None
        images.sort(key=lambda i: i["w"] * i["h"], reverse=True)
        best = images[0]
        result = PhotoPage(
            text=text,
            months=tuple(extract_months(text)),
            data=None,
            ext="jpg",
            width=best["w"],
            height=best["h"],
            loader=self._image_loader(best["src"]),
        )
        self._photo_cache[cache_key] = result
        return result


@contextmanager
def facebook_session(port, debug_dir):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.bring_to_front()
        yield FacebookSession(page, context, debug_dir)