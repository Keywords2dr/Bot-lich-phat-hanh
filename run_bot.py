import sys
from lichbot.bootstrap import resolve_publishers, run_pipeline
from lichbot.models import BotError
from lichbot.policy import expand_year_targets, normalize_target, TARGET_RE, YEAR_RE

KINDS = ("featured", "album", "hashtag", "photos")


def parse_args(argv):
    targets = []
    kinds = set()
    names = []
    for arg in argv:
        if TARGET_RE.match(arg):
            targets.append(normalize_target(arg))
        elif YEAR_RE.match(arg):
            valid, _ = expand_year_targets(arg)
            targets.extend(valid)
        elif arg in KINDS:
            kinds.add(arg)
            if arg == "album":
                kinds.add("photos")
        else:
            names.append(arg.lower())
    return targets or [None], kinds, names


def main():
    targets, kinds, names = parse_args(sys.argv[1:])
    try:
        publishers = resolve_publishers(names)
        results = run_pipeline(publishers, targets=targets, kinds=kinds or None)
        print("\n=== TOM TAT ===")
        for r in results:
            label = f"{r.publisher} ({r.target})" if r.target else r.publisher
            print(f"{r.status.value:13} {label}: {r.message}")
    except BotError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()