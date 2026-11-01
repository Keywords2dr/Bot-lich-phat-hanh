import re
import sys
from datetime import date

from lichbot.chrome import ChromeLauncher
from lichbot.facebook import facebook_session
from lichbot.models import BotError
from lichbot.publishers import PUBLISHERS
from lichbot.runner import Runner
from lichbot.settings import Settings, load_env, missing_env
from lichbot.storage import DriveStore, LocalStore

KINDS = ("featured", "album", "hashtag", "photos")
TARGET_RE = re.compile(r"^(20\d{2})[-/](0?[1-9]|1[0-2])$")
YEAR_RE = re.compile(r"^(20\d{2})$")


def parse_args(argv):
    targets = []
    kinds = set()
    names = []
    for arg in argv:
        m_target = TARGET_RE.match(arg)
        m_year = YEAR_RE.match(arg)
        if m_target:
            targets.append(f"{int(m_target.group(1)):04d}-{int(m_target.group(2)):02d}")
        elif m_year:
            year = int(m_year.group(1))
            today = date.today()
            max_m = min(12, today.month + 1) if year == today.year else 12
            targets.extend(f"{year:04d}-{m:02d}" for m in range(1, max_m + 1))
        elif arg in KINDS:
            kinds.add(arg)
            if arg == "album":
                kinds.add("photos")
        else:
            names.append(arg.lower())
    return targets or [None], kinds, names


def select_publishers(names):
    known = [p.name.lower() for p in PUBLISHERS]
    unknown = [n for n in names if n not in known]
    if unknown:
        raise BotError(
            "Khong co NXB ten: " + ", ".join(unknown)
            + ". Cac NXB co san: " + ", ".join(p.name for p in PUBLISHERS)
        )
    return [p for p in PUBLISHERS if not names or p.name.lower() in names]


def main():
    settings = Settings()
    load_env(settings.env_file)
    missing = missing_env(settings.required_env)
    if missing:
        sys.exit("Thieu " + ", ".join(missing) + " (kiem tra file secrets.env)")

    targets, kinds, names = parse_args(sys.argv[1:])
    try:
        publishers = select_publishers(names)
        stores = [LocalStore(settings.output_dir), DriveStore(settings.drive_root_folder)]
        all_results = []
        with ChromeLauncher(settings):
            with facebook_session(settings.debug_port, settings.output_dir) as fb:
                runner = Runner(fb, stores)
                for target in targets:
                    res = runner.run(publishers, target, kinds or None)
                    for r in res:
                        label = f"{r.publisher} ({target})" if target else r.publisher
                        all_results.append((label, r.ok, r.message))
    except BotError as error:
        sys.exit(str(error))

    print("\n=== TOM TAT ===")
    for label, ok, message in all_results:
        print(f"{'OK' if ok else 'LOI':4} {label}: {message}")


if __name__ == "__main__":
    main()