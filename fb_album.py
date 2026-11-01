import re
import sys
import time
import random
import unicodedata
from pathlib import Path
from playwright.sync_api import sync_playwright

ALBUM_SEL = 'a[href*="/media/set/"], a[href*="set=a."], a[href*="/albums/"]'


def fold(s):
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def pause(a=1.5, b=3):
    time.sleep(random.uniform(a, b))


def collect(page, selector):
    return page.evaluate(
        """sel => [...document.querySelectorAll(sel)]
        .map(a => ({href: a.href, text: a.innerText || ''}))""",
        selector,
    )


def collect_thumbs(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('a[href*="fbid="]')]
        .filter(a => a.querySelector('img'))
        .map(a => a.href)"""
    )


slug, year, month, name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
which = sys.argv[5] if len(sys.argv) > 5 else ""
out = Path("fb_downloads")
out.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.bring_to_front()
    page.goto(
        f"https://www.facebook.com/{slug}/photos_albums",
        wait_until="domcontentloaded",
    )
    pause(5, 7)

    titles = set()
    album = None
    for _ in range(12):
        for a in collect(page, ALBUM_SEL):
            t = " ".join(a["text"].split())
            if t:
                titles.add(t[:80])
            f = fold(t)
            if "lich phat hanh" in f and year in f:
                album = a
                break
        if album:
            break
        page.mouse.wheel(0, 900)
        pause()

    if not album:
        print("Khong thay album lich phat hanh nam", year, "- cac album da thay:")
        for t in sorted(titles):
            print(" -", t)
        sys.exit(1)

    print("Album:", " ".join(album["text"].split())[:80])
    page.goto(album["href"], wait_until="domcontentloaded")
    pause(5, 7)

    photos = {}
    for _ in range(8):
        for href in collect_thumbs(page):
            m = re.search(r"fbid=(\d+)", href)
            if m and m.group(1) not in photos:
                photos[m.group(1)] = href
        page.mouse.wheel(0, 900)
        pause()
    links = list(photos.values())
    print("So anh trong album:", len(links))
    if not links:
        print("Khong thay anh nao trong album")
        sys.exit(1)

    month_num = int(month)
    if which == "last":
        idx = len(links)
    elif which:
        idx = int(which)
    else:
        idx = 1 if month_num <= 2 else month_num - 1
    idx = max(1, min(idx, len(links)))
    print("Se mo anh thu", idx, "trong album")

    page.goto(links[idx - 1], wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "() => [...document.images].some(i => i.naturalWidth > 600)",
            timeout=20000,
        )
    except Exception:
        print("Cho 20 giay nhung chua thay anh lon nao")
    pause(2, 3)

    text = fold(page.inner_text("body"))
    months = re.findall(r"thang\s*0?(\d{1,2})(?!\d)", text)
    print("Cac thang xuat hien trong trang:", months[:8])
    if str(month_num) not in months:
        print("Canh bao: khong thay chu 'thang", month_num, "' trong trang, kiem tra lai anh")

    imgs = page.evaluate(
        """() => [...document.images]
        .map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight}))
        .filter(i => i.src.startsWith('http') && i.w > 300)"""
    )
    print("So anh lon tim thay:", len(imgs))
    if not imgs:
        shot = out / "debug.png"
        page.screenshot(path=str(shot))
        print("Khong lay duoc anh. Da chup man hinh de kiem tra:", shot)
        sys.exit(1)

    imgs.sort(key=lambda i: i["w"] * i["h"], reverse=True)
    for i in imgs[:3]:
        print("  ung vien:", i["w"], "x", i["h"], i["src"][:70])

    best = imgs[0]
    res = ctx.request.get(best["src"])
    ctype = res.headers.get("content-type", "image/jpeg")
    ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
    dest = out / f"{name}.{ext}"
    dest.write_bytes(res.body())
    print("Da luu:", dest, "-", best["w"], "x", best["h"])