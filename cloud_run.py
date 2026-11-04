import json
import os
import re
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

from lichbot.bootstrap import create_stores
from lichbot.facebook import FacebookSession
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
        parse_env_text(raw_secret_env)

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


def main():
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    load_all_env_sources(settings)

    raw_cookie_str = os.environ.get("FB_COOKIES", "").strip()
    if not raw_cookie_str:
        raise RuntimeError("Thiếu biến môi trường FB_COOKIES trên GitHub Secrets!")

    cookies = normalize_cookies(json.loads(raw_cookie_str))

    drive_keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    missing_drive = [k for k in drive_keys if not os.environ.get(k)]
    use_drive = len(missing_drive) == 0

    if not use_drive:
        print(f"[Cảnh báo] Thiếu biến Google Drive {missing_drive} -> Chỉ lưu vào GitHub Artifacts.")
    else:
        print(f"Đã kết nối đủ 3 khóa Google Drive! Thư mục Drive: '{settings.drive_root_folder}'")

    stores = create_stores(settings, use_local=True, use_drive=use_drive)
    context_state = ScanContext()
    targets = get_cloud_targets(lookback=2)

    print(f"Khởi chạy Cloud Runner | Các kỳ: {targets}")

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
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)

        fb = FacebookSession(page, ctx, settings.output_dir)
        runner = Runner(fb, stores, context=context_state)
        results = runner.run(list(PUBLISHERS), targets=targets)

        browser.close()

    print("\n=== TỔNG KẾT CLOUD RUN ===")
    for r in results:
        print(f"{r.publisher:10} | {r.target} | {r.status.value:14} | {r.message}")


if __name__ == "__main__":
    main()