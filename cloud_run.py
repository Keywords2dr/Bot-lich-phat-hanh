import json
import os
import re
import time
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

from lichbot.bootstrap import create_stores
from lichbot.facebook import FacebookClient
from lichbot.models import LoginError, RunStatus
from lichbot.policy import max_available_period
from lichbot.publishers import PUBLISHERS
from lichbot.runner import Runner
from lichbot.scan_context import ScanContext
from lichbot.settings import Settings, load_env


def parse_env_text(raw_text: str):
    loaded = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*)$", line)
        if not match:
            continue
        k, v = match.group(1), match.group(2).strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1].strip()
        if k and v:
            os.environ[k] = v
            loaded.append(k)
    return loaded


def load_all_env_sources(settings: Settings):
    raw_secret_env = os.environ.get("DOTENV_CONTENT", "").strip()
    if raw_secret_env:
        keys = parse_env_text(raw_secret_env)
        print(f"Da doc DOTENV_CONTENT tu GitHub Secrets: {keys}")

    for p in (settings.env_file, Path("secrets.env"), Path(".env")):
        if p.exists():
            load_env(p)
            parse_env_text(p.read_text(encoding="utf-8"))


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
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        item = {
            "name": str(name),
            "value": str(value),
            "domain": ".facebook.com",
            "path": c.get("path", "/"),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": True,
        }
        same_site = str(c.get("sameSite", "")).capitalize()
        if same_site in ("Strict", "Lax", "None"):
            item["sameSite"] = same_site
        exp = c.get("expires") or c.get("expirationDate")
        if isinstance(exp, (int, float)) and exp > 0:
            item["expires"] = float(exp)
        valid.append(item)
    return valid


def collect_cookie_pool():
    pool = []
    for env_name in ("FB_COOKIES", "FB_COOKIES_BACKUP", "FB_COOKIES_2"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            try:
                cookies = normalize_cookies(json.loads(raw))
                if cookies:
                    pool.append((env_name, cookies))
            except Exception as err:
                print(f"[Canh bao] Khong doc duoc {env_name}: {err}")
    return pool


def is_auth_failed(results):
    if not results:
        return True
    for r in results:
        msg = (r.message or "").lower()
        if r.status == RunStatus.ERROR and ("dang nhap" in msg or "login" in msg or "checkpoint" in msg):
            return True
    return False


def main():
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    load_all_env_sources(settings)

    cookie_pool = collect_cookie_pool()
    if not cookie_pool:
        raise RuntimeError("Khong tim thay FB_COOKIES nao trong GitHub Secrets!")

    drive_keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    missing_drive = [k for k in drive_keys if not os.environ.get(k)]
    use_drive = len(missing_drive) == 0
    stores = create_stores(settings, use_local=True, use_drive=use_drive)
    targets = get_cloud_targets(lookback=2)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        for idx, (acc_name, cookies) in enumerate(cookie_pool, 1):
            print(f"\n---> Thu chay voi tai khoan #{idx} ({acc_name})...")
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="vi-VN",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            fb = FacebookClient(page, settings.output_dir)
            runner = Runner(fb, stores, context=ScanContext())
            results = runner.run(list(PUBLISHERS), targets=targets)
            ctx.close()

            if not is_auth_failed(results):
                print(f"-> Tai khoan {acc_name} hoat dong tot! Hoan tat phien quet.")
                break
            print(f"[CANH BAO] Tai khoan {acc_name} bi chan hoac mat dang nhap! Tu dong chuyen sang tai khoan tiep theo...")

        browser.close()

    print("\n=== TONG KET CLOUD RUN ===")
    for r in results:
        print(f"{r.publisher:10} | {r.target} | {r.status.value:14} | {r.message}")


if __name__ == "__main__":
    main()