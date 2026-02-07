import argparse
import asyncio
import json
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict, List

from dotenv import load_dotenv
import imageio_ffmpeg

from voice_gen_service.cli import VoiceConfig, run_tts
from fal_integration_service.scenes import load_storyboard
from fal_integration_service.storyboard_pipeline import process_storyboard
from text_extraction_service.cli import (
    extract_scenes,
    generate_scene_prompt,
    normalize_scene_ids,
)
from openai import OpenAI


def load_env() -> None:
    load_dotenv()
    missing = []
    if not os.getenv("GRADIUM_API_KEY"):
        missing.append("GRADIUM_API_KEY")
    if not os.getenv("FAL_KEY"):
        missing.append("FAL_KEY")
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)


def build_duration_map(voice_manifest: Dict[str, Any], max_seconds: float) -> Dict[int, float]:
    durations: Dict[int, float] = {}
    for item in voice_manifest.get("items", []):
        scene_id = int(item["scene_id"])
        duration = item.get("duration_sec")
        if isinstance(duration, (int, float)):
            durations[scene_id] = min(float(duration), max_seconds)
        else:
            durations[scene_id] = max_seconds
    return durations


def mux_video_audio(video_path: str, audio_path: str, output_path: str) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg mux failed: "
            f"{result.stderr.strip()}"
        )


def concat_videos(clip_paths: List[str], output_path: str) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as handle:
        for path in clip_paths:
            handle.write(f"file '{os.path.abspath(path)}'\n")
        list_path = handle.name
    try:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "ffmpeg concat failed: "
                f"{result.stderr.strip()}"
            )
    finally:
        os.unlink(list_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate narration and stitched video from a ScenePlan."
    )
    parser.add_argument(
        "--input-file",
        help="Markdown/text file to process into a ScenePlan.",
    )
    parser.add_argument(
        "--scene-plan",
        help="ScenePlan JSON path (skip text extraction).",
    )
    parser.add_argument(
        "--number-of-scenes",
        type=int,
        default=12,
        help="Target number of scenes when extracting from text.",
    )
    parser.add_argument(
        "--llm-model",
        default=os.getenv("OPENAI_MODEL", "gpt-5.2"),
        help="OpenAI model for text extraction.",
    )
    parser.add_argument("--voice-id", required=True, help="Gradium voice_id.")
    parser.add_argument(
        "--output-dir",
        default="pipeline_output",
        help="Base output directory.",
    )
    parser.add_argument(
        "--final-video",
        default="final_video.mp4",
        help="Final stitched video filename.",
    )
    parser.add_argument(
        "--voice-manifest",
        default="voice_manifest.json",
        help="Voice manifest output filename.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=6.0,
        help="Max narration duration per scene.",
    )
    parser.add_argument(
        "--words-per-sec",
        type=float,
        default=2.5,
        help="Words-per-second for trimming.",
    )
    parser.add_argument(
        "--text-field",
        default="scene_summary",
        choices=["scene_prompt", "scene_summary", "main_point"],
        help="Scene field to narrate.",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep intermediate per-scene clips.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_env()

    if bool(args.input_file) == bool(args.scene_plan):
        raise SystemExit("Provide exactly one of --input-file or --scene-plan.")

    output_root = args.output_dir
    voice_output_dir = os.path.join(output_root, "voice_output")
    video_output_dir = os.path.join(output_root, "video_output")
    ensure_dir(output_root)
    ensure_dir(voice_output_dir)
    ensure_dir(video_output_dir)

    plan = None
    scene_plan_path = args.scene_plan
    if args.input_file:
        logging.info("Step 0/4: Extract scenes from input text")
        with open(args.input_file, "r", encoding="utf-8") as handle:
            source_text = handle.read().strip()
        if not source_text:
            raise SystemExit("Input file is empty.")
        client = OpenAI()
        extract_result = extract_scenes(
            client=client,
            model=args.llm_model,
            source_text=source_text,
            number_of_scenes=args.number_of_scenes,
            verbose=False,
        )
        warnings = list(extract_result.get("warnings", []))
        scenes = extract_result.get("scenes", [])
        scenes = normalize_scene_ids(scenes, warnings)
        logging.info("Step 0.5/4: Generate scene prompts for visuals")
        for scene in scenes:
            logging.info("Step 0.5/4: Scene %s prompt generation", scene["scene_id"])
            prompt_result = generate_scene_prompt(
                client=client,
                model=args.llm_model,
                scene=scene,
                verbose=False,
            )
            scene["scene_prompt"] = prompt_result["scene_prompt"]
        plan = {
            "project_id": None,
            "style_preset": "sketched_storyboard",
            "scenes": scenes,
            "warnings": warnings,
        }
        scene_plan_path = os.path.join(output_root, "scene_plan.json")
        write_json(scene_plan_path, plan)
    else:
        with open(args.scene_plan, "r", encoding="utf-8") as handle:
            plan = json.load(handle)

    logging.info("Step 1/4: Generate narration audio (max %.1fs)", args.max_seconds)

    voice_config = VoiceConfig(
        voice_id=args.voice_id,
        model_name="default",
        output_format="wav",
    )

    voice_manifest = asyncio.run(
        run_tts(
            plan=plan,
            scenes=plan["scenes"],
            voice_config=voice_config,
            text_field=args.text_field,
            output_dir=voice_output_dir,
            dry_run=False,
            max_seconds=args.max_seconds,
            words_per_sec=args.words_per_sec,
            retries=2,
            backoff_sec=1.0,
        )
    )
    voice_manifest_path = os.path.join(output_root, args.voice_manifest)
    write_json(voice_manifest_path, voice_manifest)

    logging.info("Step 2/4: Generate video clips per scene")
    storyboard = load_storyboard(scene_plan_path)
    per_scene_durations = build_duration_map(voice_manifest, args.max_seconds)
    video_result = process_storyboard(
        storyboard,
        per_scene_durations=per_scene_durations,
        output_dir=video_output_dir,
        return_clips=True,
    )
    clip_paths = video_result.get("clip_paths", [])

    logging.info("Step 3/4: Mux audio with per-scene video")
    audio_by_scene = {
        int(item["scene_id"]): item["audio_path"]
        for item in voice_manifest.get("items", [])
    }
    muxed_paths: List[str] = []
    for clip_path in clip_paths:
        base = os.path.basename(clip_path)
        scene_id = int(base.split("_")[1].split(".")[0])
        audio_path = audio_by_scene.get(scene_id)
        if not audio_path:
            raise SystemExit(f"No audio found for scene {scene_id}")
        muxed_path = os.path.join(video_output_dir, f"scene_{scene_id:03d}_av.mp4")
        mux_video_audio(clip_path, audio_path, muxed_path)
        muxed_paths.append(muxed_path)

    logging.info("Step 4/4: Concatenate into final video")
    final_video_path = os.path.join(output_root, args.final_video)
    muxed_paths.sort()
    concat_videos(muxed_paths, final_video_path)

    if not args.keep_intermediates:
        for path in muxed_paths:
            if os.path.exists(path):
                os.unlink(path)

    final_manifest = {
        "scene_plan": args.scene_plan,
        "voice_manifest": voice_manifest_path,
        "final_video": final_video_path,
    }
    write_json(os.path.join(output_root, "final_manifest.json"), final_manifest)
    logging.info("Final video saved: %s", final_video_path)


if __name__ == "__main__":
    main()
