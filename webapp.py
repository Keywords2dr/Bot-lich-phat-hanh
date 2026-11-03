import json
import os
import queue
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lichbot.bootstrap import resolve_publishers, run_pipeline
from lichbot.policy import expand_year_targets, max_available_period, normalize_target
from lichbot.publishers import PUBLISHERS
from lichbot.settings import Settings

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

app = FastAPI(title="LichBot Studio API")

settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def disable_browser_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/downloads", StaticFiles(directory=str(settings.output_dir)), name="downloads")
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

SCAN_STATE = {
    "running": False,
    "cancel_event": threading.Event(),
    "launcher": None,
}


class ScanRequest(BaseModel):
    publishers: list[str]
    mode: str
    single_target: str = ""
    year: str = "2026"
    start_month: int = 1
    end_month: int = 12
    sources: list[str]
    use_local: bool = True
    use_drive: bool = False


class QueueStream:
    def __init__(self, log_queue: queue.Queue, original_stdout):
        self._queue = log_queue
        self._stdout = original_stdout

    def write(self, text: str):
        if text:
            self._stdout.write(text)
            self._queue.put({"type": "log", "text": text})

    def flush(self):
        self._stdout.flush()


def scan_local_images():
    items = []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    for f in settings.output_dir.iterdir():
        if not f.is_file() or f.suffix.lower() not in exts or f.name.startswith("debug_"):
            continue
        stat = f.stat()
        stem = f.stem
        parts = stem.split("_", 1)
        pub_part = parts[0] if len(parts) > 1 else "Khác"
        period_part = parts[1] if len(parts) > 1 else ""
        items.append(
            {
                "name": f.name,
                "publisher": pub_part,
                "period": period_part,
                "size_kb": round(stat.st_size / 1024, 1),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
                "ts": stat.st_mtime,
            }
        )
    items.sort(key=lambda x: (x["period"], x["ts"]), reverse=True)
    return items


def resolve_request_targets(req: ScanRequest):
    if req.mode == "latest":
        return [None], []
    if req.mode == "single":
        norm = normalize_target(req.single_target)
        if not norm:
            raise ValueError("Định dạng tháng không hợp lệ. Hãy chọn đúng Năm và Tháng.")
        return [norm], []
    if req.mode == "full_year":
        return expand_year_targets(req.year, 1, 12)
    if req.start_month > req.end_month:
        raise ValueError("Tháng bắt đầu không được lớn hơn tháng kết thúc.")
    return expand_year_targets(req.year, req.start_month, req.end_month)


@app.get("/")
def serve_spa():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/init")
def get_init_data():
    max_y, max_m = max_available_period()
    return {
        "publishers": [{"name": p.name, "slug": p.slug} for p in PUBLISHERS],
        "max_period": f"{max_y:04d}-{max_m:02d}",
        "output_dir": str(settings.output_dir.resolve()),
        "images": scan_local_images(),
    }


@app.post("/api/cancel")
def cancel_scan():
    if not SCAN_STATE["running"]:
        return {"ok": False, "message": "Hiện không có tiến trình nào đang chạy."}
    SCAN_STATE["cancel_event"].set()
    launcher = SCAN_STATE.get("launcher")
    if launcher and getattr(launcher, "_proc", None):
        try:
            launcher._proc.terminate()
        except Exception:
            pass
    return {"ok": True, "message": "Đã gửi lệnh dừng khẩn cấp!"}


@app.post("/api/open-folder")
def open_output_folder():
    folder = settings.output_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(folder))
        return {"ok": True}
    return {"ok": False, "error": "Chỉ hỗ trợ mở nhanh trên Windows."}


@app.delete("/api/images/{filename}")
def delete_image(filename: str):
    safe_name = Path(filename).name
    target_path = settings.output_dir / safe_name
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file ảnh.")
    target_path.unlink()
    return {"ok": True, "images": scan_local_images()}


@app.post("/api/stream-run")
def stream_scan(req: ScanRequest):
    log_queue: queue.Queue = queue.Queue()
    SCAN_STATE["cancel_event"].clear()
    SCAN_STATE["running"] = True

    def worker():
        start_ts = time.time()
        old_stdout = sys.stdout
        sys.stdout = QueueStream(log_queue, old_stdout)
        try:
            if not req.publishers:
                raise ValueError("Vui lòng chọn ít nhất 1 Nhà Xuất Bản để quét.")

            targets, skipped = resolve_request_targets(req)
            if skipped:
                print(f"[Policy] Tự động bỏ qua các kỳ tương lai chưa phát hành: {', '.join(skipped)}")

            if not targets:
                raise ValueError("Không có kỳ lịch hợp lệ nào cần quét.")

            kinds = None
            if req.sources and len(req.sources) < 3:
                kinds = set()
                for s in req.sources:
                    if s == "album_photos":
                        kinds.update(("album", "photos"))
                    else:
                        kinds.add(s)

            pubs = resolve_publishers(req.publishers)
            print(f"🚀 Bắt đầu tiến trình | NXB: {', '.join(req.publishers)} | Số kỳ: {len(targets)}")

            results = run_pipeline(
                pubs,
                targets=targets,
                kinds=kinds,
                use_local=req.use_local,
                use_drive=req.use_drive,
                should_stop=SCAN_STATE["cancel_event"].is_set,
                on_chrome=lambda c: SCAN_STATE.update({"launcher": c}),
            )
            elapsed = round(time.time() - start_ts, 1)
            cancelled = SCAN_STATE["cancel_event"].is_set()
            payload = [
                {
                    "publisher": r.publisher,
                    "target": r.target or "Mới nhất",
                    "status": r.status.value,
                    "ok": r.ok,
                    "message": r.message,
                }
                for r in results
            ]
            log_queue.put(
                {
                    "type": "done",
                    "ok": not cancelled,
                    "cancelled": cancelled,
                    "elapsed": elapsed,
                    "skipped": skipped,
                    "results": payload,
                    "images": scan_local_images(),
                }
            )
        except Exception as err:
            elapsed = round(time.time() - start_ts, 1)
            cancelled = SCAN_STATE["cancel_event"].is_set()
            tb_text = traceback.format_exc()
            log_queue.put(
                {
                    "type": "done",
                    "ok": False,
                    "cancelled": cancelled,
                    "elapsed": elapsed,
                    "error": "Đã hủy tiến trình theo yêu cầu người dùng." if cancelled else str(err),
                    "traceback": "" if cancelled else tb_text,
                    "results": [],
                    "images": scan_local_images(),
                }
            )
        finally:
            SCAN_STATE["running"] = False
            SCAN_STATE["launcher"] = None
            sys.stdout = old_stdout
            log_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_generator():
        while True:
            item = log_queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)