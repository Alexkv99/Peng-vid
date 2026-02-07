from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT_DIR / "pipeline_output"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _create_run_dir() -> tuple[str, Path]:
    run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def _save_upload(upload: UploadFile, run_dir: Path, stem: str) -> Path:
    suffix = Path(upload.filename or "").suffix
    path = run_dir / f"{stem}{suffix}"
    with path.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return path


@app.post("/generate")
async def generate(
    request: Request,
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    photo: UploadFile = File(...),
    voice: UploadFile = File(...),
) -> dict[str, str]:
    if bool(text) == bool(file):
        raise HTTPException(
            status_code=400,
            detail="Provide either text or a file (but not both).",
        )

    run_id, run_dir = _create_run_dir()
    input_path = None
    try:
        if file is not None:
            input_path = _save_upload(file, run_dir, "input")
        else:
            input_path = run_dir / "input.txt"
            input_path.write_text(text or "", encoding="utf-8")

        photo_path = _save_upload(photo, run_dir, "photo")
        voice_path = _save_upload(voice, run_dir, "voice")

        cmd = [
            sys.executable,
            str(ROOT_DIR / "video_pipeline_service" / "cli.py"),
            "--input-file",
            str(input_path),
            "--create-custom-voice",
            "--custom-voice-audio",
            str(voice_path),
            "--face-image",
            str(photo_path),
            "--output-dir",
            str(run_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "Pipeline failed."
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("video_pipeline_service.api:app", host="0.0.0.0", port=8000)
