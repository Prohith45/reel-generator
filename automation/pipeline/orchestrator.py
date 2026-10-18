"""
Automation Orchestrator
Main pipeline that coordinates topic selection, generation, validation, and publishing.
Non-interactive - designed to run from cron/scheduler.
"""

import os
import sys
import json
import time
import logging
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import asdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Import existing generator components
from main import generate_single_video, load_config, PROJECT_ROOT as MAIN_PROJECT_ROOT
from automation.topic_planner.planner import create_topic_planner, TopicConfig
from automation.validator.validator import create_validator, ValidationResult
from automation.publisher import create_publishers, get_publisher_status
from automation.pipeline.history_db import get_db, PublishedReel, init_db

logger = logging.getLogger(__name__)


class AutomationOrchestrator:
    """Orchestrates the complete reel generation and publishing pipeline."""
    
    def __init__(self, config: Dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run or config.get("dry_run", {}).get("enabled", False)
        
        # Initialize components
        self.history_db = init_db()
        self.topic_planner = create_topic_planner(config, self.history_db)
        self.validator = create_validator(config)
        self.publishers = create_publishers(config)
        self.publisher_status = get_publisher_status(self.publishers)
        
        # Recovery settings
        self.recovery_config = config.get("recovery", {})
        self.max_gen_retries = self.recovery_config.get("max_generation_retries", 2)
        self.max_pub_retries = self.recovery_config.get("max_publish_retries", 3)
        self.resume_enabled = self.recovery_config.get("resume_from_last_step", True)
        
        logger.info(f"Automation Orchestrator initialized (dry_run={self.dry_run})")
        logger.info(f"Publishers available: {self.publisher_status}")
    
    def run_pipeline(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """Run the complete pipeline for one reel."""
        result = {
            "success": False,
            "topic": "",
            "video_path": "",
            "youtube": {"success": False, "video_id": "", "url": "", "error": ""},
            "instagram": {"success": False, "media_id": "", "url": "", "error": ""},
            "errors": [],
            "steps_completed": []
        }
        
        reel_record = None
        
        try:
            # Step 1: Select topic
            logger.info("[STEP 1/5] Selecting topic...")
            if topic:
                topic_config = self.topic_planner._create_topic_config(topic)
            else:
                topic_config = self.topic_planner.select_topic()
            result["topic"] = topic_config.topic
            result["steps_completed"].append("topic_selection")
            logger.info(f"Selected topic: {topic_config.topic}")
            
            # Step 2: Generate reel
            logger.info("[STEP 2/5] Generating reel...")
            video_path = self._generate_reel(topic_config)
            if not video_path:
                raise Exception("Reel generation failed")
            result["video_path"] = video_path
            result["steps_completed"].append("generation")
            logger.info(f"Reel generated: {video_path}")
            
            # Step 3: Validate video
            logger.info("[STEP 3/5] Validating video...")
            expected_dur = topic_config.generation_options.get("duration_seconds", 60)
            if topic_config.generation_options.get("use_intro", False):
                expected_dur += 10.0
            validation_result = self.validator.validate(
                video_path, 
                expected_duration=expected_dur
            )
            if not validation_result.valid:
                raise Exception(f"Video validation failed: {validation_result.errors}")
            result["steps_completed"].append("validation")
            logger.info("Video validation passed")
            
            # Create history record
            reel_record = self._create_history_record(topic_config, video_path, validation_result)
            
            # Step 4: Prepare metadata (already done in topic_config)
            logger.info("[STEP 4/5] Preparing upload metadata...")
            result["steps_completed"].append("metadata_prep")
            
            # Step 5: Publish to platforms
            logger.info("[STEP 5/5] Uploading to platforms...")
            self._publish_to_platforms(reel_record, topic_config, video_path, result)
            result["steps_completed"].append("publishing")
            
            # Determine overall success
            yt_success = result["youtube"]["success"]
            ig_success = result["instagram"]["success"]
            
            if self.dry_run:
                result["success"] = True
            elif self.publisher_status["youtube"] and self.publisher_status["instagram"]:
                result["success"] = yt_success and ig_success
            elif self.publisher_status["youtube"]:
                result["success"] = yt_success
            elif self.publisher_status["instagram"]:
                result["success"] = ig_success
            else:
                result["success"] = True  # No publishers configured, generation only
            
            logger.info(f"Pipeline completed. Success: {result['success']}")
            
        except Exception as e:
            error_msg = f"Pipeline error: {e}\n{traceback.format_exc()}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            
            # Update history record if created
            if reel_record:
                self.history_db.update_reel(reel_record.id, {
                    "overall_status": "failed",
                    "youtube_error": error_msg,
                    "instagram_error": error_msg
                })
        
        return result
    
    def _generate_reel(self, topic_config: TopicConfig) -> Optional[str]:
        """Generate a reel using the existing generator with non-interactive config."""
        
        # We need to call the generator with the topic config
        # The existing generate_single_video() is interactive - we need a non-interactive version
        
        # Let's create a modified config and call the internal pipeline functions directly
        gen_config = self._build_generation_config(topic_config)
        
        # Use the existing generation pipeline but with our config
        try:
            # Import the core pipeline functions
            from src.script_engine import generate_script
            from src.tts import synthesize_speech, get_audio_duration, split_text_to_sentences, estimate_sentence_timings
            from src.image_engine import extract_search_queries, scrape_images_for_video
            from src.video_engine import compose_video
            import shutil
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = self._sanitize_filename(topic_config.topic)
            
            output_dir = MAIN_PROJECT_ROOT / "outputs/videos"
            tts_dir = MAIN_PROJECT_ROOT / "outputs/audio"
            persistent_images_dir = MAIN_PROJECT_ROOT / "outputs/images"
            
            temp_dir = tts_dir / timestamp
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # ── STEP 1: Generate English Script ──
            logger.info("Generating English script...")
            script_text = generate_script(
                topic=topic_config.topic,
                content_type=topic_config.generation_options["content_type"],
                duration=topic_config.generation_options["duration_seconds"],
                audience=topic_config.generation_options["audience"],
                language="en",
                config=gen_config,
            )
            
            if not script_text:
                logger.error("Script generation failed")
                return None
            
            logger.info(f"Script generated: {len(script_text.split())} words")
            
            # ── STEP 2: Prepare Voice Text ──
            # For automation, we'll use the default language (English) unless specified
            selected_lang_code = "en"
            script_source = "auto"
            
            # Handle translation if needed
            if selected_lang_code != "en":
                from src.translation import translate_text
                import re
                sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
                translated_sentences = []
                for sent in sentences:
                    if sent.strip():
                        trans = translate_text(sent, selected_lang_code, gen_config)
                        translated_sentences.append(trans)
                voice_text = " ".join(translated_sentences)
            else:
                voice_text = script_text
            
            # Save original script
            from main import sanitize_filename
            script_dir = MAIN_PROJECT_ROOT / "outputs/script"
            script_dir.joinpath(f"{safe_topic}_{timestamp}_original.txt").write_text(script_text, encoding='utf-8')
            
            # ── STEP 3: Generate Voice ──
            logger.info("Synthesizing voiceover...")
            target_language = gen_config["voice"]["language"]
            lang_key = "english" if target_language == "en" else "telugu"
            engine_name = gen_config.get("voice", {}).get(lang_key, {}).get("engine", "unknown")
            
            audio_filename = f"{safe_topic}_{selected_lang_code}_{engine_name}_{timestamp}.wav"
            audio_path = str(tts_dir / audio_filename)
            
            result = synthesize_speech(
                text=voice_text,
                output_path=audio_path,
                speaker_id=0,
                config=gen_config
            )
            
            if not result:
                logger.error("Voice synthesis failed")
                return None
            
            audio_duration = get_audio_duration(audio_path)
            logger.info(f"Audio generated: {audio_duration:.1f} seconds")
            
            # ── STEP 4: Parse sentences & extract keywords ──
            logger.info("Analyzing script & extracting keywords...")
            sentences = split_text_to_sentences(script_text)
            timings = estimate_sentence_timings(sentences, audio_duration)
            search_queries = extract_search_queries(timings, topic=topic_config.topic, config=gen_config)
            
            total_queries = sum(len(sq["queries"]) for sq in search_queries)
            logger.info(f"Found {len(sentences)} sentences, {total_queries} search queries")
            
            # ── STEP 5: Scrape Images ──
            logger.info("Scraping images...")
            images_dir = str(persistent_images_dir / f"{safe_topic}_{timestamp}")
            target_images = max(1, int(audio_duration / 4))
            image_map = scrape_images_for_video(
                search_queries=search_queries,
                output_dir=images_dir,
                config=gen_config,
                target_images=target_images
            )
            
            total_images = len([img for img in image_map.values() if img])
            logger.info(f"Saved {total_images} images")
            
            # ── STEP 6: Compose Video ──
            logger.info("Composing video...")
            output_filename = f"{safe_topic}_{selected_lang_code}_{engine_name}_{timestamp}.mp4"
            output_path = str(output_dir / output_filename)
            
            # Resolve overlay path
            overlay_name = topic_config.generation_options.get("overlay", "oggy horizontal.mp4")
            overlay_path = None
            if overlay_name and overlay_name != "None":
                overlay_path = str(MAIN_PROJECT_ROOT / "assets" / "green_screen" / overlay_name)
                if not os.path.exists(overlay_path):
                    logger.warning(f"Overlay not found: {overlay_path}")
                    overlay_path = None
            
            video_path = compose_video(
                script_text=script_text,
                audio_path=audio_path,
                sentence_timings=timings,
                image_map=image_map,
                output_path=output_path,
                config=gen_config,
                animation_style=topic_config.generation_options["animation_style"],
                language=target_language,
                overlay_path=overlay_path,
                topic=topic_config.topic,
            )
            
            # Cleanup temp dir
            if not gen_config.get("output", {}).get("keep_temp_files", False):
                shutil.rmtree(str(temp_dir), ignore_errors=True)

            # ── Verify output artifact ──
            if not video_path or not os.path.exists(video_path):
                logger.error(f"[FATAL] compose_video returned path but file does not exist: {video_path}")
                return None

            file_size = os.path.getsize(video_path)
            if file_size == 0:
                logger.error(f"[FATAL] Output video is 0 bytes: {video_path}")
                return None

            logger.info(f"Output video verified: {video_path} ({file_size / (1024*1024):.1f} MB)")
            return video_path
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            traceback.print_exc()
            return None
    
    def _build_generation_config(self, topic_config: TopicConfig) -> Dict[str, Any]:
        """Build the config dict for the generation pipeline."""
        # Start with base master config from config.yaml
        from main import load_config
        gen_config = load_config()
        
        # Merge automation config
        for k, v in self.config.items():
            if k not in gen_config:
                gen_config[k] = v
            elif isinstance(v, dict) and isinstance(gen_config[k], dict):
                gen_config[k].update(v)
        
        # Override with topic-specific generation options
        gen_opts = topic_config.generation_options
        
        # Update voice config
        if "voice" not in gen_config:
            gen_config["voice"] = {}
        
        gen_config["voice"]["language"] = "en"  # Default to English for automation
        
        if gen_opts.get("tts_engine") == "kokoro":
            gen_config["voice"]["english"] = {
                "engine": "kokoro"
            }
            gen_config["voice"]["kokoro"] = {
                "voice_id": gen_opts.get("kokoro_voice", "am_adam"),
                "lang_code": gen_opts.get("kokoro_pipeline", "a"),
                "speed": 1.0
            }
        elif gen_opts.get("tts_engine") == "supertonic":
            gen_config["voice"]["english"] = {
                "engine": "supertonic",
                "supertonic_voice": "M1.json",
                "supertonic_vibe": "professional",
                "supertonic_lang": "en"
            }
        elif gen_opts.get("tts_engine") == "indic":
            gen_config["voice"]["english"] = {"engine": "indic"}
            gen_config["voice"]["telugu"] = {"engine": "indic"}
            gen_config["voice"]["indic"] = {
                "language": "Telugu",
                "lang_code": "te",
                "speaker": "Prakash",
                "vibe": "1",
                "engine": "indic"
            }
        
        # Subtitle style
        if "subtitles" not in gen_config:
            gen_config["subtitles"] = {}
        gen_config["subtitles"]["entrance_animation"] = gen_opts.get("subtitle_style", "fade_up")
        
        # Oggy intro
        gen_config["use_oggy_intro"] = gen_opts.get("use_intro", True)
        
        return gen_config
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for filename."""
        import re
        name = name.replace(' ', '_')
        name = re.sub(r'[^\w\.\-]', '', name)
        return name[:30]
    
    def _create_history_record(self, topic_config: TopicConfig, video_path: str, validation: ValidationResult) -> PublishedReel:
        """Create and save history record."""
        import os
        
        reel = PublishedReel(
            topic=topic_config.topic,
            title=topic_config.title,
            hook=topic_config.hook,
            description=topic_config.description,
            hashtags=json.dumps(topic_config.hashtags),
            generation_options=json.dumps(topic_config.generation_options),
            video_path=video_path,
            video_filename=os.path.basename(video_path),
            generated_at=datetime.now().isoformat(),
            duration_seconds=validation.duration_seconds,
            file_size_bytes=validation.file_size_bytes,
            youtube_status="pending" if self.publisher_status["youtube"] else "skipped",
            instagram_status="pending" if self.publisher_status["instagram"] else "skipped",
            overall_status="pending",
            dry_run=self.dry_run
        )
        
        reel_id = self.history_db.add_reel(reel)
        reel.id = reel_id
        return reel
    
    def _publish_to_platforms(self, reel_record: PublishedReel, topic_config: TopicConfig, video_path: str, result: Dict[str, Any]):
        """Publish to all configured platforms."""
        
        # YouTube
        if self.publisher_status["youtube"]:
            logger.info("Publishing to YouTube...")
            yt_result = self.publishers["youtube"].upload(video_path, topic_config, self.dry_run)
            result["youtube"] = {
                "success": yt_result.success,
                "video_id": yt_result.video_id,
                "url": yt_result.url,
                "error": yt_result.error
            }
            
            if yt_result.success:
                self.history_db.mark_youtube_published(reel_record.id, yt_result.video_id, yt_result.url)
            else:
                self.history_db.mark_youtube_failed(reel_record.id, yt_result.error)
        
        # Instagram
        if self.publisher_status["instagram"]:
            logger.info("Publishing to Instagram...")
            ig_result = self.publishers["instagram"].upload(video_path, topic_config, self.dry_run)
            result["instagram"] = {
                "success": ig_result.success,
                "media_id": ig_result.media_id,
                "url": ig_result.url,
                "error": ig_result.error
            }
            
            if ig_result.success:
                self.history_db.mark_instagram_published(reel_record.id, ig_result.media_id, ig_result.url)
            else:
                self.history_db.mark_instagram_failed(reel_record.id, ig_result.error)
    
    def retry_failed_publishing(self) -> Dict[str, Any]:
        """Retry failed publishing tasks from history."""
        results = {"youtube": [], "instagram": []}
        
        # Retry YouTube
        if self.publisher_status["youtube"]:
            failed_yt = self.history_db.get_failed_publish("youtube", self.max_pub_retries)
            for reel in failed_yt:
                logger.info(f"Retrying YouTube for reel {reel.id}: {reel.topic}")
                # Need topic_config - reconstruct from history
                topic_config = self._reconstruct_topic_config(reel)
                yt_result = self.publishers["youtube"].upload(reel.video_path, topic_config, self.dry_run)
                
                if yt_result.success:
                    self.history_db.mark_youtube_published(reel.id, yt_result.video_id, yt_result.url)
                    results["youtube"].append({"id": reel.id, "success": True})
                else:
                    self.history_db.mark_youtube_failed(reel.id, yt_result.error)
                    results["youtube"].append({"id": reel.id, "success": False, "error": yt_result.error})
        
        # Retry Instagram
        if self.publisher_status["instagram"]:
            failed_ig = self.history_db.get_failed_publish("instagram", self.max_pub_retries)
            for reel in failed_ig:
                logger.info(f"Retrying Instagram for reel {reel.id}: {reel.topic}")
                topic_config = self._reconstruct_topic_config(reel)
                ig_result = self.publishers["instagram"].upload(reel.video_path, topic_config, self.dry_run)
                
                if ig_result.success:
                    self.history_db.mark_instagram_published(reel.id, ig_result.media_id, ig_result.url)
                    results["instagram"].append({"id": reel.id, "success": True})
                else:
                    self.history_db.mark_instagram_failed(reel.id, ig_result.error)
                    results["instagram"].append({"id": reel.id, "success": False, "error": ig_result.error})
        
        return results
    
    def _reconstruct_topic_config(self, reel: PublishedReel) -> TopicConfig:
        """Reconstruct TopicConfig from history record."""
        import json
        return TopicConfig(
            topic=reel.topic,
            title=reel.title,
            hook=reel.hook,
            description=reel.description,
            hashtags=json.loads(reel.hashtags) if reel.hashtags else [],
            generation_options=json.loads(reel.generation_options) if reel.generation_options else {}
        )


def create_orchestrator(config: Dict[str, Any], dry_run: bool = False) -> AutomationOrchestrator:
    """Factory function to create AutomationOrchestrator."""
    return AutomationOrchestrator(config, dry_run)


def main():
    """Main entry point for automation CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Reel Automation Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no publishing)")
    parser.add_argument("--config", default="config/automation.yaml", help="Path to automation config")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed publishing tasks")
    parser.add_argument("--topic", help="Specific topic to generate (bypass planner)")
    parser.add_argument("--llm", choices=["local", "api"], default=None, help="LLM mode: 'local' (default) or 'api' (Google Gemini cloud API)")
    parser.add_argument("--upload", choices=["youtube", "instagram", "both", "none"], default="both", help="Upload target: youtube, instagram, both (default), or none")
    args = parser.parse_args()
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    # Load configs
    import yaml
    config_path = PROJECT_ROOT / args.config
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Override dry_run from CLI
    dry_run = args.dry_run or config.get("dry_run", {}).get("enabled", False)

    # Override llm_mode if provided
    if args.llm:
        if "script" not in config:
            config["script"] = {}
        config["script"]["llm_mode"] = args.llm

    # Override upload targets if provided
    if args.upload == "none":
        config.setdefault("youtube", {})["enabled"] = False
        config.setdefault("instagram", {})["enabled"] = False
    elif args.upload == "youtube":
        config.setdefault("youtube", {})["enabled"] = True
        config.setdefault("instagram", {})["enabled"] = False
    elif args.upload == "instagram":
        config.setdefault("youtube", {})["enabled"] = False
        config.setdefault("instagram", {})["enabled"] = True
    # else "both" — keep defaults from config
    
    # Setup logging
    log_config = config.get("logging", {})
    log_file = PROJECT_ROOT / log_config.get("file", "logs/automation.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_config.get("level", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Create orchestrator
    orchestrator = create_orchestrator(config, dry_run)
    
    if args.retry_failed:
        logger.info("Retrying failed publishing tasks...")
        results = orchestrator.retry_failed_publishing()
        logger.info(f"Retry results: {results}")
    else:
        logger.info("Starting automation pipeline...")
        result = orchestrator.run_pipeline(topic=args.topic)
        logger.info(f"Pipeline result: {json.dumps(result, indent=2)}")
        
        if not result["success"]:
            sys.exit(1)


if __name__ == "__main__":
    main()