from .chrome import ChromeLauncher
from .facebook import facebook_session
from .models import BotError
from .publishers import PUBLISHERS
from .runner import Runner
from .scan_context import ScanContext
from .settings import Settings, load_env, missing_env
from .storage import DedupStore, DriveStore, LocalStore


def create_stores(settings, use_local=True, use_drive=True):
    raw = []
    if use_local:
        raw.append(LocalStore(settings.output_dir))
    if use_drive:
        raw.append(DriveStore(settings.drive_root_folder))
    return [DedupStore(s) for s in raw]


def resolve_publishers(names):
    known = {p.name.lower(): p for p in PUBLISHERS}
    if not names:
        return list(PUBLISHERS)
    unknown = [n for n in names if n.lower() not in known]
    if unknown:
        raise BotError("Khong co NXB: " + ", ".join(unknown))
    return [known[n.lower()] for n in names]


def run_pipeline(
    publishers,
    targets=None,
    kinds=None,
    use_local=True,
    use_drive=True,
    should_stop=None,
    on_chrome=None,
):
    settings = Settings()
    load_env(settings.env_file)
    missing = missing_env(settings.required_env)
    if use_drive and missing:
        raise BotError("Thieu bien moi truong: " + ", ".join(missing))

    stores = create_stores(settings, use_local, use_drive)
    context = ScanContext()

    with ChromeLauncher(settings) as launcher:
        if on_chrome:
            on_chrome(launcher)
        with facebook_session(settings.debug_port, settings.output_dir) as fb:
            runner = Runner(fb, stores, context=context, should_stop=should_stop)
            return runner.run(publishers, kinds=kinds, targets=targets)