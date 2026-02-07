"""Thin wrapper around the fal-client SDK for text-to-image generation."""

import os
import fal_client

# Default image model — Flux Dev produces high-quality stylized images.
# Alternatives:
#   "fal-ai/flux/schnell"    — Faster, lower cost
#   "fal-ai/fast-sdxl"       — SDXL-based, general purpose
DEFAULT_IMAGE_MODEL = "fal-ai/flux/dev"


def _ensure_api_key() -> None:
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )


def generate_image(
    prompt: str,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    image_size: str = "landscape_16_9",
) -> str:
    """Generate an image and return the image URL.

    Returns the direct URL string to the generated image.
    """
    _ensure_api_key()

    result = fal_client.subscribe(
        model,
        arguments={
            "prompt": prompt,
            "image_size": image_size,
        },
        with_logs=True,
    )

    # Fal image responses: {"images": [{"url": "..."}]} or {"image": {"url": "..."}}
    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first["url"]
        return first

    image = result.get("image")
    if isinstance(image, dict):
        return image["url"]
    if isinstance(image, str):
        return image

    raise RuntimeError(f"Could not extract image URL from fal response: {result}")
