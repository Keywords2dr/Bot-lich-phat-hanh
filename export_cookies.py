import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from lichbot.chrome import ChromeLauncher
from lichbot.settings import Settings

LOGIN_TIMEOUT_SECONDS = 300


def facebook_cookies(context):
    return [c for c in context.cookies() if "facebook.com" in c.get("domain", "")]


def find_cookie(cookies, name):
    for c in cookies:
        if c.get("name") == name:
            return c
    return None


def main():
    settings = Settings()
    print(f"Chrome cua bot dung rieng thu muc: {settings.profile_dir}")
    print("(Day KHONG phai Chrome thuong ngay cua ban, nen tai khoan dang nhap o Chrome thuong khong lien quan.)\n")

    answer = input("Xoa phien dang nhap cu trong Chrome cua bot de dang nhap tai khoan khac? (y/N): ").strip().lower()
    clear_old = answer in ("y", "yes", "c", "co")

    with ChromeLauncher(settings):
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{settings.debug_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            if clear_old:
                context.clear_cookies()
                print("Da xoa phien dang nhap cu.")

            page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)
            page.bring_to_front()

            cookies = facebook_cookies(context)
            logged_in = find_cookie(cookies, "c_user") and find_cookie(cookies, "xs")
            if logged_in and not clear_old:
                print("Dang co phien dang nhap san trong Chrome cua bot.")
            else:
                print(f"\nHay DANG NHAP tai khoan Facebook mong muon trong cua so Chrome vua mo (toi da {LOGIN_TIMEOUT_SECONDS // 60} phut).")
                print("Script se tu dong nhan ra khi ban dang nhap xong.")
                deadline = time.time() + LOGIN_TIMEOUT_SECONDS
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    cookies = facebook_cookies(context)
                    if find_cookie(cookies, "c_user") and find_cookie(cookies, "xs"):
                        break
                else:
                    print("\n[LOI] Het thoi gian cho ma chua thay dang nhap. Hay chay lai.")
                    return

            user_id = find_cookie(cookies, "c_user")["value"]
            print(f"\nDa nhan ra dang nhap. ID tai khoan (c_user): {user_id}")
            print(f"Kiem tra dung tai khoan chua: https://www.facebook.com/profile.php?id={user_id}")

            print("\nBay gio hay LUOT Facebook khoang 1 phut trong cua so Chrome do (bang tin, mo vai trang)")
            print("de trinh duyet tao du cookie. KHONG bam 'Dang xuat'.")
            input("Luot xong thi nhan Enter o day de xuat cookie... ")

            cookies = facebook_cookies(context)
            names = [c.get("name") for c in cookies]
            print("Cac cookie tim thay:", names)

            if "c_user" not in names or "xs" not in names:
                print("\n[LOI] Mat cookie dang nhap ('c_user' va 'xs'). Hay chay lai.")
                return

            user_agent = page.evaluate("navigator.userAgent")
            Path("fb_user_agent.txt").write_text(user_agent, encoding="utf-8")
            if len(cookies) < 10:
                print(f"\n[CANH BAO] Moi co {len(cookies)} cookie. Neu workflow van that bai, hay luot Facebook lau hon roi xuat lai.")

            out_file = Path("fb_cookies.json")
            out_file.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
            print(f"\n[THANH CONG] Da xuat {len(cookies)} cookies ra: {out_file.resolve()}")
            print("\nUser-Agent cua trinh duyet nay (them vao secret DOTENV_CONTENT 1 dong):")
            print(f"FB_USER_AGENT={user_agent}")


if __name__ == "__main__":
    main()