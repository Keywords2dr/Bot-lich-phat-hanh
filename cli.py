import hashlib
import re
import sys
from datetime import date
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lichbot.chrome import ChromeLauncher
from lichbot.facebook import facebook_session
from lichbot.models import BotError
from lichbot.publishers import PUBLISHERS
from lichbot.runner import Runner
from lichbot.settings import Settings, load_env, missing_env
from lichbot.storage import DriveStore, LocalStore

console = Console()
TARGET_RE = re.compile(r"^(20\d{2})[-/](0?[1-9]|1[0-2])$")
YEAR_RE = re.compile(r"^(20\d{2})$")
RANGE_RE = re.compile(r"^(0?[1-9]|1[0-2])\s*-\s*(0?[1-9]|1[0-2])$")


def max_available_period(today=None):
    today = today or date.today()
    if today.day >= 20:
        if today.month == 12:
            return today.year + 1, 1
        return today.year, today.month + 1
    return today.year, today.month


def normalize_target(text):
    m = TARGET_RE.match(text.strip())
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"


def build_year_targets(year_str, start_m=1, end_m=12):
    year = int(year_str)
    today = date.today()
    max_y, max_m = max_available_period(today)

    valid_months = []
    skipped_months = []
    for m in range(end_m, start_m - 1, -1):
        if (year, m) > (max_y, max_m):
            skipped_months.append(f"{year:04d}-{m:02d}")
        else:
            valid_months.append(f"{year:04d}-{m:02d}")

    if skipped_months:
        console.print(
            f"[yellow]Lưu ý: Hôm nay là {today.strftime('%d/%m/%Y')} (chưa qua ngày 20 của tháng {today.month}), "
            f"tự động bỏ qua các tháng tương lai chưa có lịch: {', '.join(reversed(skipped_months))}[/yellow]"
        )
    return valid_months


class DedupMergedStore:
    def __init__(self, inner_store):
        self._inner = inner_store
        self._saved_hashes = {}

    def save(self, publisher, poster):
        digest = hashlib.sha256(poster.data).hexdigest()
        key = (publisher, digest)
        if key in self._saved_hashes:
            prev_period = self._saved_hashes[key]
            msg = f"lịch gộp chung với {prev_period} (bỏ qua lưu trùng)"
            print(f"-> Phat hien lich gop: {poster.period} trung anh voi {prev_period}, bo qua luu trung!")
            return msg
        res = self._inner.save(publisher, poster)
        self._saved_hashes[key] = poster.period
        return res


def ask_targets():
    mode = questionary.select(
        "Chọn chế độ lấy lịch:",
        choices=[
            questionary.Choice("1. Lấy lịch mới nhất hiện có (Tự động)", value="latest"),
            questionary.Choice("2. Chỉ định 1 tháng cụ thể (VD: 2026-5 hoặc 2026-05)", value="single"),
            questionary.Choice("3. Lấy TOÀN BỘ lịch trong 1 năm (VD: 2025 hoặc 2026)", value="full_year"),
            questionary.Choice("4. Lấy theo khoảng tháng trong năm (VD: Năm 2025, từ tháng 1 đến 6)", value="range"),
        ],
    ).ask()

    if not mode:
        return None

    if mode == "latest":
        return [None]

    if mode == "single":
        raw = questionary.text(
            "Nhập năm-tháng cần lấy (VD: 2026-5, 2026-10):",
            validate=lambda t: bool(TARGET_RE.match(t.strip()))
            or "Vui lòng nhập định dạng YYYY-M hoặc YYYY-MM (tháng 1..12)",
        ).ask()
        if not raw:
            return None
        norm = normalize_target(raw)
        y, m = (int(x) for x in norm.split("-"))
        max_y, max_m = max_available_period()
        if (y, m) > (max_y, max_m):
            console.print(
                f"[bold yellow]Cảnh báo:[/bold yellow] Kỳ lịch {norm} chưa tới hạn phát hành "
                f"(hôm nay là {date.today().strftime('%d/%m/%Y')})."
            )
            if not questionary.confirm("Bạn vẫn muốn thử quét tháng này chứ?", default=False).ask():
                return None
        return [norm]

    if mode == "full_year":
        raw_year = questionary.text(
            "Nhập năm cần lấy toàn bộ lịch (VD: 2025, 2026):",
            validate=lambda t: bool(YEAR_RE.match(t.strip())) or "Vui lòng nhập năm 4 chữ số (VD: 2025)",
        ).ask()
        if not raw_year:
            return None
        targets = build_year_targets(raw_year.strip())
        if targets:
            console.print(f"[dim]-> Sẽ quét {len(targets)} mốc thời gian: {', '.join(targets)}[/dim]")
        return targets

    if mode == "range":
        raw_year = questionary.text(
            "Nhập năm (VD: 2025, 2026):",
            validate=lambda t: bool(YEAR_RE.match(t.strip())) or "Vui lòng nhập năm 4 chữ số (VD: 2025)",
        ).ask()
        if not raw_year:
            return None
        raw_range = questionary.text(
            "Nhập khoảng tháng bắt đầu - kết thúc (VD: 1-6 hoặc 10-12):",
            validate=lambda t: (
                bool(RANGE_RE.match(t.strip()))
                and int(RANGE_RE.match(t.strip()).group(1)) <= int(RANGE_RE.match(t.strip()).group(2))
            )
            or "Vui lòng nhập dạng ThángĐầu-ThángCuối hợp lệ (VD: 1-6)",
        ).ask()
        if not raw_range:
            return None
        m = RANGE_RE.match(raw_range.strip())
        start_m, end_m = int(m.group(1)), int(m.group(2))
        targets = build_year_targets(raw_year.strip(), start_m, end_m)
        if targets:
            console.print(f"[dim]-> Sẽ quét {len(targets)} mốc thời gian (từ mới về cũ): {', '.join(targets)}[/dim]")
        return targets


def format_status(ok, msg):
    if ok:
        return "[bold green]THÀNH CÔNG[/bold green]"
    if "chua dang lich" in msg.lower():
        return "[bold yellow]CHƯA ĐĂNG[/bold yellow]"
    if "khong tim thay" in msg.lower():
        return "[bold red]KHÔNG THẤY[/bold red]"
    return "[bold red]LỖI[/bold red]"


def main():
    console.print(
        Panel.fit(
            "[bold cyan]BOT SĂN LỊCH PHÁT HÀNH TRUYỆN TRANH[/bold cyan]",
            border_style="cyan",
        )
    )

    settings = Settings()
    load_env(settings.env_file)
    missing = missing_env(settings.required_env)
    if missing:
        console.print(f"[bold red]Thiếu biến môi trường:[/bold red] {', '.join(missing)} (kiểm tra secrets.env)")
        sys.exit(1)

    pub_mode = questionary.select(
        "Bạn muốn lấy lịch của Nhà Xuất Bản nào?",
        choices=[
            questionary.Choice("Tất cả Nhà Xuất Bản hiện có", value="all"),
            questionary.Choice("Tùy chọn từng Nhà Xuất Bản...", value="custom"),
        ],
    ).ask()

    if not pub_mode:
        return

    if pub_mode == "all":
        publishers = list(PUBLISHERS)
    else:
        pub_choices = [p.name for p in PUBLISHERS]
        selected_names = questionary.checkbox(
            "Chọn Nhà Xuất Bản (Space để chọn, Enter để xác nhận):",
            choices=[questionary.Choice(name, checked=True) for name in pub_choices],
        ).ask()
        if not selected_names:
            console.print("[yellow]Bạn chưa chọn NXB nào. Đã hủy thao tác.[/yellow]")
            return
        publishers = [p for p in PUBLISHERS if p.name in selected_names]

    targets = ask_targets()
    if not targets:
        console.print("[yellow]Không có mốc thời gian nào cần quét. Đã dừng.[/yellow]")
        return

    source_choices = [
        questionary.Choice("Bài ghim / Đáng chú ý (featured)", value="featured", checked=True),
        questionary.Choice("Album ảnh (album / photos)", value="album_photos", checked=True),
        questionary.Choice("Hashtag (hashtag)", value="hashtag", checked=True),
    ]
    selected_groups = questionary.checkbox(
        "Chọn các nguồn quét (Space để bật/tắt, Enter để xác nhận):",
        choices=source_choices,
    ).ask()

    kinds_filter = None
    if selected_groups and len(selected_groups) < len(source_choices):
        kinds_filter = set()
        for g in selected_groups:
            if g == "album_photos":
                kinds_filter.update(("album", "photos"))
            else:
                kinds_filter.add(g)

    store_choices = questionary.checkbox(
        "Chọn nơi lưu ảnh:",
        choices=[
            questionary.Choice("Lưu máy cục bộ (fb_downloads)", value="local", checked=True),
            questionary.Choice("Upload lên Google Drive", value="drive", checked=True),
        ],
    ).ask()

    if not store_choices:
        console.print("[yellow]Chưa chọn nơi lưu trữ. Đã hủy.[/yellow]")
        return

    raw_stores = []
    if "local" in store_choices:
        raw_stores.append(LocalStore(settings.output_dir))
    if "drive" in store_choices:
        raw_stores.append(DriveStore(settings.drive_root_folder))
    stores = [DedupMergedStore(s) for s in raw_stores]

    console.print("\n[bold green]Đang khởi động trình duyệt và bắt đầu quét...[/bold green]")
    all_results = []
    try:
        with ChromeLauncher(settings):
            with facebook_session(settings.debug_port, settings.output_dir) as fb:
                runner = Runner(fb, stores)
                for pub_idx, pub in enumerate(publishers):
                    if pub_idx:
                        console.print("[dim]Nghỉ ngắn giữa các NXB...[/dim]")
                    for t in targets:
                        label = f"{pub.name} ({t})" if t else pub.name
                        console.print(f"\n[bold cyan]>>> Đang xử lý: {label}[/bold cyan]")
                        res_list = runner.run([pub], t, kinds_filter)
                        for r in res_list:
                            all_results.append((pub.name, t or "Mới nhất", r.ok, r.message))
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Đã dừng quét theo yêu cầu người dùng (Ctrl+C). Hiển thị kết quả đã lấy được:[/bold yellow]")
    except BotError as error:
        console.print(f"\n[bold red]Lỗi:[/bold red] {error}")
        sys.exit(1)

    if all_results:
        table = Table(title="\nKẾT QUẢ THU THẬP LỊCH PHÁT HÀNH", show_header=True, header_style="bold magenta")
        table.add_column("Nhà Xuất Bản", style="cyan", width=14)
        table.add_column("Kỳ Lịch", style="yellow", width=10)
        table.add_column("Trạng Thái", width=12)
        table.add_column("Chi Tiết / Nguyên Nhân", style="white")

        for pub_name, period_label, ok, msg in all_results:
            table.add_row(pub_name, period_label, format_status(ok, msg), msg)

        console.print(table)


if __name__ == "__main__":
    main()