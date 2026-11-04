import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from lichbot.chrome import ChromeLauncher
from lichbot.settings import Settings


def main():
    settings = Settings()
    with ChromeLauncher(settings):
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{settings.debug_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            all_cookies = context.cookies()
            fb_cookies = [c for c in all_cookies if "facebook.com" in c.get("domain", "")]
            names = [c.get("name") for c in fb_cookies]
            print("Cac cookie tim thay:", names)

            if "c_user" not in names or "xs" not in names:
                print("\n[LOI] Chua tim thay cookie dang nhap ('c_user' va 'xs')!")
                print("Hay dang nhap Facebook tren cua so Chrome vua mo, sau do chay lai lenh nay.")
                return

            out_file = Path("fb_cookies.json")
            out_file.write_text(json.dumps(fb_cookies, ensure_ascii=False), encoding="utf-8")
            print(f"\n[THANH CONG] Da xuat {len(fb_cookies)} cookies (co du c_user & xs) ra: {out_file.resolve()}")


if __name__ == "__main__":
    main()