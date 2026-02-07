"""Scene dataclass and JSON parser for storyboard input."""

import json
from dataclasses import dataclass, field


@dataclass
class Scene:
    """A single scene from a storyboard."""
    scene_id: int
    title: str
    main_point: str
    scene_summary: str
    key_elements: list[str]
    scene_prompt: str


@dataclass
class Storyboard:
    """A full storyboard with a style preset and list of scenes."""
    style_preset: str
    scenes: list[Scene]


def parse_storyboard(data: dict | str) -> Storyboard:
    """Parse a storyboard from a dict or JSON string.

    Accepts either a raw dict or a JSON-encoded string.
    """
    if isinstance(data, str):
        data = json.loads(data)

    style_preset = data.get("style_preset", "")
    scenes = [
        Scene(
            scene_id=s["scene_id"],
            title=s["title"],
            main_point=s["main_point"],
            scene_summary=s["scene_summary"],
            key_elements=s.get("key_elements", []),
            scene_prompt=s["scene_prompt"],
        )
        for s in data["scenes"]
    ]
    return Storyboard(style_preset=style_preset, scenes=scenes)


def load_storyboard(path: str) -> Storyboard:
    """Load a storyboard from a JSON file on disk."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_storyboard(data)
