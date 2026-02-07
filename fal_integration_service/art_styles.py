"""Predefined art-style registry for consistent image generation.

Each style defines two prompt fragments:
  - **prompt_prefix**: injected by the text-extraction LLM when writing
    scene prompts.  It is short and generic so the LLM can reason about
    composition without being overwhelmed by style detail.
  - **image_prefix**: the detailed directive that *replaces* the
    prompt_prefix right before the prompt is sent to the image-generation
    model.  This is where we enforce strict visual consistency.

The default / fallback style is ``miyazaki``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtStyle:
    """A single predefined art style."""

    key: str
    name: str
    prompt_prefix: str
    image_prefix: str
    protagonist_hint: str


# -- Style definitions --------------------------------------------------------

_STYLES: dict[str, ArtStyle] = {}


def _register(style: ArtStyle) -> ArtStyle:
    _STYLES[style.key] = style
    return style


DEFAULT_STYLE = "miyazaki"

# 1. Miyazaki / Studio Ghibli  (DEFAULT)
_register(ArtStyle(
    key="miyazaki",
    name="Miyazaki / Studio Ghibli",
    prompt_prefix=(
        "Studio Ghibli anime style, soft pastel colors, "
        "hand-painted backgrounds, gentle lighting."
    ),
    image_prefix=(
        "Studio Ghibli anime style by Hayao Miyazaki. Soft pastel color "
        "palette, hand-painted watercolor backgrounds, gentle diffused "
        "lighting, rounded character features with expressive eyes, lush "
        "natural details, whimsical atmosphere. Consistent cel-shaded "
        "rendering throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently in the scene with a clear, "
        "recognisable face in Ghibli style. "
    ),
))

# 2. Superhero / Comic Book
_register(ArtStyle(
    key="superhero",
    name="Superhero Comic Book",
    prompt_prefix=(
        "Bold comic book superhero style, dynamic poses, "
        "vivid colors, ink outlines."
    ),
    image_prefix=(
        "American comic book superhero style. Bold saturated primary "
        "colors, thick black ink outlines, dynamic action poses, dramatic "
        "foreshortening, halftone dot shading, muscular heroic proportions. "
        "Consistent with classic superhero comic art throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently in a heroic pose with a "
        "clear, recognisable face rendered in bold ink outlines. "
    ),
))

# 3. Watercolor
_register(ArtStyle(
    key="watercolor",
    name="Watercolor Painting",
    prompt_prefix=(
        "Delicate watercolor painting style, soft washes, "
        "visible brush strokes, muted tones."
    ),
    image_prefix=(
        "Traditional watercolor painting style. Soft transparent washes "
        "of color bleeding into wet paper, visible brushstrokes, muted and "
        "harmonious tones, white paper showing through, gentle gradients, "
        "slightly imperfect edges, organic flowing forms. Consistent fine "
        "art watercolor technique throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently in the scene with a clear, "
        "recognisable face rendered in soft watercolor washes. "
    ),
))

# 4. Pixel Art
_register(ArtStyle(
    key="pixel_art",
    name="Retro Pixel Art",
    prompt_prefix=(
        "Retro 16-bit pixel art style, limited color palette, "
        "crisp pixels, nostalgic."
    ),
    image_prefix=(
        "Retro 16-bit pixel art style. Crisp visible square pixels, "
        "limited 32-color palette, dithering for shading, no anti-aliasing, "
        "bright saturated colors, clear silhouettes, NES/SNES era aesthetic. "
        "Consistent pixel density and palette throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "pixel-art face using distinct colors. "
    ),
))

# 5. Film Noir
_register(ArtStyle(
    key="noir",
    name="Film Noir",
    prompt_prefix=(
        "Film noir style, high contrast black and white, "
        "dramatic shadows, moody atmosphere."
    ),
    image_prefix=(
        "Classic film noir style. High contrast black and white imagery, "
        "deep dramatic shadows, venetian blind light patterns, fog and "
        "rain, moody 1940s urban atmosphere, sharp angular compositions, "
        "cigarette smoke wisps. Consistent monochrome noir rendering "
        "throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "face lit by dramatic chiaroscuro noir lighting. "
    ),
))

# 6. Cyberpunk
_register(ArtStyle(
    key="cyberpunk",
    name="Cyberpunk Neon",
    prompt_prefix=(
        "Cyberpunk neon style, dark urban setting, "
        "glowing neon lights, futuristic tech."
    ),
    image_prefix=(
        "Cyberpunk neon-noir style. Dark rain-slicked urban streets, vivid "
        "neon pink and cyan lighting, holographic advertisements, chrome and "
        "glass architecture, dense vertical cityscape, atmospheric fog "
        "diffusing neon glow. Consistent cyberpunk aesthetic throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "face illuminated by vivid neon lighting. "
    ),
))

# 7. Classic Disney
_register(ArtStyle(
    key="disney_classic",
    name="Classic Disney Animation",
    prompt_prefix=(
        "Classic Disney animation style, clean lines, "
        "warm colors, expressive characters."
    ),
    image_prefix=(
        "Classic Disney feature animation style. Clean flowing ink outlines, "
        "warm rich color palette, expressive character animation with large "
        "eyes, painterly backgrounds with depth, soft rim lighting, "
        "fairy-tale atmosphere, appealing character design. Consistent "
        "Disney cel animation look throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "face in expressive Disney-style rendering. "
    ),
))

# 8. Manga
_register(ArtStyle(
    key="manga",
    name="Black & White Manga",
    prompt_prefix=(
        "Black and white manga style, screentone shading, "
        "dramatic expressions, clean linework."
    ),
    image_prefix=(
        "Japanese manga illustration style. Black and white ink art, "
        "screentone dot patterns for shading, speed lines for motion, "
        "dramatic facial expressions with large detailed eyes, dynamic "
        "panel-like composition, hatching for texture, clean precise "
        "linework. Consistent shonen manga aesthetic throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "face rendered in detailed manga linework. "
    ),
))

# 9. Oil Painting
_register(ArtStyle(
    key="oil_painting",
    name="Classical Oil Painting",
    prompt_prefix=(
        "Classical oil painting style, rich textures, "
        "warm golden light, Renaissance composition."
    ),
    image_prefix=(
        "Classical oil painting style reminiscent of the Old Masters. Rich "
        "impasto texture with visible palette knife marks, warm golden "
        "chiaroscuro lighting, deep saturated earth tones and jewel colors, "
        "Renaissance compositional balance, sfumato blending. Consistent "
        "fine art oil painting technique throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "face painted in warm chiaroscuro oil-painting light. "
    ),
))

# 10. Epic Fantasy
_register(ArtStyle(
    key="fantasy",
    name="Epic Fantasy Illustration",
    prompt_prefix=(
        "Epic fantasy illustration style, detailed environments, "
        "magical lighting, grand scale."
    ),
    image_prefix=(
        "Epic high fantasy illustration style. Richly detailed environments "
        "with sweeping vistas, magical luminous effects, dramatic scale "
        "with towering structures, ornate armor and robes, mythical "
        "creatures, volumetric god-ray lighting, painterly digital art "
        "technique. Consistent fantasy book-cover illustration style "
        "throughout."
    ),
    protagonist_hint=(
        " The protagonist is shown prominently with a clear, recognisable "
        "face bathed in magical fantasy lighting. "
    ),
))


# -- Public helpers -----------------------------------------------------------

def get_style(key: str | None) -> ArtStyle:
    """Return the :class:`ArtStyle` for *key*, falling back to the default."""
    if key is None:
        key = DEFAULT_STYLE
    style = _STYLES.get(key)
    if style is None:
        raise ValueError(
            f"Unknown art style {key!r}. "
            f"Available styles: {', '.join(sorted(_STYLES))}"
        )
    return style


def available_styles() -> list[str]:
    """Return a sorted list of registered style keys."""
    return sorted(_STYLES)


def style_choices_help() -> str:
    """Return a human-readable help string listing all styles."""
    lines = []
    for key in sorted(_STYLES):
        s = _STYLES[key]
        default = " (default)" if key == DEFAULT_STYLE else ""
        lines.append(f"  {key:18s} {s.name}{default}")
    return "\n".join(lines)
