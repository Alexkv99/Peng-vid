"""Pipeline that takes a list of speech chapters and generates one video per chapter."""

import json
import os
import requests

from .chapters import Chapter
from .fal_video import generate_video


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def _download_video(url: str, dest: str) -> None:
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def process_chapters(
    chapters: list[Chapter],
    *,
    model: str | None = None,
    download: bool = True,
) -> list[dict]:
    """Generate a video for each chapter and optionally download the files.

    Returns a list of result dicts, one per chapter, containing:
        - chapter: the Chapter object
        - response: raw fal API response
        - video_url: direct URL to the generated video
        - local_path: path to the downloaded file (if download=True)
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results: list[dict] = []

    for chapter in chapters:
        print(f"\n{'='*60}")
        print(f"Chapter {chapter.number}: {chapter.title}")
        print(f"{'='*60}")
        print(f"Speech: {chapter.speech_text[:80]}...")
        print(f"Prompt: {chapter.video_prompt[:80]}...")
        print("Generating video...")

        kwargs = {}
        if model:
            kwargs["model"] = model

        response = generate_video(chapter.video_prompt, **kwargs)

        # fal responses vary by model but typically have video.url or video
        video_url = None
        if isinstance(response, dict):
            video = response.get("video")
            if isinstance(video, dict):
                video_url = video.get("url")
            elif isinstance(video, str):
                video_url = video

        result = {
            "chapter": chapter,
            "response": response,
            "video_url": video_url,
            "local_path": None,
        }

        if video_url and download:
            filename = f"chapter_{chapter.number:02d}_{chapter.title.lower().replace(' ', '_')}.mp4"
            local_path = os.path.join(OUTPUT_DIR, filename)
            print(f"Downloading to {local_path}...")
            _download_video(video_url, local_path)
            result["local_path"] = local_path
            print(f"Saved: {local_path}")
        elif video_url:
            print(f"Video URL: {video_url}")
        else:
            print("Warning: no video URL found in response.")
            print(f"Full response: {json.dumps(response, indent=2, default=str)}")

        results.append(result)

    return results
