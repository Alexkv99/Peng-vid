from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from fal_integration_service.art_styles import DEFAULT_STYLE, available_styles, get_style

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT_DIR / "pipeline_output"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _create_run_dir(run_id: str | None = None) -> tuple[str, Path]:
    run_id = run_id or f"run_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def _save_upload(upload: UploadFile, run_dir: Path, stem: str) -> Path:
    suffix = Path(upload.filename or "").suffix
    path = run_dir / f"{stem}{suffix}"
    with path.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return path


def _write_text_upload(upload: UploadFile, run_dir: Path) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    allowed = {".txt", ".md", ".csv"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Only text files are supported right now. Paste the text instead.",
        )
    raw = upload.file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Text file must be UTF-8 encoded. Paste the text instead.",
        ) from exc
    path = run_dir / "input.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _read_log_tail(path: Path, max_bytes: int = 8000) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(size - max_bytes, 0))
        return handle.read().decode("utf-8", errors="replace").strip()


def _safe_voice_name(filename: str | None) -> str:
    raw = Path(filename or "").stem.strip()
    if not raw:
        return f"custom_voice_{int(time.time())}"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)
    return safe[:64] or f"custom_voice_{int(time.time())}"


@app.post("/generate")
async def generate(
    request: Request,
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    photo: UploadFile = File(...),
    voice: UploadFile = File(...),
    run_id: str | None = Form(None),
    style: str | None = Form(None),
) -> dict[str, str]:
    if bool(text) == bool(file):
        raise HTTPException(
            status_code=400,
            detail="Provide either text or a file (but not both).",
        )

    run_id, run_dir = _create_run_dir(run_id)
    input_path = None
    try:
        if file is not None:
            input_path = _write_text_upload(file, run_dir)
        else:
            input_path = run_dir / "input.txt"
            input_path.write_text(text or "", encoding="utf-8")

        photo_path = _save_upload(photo, run_dir, "photo")
        voice_path = _save_upload(voice, run_dir, "voice")
        voice_name = _safe_voice_name(voice.filename)

        style_key = style or DEFAULT_STYLE
        cmd = [
            sys.executable,
            "-u",
            str(ROOT_DIR / "video_pipeline_service" / "cli.py"),
            "--input-file",
            str(input_path),
            "--create-custom-voice",
            "--custom-voice-audio",
            str(voice_path),
            "--custom-voice-name",
            voice_name,
            "--face-image",
            str(photo_path),
            "--output-dir",
            str(run_dir),
            "--style",
            style_key,
        ]
        log_path = run_dir / "pipeline.log"
        with log_path.open("w", encoding="utf-8") as handle:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            returncode = process.wait()
        if returncode != 0:
            detail = _read_log_tail(log_path) or "Pipeline failed."
            raise HTTPException(status_code=500, detail=detail)
    finally:
        for upload in (file, photo, voice):
            if upload is not None and upload.file:
                upload.file.close()

    final_video = run_dir / "final_video.mp4"
    if not final_video.exists():
        raise HTTPException(status_code=500, detail="Final video not found.")

    base = str(request.base_url).rstrip("/")
    return {"run_id": run_id, "video_url": f"{base}/video/{run_id}"}


@app.get("/video/{run_id}")
def get_video(run_id: str) -> FileResponse:
    video_path = OUTPUT_ROOT / run_id / "final_video.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found.")
    return FileResponse(video_path, media_type="video/mp4", filename=f"{run_id}.mp4")


@app.get("/logs/{run_id}")
def get_logs(run_id: str) -> dict[str, str]:
    log_path = OUTPUT_ROOT / run_id / "pipeline.log"
    if not log_path.exists():
        return {"log": ""}
    return {"log": log_path.read_text(encoding="utf-8", errors="replace")}


@app.get("/styles")
def get_styles() -> dict[str, object]:
    styles = []
    for key in available_styles():
        style = get_style(key)
        styles.append({"key": style.key, "name": style.name})
    return {"default": DEFAULT_STYLE, "styles": styles}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("video_pipeline_service.api:app", host="0.0.0.0", port=8000)
