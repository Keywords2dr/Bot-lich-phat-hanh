import os
import re
import sys
import time
import socket
import random
import subprocess
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright
from drive import get_service, get_or_create_folder, upload

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = str(Path("chrome_bot").resolve())
PORT = 9222
ROOT_FOLDER = "Lich phat hanh"
MAX_HASHTAG_PHOTOS = 12
MAX_PHOTOS_SCAN = 12
OUT = Path("fb_downloads")
ALBUM_SEL = 'a[href*="/media/set/"], a[href*="set=a."], a[href*="/albums/"]'
PAIR = re.compile(r"thang\s*0?(\d{1,2})\s*[-–./]?\s*(20\d\d)")
LOGIN_MSG = "Chua dang nhap Facebook trong Chrome cua bot. Hay dang nhap roi chay lai."

PUBLISHERS = [
    {
        "name": "Kim-Dong",
        "slug": "nxbkimdong",
        "album_keys": ["lich phat hanh"],
        "hashtag": "https://www.facebook.com/hashtag/lich_phat_hanh_comick%C4%91",
        "text_key": "kim dong",
    },
    {
        "name": "IPM",
        "slug": "ipmvn",
        "mode": "photos",
        "photos_url": "https://www.facebook.com/media/set/?set=a.452839023556014&type=3",
        "order": "newest_first",
        "required_keys": ["thang_nay_ipm_co_gi"],
        "year_mode": "nearest",
    },
]


class BotError(Exception):
    pass


class LoginError(BotError):
    pass


def fold(s):
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def pause(a=1.5, b=3):
    time.sleep(random.uniform(a, b))


def nearest_year(month, today):
    now = today.year * 12 + today.month
    return min(
        (today.year - 1, today.year, today.year + 1),
        key=lambda y: abs(y * 12 + month - now),
    )


def load_env():
    f = Path("secrets.env")
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def port_open():
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def ensure_chrome():
    if port_open():
        return None
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--remote-allow-origins=*",
        ]
    )
    for _ in range(30):
        if port_open():
            return proc
        time.sleep(1)
    proc.terminate()
    sys.exit("Khong mo duoc Chrome cua bot (cong 9222 khong mo)")


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


def collect_big_photo_links(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('a[href*="fbid="]')]
        .filter(a => a.querySelector('img') && a.getBoundingClientRect().width > 200)
        .map(a => a.href)"""
    )


def find_album(page, pub, year):
    page.goto(
        f"https://www.facebook.com/{pub['slug']}/photos_albums",
        wait_until="domcontentloaded",
    )
    pause(5, 7)
    if page.locator('input[name="pass"]').count():
        raise LoginError(LOGIN_MSG)
    keys = pub.get("album_keys", ["lich phat hanh"])
    for _ in range(12):
        for a in collect(page, ALBUM_SEL):
            f = fold(a["text"])
            if all(k in f for k in keys) and year in f:
                return a
        page.mouse.wheel(0, 900)
        pause()
    return None


def list_photos(page, href):
    page.goto(href, wait_until="domcontentloaded")
    pause(5, 7)
    photos = {}
    for _ in range(8):
        for h in collect_thumbs(page):
            m = re.search(r"fbid=(\d+)", h)
            if m and m.group(1) not in photos:
                photos[m.group(1)] = h
        page.mouse.wheel(0, 900)
        pause()
    return list(photos.values())


def open_photo(page, ctx, pub, href):
    page.goto(href, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "() => [...document.images].some(i => i.naturalWidth > 600)",
            timeout=20000,
        )
    except Exception:
        pass
    pause(2, 3)
    text = fold(page.inner_text("body"))
    found = [
        int(x)
        for x in re.findall(r"thang\s*0?(\d{1,2})(?!\d)", text)
        if 1 <= int(x) <= 12
    ]
    month = Counter(found).most_common(1)[0][0] if found else None
    pairs = [(int(m), int(y)) for m, y in PAIR.findall(text) if 1 <= int(m) <= 12]
    years = [y for m, y in pairs if m == month] or [y for m, y in pairs]
    if not years:
        years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", text)]
    year = Counter(years).most_common(1)[0][0] if years else None
    imgs = page.evaluate(
        """() => [...document.images]
        .map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight}))
        .filter(i => i.src.startsWith('http') && i.w > 300)"""
    )
    if not imgs:
        return None
    imgs.sort(key=lambda i: i["w"] * i["h"], reverse=True)
    res = ctx.request.get(imgs[0]["src"])
    ctype = res.headers.get("content-type", "image/jpeg")
    ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
    text_key = pub.get("text_key")
    return {
        "month": month,
        "months": found,
        "year": year,
        "text": text,
        "publisher_ok": (text_key in text) if text_key else True,
        "data": res.body(),
        "ext": ext,
        "w": imgs[0]["w"],
        "h": imgs[0]["h"],
    }


def from_album(page, ctx, pub, target, year):
    album = find_album(page, pub, str(year))
    if not album:
        print("Khong thay album lich phat hanh nam", year)
        return None
    print("Album:", " ".join(album["text"].split())[:80])
    links = list_photos(page, album["href"])
    print("So anh trong album:", len(links))
    if not links:
        return None
    if target:
        want = int(target.split("-")[1])
        guess = 1 if want <= 2 else want
        order = sorted(range(1, len(links) + 1), key=lambda i: abs(i - guess))[:4]
        for i in order:
            r = open_photo(page, ctx, pub, links[i - 1])
            print(f"Thu anh {i}: thang nhan ra =", r["month"] if r else None)
            if r and (r["month"] == want or (want <= 2 and r["month"] in (1, 2))):
                return f"{year}-{want:02d}", r
        return None
    r = open_photo(page, ctx, pub, links[-1])
    if not r or not r["month"]:
        return None
    print("Anh moi nhat la thang", r["month"])
    return f"{year}-{r['month']:02d}", r


def from_hashtag(page, ctx, pub, target):
    page.goto(pub["hashtag"], wait_until="domcontentloaded")
    pause(5, 7)
    if page.locator('input[name="pass"]').count():
        raise LoginError(LOGIN_MSG)
    photos = {}
    for _ in range(10):
        for h in collect_big_photo_links(page):
            m = re.search(r"fbid=(\d+)", h)
            if m and m.group(1) not in photos:
                photos[m.group(1)] = h
        if len(photos) >= MAX_HASHTAG_PHOTOS:
            break
        page.mouse.wheel(0, 900)
        pause()
    links = list(photos.values())[:MAX_HASHTAG_PHOTOS]
    print("Hashtag: so anh tim thay:", len(links))
    if not links:
        OUT.mkdir(exist_ok=True)
        shot = OUT / f"debug_hashtag_{pub['name']}.png"
        page.screenshot(path=str(shot))
        print("Khong thay link anh nao trong trang hashtag. Da chup man hinh:", shot)
        return None

    want_year = want_month = None
    if target:
        want_year, want_month = (int(x) for x in target.split("-"))
    cands = []
    for i, href in enumerate(links, 1):
        r = open_photo(page, ctx, pub, href)
        if not r or not r["month"] or not r["publisher_ok"]:
            print(f"Anh {i}: bo qua")
            continue
        print(f"Anh {i}: thang {r['month']} nam {r['year']}")
        if target:
            month_ok = r["month"] == want_month or (
                want_month <= 2 and r["month"] in (1, 2)
            )
            if month_ok and r["year"] in (want_year, None):
                return f"{want_year}-{want_month:02d}", r
        elif r["year"]:
            cands.append((r["year"], r["month"], r))
    if target or not cands:
        return None
    y, m, r = max(cands, key=lambda c: (c[0], c[1]))
    print("Anh moi nhat tren hashtag la thang", m, "nam", y)
    return f"{y}-{m:02d}", r


def from_photos(page, ctx, pub, target):
    url = pub.get("photos_url") or f"https://www.facebook.com/{pub['slug']}/photos"
    page.goto(url, wait_until="domcontentloaded")
    pause(5, 7)
    if page.locator('input[name="pass"]').count():
        raise LoginError(LOGIN_MSG)
    limit = pub.get("scan_limit", MAX_PHOTOS_SCAN)
    oldest_first = pub.get("order", "newest_first") == "oldest_first"
    photos = {}
    stable = 0
    for _ in range(40 if oldest_first else 10):
        before = len(photos)
        for h in collect_thumbs(page):
            m = re.search(r"fbid=(\d+)", h)
            if m and m.group(1) not in photos:
                photos[m.group(1)] = h
        if not oldest_first and len(photos) >= limit:
            break
        stable = stable + 1 if len(photos) == before else 0
        if oldest_first and stable >= 3:
            break
        page.mouse.wheel(0, 1500)
        pause()
    links = list(photos.values())
    if oldest_first:
        links.reverse()
    links = links[:limit]
    print(
        "Album anh: so anh doc duoc:", len(photos),
        "- se kiem tra", len(links), "anh moi nhat",
    )
    if not links:
        OUT.mkdir(exist_ok=True)
        shot = OUT / f"debug_photos_{pub['name']}.png"
        page.screenshot(path=str(shot))
        print("Khong thay anh nao trong album. Da chup man hinh:", shot)
        return None

    keys = [fold(k) for k in pub.get("required_keys", [])]
    want_year = want_month = None
    if target:
        want_year, want_month = (int(x) for x in target.split("-"))
    today = date.today()
    for i, href in enumerate(links, 1):
        r = open_photo(page, ctx, pub, href)
        if not r or not r["month"]:
            print(f"Anh {i}: bo qua (khong nhan ra thang)")
            continue
        if not all(k in r["text"] for k in keys):
            print(f"Anh {i}: bo qua (thieu hashtag bat buoc)")
            continue
        if pub.get("year_mode") == "nearest" or not r["year"]:
            year = nearest_year(r["month"], today)
        else:
            year = r["year"]
        print(
            f"Anh {i}: khop, thang {r['month']} nam {year}",
            "(cac thang thay trong trang:", sorted(set(r["months"])), ")",
        )
        if not target or (r["month"] == want_month and year == want_year):
            return f"{year}-{r['month']:02d}", r
    return None

def fetch_one(page, ctx, pub, target, source):
    today = date.today()
    result = None
    if pub.get("mode") == "photos":
        result = from_photos(page, ctx, pub, target)
    else:
        if source in ("auto", "album"):
            year = int(target[:4]) if target else today.year
            result = from_album(page, ctx, pub, target, year)
        if not result and source in ("auto", "hashtag") and pub.get("hashtag"):
            print("Chuyen sang hashtag")
            result = from_hashtag(page, ctx, pub, target)
        if not result and source == "auto" and not target:
            print("Thu album nam truoc")
            result = from_album(page, ctx, pub, target, today.year - 1)
    if not result:
        raise BotError("Khong lay duoc anh")
    return result


def save_and_upload(service, pub, ym, r):
    OUT.mkdir(exist_ok=True)
    fname = f"{pub['name']}_{ym}.{r['ext']}"
    (OUT / fname).write_bytes(r["data"])
    print("Da luu may:", OUT / fname, "-", r["w"], "x", r["h"])
    root = get_or_create_folder(service, ROOT_FOLDER)
    pub_folder = get_or_create_folder(service, pub["name"], root)
    folder = get_or_create_folder(service, ym, pub_folder)
    q = f"name='{fname}' and '{folder}' in parents and trashed=false"
    if service.files().list(q=q, fields="files(id)").execute()["files"]:
        print("Da co tren Drive, bo qua:", fname)
        return "da co tren Drive: " + ym
    mime = "image/" + ("jpeg" if r["ext"] == "jpg" else r["ext"])
    res = upload(service, folder, fname, r["data"], mime)
    print("OK:", res["webViewLink"])
    return "da upload: " + ym


def main():
    load_env()
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"):
        if not os.environ.get(k):
            sys.exit(f"Thieu {k} (kiem tra file secrets.env)")

    target = ""
    source = "auto"
    names = []
    for a in sys.argv[1:]:
        if re.fullmatch(r"\d{4}-\d{2}", a):
            target = a
        elif a in ("album", "hashtag"):
            source = a
        else:
            names.append(a.lower())

    known = [p["name"].lower() for p in PUBLISHERS]
    unknown = [n for n in names if n not in known]
    if unknown:
        sys.exit(
            "Khong co NXB ten: " + ", ".join(unknown)
            + ". Cac NXB co san: " + ", ".join(p["name"] for p in PUBLISHERS)
        )
    pubs = [p for p in PUBLISHERS if not names or p["name"].lower() in names]

    service = get_service()
    proc = ensure_chrome()
    summary = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.bring_to_front()
            for n, pub in enumerate(pubs):
                if n:
                    time.sleep(random.uniform(10, 20))
                print("\n=== " + pub["name"] + " ===")
                try:
                    ym, r = fetch_one(page, ctx, pub, target, source)
                    summary.append((pub["name"], "OK", save_and_upload(service, pub, ym, r)))
                except LoginError as e:
                    print(e)
                    summary.append((pub["name"], "LOI", str(e)))
                    break
                except Exception as e:
                    print("Loi:", str(e)[:200])
                    summary.append((pub["name"], "LOI", str(e)[:200]))
    finally:
        if proc:
            proc.terminate()

    print("\n=== TOM TAT ===")
    for name, status, msg in summary:
        print(f"{status:4} {name}: {msg}")


if __name__ == "__main__":
    main()