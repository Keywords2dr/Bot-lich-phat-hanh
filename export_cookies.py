import json
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
            all_cookies = context.cookies("https://www.facebook.com")
            important = [
                c for c in all_cookies
                if "facebook.com" in c.get("domain", "")
            ]
            out_file = Path("fb_cookies.json")
            out_file.write_text(json.dumps(important, ensure_ascii=False), encoding="utf-8")
            print(f"Da xuat {len(important)} cookies ra file: {out_file.resolve()}")
            print("Hay mo file fb_cookies.json, copy toan bo noi dung va dan vao GitHub Secret ten la FB_COOKIES.")


if __name__ == "__main__":
    main()