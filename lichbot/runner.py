import random
import time
from datetime import date

from .models import BotError, LoginError, RunResult
from .sources import build_sources


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
                message = str(error)[:200]
                print("Loi:", message)
                results.append(RunResult(publisher.name, False, message))
        return results

    def _run_one(self, publisher, target, kinds):
        sources = self._build_sources(self._session, publisher, self._today, kinds)
        if not sources:
            return RunResult(publisher.name, True, "bo qua (khong co nguon phu hop)")
        poster = None
        for source in sources:
            print("Nguon:", source.kind)
            poster = source.fetch(target)
            if poster:
                break
        if not poster:
            raise BotError("Khong lay duoc anh")
        notes = [store.save(publisher.name, poster) for store in self._stores]
        age = (self._today.year - poster.year) * 12 + self._today.month - poster.month
        if not target and age > 2:
            warning = f"CANH BAO: lich thang {poster.period} da cu {age} thang, co the chua phai lich moi nhat"
            print(warning)
            notes.append(warning)
        return RunResult(publisher.name, True, "; ".join(notes))
