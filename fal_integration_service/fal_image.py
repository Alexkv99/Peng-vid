"""Thin wrapper around the fal-client SDK for text-to-image generation."""

import os
import fal_client

# Default image model — Flux Dev produces high-quality stylized images.
# Alternatives:
#   "fal-ai/flux/schnell"    — Faster, lower cost
#   "fal-ai/fast-sdxl"       — SDXL-based, general purpose
DEFAULT_IMAGE_MODEL = "fal-ai/flux/dev"

# PuLID Flux — identity-conditioned generation.
# Embeds a reference face directly into the diffusion process so the
# generated character already looks like the target person.
PULID_IMAGE_MODEL = "fal-ai/flux-pulid"

# Style prefix injected by text_extraction_service — we intercept and
# replace it here so the extraction layer stays untouched.
_OLD_STYLE_PREFIX = "Sketched storyboard style, pencil lines, minimal shading."

_NEW_STYLE_PREFIX = (
    "Studio Ghibli anime style, Hayao Miyazaki inspired, "
    "soft watercolor tones, expressive detailed faces, "
    "warm cinematic palette, clear facial features."
)

# Extra prompt fragment added when a face reference is active so the
# diffusion model foregrounds the protagonist's face.
_PROTAGONIST_HINT = (
    " The protagonist is shown prominently in the scene with a clear, "
    "detailed, front-facing visible face as the central focus of the image."
)


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


def _restyle_prompt(prompt: str, *, face_mode: bool) -> str:
    """Replace the old sketch style with Miyazaki anime style.

    When *face_mode* is True an extra hint is appended so the model
    keeps the protagonist's face prominent and recognisable.
    """
    restyled = prompt.replace(_OLD_STYLE_PREFIX, _NEW_STYLE_PREFIX, 1)
    if face_mode:
        restyled = restyled.rstrip() + _PROTAGONIST_HINT
    return restyled


def generate_image(
    prompt: str,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    image_size: str = "landscape_16_9",
    reference_face_url: str | None = None,
) -> str:
    """Generate an image and return the image URL.

    When *reference_face_url* is provided the function switches to the
    PuLID Flux model so the generated character inherits the identity of
    the reference face.  Without it, plain Flux Dev is used as before.

    The prompt style is always upgraded from the legacy sketch preset to
    a Miyazaki anime style for better face visibility.

    Returns the direct URL string to the generated image.
    """
    _ensure_api_key()

    styled_prompt = _restyle_prompt(prompt, face_mode=bool(reference_face_url))

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
