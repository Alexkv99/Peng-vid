"""Thin wrapper around the fal-client SDK for text-to-image generation."""

from __future__ import annotations

import os
import fal_client

from .art_styles import ArtStyle, get_style

# Default image model — Flux Dev produces high-quality stylized images.
# Alternatives:
#   "fal-ai/flux/schnell"    — Faster, lower cost
#   "fal-ai/fast-sdxl"       — SDXL-based, general purpose
DEFAULT_IMAGE_MODEL = "fal-ai/flux/dev"

# PuLID Flux — identity-conditioned generation.
# Embeds a reference face directly into the diffusion process so the
# generated character already looks like the target person.
PULID_IMAGE_MODEL = "fal-ai/flux-pulid"


def _ensure_api_key() -> None:
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )

def _extract_image_url(result: dict) -> str:
    """Extract the image URL from a fal image-generation response."""
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


def _restyle_prompt(prompt: str, *, face_mode: bool, style: ArtStyle) -> str:
    """Replace the short style prefix with the full image directive.

    The scene prompt begins with the style's ``prompt_prefix`` (a short
    phrase the LLM was told to use).  This function swaps it out for the
    much more detailed ``image_prefix`` so the image model receives
    strict, consistent styling instructions.

    When *face_mode* is True the style's protagonist hint is appended so
    the model foregrounds the character's face.
    """
    restyled = prompt.replace(style.prompt_prefix, style.image_prefix, 1)
    if face_mode:
        restyled = restyled.rstrip() + style.protagonist_hint
    return restyled


def generate_image(
    prompt: str,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    image_size: str = "landscape_16_9",
    reference_face_url: str | None = None,
    style_key: str | None = None,
) -> str:
    """Generate an image and return the image URL.

    When *reference_face_url* is provided the function switches to the
    PuLID Flux model so the generated character inherits the identity of
    the reference face.  Without it, plain Flux Dev is used as before.

    The prompt's short style prefix is replaced with the full image
    directive for the chosen art style (defaults to ``miyazaki``).

    Returns the direct URL string to the generated image.
    """
    _ensure_api_key()

    style = get_style(style_key)
    styled_prompt = _restyle_prompt(
        prompt, face_mode=bool(reference_face_url), style=style,
    )

    if reference_face_url:
        active_model = PULID_IMAGE_MODEL
        arguments = {
            "prompt": styled_prompt,
            "reference_image_url": reference_face_url,
            "image_size": image_size,
            "id_weight": 1,
        }
    else:
        active_model = model
        arguments = {
            "prompt": styled_prompt,
            "image_size": image_size,
        }

    result = fal_client.subscribe(
        active_model,
        arguments=arguments,
        with_logs=True,
    )

    return _extract_image_url(result)
