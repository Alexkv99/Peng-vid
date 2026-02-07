"""Thin wrapper around the fal-client SDK for face swapping."""

import os
import fal_client


DEFAULT_FACE_SWAP_MODEL = "fal-ai/face-swap"


def _ensure_api_key() -> None:
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )


def upload_local_image(path: str) -> str:
    """Upload a local image file to fal storage and return its URL."""
    _ensure_api_key()
    url = fal_client.upload_file(path)
    return url


def face_swap(
    base_image_url: str,
    swap_image_url: str,
    *,
    model: str = DEFAULT_FACE_SWAP_MODEL,
) -> str:
    """Swap the face in base_image with the face from swap_image.

    Args:
        base_image_url: URL of the generated scene image (target).
        swap_image_url: URL of the reference face image (source face).
        model: fal.ai model endpoint for face swap.

    Returns the URL of the face-swapped image.
    """
    _ensure_api_key()

    result = fal_client.subscribe(
        model,
        arguments={
            "base_image_url": base_image_url,
            "swap_image_url": swap_image_url,
        },
        with_logs=True,
    )

    # Response format: {"image": {"url": "..."}} or {"image": "url"}
    image = result.get("image")
    if isinstance(image, dict):
        return image["url"]
    if isinstance(image, str):
        return image

    raise RuntimeError(f"Could not extract image URL from face-swap response: {result}")
