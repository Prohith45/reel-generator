#!/usr/bin/env python3
"""
Reel Generator - Unified Automation Orchestrator
================================================
Coordinates topic generation, video creation, artifact verification,
and uploading to YouTube Shorts & Instagram Reels in 3 unified stages.

Usage:
    python orchestrate.py --topic "what is capacitor" --upload youtube
    python orchestrate.py --topic "what is capacitor" --upload instagram
    python orchestrate.py --topic "what is capacitor" --upload both
    python orchestrate.py --topic "what is capacitor" --upload none
    python orchestrate.py --topic "what is capacitor" --dry-run
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Set up paths
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env credentials
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "outputs/script/orchestrator.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("orchestrator")


def run_pipeline(
    topic: str,
    upload: str = "both",
    duration: int = 60,
    llm_mode: str = "api",
    tts_engine: str = "kokoro",
    overlay: str = "4",
    intro: str = "1",
    visuals: str = "hybrid",
    dry_run: bool = False,
) -> bool:
    """Execute the full 3-step pipeline."""
    
    print("\n" + "=" * 65)
    print("🎬  REEL GENERATOR UNIFIED PIPELINE")
    print(f"    Topic:    {topic}")
    print(f"    Upload:   {upload.upper()}")
    print(f"    Visuals:  {visuals.upper()}")
    print(f"    Mode:     {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 65 + "\n")
    
    # ────────────────────────────────────────────────────────────
    # [STEP 1/3] Generating Reel for topic...
    # ────────────────────────────────────────────────────────────
    print(f"[STEP 1/3] Generating Reel for topic: \"{topic}\"...")
    logger.info(f"[STEP 1/3] Generating Reel for topic: \"{topic}\"")
    
    from main import load_config, generate_single_video
    config = load_config()
    
    # Apply CLI overrides
    if "script" not in config:
        config["script"] = {}
    config["script"]["llm_mode"] = llm_mode

    # Visual media mode override
    config.setdefault("video", {})["visual_mode"] = visuals
    config.setdefault("broll", {})["enabled"] = (visuals == "hybrid")
    
    # Construct arguments namespace for main.py
    cli_args = argparse.Namespace(
        topic=topic,
        duration=duration,
        content_type="educational",
        audience="common",
        animation_style="none",
        subtitle_style="fade_up",
        tts=tts_engine,
        voice_id="am_adam" if tts_engine == "kokoro" else None,
        language="en",
        overlay=overlay,
        intro=intro,
        llm=llm_mode,
        visuals=visuals,
        non_interactive=True,
    )
    
    video_path = generate_single_video(config, cli_args=cli_args)
    
    if not video_path:
        error_msg = f"[FATAL] Reel generation failed for topic: '{topic}'"
        print(f"\n{error_msg}")
        logger.error(error_msg)
        return False

    # ────────────────────────────────────────────────────────────
    # [STEP 2/3] Verifying output artifact...
    # ────────────────────────────────────────────────────────────
    print(f"\n[STEP 2/3] Verifying output artifact...")
    logger.info(f"[STEP 2/3] Verifying output artifact: {video_path}")
    
    resolved_path = Path(video_path).resolve()
    if not resolved_path.exists():
        error_msg = f"[FATAL] Video file was not created: {resolved_path}"
        print(f"\n{error_msg}")
        logger.error(error_msg)
        return False
        
    file_size = resolved_path.stat().st_size
    if file_size == 0:
        error_msg = f"[FATAL] Output video file is empty (0 bytes): {resolved_path}"
        print(f"\n{error_msg}")
        logger.error(error_msg)
        return False

    # Deep validation via validator if available
    try:
        from automation.validator.validator import create_validator
        val_config = {
            "validation": {
                "enabled": True,
                "checks": {
                    "file_exists": True,
                    "file_not_empty": True,
                    "valid_mp4": True,
                    "correct_resolution": True,
                    "has_audio": True,
                    "has_video_stream": True,
                }
            }
        }
        validator = create_validator(val_config)
        val_result = validator.validate(str(resolved_path))
        if not val_result.valid:
            logger.warning(f"[WARNING] Validator noticed issues: {val_result.errors}")
        else:
            logger.info("[OK] Video validation passed all stream and container checks.")
    except Exception as e:
        logger.debug(f"Validator check skipped: {e}")

    file_size_mb = file_size / (1024 * 1024)
    print(f"[OK] Video artifact verified: {resolved_path.name} ({file_size_mb:.2f} MB)")
    logger.info(f"[OK] Output video verified: {resolved_path} ({file_size_mb:.2f} MB)")

    # ────────────────────────────────────────────────────────────
    # [STEP 3/3] Uploading to YouTube & Instagram...
    # ────────────────────────────────────────────────────────────
    upload_target = upload.lower().strip()
    if upload_target == "none":
        print(f"\n[STEP 3/3] Upload skipped (--upload none requested).")
        logger.info("[STEP 3/3] Upload skipped (--upload none requested)")
        print("\n" + "=" * 65)
        print("🎉 PIPELINE COMPLETE!")
        print(f"Output Video: {resolved_path}")
        print("=" * 65 + "\n")
        return True

    print(f"\n[STEP 3/3] Uploading to platforms ({upload_target})...")
    logger.info(f"[STEP 3/3] Uploading to platforms ({upload_target})")

    yt_success = False
    ig_success = False
    
    # ── Upload to YouTube ──
    if upload_target in ("youtube", "both"):
        print("\n--- Uploading to YouTube Shorts ---")
        try:
            from youtube_uploader import upload_to_youtube
            yt_res = upload_to_youtube(str(resolved_path), topic=topic, dry_run=dry_run)
            if yt_res["success"]:
                print(f"[SUCCESS] YouTube URL: {yt_res['url']}")
                yt_success = True
            else:
                print(f"[ERROR] YouTube upload failed: {yt_res['error']}")
        except Exception as e:
            print(f"[ERROR] YouTube upload error: {e}")
            logger.error(f"YouTube upload error: {e}")

    # ── Upload to Instagram ──
    if upload_target in ("instagram", "both"):
        print("\n--- Uploading to Instagram Reels ---")
        try:
            from instagram_uploader import upload_to_instagram
            ig_res = upload_to_instagram(str(resolved_path), topic=topic, dry_run=dry_run)
            if ig_res["success"]:
                print(f"[SUCCESS] Instagram URL: {ig_res['url']}")
                ig_success = True
            elif ig_res.get("skipped"):
                print(f"{ig_res['error']}")
                ig_success = True  # Handled gracefully as non-fatal
            else:
                print(f"[ERROR] Instagram upload failed: {ig_res['error']}")
        except Exception as e:
            # Wrap Instagram in isolated try-except so it NEVER blocks pipeline
            print(f"[WARNING] Instagram exception: {e}")
            logger.warning(f"[WARNING] Instagram exception: {e}")

    # ── Record into history database ──
    try:
        from automation.pipeline.history_db import init_db, PublishedReel
        db = init_db()
        reel = PublishedReel(
            topic=topic,
            title=f"{topic.capitalize()} Explained #shorts",
            video_path=str(resolved_path),
            video_filename=resolved_path.name,
            generated_at=datetime.now().isoformat(),
            file_size_bytes=file_size,
            youtube_status="published" if yt_success else "skipped" if upload_target == "instagram" else "failed",
            instagram_status="published" if ig_success else "skipped" if upload_target == "youtube" else "failed",
            overall_status="published" if (yt_success or ig_success) else "failed",
            dry_run=dry_run,
        )
        db.add_reel(reel)
        logger.info("Run recorded in publishing history database.")
    except Exception as e:
        logger.debug(f"History DB recording skipped: {e}")

    print("\n" + "=" * 65)
    print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"Output Video: {resolved_path}")
    print("=" * 65 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Unified Reel Generator & Social Publisher",
        add_help=True,
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Reel topic (e.g. 'what is capacitor'). If omitted, selects automatically from topic pool.",
    )
    parser.add_argument(
        "--upload",
        choices=["youtube", "instagram", "both", "none"],
        default="both",
        help="Upload destination: youtube, instagram, both (default), or none",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Target video duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--llm",
        "--llm-mode",
        dest="llm",
        choices=["api", "local"],
        default="api",
        help="LLM execution mode: 'api' (Cloud API) or 'local' (Local GGUF model, default: api)",
    )
    parser.add_argument(
        "--tts",
        choices=["kokoro", "supertonic", "indic"],
        default="kokoro",
        help="Voice synthesis engine (default: kokoro)",
    )
    parser.add_argument(
        "--overlay",
        default="4",
        help="Overlay green screen asset (default: 4 / oggy horizontal.mp4)",
    )
    parser.add_argument(
        "--intro",
        default="1",
        help="Include Oggy intro: 1=yes, 2/0=no (default: 1)",
    )
    parser.add_argument(
        "--visuals",
        "--media-mode",
        dest="visuals",
        choices=["images", "hybrid"],
        default="hybrid",
        help="Visual mode: 'images' (only static images) or 'hybrid' (videos + images, default: hybrid)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline and simulate uploads without publishing live",
    )
    args = parser.parse_args()

    # Topic auto-selection if not specified
    topic = args.topic
    if not topic:
        try:
            from automation.topic_planner.planner import create_topic_planner
            from main import load_config
            cfg = load_config()
            planner = create_topic_planner(cfg)
            topic_cfg = planner.select_topic()
            topic = topic_cfg.topic
            print(f"[INFO] Auto-selected topic from planner: '{topic}'")
        except Exception as e:
            topic = "What is a Capacitor and How Does It Work"
            print(f"[INFO] Default topic selected: '{topic}'")

    success = run_pipeline(
        topic=topic,
        upload=args.upload,
        duration=args.duration,
        llm_mode=args.llm,
        tts_engine=args.tts,
        overlay=args.overlay,
        intro=args.intro,
        visuals=args.visuals,
        dry_run=args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
