"""Pipeline: Storyboard JSON → fal.ai image per scene → fal.ai video → combined output."""

import json
import os
import subprocess
import tempfile
import requests
import imageio_ffmpeg

from .scenes import Storyboard
from .fal_image import generate_image
from .fal_video import generate_video_from_image


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
) -> dict:
    """Generate a video for each scene and combine into one final video.

    Step 1: Generate a storyboard frame image with fal.ai (Flux).
    Step 2: Animate that image into a video clip with fal.ai (Kling).
    Step 3: Adjust each clip to the target per-scene duration (if total_duration set).
    Step 4: Concatenate all clips into one video with ffmpeg.

    Args:
        total_duration: Total video length in seconds. Divided equally across
                        scenes. Each clip is speed-adjusted to match. If None,
                        clips use their native Kling duration (5s each).

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
        print(f"Target: {total_duration}s total → {per_scene_duration:.1f}s per scene")
    else:
        per_scene_duration = None

    try:
        for scene in storyboard.scenes:
            print(f"\n{'='*60}")
            print(f"Scene {scene.scene_id}: {scene.title}")
            print(f"{'='*60}")
            print(f"Main point: {scene.main_point}")
            print(f"Prompt: {scene.scene_prompt[:80]}...")

            # --- Step 1: Generate image with fal.ai ---
            print("[1/2] Generating image with fal.ai (Flux)...")
            image_url = generate_image(scene.scene_prompt)
            print(f"  Image ready: {image_url[:80]}...")

            # --- Step 2: Animate with fal.ai image-to-video ---
            target_duration = None
            if per_scene_durations:
                target_duration = per_scene_durations.get(scene.scene_id)
            if target_duration is None:
                target_duration = per_scene_duration

            kling_dur = _pick_kling_duration(target_duration) if target_duration else "5"
            print(f"[2/2] Animating image with fal.ai (Kling, {kling_dur}s clip)...")

            i2v_kwargs = {"duration": kling_dur}
            if video_model:
                i2v_kwargs["model"] = video_model

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
                print(f"  Downloading clip...")
                _download_file(video_url, tmp.name)

                # --- Step 3: Speed-adjust if duration target is set ---
                final_clip = tmp.name
                if target_duration:
                    adjusted = tmp.name + ".adj.mp4"
                    print(f"  Adjusting clip to {target_duration:.1f}s...")
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

                print(f"  Scene {scene.scene_id} clip ready.")
            else:
                print("Warning: no video URL found in response.")
                print(f"Full response: {json.dumps(video_response, indent=2, default=str)}")

            scene_results.append(scene_result)

        # --- Step 4: Concatenate all clips ---
        output_path = os.path.join(output_root, output_filename)

        if len(temp_clips) == 0:
            print("\nNo scene clips were generated. Cannot create combined video.")
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
            print(f"\n{'='*60}")
            print(f"Combining {len(temp_clips)} scene clips into one video...")
            print(f"{'='*60}")
            _concatenate_videos(temp_clips, output_path)

        print(f"Final video saved: {output_path}")
        return {"scenes": scene_results, "output_path": output_path}

    finally:
        if not return_clips:
            for path in temp_clips:
                if os.path.exists(path):
                    os.unlink(path)
