import os
import re
import sys
from datetime import date
from pathlib import Path

from lichbot.bootstrap import create_stores
from lichbot.models import RunStatus
from lichbot.policy import max_available_period
from lichbot.publishers import PUBLISHERS
from lichbot.runner import Runner
from lichbot.scan_context import ScanContext
from lichbot.settings import Settings, load_env
from lichbot.sources.apify_fb import ApifySession, build_apify_sources
from lichbot.storage import make_skip_check


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


def main():
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    load_all_env_sources(settings)

    apify_token = os.environ.get("APIFY_TOKEN", "").strip()
    if not apify_token:
        raise RuntimeError("Thiếu biến môi trường APIFY_TOKEN trên GitHub Secrets hoặc .env!")

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

    print(f"Khởi chạy Cloud Runner (Apify API) | Các kỳ: {targets}")

    force = os.environ.get("FORCE_RESCAN", "").strip().lower() in ("1", "true", "yes")
    skip_check = None if force else make_skip_check(stores)
    if force:
        print("[Cấu hình] FORCE_RESCAN bật: quét lại tất cả, không bỏ qua kỳ đã có trên Drive.")
    if skip_check:
        pending = [(p.name, t) for p in PUBLISHERS for t in targets if not skip_check(p.name, t)]
        if not pending:
            print("Tất cả các kỳ đã có trên Drive, không cần gọi Apify. Kết thúc.")
            return
        print(f"Còn {len(pending)} kỳ cần quét: {pending}")

    results_limit = int(os.environ.get("APIFY_RESULTS_LIMIT", "50" if force else "35"))
    days_back = int(os.environ.get("APIFY_DAYS_BACK", "75"))

    session = ApifySession(
        token=apify_token,
        results_limit=results_limit,
        days_back=days_back,
    )
    runner = Runner(
        session,
        stores,
        sleep=lambda _: None,  # Không cần nghỉ 10-20s như khi dùng trình duyệt Facebook thật
        source_factory=build_apify_sources,
        context=context_state,
        skip_check=skip_check,
    )
    results = runner.run(list(PUBLISHERS), targets=targets)

    print("\n=== TỔNG KẾT CLOUD RUN ===")
    for r in results:
        print(f"{r.publisher:10} | {r.target} | {r.status.value:14} | {r.message}")

    if any(r.status == RunStatus.ERROR for r in results):
        print("\n[LỖI] Có kỳ bị ERROR (xem bảng trên): đánh dấu workflow thất bại để bạn được báo.")
        sys.exit(1)


if __name__ == "__main__":
    main()