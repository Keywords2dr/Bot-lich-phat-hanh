import inspect
import random
import time
from datetime import date

from .models import BotError, LoginError, RunResult, RunStatus
from .policy import parse_target
from .scan_context import ScanContext
from .sources import build_sources


class Runner:
    def __init__(
        self,
        session,
        stores,
        today=None,
        sleep=time.sleep,
        source_factory=build_sources,
        context=None,
        should_stop=None,
    ):
        self._session = session
        self._stores = stores
        self._today = today or date.today()
        self._sleep = sleep
        self._build_sources = source_factory
        self._ctx = context or ScanContext()
        self._should_stop = should_stop or (lambda: False)

    def _interruptible_sleep(self, seconds):
        if self._sleep is not time.sleep:
            self._sleep(seconds)
            return
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self._should_stop():
                break
            time.sleep(min(0.25, max(0.0, end_time - time.time())))

    def run(self, publishers, target=None, kinds=None, targets=None):
        all_targets = targets if targets is not None else [target]
        results = []

        for index, publisher in enumerate(publishers):
            if self._should_stop():
                print("\n[DA HUY] Tien trinh da dung theo yeu cau nguoi dung.")
                break

            if index > 0:
                delay = random.uniform(10, 20)
                print(f"\n[Nghi giua cac NXB: {delay:.1f}s de giu an toan tai khoan...]")
                self._interruptible_sleep(delay)
                if self._should_stop():
                    print("\n[DA HUY] Da dung trong luc nghi giua cac NXB.")
                    break

            print("\n=== " + publisher.name + " ===")
            for t in all_targets:
                if self._should_stop():
                    print(f"[DA HUY] Bo qua ky {t} do nguoi dung da bam dung.")
                    break
                try:
                    res = self._run_one(publisher, t, kinds)
                    results.append(res)
                except LoginError as error:
                    print(error)
                    results.append(RunResult(publisher.name, t, RunStatus.ERROR, str(error)))
                    return results
                except BotError as error:
                    msg = str(error)
                    print(f"Loi: {msg}")
                    status = (
                        RunStatus.NOT_PUBLISHED
                        if "chua dang" in msg
                        else RunStatus.NOT_FOUND
                    )
                    results.append(RunResult(publisher.name, t, status, msg))
                except Exception as error:
                    if self._should_stop():
                        print("\n[DA HUY] Da ngat phien trinh duyet theo yeu cau.")
                        return results
                    message = str(error).splitlines()[0][:200]
                    print("Loi:", message)
                    results.append(RunResult(publisher.name, t, RunStatus.ERROR, message))
        return results

    def _call_build_sources(self, publisher, kinds):
        try:
            sig = inspect.signature(self._build_sources)
            if "context" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                return self._build_sources(
                    self._session, publisher, self._today, kinds, context=self._ctx
                )
        except (ValueError, TypeError):
            pass
        return self._build_sources(self._session, publisher, self._today, kinds)

    def _explain_missing(self, publisher, want, tried_kinds):
        if not want:
            return "Khong lay duoc anh"
        wy, wm = want
        period_str = f"{wy:04d}-{wm:02d}"

        known = self._ctx.all_known_periods(publisher.slug, wy)
        if known:
            latest_y, latest_m = max(known)
            if (wy, wm) > (latest_y, latest_m):
                return (
                    f"NXB chua dang lich {period_str} "
                    f"(lich moi nhat tren Fanpage: {latest_y:04d}-{latest_m:02d})"
                )

        if (wy, wm) >= (self._today.year, self._today.month):
            return f"NXB chua dang lich thang {wm}/{wy} tren Fanpage"

        return f"Khong tim thay lich {period_str} tren Fanpage (da thu: {', '.join(tried_kinds)})"

    def _run_one(self, publisher, target, kinds):
        sources = self._call_build_sources(publisher, kinds)
        if not sources:
            return RunResult(publisher.name, target, RunStatus.SUCCESS, "bo qua (khong co nguon phu hop)")

        want = parse_target(target)
        poster = None
        tried_kinds = []

        for source in sources:
            if self._should_stop():
                raise BotError("Da huy boi nguoi dung")
            supports_fn = getattr(source, "supports", None)
            if callable(supports_fn) and not supports_fn(target):
                continue
            print("Nguon:", source.kind)
            tried_kinds.append(source.kind)
            poster = source.fetch(target)
            if poster:
                print(f"Da tim thay ket qua ({poster.period}) tu '{source.kind}'!")
                break

        if not poster:
            raise BotError(self._explain_missing(publisher, want, tried_kinds))

        notes = [store.save(publisher.name, poster) for store in self._stores]
        age = (self._today.year - poster.year) * 12 + self._today.month - poster.month
        if not target and age > 2:
            warning = f"CANH BAO: lich thang {poster.period} da cu {age} thang, co the chua phai lich moi nhat"
            print(warning)
            notes.append(warning)
        return RunResult(publisher.name, target, RunStatus.SUCCESS, "; ".join(notes))