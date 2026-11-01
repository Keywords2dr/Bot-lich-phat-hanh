import sys
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lichbot.bootstrap import resolve_publishers, run_pipeline
from lichbot.models import BotError, RunStatus
from lichbot.policy import expand_year_targets, max_available_period, normalize_target, RANGE_RE, TARGET_RE, YEAR_RE
from lichbot.publishers import PUBLISHERS

console = Console()


def ask_targets():
    mode = questionary.select(
        "Chon che do lay lich:",
        choices=[
            questionary.Choice("1. Lay lich moi nhat hien co (Tu dong)", value="latest"),
            questionary.Choice("2. Chi dinh 1 thang cu the (VD: 2026-5 hoac 2026-05)", value="single"),
            questionary.Choice("3. Lay TOAN BO lich trong 1 nam (VD: 2025 hoac 2026)", value="full_year"),
            questionary.Choice("4. Lay theo khoang thang trong nam (VD: Nam 2025, tu thang 1 den 6)", value="range"),
        ],
    ).ask()

    if not mode:
        return None
    if mode == "latest":
        return [None]

    if mode == "single":
        raw = questionary.text(
            "Nhap nam-thang can lay (VD: 2026-5, 2026-10):",
            validate=lambda t: bool(TARGET_RE.match(t.strip())) or "Dinh dang: YYYY-M hoac YYYY-MM",
        ).ask()
        return [normalize_target(raw)] if raw else None

    if mode in ("full_year", "range"):
        raw_year = questionary.text(
            "Nhap nam (VD: 2025, 2026):",
            validate=lambda t: bool(YEAR_RE.match(t.strip())) or "Nhap nam 4 chu so (VD: 2025)",
        ).ask()
        if not raw_year:
            return None

        start_m, end_m = 1, 12
        if mode == "range":
            raw_r = questionary.text(
                "Nhap khoang thang bat dau - ket thuc (VD: 1-6 hoac 10-12):",
                validate=lambda t: bool(RANGE_RE.match(t.strip())) or "Dinh dang: Dau-Cuoi (VD: 1-6)",
            ).ask()
            if not raw_r:
                return None
            m = RANGE_RE.match(raw_r.strip())
            start_m, end_m = int(m.group(1)), int(m.group(2))

        valid, skipped = expand_year_targets(raw_year.strip(), start_m, end_m)
        if skipped:
            console.print(f"[yellow]Bo qua cac thang tuong lai chua phat hanh: {', '.join(skipped)}[/yellow]")
        return valid


def render_table(results):
    table = Table(title="\nKET QUA THU THAP LICH PHAT HANH", show_header=True, header_style="bold magenta")
    table.add_column("Nha Xuat Ban", style="cyan", width=14)
    table.add_column("Ky Lich", style="yellow", width=10)
    table.add_column("Trang Thai", width=14)
    table.add_column("Chi Tiet", style="white")

    color_map = {
        RunStatus.SUCCESS: "[bold green]THANH CONG[/bold green]",
        RunStatus.NOT_PUBLISHED: "[bold yellow]CHUA DANG[/bold yellow]",
        RunStatus.NOT_FOUND: "[bold red]KHONG THAY[/bold red]",
        RunStatus.ERROR: "[bold red]LOI[/bold red]",
    }

    for r in results:
        status_text = color_map.get(r.status, str(r.status))
        table.add_row(r.publisher, r.target or "Moi nhat", status_text, r.message)

    console.print(table)


def main():
    console.print(Panel.fit("[bold cyan]BOT SAN LICH PHAT HANH TRUYEN TRANH[/bold cyan]", border_style="cyan"))

    pub_choices = [p.name for p in PUBLISHERS]
    selected_names = questionary.checkbox(
        "Chon Nha Xuat Ban (Space de chon, Enter de xac nhan):",
        choices=[questionary.Choice(n, checked=True) for n in pub_choices],
    ).ask()
    if not selected_names:
        return

    targets = ask_targets()
    if not targets:
        return

    selected_sources = questionary.checkbox(
        "Chon nguon quet:",
        choices=[
            questionary.Choice("Bai ghim (featured)", value="featured", checked=True),
            questionary.Choice("Album anh (album / photos)", value="album_photos", checked=True),
            questionary.Choice("Hashtag (hashtag)", value="hashtag", checked=True),
        ],
    ).ask()

    kinds = None
    if selected_sources and len(selected_sources) < 3:
        kinds = set()
        for s in selected_sources:
            if s == "album_photos":
                kinds.update(("album", "photos"))
            else:
                kinds.add(s)

    stores = questionary.checkbox(
        "Noi luu anh:",
        choices=[
            questionary.Choice("Luu may cuc bo", value="local", checked=True),
            questionary.Choice("Upload Google Drive", value="drive", checked=True),
        ],
    ).ask()

    publishers = resolve_publishers(selected_names)
    console.print("\n[bold green]Bat dau quet...[/bold green]")
    try:
        results = run_pipeline(
            publishers,
            targets=targets,
            kinds=kinds,
            use_local="local" in stores,
            use_drive="drive" in stores,
        )
        render_table(results)
    except KeyboardInterrupt:
        console.print("\n[yellow]Da dung theo yeu cau.[/yellow]")
    except BotError as err:
        console.print(f"[bold red]Loi:[/bold red] {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()