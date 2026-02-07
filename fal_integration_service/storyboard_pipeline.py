"""Pipeline: Storyboard JSON → fal.ai image per scene → fal.ai video → combined output."""

import json
import logging
import os
import subprocess
import tempfile
import requests
import imageio_ffmpeg

from .scenes import Storyboard
from .fal_image import generate_image
from .fal_video import generate_video_from_image, generate_video_from_reference


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Kling only supports these clip durations.
KLING_DURATIONS = [5, 10]


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
) -> dict:
    """Generate a video for each scene and combine into one final video.

    Step 1: Generate a storyboard frame image with fal.ai.
            Uses PuLID Flux (identity-conditioned) when a face reference is
            provided, otherwise plain Flux Dev.
    Step 2: Animate that image into a video clip with fal.ai (Kling).
            If a reference element is provided, use Kling O1 reference-to-video
            to preserve identity.
    Step 3: Adjust each clip to the target per-scene duration (if total_duration set).
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

    Returns a result dict containing:
        - scenes: list of per-scene results (scene, image_url, video_url)
        - output_path: path to the combined video file
    """
    output_root = output_dir or OUTPUT_DIR
    os.makedirs(output_root, exist_ok=True)
    scene_results: list[dict] = []
    temp_clips: list[str] = []
    num_scenes = len(storyboard.scenes)

    # Calculate per-scene target duration
    if total_duration and num_scenes > 0:
        per_scene_duration = total_duration / num_scenes
        logging.info(
            "VideoGen: target %.1fs total -> %.1fs per scene",
            total_duration,
            per_scene_duration,
        )
    else:
        per_scene_duration = None

    try:
        for scene in storyboard.scenes:
            logging.info("VideoGen: Scene %s - %s", scene.scene_id, scene.title)
            logging.info("VideoGen: Main point: %s", scene.main_point)
            logging.info("VideoGen: Prompt: %s...", scene.scene_prompt[:80])

            # --- Step 1: Generate image with fal.ai ---
            if face_swap_url:
                logging.info(
                    "VideoGen: [1/2] Generating image with fal.ai (PuLID Flux, face-conditioned)"
                )
            else:
                logging.info("VideoGen: [1/2] Generating image with fal.ai (Flux)")
            image_url = generate_image(
                scene.scene_prompt, reference_face_url=face_swap_url
            )
            logging.info("VideoGen: Image ready: %s...", image_url[:80])

            # --- Step 2: Animate with fal.ai image-to-video ---
            target_duration = None
            if per_scene_durations:
                target_duration = per_scene_durations.get(scene.scene_id)
            if target_duration is None:
                target_duration = per_scene_duration

            kling_dur = _pick_kling_duration(target_duration) if target_duration else "5"
            logging.info(
                "VideoGen: [2/2] Animating image with fal.ai (Kling, %ss clip)",
                kling_dur,
            )

            i2v_kwargs = {"duration": kling_dur}
            if video_model:
                i2v_kwargs["model"] = video_model

            if reference_element:
                logging.info(
                    "VideoGen: [2/2] Animating with Kling O1 reference-to-video"
                )
                ref_prompt = (
                    f"{scene.scene_prompt}\n"
                    "Main character: @Element1. Use @Image1 as style reference."
                )
                video_response = generate_video_from_reference(
                    elements=[reference_element],
                    image_urls=[image_url],
                    prompt=ref_prompt,
                    **i2v_kwargs,
                )
            else:
                video_response = generate_video_from_image(
                    image_url,
                    scene.scene_prompt,
                    **i2v_kwargs,
                )

            video_url = _extract_video_url(video_response)

            scene_result = {
                "scene": scene,
                "image_url": image_url,
                "video_url": video_url,
            }

            if video_url:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False, dir=output_root
                )
                tmp.close()
                logging.info("VideoGen: Downloading clip")
                _download_file(video_url, tmp.name)

                # --- Step 3: Speed-adjust if duration target is set ---
                final_clip = tmp.name
                if target_duration:
                    adjusted = tmp.name + ".adj.mp4"
                    logging.info(
                        "VideoGen: Adjusting clip to %.1fs",
                        target_duration,
                    )
                    _adjust_clip_speed(tmp.name, adjusted, target_duration)
                    os.unlink(tmp.name)
                    final_clip = adjusted

                if return_clips:
                    named = os.path.join(
                        output_root, f"scene_{scene.scene_id:03d}.mp4"
                    )
                    os.replace(final_clip, named)
                    final_clip = named

                temp_clips.append(final_clip)

                logging.info("VideoGen: Scene %s clip ready", scene.scene_id)
            else:
                logging.warning("VideoGen: no video URL found in response.")
                logging.warning(
                    "VideoGen: response: %s",
                    json.dumps(video_response, indent=2, default=str),
                )

            scene_results.append(scene_result)

        # --- Step 4: Concatenate all clips ---
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
