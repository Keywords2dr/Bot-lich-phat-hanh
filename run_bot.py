import re
import sys

from lichbot.chrome import ChromeLauncher
from lichbot.facebook import facebook_session
from lichbot.models import BotError
from lichbot.publishers import PUBLISHERS
from lichbot.runner import Runner
from lichbot.settings import Settings, load_env, missing_env
from lichbot.storage import DriveStore, LocalStore

KINDS = ("featured", "album", "hashtag", "photos")


def parse_args(argv):
    target = None
    kinds = set()
    names = []
    for arg in argv:
        if re.fullmatch(r"\d{4}-\d{2}", arg):
            target = arg
        elif arg in KINDS:
            kinds.add(arg)
        else:
            names.append(arg.lower())
    return target, kinds, names


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

    target, kinds, names = parse_args(sys.argv[1:])
    try:
        publishers = select_publishers(names)
        stores = [LocalStore(settings.output_dir), DriveStore(settings.drive_root_folder)]
        with ChromeLauncher(settings):
            with facebook_session(settings.debug_port, settings.output_dir) as fb:
                results = Runner(fb, stores).run(publishers, target, kinds or None)
    except BotError as error:
        sys.exit(str(error))

    print("\n=== TOM TAT ===")
    for result in results:
        print(f"{'OK' if result.ok else 'LOI':4} {result.publisher}: {result.message}")


if __name__ == "__main__":
    main()
