import sys
import feedparser
import requests

HEADERS = {"User-Agent": "LichPhatHanhBot/1.0 (personal use)"}
PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/index.xml"]

site = sys.argv[1].rstrip("/")
found = False
for p in PATHS:
    url = site + p
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
    except Exception as e:
        print("LOI", url, type(e).__name__)
        continue
    feed = feedparser.parse(r.content)
    if feed.entries:
        found = True
        print("CO RSS:", url, "-", len(feed.entries), "bai")
        for e in feed.entries[:5]:
            print("   -", e.title)
        break
    print("khong co:", url, r.status_code)
if not found:
    print("Khong tim thay RSS, can scrape trang danh sach bai viet")