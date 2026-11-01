import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    profile_dir: Path = BASE_DIR / "chrome_bot"
    debug_port: int = 9222
    output_dir: Path = BASE_DIR / "fb_downloads"
    drive_root_folder: str = "Lich phat hanh"
    env_file: Path = BASE_DIR / "secrets.env"
    required_env: tuple = (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
    )


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def missing_env(names):
    return [name for name in names if not os.environ.get(name)]
