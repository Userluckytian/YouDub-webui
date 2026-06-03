from __future__ import annotations

import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from . import database, worker
from .adapters.local_video import remove_upload, upload_dir
from .adapters.openai_translate import list_models as list_openai_models
from .config import UPLOAD_TEMP_DIR, WORKFOLDER, YOUTUBE_COOKIE_PATH, ensure_runtime_dirs
from .pipeline import run_task
from .runtime_checks import validate_runtime_device
from .sanitize import sanitize_text
from .youtube import LOCAL_UPLOAD_DIRECTIONS, extract_video_id, is_local_upload_url

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".flv", ".wmv"}
LOCAL_UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_LOCAL_UPLOAD_BYTES = int(os.getenv("LOCAL_UPLOAD_MAX_BYTES", str(4 * 1024 * 1024 * 1024)))

# Global lock for manifest file access
upload_locks: dict[str, threading.Lock] = {}
upload_locks_lock = threading.Lock()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return "********"


class TaskCreate(BaseModel):
    url: str


class YouTubeCookieUpdate(BaseModel):
    content: str


class OpenAISettingsUpdate(BaseModel):
    base_url: str
    api_key: str = ""
    clear_api_key: bool = False
    model: str
    translate_concurrency: str = ""


class OpenAIModelsRequest(BaseModel):
    base_url: str = ""
    api_key: str = ""


class YtdlpSettingsUpdate(BaseModel):
    proxy_port: str = ""


class UploadSettingsUpdate(BaseModel):
    mode: str = "chunked"  # "single" or "chunked"
    chunk_size_mb: str = "10"
    concurrency: str = "3"


class ChunkUploadInitRequest(BaseModel):
    direction: str = "en-zh"
    file_name: str
    file_size: int
    total_chunks: int


class ChunkUploadChunkRequest(BaseModel):
    upload_id: str
    chunk_index: int


def normalize_proxy_port(value: str) -> str:
    proxy_port = value.strip()
    if not proxy_port:
        return ""
    if not proxy_port.isdigit():
        raise HTTPException(status_code=422, detail="Proxy port must be numeric.")
    port = int(proxy_port)
    if port < 1 or port > 65535:
        raise HTTPException(status_code=422, detail="Proxy port must be between 1 and 65535.")
    return str(port)


def normalize_translate_concurrency(value: str) -> str:
    concurrency = value.strip()
    if not concurrency:
        return ""
    if not all("0" <= char <= "9" for char in concurrency):
        raise HTTPException(status_code=422, detail="Translate concurrency must be numeric.")
    workers = int(concurrency)
    if workers < 1 or workers > 200:
        raise HTTPException(
            status_code=422, detail="Translate concurrency must be between 1 and 200."
        )
    return concurrency


def normalize_upload_mode(value: str) -> str:
    mode = value.strip()
    if mode not in ("single", "chunked"):
        raise HTTPException(status_code=422, detail="Upload mode must be 'single' or 'chunked'.")
    return mode


def normalize_chunk_size_mb(value: str) -> str:
    size = value.strip()
    if not size:
        return "10"
    if not all("0" <= char <= "9" for char in size):
        raise HTTPException(status_code=422, detail="Chunk size must be numeric.")
    size_mb = int(size)
    if size_mb < 1 or size_mb > 1000:
        raise HTTPException(status_code=422, detail="Chunk size must be between 1 and 1000 MB.")
    return str(size_mb)


def normalize_upload_concurrency(value: str) -> str:
    concurrency = value.strip()
    if not concurrency:
        return "3"
    if not all("0" <= char <= "9" for char in concurrency):
        raise HTTPException(status_code=422, detail="Upload concurrency must be numeric.")
    workers = int(concurrency)
    if workers < 1 or workers > 10:
        raise HTTPException(status_code=422, detail="Upload concurrency must be between 1 and 10.")
    return str(workers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_runtime_dirs()
    database.init_db()
    database.backfill_titles_from_metadata()
    database.fail_stale_active_tasks()
    worker.start(run_task)
    yield


app = FastAPI(title="YouDub API", lifespan=lifespan)


DEFAULT_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|"
    r"127(?:\.\d{1,3}){3}|"
    r"0\.0\.0\.0|"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
    r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}|"
    r"\[::1\]"
    r"):3000$"
)


def cors_origins() -> list[str]:
    defaults = ["http://localhost:3000", "http://127.0.0.1:3000"]
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    extra = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [*defaults, *extra]


def cors_origin_regex() -> str:
    configured = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
    return configured or DEFAULT_CORS_ORIGIN_REGEX


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_origin_regex=cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _ensure_runtime_ready() -> None:
    try:
        validate_runtime_device()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskCreate) -> dict:
    try:
        video_id = extract_video_id(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing_id = database.find_task_by_video_id(video_id)
    if existing_id:
        return database.get_task(existing_id)

    _ensure_runtime_ready()
    task_id = database.create_task(payload.url.strip(), task_id=video_id)
    worker.enqueue(task_id)
    return database.get_task(task_id)


def _clean_upload_filename(filename: str | None) -> str:
    original = Path(filename or "").name.strip()
    if not original:
        raise HTTPException(status_code=422, detail="Video filename is required.")
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(status_code=422, detail="Unsupported video file type.")
    safe_stem = sanitize_text(Path(original).stem) or "video"
    return f"{safe_stem}{suffix}"


def _save_uploaded_file(file: UploadFile, destination: Path) -> int:
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while True:
            chunk = file.file.read(LOCAL_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_LOCAL_UPLOAD_BYTES:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded video is too large.")
            handle.write(chunk)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Uploaded video is empty.")
    return total


@app.post("/api/tasks/upload", status_code=201)
def upload_local_video(direction: str = Form("en-zh"), file: UploadFile = File(...)) -> dict:
    if direction not in LOCAL_UPLOAD_DIRECTIONS:
        raise HTTPException(status_code=422, detail="Unsupported local video direction.")

    _ensure_runtime_ready()
    original_name = Path(file.filename or "").name.strip()
    stored_name = _clean_upload_filename(original_name)
    task_id = str(uuid.uuid4())
    target_dir = upload_dir(WORKFOLDER, task_id)
    try:
        _save_uploaded_file(file, target_dir / stored_name)
    except HTTPException:
        remove_upload(WORKFOLDER, task_id)
        raise

    url = f"local://upload/{task_id}?direction={direction}&filename={quote(original_name)}"
    database.create_task(url, task_id=task_id)
    database.update_task(task_id, title=Path(original_name).stem)
    worker.enqueue(task_id)
    return database.get_task(task_id)


def _get_upload_temp_dir(upload_id: str) -> Path:
    return UPLOAD_TEMP_DIR / upload_id


def _get_chunk_path(upload_id: str, chunk_index: int) -> Path:
    return _get_upload_temp_dir(upload_id) / f"chunk_{chunk_index}.part"


def _get_chunk_manifest_path(upload_id: str) -> Path:
    return _get_upload_temp_dir(upload_id) / "manifest.json"


@app.post("/api/tasks/upload/init", status_code=201)
def init_chunk_upload(payload: ChunkUploadInitRequest) -> dict:
    if payload.direction not in LOCAL_UPLOAD_DIRECTIONS:
        raise HTTPException(status_code=422, detail="Unsupported local video direction.")

    _ensure_runtime_ready()
    task_id = str(uuid.uuid4())
    temp_dir = _get_upload_temp_dir(task_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Save manifest
    import json
    manifest = {
        "task_id": task_id,
        "direction": payload.direction,
        "file_name": payload.file_name,
        "file_size": payload.file_size,
        "total_chunks": payload.total_chunks,
        "uploaded_chunks": [],
    }
    _get_chunk_manifest_path(task_id).write_text(json.dumps(manifest), encoding="utf-8")

    return {
        "upload_id": task_id,
        "chunk_size": int(database.get_upload_settings()["chunk_size_mb"]) * 1024 * 1024,
    }


@app.post("/api/tasks/upload/chunk")
def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
) -> dict:
    temp_dir = _get_upload_temp_dir(upload_id)
    if not temp_dir.exists():
        raise HTTPException(status_code=404, detail="Upload session not found.")

    manifest_path = _get_chunk_manifest_path(upload_id)
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Upload manifest not found.")

    import json

    chunk_path = _get_chunk_path(upload_id, chunk_index)

    # Get or create lock for this upload_id
    with upload_locks_lock:
        if upload_id not in upload_locks:
            upload_locks[upload_id] = threading.Lock()
        lock = upload_locks[upload_id]

    # Use lock to prevent concurrent access
    with lock:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if chunk_index < 0 or chunk_index >= manifest["total_chunks"]:
            raise HTTPException(status_code=422, detail="Invalid chunk index.")

        # Skip if already uploaded
        if chunk_path.exists():
            if chunk_index not in manifest["uploaded_chunks"]:
                manifest["uploaded_chunks"].append(chunk_index)
                manifest["uploaded_chunks"].sort()
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            return {"uploaded_chunks": manifest["uploaded_chunks"]}

        # Save chunk
        chunk_path.write_bytes(file.file.read())

        # Update manifest
        if chunk_index not in manifest["uploaded_chunks"]:
            manifest["uploaded_chunks"].append(chunk_index)
            manifest["uploaded_chunks"].sort()
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    return {"uploaded_chunks": manifest["uploaded_chunks"]}


@app.post("/api/tasks/upload/complete", status_code=201)
def complete_chunk_upload(upload_id: str = Form(...)) -> dict:
    temp_dir = _get_upload_temp_dir(upload_id)
    if not temp_dir.exists():
        raise HTTPException(status_code=404, detail="Upload session not found.")

    manifest_path = _get_chunk_manifest_path(upload_id)
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Upload manifest not found.")

    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if len(manifest["uploaded_chunks"]) != manifest["total_chunks"]:
        raise HTTPException(
            status_code=400,
            detail=f"Upload incomplete: {len(manifest['uploaded_chunks'])}/{manifest['total_chunks']} chunks uploaded.",
        )

    # Merge chunks
    task_id = manifest["task_id"]
    original_name = manifest["file_name"]
    stored_name = _clean_upload_filename(original_name)
    target_dir = upload_dir(WORKFOLDER, task_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / stored_name

    with target_file.open("wb") as output:
        for chunk_index in range(manifest["total_chunks"]):
            chunk_path = _get_chunk_path(upload_id, chunk_index)
            if not chunk_path.exists():
                raise HTTPException(status_code=500, detail=f"Chunk {chunk_index} missing.")
            output.write(chunk_path.read_bytes())

    # Cleanup temp directory
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Create task
    direction = manifest["direction"]
    url = f"local://upload/{task_id}?direction={direction}&filename={quote(original_name)}"
    database.create_task(url, task_id=task_id)
    database.update_task(task_id, title=Path(original_name).stem)
    worker.enqueue(task_id)

    return database.get_task(task_id)


@app.get("/api/tasks/upload/status/{upload_id}")
def get_chunk_upload_status(upload_id: str) -> dict:
    temp_dir = _get_upload_temp_dir(upload_id)
    if not temp_dir.exists():
        raise HTTPException(status_code=404, detail="Upload session not found.")

    manifest_path = _get_chunk_manifest_path(upload_id)
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Upload manifest not found.")

    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return {
        "uploaded_chunks": manifest["uploaded_chunks"],
        "total_chunks": manifest["total_chunks"],
        "progress": len(manifest["uploaded_chunks"]) / manifest["total_chunks"] * 100,
    }


@app.get("/api/settings/upload")
def get_upload_settings() -> dict:
    return database.get_upload_settings()


@app.post("/api/settings/upload")
def save_upload_settings(payload: UploadSettingsUpdate) -> dict:
    database.save_upload_settings(
        normalize_upload_mode(payload.mode),
        normalize_chunk_size_mb(payload.chunk_size_mb),
        normalize_upload_concurrency(payload.concurrency),
    )
    return get_upload_settings()


@app.get("/api/tasks/current")
def current_task() -> dict | None:
    return database.get_current_task()


@app.get("/api/tasks")
def list_tasks(limit: int = 100) -> dict:
    return {"tasks": database.list_tasks(limit=limit)}


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str) -> dict:
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _is_inside_workfolder(path: Path) -> bool:
    workfolder = WORKFOLDER.resolve()
    try:
        path.resolve().relative_to(workfolder)
    except ValueError:
        return False
    return True


def _purge_task(task: dict) -> None:
    session_path = task.get("session_path")
    if session_path:
        session_dir = Path(session_path)
        if session_dir.exists() and _is_inside_workfolder(session_dir):
            shutil.rmtree(session_dir)
    log_file = database.log_path(task["id"])
    if log_file.exists():
        log_file.unlink()
    database.delete_task(task["id"])


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str) -> Response:
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task["status"] == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running task.")
    _purge_task(task)
    if is_local_upload_url(task["url"]):
        remove_upload(WORKFOLDER, task["id"])
    return Response(status_code=204)


@app.post("/api/tasks/{task_id}/rerun")
def rerun_task(task_id: str) -> dict:
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task["status"] == "running":
        raise HTTPException(status_code=409, detail="Cannot rerun a running task.")

    _ensure_runtime_ready()
    url = task["url"]
    _purge_task(task)
    new_id = database.create_task(url, task_id=task_id)
    worker.enqueue(new_id)
    return database.get_task(new_id)


@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict:
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task["status"] != "failed":
        raise HTTPException(status_code=409, detail="Only failed tasks can be resumed.")
    _ensure_runtime_ready()
    database.reset_failed_for_resume(task_id)
    worker.enqueue(task_id)
    return database.get_task(task_id)


@app.get("/api/tasks/{task_id}/log", response_class=PlainTextResponse)
def task_log(task_id: str) -> str:
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    path = database.log_path(task_id)
    return path.read_text(encoding="utf-8") if path.exists() else ""


@app.get("/api/tasks/{task_id}/artifact/final-video")
def final_video(task_id: str, download: bool = False) -> FileResponse:
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    final_path = task.get("final_video_path")
    if not final_path or not Path(final_path).exists():
        raise HTTPException(status_code=404, detail="Final video is not available.")
    name = Path(final_path).name
    if download:
        return FileResponse(final_path, media_type="video/mp4", filename=name)
    headers = {"Content-Disposition": f'inline; filename="{name}"'}
    return FileResponse(final_path, media_type="video/mp4", headers=headers)


@app.get("/api/cookies/youtube")
def get_youtube_cookie() -> dict:
    exists = YOUTUBE_COOKIE_PATH.exists()
    size = YOUTUBE_COOKIE_PATH.stat().st_size if exists else 0
    updated_at = YOUTUBE_COOKIE_PATH.stat().st_mtime if exists else None
    return {"exists": exists, "size": size, "updated_at": updated_at, "content": ""}


@app.post("/api/cookies/youtube")
def save_youtube_cookie(payload: YouTubeCookieUpdate) -> dict:
    YOUTUBE_COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = payload.content.strip()
    if content:
        YOUTUBE_COOKIE_PATH.write_text(content + "\n", encoding="utf-8")
    elif YOUTUBE_COOKIE_PATH.exists():
        YOUTUBE_COOKIE_PATH.unlink()
    return get_youtube_cookie()


@app.get("/api/settings/openai")
def get_openai_settings() -> dict:
    settings = database.get_openai_settings()
    return {
        "base_url": settings["base_url"],
        "api_key": mask_secret(settings["api_key"]),
        "has_api_key": bool(settings["api_key"]),
        "model": settings["model"],
        "translate_concurrency": settings["translate_concurrency"],
    }


@app.post("/api/settings/openai")
def save_openai_settings(payload: OpenAISettingsUpdate) -> dict:
    database.save_openai_settings(
        payload.base_url,
        payload.api_key,
        payload.model,
        normalize_translate_concurrency(payload.translate_concurrency),
        clear_api_key=payload.clear_api_key,
    )
    return get_openai_settings()


@app.post("/api/settings/openai/models")
def get_openai_models(payload: OpenAIModelsRequest) -> dict:
    settings = database.get_openai_settings()
    base_url = payload.base_url.strip() or settings["base_url"]
    api_key = payload.api_key.strip() or settings["api_key"]
    try:
        models = list_openai_models(base_url=base_url, api_key=api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {exc}") from exc
    return {"models": models}


@app.get("/api/settings/ytdlp")
def get_ytdlp_settings() -> dict:
    return database.get_ytdlp_settings()


@app.post("/api/settings/ytdlp")
def save_ytdlp_settings(payload: YtdlpSettingsUpdate) -> dict:
    database.save_ytdlp_settings(normalize_proxy_port(payload.proxy_port))
    return get_ytdlp_settings()
