"""Thin wrapper around the fal-client SDK for video generation."""

import os
import fal_client

# Default text-to-video model.
# Alternatives:
#   "fal-ai/wan-t2v"                              — Wan 2.1 (budget-friendly)
#   "fal-ai/hunyuan-video"                        — Hunyuan by Tencent
#   "fal-ai/minimax/hailuo-02/pro/text-to-video"  — Hailuo 02 Pro (1080p)
DEFAULT_MODEL = "fal-ai/minimax/video-01"

# Default image-to-video model.
# Alternatives:
#   "fal-ai/kling-video/v2.1/pro/image-to-video"    — Pro quality
#   "fal-ai/kling-video/v2/master/image-to-video"    — Master quality
DEFAULT_I2V_MODEL = "fal-ai/kling-video/v2.1/standard/image-to-video"


def _ensure_api_key() -> None:
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )


def generate_video(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Submit a text-to-video request and wait for the result.

    Returns the raw response dict from fal (contains video URL, metadata, etc.).
    """
    _ensure_api_key()

    result = fal_client.subscribe(
        model,
        arguments={"prompt": prompt},
        with_logs=True,
    )
    return result


def generate_video_from_image(
    image_url: str,
    prompt: str,
    *,
    model: str = DEFAULT_I2V_MODEL,
    duration: str = "5",
    aspect_ratio: str = "16:9",
) -> dict:
    """Submit an image-to-video request and wait for the result.

    Takes a source image URL and a prompt describing the desired motion/animation.
    Returns the raw response dict from fal (contains video URL, metadata, etc.).
    """
    _ensure_api_key()

    result = fal_client.subscribe(
        model,
        arguments={
            "image_url": image_url,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        },
        with_logs=True,
    )
    return result
