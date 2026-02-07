import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

STYLE_PREFIX = "Sketched style, pencil lines, minimal shading."
SCENE_PROMPT_MAX_TOKENS = 40

EXTRACT_SCENES_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "main_point": {"type": "string"},
                    "scene_summary": {"type": "string"},
                    "key_elements": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "scene_id",
                    "title",
                    "main_point",
                    "scene_summary",
                    "key_elements",
                ],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scenes", "warnings"],
    "additionalProperties": False,
}

SCENE_PROMPT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "scene_id": {"type": "integer"},
        "scene_prompt": {"type": "string"},
    },
    "required": ["scene_id", "scene_prompt"],
    "additionalProperties": False,
}

BANNED_TERMS_PATTERN = re.compile(
    r"\b(camera|lens|lighting|day|night|fps|aspect ratio|depth of field|dof)\b",
    re.IGNORECASE,
)


def load_env() -> None:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Add it to .env or your environment."
        )


def call_structured_output(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: Dict[str, Any],
    temperature: float = 0.2,
    verbose: bool = False,
) -> Dict[str, Any]:
    logging.info("LLM call start: %s", schema_name)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "description": f"{schema_name} schema",
                "strict": True,
            }
        },
    )
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        output_text = output_text.strip()
    else:
        chunks: List[str] = []
        for item in response.output:
            if getattr(item, "type", None) == "message":
                for content in item.content:
                    if getattr(content, "type", None) == "output_text":
                        chunks.append(content.text)
        output_text = "".join(chunks).strip()
    if not output_text:
        raise RuntimeError("No output_text returned from the model.")
    if verbose:
        print(f"\n=== LLM RESPONSE ({schema_name}) ===\n{output_text}\n")
    logging.info("LLM call complete: %s", schema_name)
    return json.loads(output_text)


def extract_scenes(
    client: OpenAI, model: str, source_text: str, number_of_scenes: int, verbose: bool
) -> Dict[str, Any]:
    system_prompt = (
        "You are a script editor extracting filmable scene beats and concise "
        "voiceover narration for a short video. You think in terms of a "
        "complete narrative arc: every story has a beginning that sets the "
        "stage, a middle that develops the core events, and an ending that "
        "resolves or concludes the story."
    )
    user_prompt = (
        "Text:\n"
        f"{source_text}\n\n"
        "Rules:\n"
        "1) Return a list of scenes in chronological order.\n"
        "2) Each scene should represent a single beat that could fit ~5 seconds.\n"
        "3) Stay faithful to the text; do not invent new events or entities.\n"
        "4) Keep scenes distinct; merge duplicates.\n"
        "5) Write scene_summary as concise explanatory narration in past tense.\n"
        "   Use active voice and a spoken cadence.\n"
        "   Describe the idea/event directly; avoid meta phrasing like\n"
        "   'I describe/I explain/I outline' or 'this scene shows', and avoid\n"
        "   passive framing like 'was framed/was described/was positioned'.\n"
        "   Use first-person only when the source text is explicitly first-person;\n"
        "   otherwise use neutral narration.\n"
        "6) Make the first scene feel introductory and the last scene feel like a closing.\n"
        "7) Keep scene_summary short enough to narrate in under 6 seconds.\n"
        "   Target 12-16 words, max 18 words.\n"
        f"8) Aim for exactly {number_of_scenes} scenes when possible. "
        "If the text is too short, return fewer and add a warning.\n"
        "9) Output MUST match the JSON schema."
    )
    return call_structured_output(
        client=client,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name="ExtractScenes",
        schema=EXTRACT_SCENES_SCHEMA,
        verbose=verbose,
    )


def generate_scene_prompt(
    client: OpenAI,
    model: str,
    scene: Dict[str, Any],
    verbose: bool,
    all_scenes: List[Dict[str, Any]] | None = None,
    *,
    style: ArtStyle | None = None,
) -> Dict[str, Any]:
    total = len(all_scenes) if all_scenes else 0
    scene_id = scene.get("scene_id", 0)

    if total > 0:
        if scene_id == 1:
            position_hint = (
                "This is the OPENING scene (scene 1 of {total}). "
                "It should establish the setting and introduce the subject."
            ).format(total=total)
        elif scene_id == total:
            position_hint = (
                "This is the FINAL scene (scene {sid} of {total}). "
                "It should convey resolution or a concluding moment."
            ).format(sid=scene_id, total=total)
        else:
            position_hint = (
                "This is scene {sid} of {total} (middle of the story). "
                "It should continue naturally from the previous scene."
            ).format(sid=scene_id, total=total)
    else:
        position_hint = ""

    # Build a brief outline of surrounding scenes for continuity.
    context_lines: List[str] = []
    if all_scenes and total > 1:
        for s in all_scenes:
            sid = s.get("scene_id", 0)
            marker = " <-- current" if sid == scene_id else ""
            context_lines.append(
                f"  Scene {sid}: {s.get('title', '')}{marker}"
            )
        context_block = (
            "Story outline (all scenes in order):\n"
            + "\n".join(context_lines)
            + "\n\n"
        )
    else:
        context_block = ""

    if style is None:
        style = get_style(DEFAULT_STYLE)
    style_prefix = style.prompt_prefix

    system_prompt = (
        "You will generate ONE short image-generation prompt for the given "
        "scene. The scene is part of a single continuous story — keep visual "
        "continuity with the scenes before and after it."
    )
    user_prompt = (
        f"{context_block}"
        f"{position_hint}\n\n"
        "Scene JSON:\n"
        f"{json.dumps(scene, ensure_ascii=True)}\n\n"
        "Rules:\n"
        f'1) Start with the exact style prefix: "{style_prefix}"\n'
        "2) 2-4 lines max. Keep it concise.\n"
        "3) Describe only: who is present, what happens (single beat), "
        "where it happens, implied emotion (only if explicit).\n"
        "4) Maintain visual continuity: characters and settings that appeared "
        "in earlier scenes should be depicted consistently.\n"
        "5) Do NOT add camera/lens/lighting/day-night/fps/aspect-ratio instructions.\n"
        "6) Do NOT invent new plot points beyond the provided scene fields.\n"
        "7) Output MUST match the JSON schema."
    )
    return call_structured_output(
        client=client,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name="GeneratePrompt",
        schema=SCENE_PROMPT_SCHEMA,
        verbose=verbose,
    )


def normalize_scene_ids(
    scenes: List[Dict[str, Any]], warnings: List[str]
) -> List[Dict[str, Any]]:
    expected_ids = list(range(1, len(scenes) + 1))
    actual_ids = [scene.get("scene_id") for scene in scenes]
    if actual_ids != expected_ids:
        warnings.append(
            "Scene IDs were not sequential starting at 1. Reassigning sequential IDs."
        )
        for idx, scene in enumerate(scenes, start=1):
            scene["scene_id"] = idx
    return scenes


def normalize_prompt(
    scene_id: int, prompt: str, warnings: List[str], *, style: ArtStyle | None = None,
) -> str:
    if style is None:
        style = get_style(DEFAULT_STYLE)
    prefix = style.prompt_prefix

    cleaned = prompt.strip()
    if not cleaned.startswith(prefix):
        warnings.append(
            f"scene_id {scene_id}: prompt did not start with the style prefix; "
            "prefix was added."
        )
        cleaned = f"{prefix} {cleaned.lstrip()}"

    if BANNED_TERMS_PATTERN.search(cleaned):
        warnings.append(
            f"scene_id {scene_id}: prompt may contain banned camera/lighting terms."
        )

    tokens = cleaned.split()
    if len(tokens) > SCENE_PROMPT_MAX_TOKENS:
        cleaned = " ".join(tokens[:SCENE_PROMPT_MAX_TOKENS])
        warnings.append(
            f"scene_id {scene_id}: prompt trimmed to {SCENE_PROMPT_MAX_TOKENS} tokens."
        )

    return cleaned


def merge_scene_prompts(
    scenes: List[Dict[str, Any]],
    prompts: List[Dict[str, Any]],
    warnings: List[str],
    *,
    style: ArtStyle | None = None,
) -> Dict[str, Any]:
    if style is None:
        style = get_style(DEFAULT_STYLE)

    prompt_by_id = {item["scene_id"]: item["scene_prompt"] for item in prompts}
    merged_scenes: List[Dict[str, Any]] = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        prompt = prompt_by_id.get(scene_id)
        if not prompt:
            warnings.append(f"Missing prompt for scene_id {scene_id}.")
            prompt = style.prompt_prefix
        prompt = normalize_prompt(scene_id, prompt, warnings, style=style)
        merged_scene = dict(scene)
        merged_scene["scene_prompt"] = prompt
        merged_scenes.append(merged_scene)

    project_id = datetime.now(timezone.utc).strftime("proj_%Y%m%d_%H%M%S")
    return {
        "project_id": project_id,
        "style_preset": style.key,
        "scenes": merged_scenes,
        "warnings": warnings,
    }


def read_source_text(args: argparse.Namespace) -> str:
    if args.input and args.input_file:
        raise SystemExit("Provide only one of --input or --input-file.")

    if args.input:
        return args.input.strip()

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    raise SystemExit("Provide --input, --input-file, or pipe text via stdin.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a sketched storyboard ScenePlan from source text."
    )
    parser.add_argument("--input", help="Source text to process.")
    parser.add_argument("--input-file", help="Path to a text file.")
    parser.add_argument(
        "--number-of-scenes",
        type=int,
        default=12,
        help="Target number of scenes.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-5.2"),
        help="OpenAI model name (default: env OPENAI_MODEL or gpt-5.2).",
    )
    parser.add_argument(
        "--output",
        help="Write JSON output to a file (defaults to stdout).",
    )
    parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        choices=available_styles(),
        help=(
            "Art style for the generated images. "
            f"Default: {DEFAULT_STYLE}. Available:\n"
            + style_choices_help()
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print LLM responses to the terminal.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    source_text = read_source_text(args)
    if not source_text:
        raise SystemExit("Source text is empty.")

    if args.number_of_scenes < 1:
        raise SystemExit("--number-of-scenes must be >= 1.")

    load_env()
    client = OpenAI()
    art_style = get_style(args.style)
    logging.info("Using art style: %s (%s)", art_style.key, art_style.name)

    logging.info("Step 1/3: Extract scenes")
    extract_result = extract_scenes(
        client=client,
        model=args.model,
        source_text=source_text,
        number_of_scenes=args.number_of_scenes,
        verbose=args.verbose,
    )
    warnings = list(extract_result.get("warnings", []))
    scenes = extract_result.get("scenes", [])

    if len(scenes) != args.number_of_scenes:
        warnings.append(
            f"Requested {args.number_of_scenes} scenes, received {len(scenes)}."
        )

    scenes = normalize_scene_ids(scenes, warnings)

    logging.info("Step 2/3: Generate prompts per scene")
    prompt_results: List[Dict[str, Any]] = []
    for scene in scenes:
        prompt_result = generate_scene_prompt(
            client=client,
            model=args.model,
            scene=scene,
            verbose=args.verbose,
            all_scenes=scenes,
            style=art_style,
        )
        if prompt_result.get("scene_id") != scene.get("scene_id"):
            warnings.append(
                f"scene_id mismatch in prompt output for scene {scene.get('scene_id')}; "
                "using input scene_id."
            )
        prompt_results.append(
            {"scene_id": scene["scene_id"], "scene_prompt": prompt_result["scene_prompt"]}
        )

    logging.info("Step 3/3: Merge prompts into final plan")
    final_plan = merge_scene_prompts(
        scenes=scenes,
        prompts=prompt_results,
        warnings=warnings,
        style=art_style,
    )

    output_json = json.dumps(final_plan, indent=2, ensure_ascii=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output_json + "\n")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
