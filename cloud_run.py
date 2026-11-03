import json
import os
import time
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

from lichbot.bootstrap import create_stores
from lichbot.facebook import FacebookClient
from lichbot.policy import max_available_period
from lichbot.publishers import PUBLISHERS
from lichbot.runner import Runner
from lichbot.scan_context import ScanContext
from lichbot.settings import Settings, load_env, missing_env


def get_cloud_targets(today=None, lookback=2):
    today = today or date.today()
    max_y, max_m = max_available_period(today)
    targets = []
    y, m = max_y, max_m
    for _ in range(lookback):
        targets.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return targets


def normalize_cookies(raw_cookies):
    valid = []
    for c in raw_cookies:
        item = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".facebook.com"),
            "path": c.get("path", "/"),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
        }
        same_site = str(c.get("sameSite", "")).capitalize()
        if same_site in ("Strict", "Lax", "None"):
            item["sameSite"] = same_site
        if "expires" in c and isinstance(c["expires"], (int, float)) and c["expires"] > 0:
            item["expires"] = c["expires"]
        valid.append(item)
    return valid


def main():
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    load_env(settings.env_file)
    load_env(Path(".env"))

    raw_cookie_str = os.environ.get("FB_COOKIES", "").strip()
    if not raw_cookie_str:
        raise RuntimeError("Thieu bien moi truong FB_COOKIES tren GitHub Secrets!")

    cookies = normalize_cookies(json.loads(raw_cookie_str))
    missing_drive_vars = missing_env(settings.required_env)
    use_drive = len(missing_drive_vars) == 0

    if not use_drive:
        print(f"[Canh bao] Thieu bien Google Drive {missing_drive_vars} -> Chi luu vao GitHub Artifacts (fb_downloads).")

    stores = create_stores(settings, use_local=True, use_drive=use_drive)
    context_state = ScanContext()
    targets = get_cloud_targets(lookback=2)

    print(f"Khoi chay Cloud Runner | Luu Drive: {use_drive} | Cac ky: {targets}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="vi-VN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        fb = FacebookClient(page, settings.output_dir)
        runner = Runner(fb, stores, context=context_state)
        results = runner.run(list(PUBLISHERS), targets=targets)

        browser.close()

    print("\n=== TONG KET CLOUD RUN ===")
    for r in results:
        print(f"{r.publisher:10} | {r.target} | {r.status.value:14} | {r.message}")


if __name__ == "__main__":
    main()