import random
import time
from datetime import date

from .models import BotError, LoginError, RunResult
from .sources import build_sources
from .text_utils import parse_target


class Runner:
    def __init__(self, session, stores, today=None, sleep=time.sleep, source_factory=build_sources):
        self._session = session
        self._stores = stores
        self._today = today or date.today()
        self._sleep = sleep
        self._build_sources = source_factory

    def run(self, publishers, target=None, kinds=None):
        results = []
        for index, publisher in enumerate(publishers):
            if index:
                self._sleep(random.uniform(10, 20))
            print("\n=== " + publisher.name + " ===")
            try:
                results.append(self._run_one(publisher, target, kinds))
            except LoginError as error:
                print(error)
                results.append(RunResult(publisher.name, False, str(error)))
                break
            except Exception as error:
                message = str(error).splitlines()[0][:200]
                print("Loi:", message)
                results.append(RunResult(publisher.name, False, message))
        return results

    def _explain_missing(self, publisher, want, tried_kinds):
        if not want:
            return "Khong lay duoc anh"
        wy, wm = want
        period_str = f"{wy:04d}-{wm:02d}"

        known_periods = set()
        state_map = getattr(self._session, "_photos_scan_state", None) or {}
        for st in state_map.values():
            known_periods.update(st.get("found", {}).keys())

        album_map = getattr(self._session, "_album_photo_months", None) or {}
        if (publisher.slug, wy) in album_map:
            for m, _ in album_map[(publisher.slug, wy)].values():
                if m:
                    known_periods.add((wy, m))

        if known_periods:
            latest_y, latest_m = max(known_periods)
            if (wy, wm) > (latest_y, latest_m):
                return (
                    f"NXB chua dang lich {period_str} "
                    f"(lich moi nhat hien co tren Fanpage: {latest_y:04d}-{latest_m:02d})"
                )

        if (wy, wm) >= (self._today.year, self._today.month):
            return f"NXB chua dang lich thang {wm}/{wy} tren Fanpage (da quet: {', '.join(tried_kinds)})"

        return f"Khong tim thay lich {period_str} tren Fanpage (da quet: {', '.join(tried_kinds)})"

    def _run_one(self, publisher, target, kinds):
        sources = self._build_sources(self._session, publisher, self._today, kinds)
        if not sources:
            return RunResult(publisher.name, True, "bo qua (khong co nguon phu hop)")

        want = parse_target(target)
        is_old_target = False
        if want and len(sources) > 1:
            months_ago = (self._today.year - want[0]) * 12 + (self._today.month - want[1])
            is_old_target = months_ago >= 2

        poster = None
        tried_kinds = []
        for source in sources:
            if target and getattr(source, "_opts", {}).get("year_offset"):
                continue
            if is_old_target and source.kind == "featured" and (not kinds or len(kinds) > 1):
                print("Bo qua 'featured' vi dang tim lich cu:", target)
                continue
            print("Nguon:", source.kind)
            tried_kinds.append(source.kind)
            poster = source.fetch(target)
            if poster:
                print(f"Da tim thay ket qua ({poster.period}) tu nguon '{source.kind}', khong tim nguon tiep theo.")
                break
        if not poster:
            raise BotError(self._explain_missing(publisher, want, tried_kinds))
        notes = [store.save(publisher.name, poster) for store in self._stores]
        age = (self._today.year - poster.year) * 12 + self._today.month - poster.month
        if not target and age > 2:
            warning = f"CANH BAO: lich thang {poster.period} da cu {age} thang, co the chua phai lich moi nhat"
            print(warning)
            notes.append(warning)
        return RunResult(publisher.name, True, "; ".join(notes))