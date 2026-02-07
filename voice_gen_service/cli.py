import argparse
import asyncio
import json
import logging
import os
import sys
import time
import wave
from dataclasses import dataclass
from typing import Any, Dict, List

from dotenv import load_dotenv
import gradium


@dataclass
class VoiceConfig:
    voice_id: str
    model_name: str
    output_format: str


def load_env() -> None:
    load_dotenv()
    if not os.getenv("GRADIUM_API_KEY"):
        raise SystemExit(
            "GRADIUM_API_KEY is not set. Add it to .env or your environment."
        )


def read_scene_plan(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_scene_plan(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "scenes" not in data or not isinstance(data["scenes"], list):
        raise SystemExit("ScenePlan JSON must include a 'scenes' array.")
    scenes = data["scenes"]
    for scene in scenes:
        if "scene_id" not in scene:
            raise SystemExit("Each scene must include 'scene_id'.")
    return scenes


def pick_scene_text(scene: Dict[str, Any], text_field: str) -> str:
    text = scene.get(text_field, "")
    if not isinstance(text, str) or not text.strip():
        raise SystemExit(f"Scene {scene.get('scene_id')} missing text field '{text_field}'.")
    return text.strip()


def trim_text_to_max_seconds(
    text: str, max_seconds: float, words_per_sec: float
) -> tuple[str, bool]:
    words = text.split()
    if not words:
        return text, False
    max_words = max(1, int(max_seconds * words_per_sec))
    if len(words) <= max_words:
        return text, False
    trimmed = " ".join(words[:max_words])
    return trimmed, True


def ensure_output_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def build_manifest(
    plan: Dict[str, Any],
    items: List[Dict[str, Any]],
    voice_config: VoiceConfig,
) -> Dict[str, Any]:
    return {
        "project_id": plan.get("project_id"),
        "style_preset": plan.get("style_preset"),
        "voice_id": voice_config.voice_id,
        "model_name": voice_config.model_name,
        "output_format": voice_config.output_format,
        "items": items,
    }


async def create_custom_voice(
    client: gradium.client.GradiumClient,
    audio_path: str,
    name: str,
    description: str | None,
    start_s: float | None,
) -> str:
    if not os.path.isfile(audio_path):
        raise SystemExit(f"Custom voice audio file not found: {audio_path}")
    result = await gradium.voices.create(
        client,
        audio_file=audio_path,
        name=name,
        description=description,
        start_s=start_s or 0.0,
    )
    if isinstance(result, dict) and result.get("error"):
        raise SystemExit(f"Gradium voice creation failed: {result['error']}")
    voice_id = None
    if isinstance(result, dict):
        voice_id = result.get("uid") or result.get("voice_id") or result.get("id")
    else:
        voice_id = getattr(result, "uid", None) or getattr(result, "voice_id", None)
    if not voice_id:
        raise SystemExit("Gradium voice creation did not return a voice id.")
    return str(voice_id)


async def tts_with_retry(
    client: gradium.client.GradiumClient,
    text: str,
    voice_config: VoiceConfig,
    retries: int,
    backoff_sec: float,
) -> Any:
    attempt = 0
    while True:
        try:
            return await client.tts(
                setup={
                    "model_name": voice_config.model_name,
                    "voice_id": voice_config.voice_id,
                    "output_format": voice_config.output_format,
                },
                text=text,
            )
        except Exception as exc:
            attempt += 1
            if attempt > retries:
                raise
            sleep_for = backoff_sec * (2 ** (attempt - 1))
            logging.warning(
                "TTS failed (attempt %s/%s): %s. Retrying in %.1fs",
                attempt,
                retries,
                exc,
                sleep_for,
            )
            await asyncio.sleep(sleep_for)


async def run_tts(
    plan: Dict[str, Any],
    scenes: List[Dict[str, Any]],
    voice_config: VoiceConfig,
    text_field: str,
    output_dir: str,
    dry_run: bool,
    max_seconds: float | None,
    words_per_sec: float,
    retries: int,
    backoff_sec: float,
) -> Dict[str, Any]:
    client = gradium.client.GradiumClient()
    items: List[Dict[str, Any]] = []

    for scene in scenes:
        scene_id = scene.get("scene_id")
        title = scene.get("title")
        text = pick_scene_text(scene, text_field)
        trimmed = False
        if max_seconds is not None:
            text, trimmed = trim_text_to_max_seconds(text, max_seconds, words_per_sec)
        filename = f"scene_{int(scene_id):03d}.wav"
        output_path = os.path.join(output_dir, filename)

        logging.info("Scene %s: generating audio", scene_id)
        if dry_run:
            items.append(
                {
                    "scene_id": scene_id,
                    "title": title,
                    "text_field": text_field,
                    "text": text,
                    "trimmed": trimmed,
                    "max_seconds": max_seconds,
                    "audio_path": output_path,
                    "request_id": None,
                    "duration_sec": None,
                }
            )
            continue

        result = await tts_with_retry(
            client=client,
            text=text,
            voice_config=voice_config,
            retries=retries,
            backoff_sec=backoff_sec,
        )
        with open(output_path, "wb") as handle:
            handle.write(result.raw_data)

        duration_sec = None
        try:
            with wave.open(output_path, "rb") as wav:
                duration_sec = wav.getnframes() / float(wav.getframerate())
        except wave.Error:
            duration_sec = None

        items.append(
            {
                "scene_id": scene_id,
                "title": title,
                "text_field": text_field,
                "text": text,
                "trimmed": trimmed,
                "max_seconds": max_seconds,
                "audio_path": output_path,
                "request_id": getattr(result, "request_id", None),
                "sample_rate": getattr(result, "sample_rate", None),
                "duration_sec": duration_sec,
            }
        )
        logging.info("Scene %s: saved %s", scene_id, output_path)

    return build_manifest(plan, items, voice_config)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate WAV audio per scene using Gradium TTS."
    )
    parser.add_argument(
        "--scene-plan",
        required=True,
        help="Path to ScenePlan JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default="voice_output",
        help="Directory for generated audio files.",
    )
    voice_group = parser.add_mutually_exclusive_group(required=True)
    voice_group.add_argument("--voice-id", help="Gradium voice_id.")
    voice_group.add_argument(
        "--create-custom-voice",
        action="store_true",
        help="Create a custom voice from an audio file and use it for TTS.",
    )
    parser.add_argument(
        "--custom-voice-audio",
        help="Path to the audio file used to create the custom voice.",
    )
    parser.add_argument(
        "--custom-voice-name",
        help="Name for the custom voice.",
    )
    parser.add_argument(
        "--custom-voice-description",
        help="Optional description for the custom voice.",
    )
    parser.add_argument(
        "--custom-voice-start-s",
        type=float,
        help="Optional start offset in seconds for the custom voice sample.",
    )
    parser.add_argument(
        "--model-name",
        default="default",
        help="Gradium model name (default: default).",
    )
    parser.add_argument(
        "--text-field",
        default="scene_summary",
        choices=["scene_prompt", "scene_summary", "main_point"],
        help="Scene field to synthesize (default: scene_summary).",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=6.0,
        help="Maximum narration length in seconds (default: 6).",
    )
    parser.add_argument(
        "--words-per-sec",
        type=float,
        default=2.5,
        help="Words per second used for trimming (default: 2.5).",
    )
    parser.add_argument(
        "--manifest",
        default="voice_manifest.json",
        help="Output manifest JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan and manifest without calling TTS.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries for TTS failures.",
    )
    parser.add_argument(
        "--backoff-sec",
        type=float,
        default=1.0,
        help="Base backoff time in seconds for retries.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    load_env()
    ensure_output_dir(args.output_dir)

    plan = read_scene_plan(args.scene_plan)
    scenes = validate_scene_plan(plan)
    if args.create_custom_voice:
        if not args.custom_voice_audio or not args.custom_voice_name:
            raise SystemExit(
                "--create-custom-voice requires --custom-voice-audio and "
                "--custom-voice-name."
            )
    else:
        extra_custom_args = [
            args.custom_voice_audio,
            args.custom_voice_name,
            args.custom_voice_description,
            args.custom_voice_start_s,
        ]
        if any(value is not None for value in extra_custom_args):
            raise SystemExit(
                "Custom voice arguments require --create-custom-voice."
            )

    voice_id = args.voice_id
    if args.create_custom_voice:
        logging.info("Creating custom voice from %s", args.custom_voice_audio)
        client = gradium.client.GradiumClient()
        voice_id = asyncio.run(
            create_custom_voice(
                client=client,
                audio_path=args.custom_voice_audio,
                name=args.custom_voice_name,
                description=args.custom_voice_description,
                start_s=args.custom_voice_start_s,
            )
        )
        logging.info("Custom voice created: %s", voice_id)

    voice_config = VoiceConfig(
        voice_id=voice_id,
        model_name=args.model_name,
        output_format="wav",
    )

    logging.info("Starting Gradium voice generation")
    start = time.time()
    manifest = asyncio.run(
        run_tts(
            plan=plan,
            scenes=scenes,
            voice_config=voice_config,
            text_field=args.text_field,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            max_seconds=args.max_seconds,
            words_per_sec=args.words_per_sec,
            retries=args.retries,
            backoff_sec=args.backoff_sec,
        )
    )
    elapsed = time.time() - start
    logging.info("Completed in %.1fs", elapsed)

    with open(args.manifest, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=True)

    logging.info("Manifest written to %s", args.manifest)


if __name__ == "__main__":
    main()
