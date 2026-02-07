"""Pipeline: Storyboard JSON → fal.ai image per scene → fal.ai video → combined output."""

import asyncio
import json
import logging
import math
import os
import subprocess
import tempfile
import requests
import imageio_ffmpeg

from .scenes import Scene, Storyboard
from .fal_image import generate_image
from .fal_video import (
    DEFAULT_REF_I2V_MODEL,
    generate_video_from_image,
    generate_video_from_reference,
)


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Kling only supports these clip durations (image-to-video).
KLING_DURATIONS = [5, 10]

# Default max concurrent FAL API calls.  Keeps us under typical rate limits.
DEFAULT_FAL_CONCURRENCY = 3


def _download_file(url: str, dest: str) -> None:
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def _extract_video_url(response: dict) -> str | None:
    """Extract the video URL from a fal response."""
    video = response.get("video")
    if isinstance(video, dict):
        return video.get("url")
    if isinstance(video, str):
        return video
    return None


def _pick_kling_duration(target_seconds: float) -> str:
    """Pick the Kling generation duration closest to the target.

    Kling supports 5s or 10s clips. We prefer generating longer and
    speeding up slightly over generating shorter and slowing down,
    since speed-up generally looks better than slow-motion.
    """
    if target_seconds >= 7.5:
        return "10"
    return "5"


def _pick_reference_duration(target_seconds: float) -> int:
    """Round up to whole seconds for reference-to-video models."""
    rounded = int(math.ceil(target_seconds))
    return min(8, max(1, rounded))


def _adjust_clip_speed(input_path: str, output_path: str, target_seconds: float) -> None:
    """Re-time a video clip to exactly target_seconds using ffmpeg setpts filter."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # Probe the actual clip duration
    probe = subprocess.run(
        [ffmpeg, "-i", input_path],
        capture_output=True, text=True,
    )
    # ffmpeg prints info to stderr
    duration_actual = None
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            # Format: Duration: HH:MM:SS.ms
            parts = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = parts.split(":")
            duration_actual = int(h) * 3600 + int(m) * 60 + float(s)
            break

    if duration_actual is None or duration_actual == 0:
        # Can't determine duration, just copy as-is
        os.rename(input_path, output_path)
        return

    speed_factor = duration_actual / target_seconds

    # setpts adjusts video, atempo adjusts audio
    # atempo only accepts values between 0.5 and 100.0
    video_filter = f"setpts={1/speed_factor}*PTS"

    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-filter:v", video_filter,
    ]

    # Handle audio tempo if present (chain atempo filters for extreme values)
    if 0.5 <= speed_factor <= 100.0:
        cmd += ["-filter:a", f"atempo={speed_factor}"]
    else:
        cmd += ["-an"]  # drop audio if factor is out of range

    cmd += ["-preset", "fast", output_path]

    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _concatenate_videos(clip_paths: list[str], output_path: str) -> None:
    """Concatenate video clips into a single file using ffmpeg."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for path in clip_paths:
            f.write(f"file '{path}'\n")
        list_file = f.name

    try:
        subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        os.unlink(list_file)


# ---------------------------------------------------------------------------
# Async helpers – wrap blocking fal_client.subscribe calls with a semaphore
# ---------------------------------------------------------------------------

async def _generate_image_async(
    semaphore: asyncio.Semaphore,
    scene: Scene,
    face_swap_url: str | None,
    progress: dict,
    progress_lock: asyncio.Lock,
    total: int,
) -> tuple[Scene, str]:
    """Generate an image for a single scene, bounded by *semaphore*."""
    async with semaphore:
        async with progress_lock:
            progress["images_started"] += 1
            logging.info(
                "VideoGen: [img] started %d/%d",
                progress["images_started"],
                total,
            )
        if face_swap_url:
            logging.info(
                "VideoGen: Scene %s - [img] generating (PuLID Flux, face-conditioned)",
                scene.scene_id,
            )
        else:
            logging.info("VideoGen: Scene %s - [img] generating (Flux)", scene.scene_id)

        image_url = await asyncio.to_thread(
            generate_image,
            scene.scene_prompt,
            reference_face_url=face_swap_url,
        )
        async with progress_lock:
            progress["images_done"] += 1
            logging.info(
                "VideoGen: [img] done %d/%d",
                progress["images_done"],
                total,
            )
        logging.info(
            "VideoGen: Scene %s - [img] ready: %s...",
            scene.scene_id,
            image_url[:80],
        )
        return scene, image_url


async def _generate_video_async(
    semaphore: asyncio.Semaphore,
    scene: Scene,
    image_url: str,
    duration: int | str,
    video_model: str | None,
    reference_element: dict | None,
    progress: dict,
    progress_lock: asyncio.Lock,
    total: int,
) -> tuple[Scene, str, dict]:
    """Animate an image into a video for a single scene, bounded by *semaphore*."""
    async with semaphore:
        async with progress_lock:
            progress["videos_started"] += 1
            logging.info(
                "VideoGen: [vid] started %d/%d",
                progress["videos_started"],
                total,
            )
        logging.info(
            "VideoGen: Scene %s - [vid] animating (%ss clip)",
            scene.scene_id,
            duration,
        )

        if reference_element:
            reference_model = video_model or DEFAULT_REF_I2V_MODEL
            ref_prompt = (
                scene.scene_prompt
                if reference_model.startswith("fal-ai/vidu/")
                else (
                    f"{scene.scene_prompt}\n"
                    "Main character: @Element1. Use @Image1 as style reference."
                )
            )
            video_response = await asyncio.to_thread(
                generate_video_from_reference,
                elements=[reference_element],
                image_urls=[image_url],
                prompt=ref_prompt,
                model=reference_model,
                duration=duration,
            )
        else:
            i2v_kwargs: dict = {"duration": duration}
            if video_model:
                i2v_kwargs["model"] = video_model
            video_response = await asyncio.to_thread(
                generate_video_from_image,
                image_url,
                scene.scene_prompt,
                **i2v_kwargs,
            )
        async with progress_lock:
            progress["videos_done"] += 1
            logging.info(
                "VideoGen: [vid] done %d/%d",
                progress["videos_done"],
                total,
            )

        logging.info("VideoGen: Scene %s - [vid] ready", scene.scene_id)
        return scene, image_url, video_response


# ---------------------------------------------------------------------------
# Core async pipeline
# ---------------------------------------------------------------------------

async def _process_storyboard_parallel(
    storyboard: Storyboard,
    *,
    video_model: str | None,
    total_duration: float | None,
    per_scene_durations: dict[int, float] | None,
    output_filename: str,
    output_dir: str | None,
    return_clips: bool,
    face_swap_url: str | None,
    reference_element: dict | None,
    fal_concurrency: int,
) -> dict:
    output_root = output_dir or OUTPUT_DIR
    os.makedirs(output_root, exist_ok=True)
    num_scenes = len(storyboard.scenes)

    # Per-scene target duration
    if total_duration and num_scenes > 0:
        default_per_scene = total_duration / num_scenes
        logging.info(
            "VideoGen: target %.1fs total -> %.1fs per scene",
            total_duration,
            default_per_scene,
        )
    else:
        default_per_scene = None

    semaphore = asyncio.Semaphore(fal_concurrency)
    progress_lock = asyncio.Lock()
    progress = {
        "images_started": 0,
        "images_done": 0,
        "videos_started": 0,
        "videos_done": 0,
    }
    logging.info(
        "VideoGen: processing %d scenes (max %d parallel FAL calls)",
        num_scenes,
        fal_concurrency,
    )

    # ------------------------------------------------------------------
    # Phase 1 – generate all images in parallel
    # ------------------------------------------------------------------
    logging.info("VideoGen: Phase 1/2 – generating images for all scenes")
    image_tasks = [
        _generate_image_async(
            semaphore,
            scene,
            face_swap_url,
            progress,
            progress_lock,
            num_scenes,
        )
        for scene in storyboard.scenes
    ]
    image_results: list[tuple[Scene, str]] = await asyncio.gather(*image_tasks)

    # ------------------------------------------------------------------
    # Phase 2 – generate all videos in parallel
    # ------------------------------------------------------------------
    logging.info("VideoGen: Phase 2/2 – generating videos for all scenes")
    video_tasks = []
    for scene, image_url in image_results:
        target_duration = None
        if per_scene_durations:
            target_duration = per_scene_durations.get(scene.scene_id)
        if target_duration is None:
            target_duration = default_per_scene

        if reference_element:
            duration = (
                _pick_reference_duration(target_duration)
                if target_duration
                else 5
            )
        else:
            duration = (
                _pick_kling_duration(target_duration)
                if target_duration
                else "5"
            )
        video_tasks.append(
            _generate_video_async(
                semaphore,
                scene,
                image_url,
                duration,
                video_model,
                reference_element,
                progress,
                progress_lock,
                num_scenes,
            )
        )
    video_results: list[tuple[Scene, str, dict]] = await asyncio.gather(*video_tasks)

    # ------------------------------------------------------------------
    # Phase 3 – download, speed-adjust, concatenate (local / sequential)
    # ------------------------------------------------------------------
    scene_results: list[dict] = []
    temp_clips: list[str] = []

    try:
        for scene, image_url, video_response in video_results:
            video_url = _extract_video_url(video_response)

            scene_result: dict = {
                "scene": scene,
                "image_url": image_url,
                "video_url": video_url,
            }

            if video_url:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False, dir=output_root,
                )
                tmp.close()
                logging.info("VideoGen: Scene %s - downloading clip", scene.scene_id)
                _download_file(video_url, tmp.name)

                # Speed-adjust if duration target is set
                target_duration = None
                if per_scene_durations:
                    target_duration = per_scene_durations.get(scene.scene_id)
                if target_duration is None:
                    target_duration = default_per_scene

                final_clip = tmp.name
                if target_duration:
                    adjusted = tmp.name + ".adj.mp4"
                    logging.info(
                        "VideoGen: Scene %s - adjusting clip to %.1fs",
                        scene.scene_id,
                        target_duration,
                    )
                    _adjust_clip_speed(tmp.name, adjusted, target_duration)
                    os.unlink(tmp.name)
                    final_clip = adjusted

                if return_clips:
                    named = os.path.join(
                        output_root, f"scene_{scene.scene_id:03d}.mp4",
                    )
                    os.replace(final_clip, named)
                    final_clip = named

                temp_clips.append(final_clip)
                logging.info("VideoGen: Scene %s clip ready", scene.scene_id)
            else:
                logging.warning("VideoGen: Scene %s - no video URL in response.", scene.scene_id)
                logging.warning(
                    "VideoGen: response: %s",
                    json.dumps(video_response, indent=2, default=str),
                )

            scene_results.append(scene_result)

        # Concatenate all clips
        output_path = os.path.join(output_root, output_filename)

        if len(temp_clips) == 0:
            logging.warning("VideoGen: no scene clips were generated")
            return {"scenes": scene_results, "output_path": None}

        if return_clips:
            return {
                "scenes": scene_results,
                "output_path": None,
                "clip_paths": temp_clips,
            }

        if len(temp_clips) == 1:
            os.rename(temp_clips[0], output_path)
            temp_clips.clear()
        else:
            logging.info(
                "VideoGen: combining %s scene clips into one video",
                len(temp_clips),
            )
            _concatenate_videos(temp_clips, output_path)

        logging.info("VideoGen: final video saved: %s", output_path)
        return {"scenes": scene_results, "output_path": output_path}

    finally:
        if not return_clips:
            for path in temp_clips:
                if os.path.exists(path):
                    os.unlink(path)


# ---------------------------------------------------------------------------
# Public API  (unchanged signature + new fal_concurrency kwarg)
# ---------------------------------------------------------------------------

def process_storyboard(
    storyboard: Storyboard,
    *,
    video_model: str | None = None,
    total_duration: float | None = None,
    per_scene_durations: dict[int, float] | None = None,
    output_filename: str = "storyboard.mp4",
    output_dir: str | None = None,
    return_clips: bool = False,
    face_swap_url: str | None = None,
    reference_element: dict | None = None,
    fal_concurrency: int = DEFAULT_FAL_CONCURRENCY,
) -> dict:
    """Generate a video for each scene and combine into one final video.

    FAL API calls (image generation and video animation) run in parallel,
    bounded by *fal_concurrency* to stay within rate limits.

    Step 1: Generate storyboard frame images with fal.ai (parallel).
            Uses PuLID Flux (identity-conditioned) when a face reference is
            provided, otherwise plain Flux Dev.
    Step 2: Animate images into video clips with fal.ai / Kling (parallel).
            If a reference element is provided, use Kling O1 reference-to-video
            to preserve identity.
    Step 3: Download and adjust each clip to the target per-scene duration.
    Step 4: Concatenate all clips into one video with ffmpeg.

    Args:
        total_duration: Total video length in seconds. Divided equally across
                        scenes. Each clip is speed-adjusted to match. If None,
                        clips use their native Kling duration (5s each).
        face_swap_url: URL of a reference face image. When provided, PuLID Flux
                       conditions generation on this face so the main character
                       inherits the person's identity.
        reference_element: Reference element dict for Kling O1. When provided,
                          this is used for identity conditioning during video
                          generation.
        fal_concurrency: Maximum number of concurrent FAL API calls.

    Returns a result dict containing:
        - scenes: list of per-scene results (scene, image_url, video_url)
        - output_path: path to the combined video file
    """
    return asyncio.run(
        _process_storyboard_parallel(
            storyboard,
            video_model=video_model,
            total_duration=total_duration,
            per_scene_durations=per_scene_durations,
            output_filename=output_filename,
            output_dir=output_dir,
            return_clips=return_clips,
            face_swap_url=face_swap_url,
            reference_element=reference_element,
            fal_concurrency=fal_concurrency,
        )
    )
