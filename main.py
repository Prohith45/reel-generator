#!/usr/bin/env python3
"""
🎬 REEL GENERATOR - Main CLI Entry Point
=========================================
Robust Multi-Language & Modular Version
"""

import os
import sys
import yaml
import logging
import shutil
import random
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Force UTF-8 encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.environ['PYTHONIOENCODING'] = 'utf-8'

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Ensure necessary directories exist
def _ensure_dirs():
    dirs = [
        'assets/templates',
        'assets/green_screen',
        'outputs/script',          # English original scripts + log
        'outputs/translation',     # NLLB / manual translation outputs
        'outputs/audio',           # Persistent audio files
        'outputs/images',          # Persistent scraped images
        'outputs/videos',          # Final reels
    ]
    for d in dirs:
        os.makedirs(PROJECT_ROOT / d, exist_ok=True)

_ensure_dirs()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(str(PROJECT_ROOT / "outputs/script/reel_generator.log"), encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Try rich for pretty console output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import print as rprint
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None


# ============================================================================
# HELPERS
# ============================================================================

def sanitize_filename(name: str) -> str:
    """Sanitize string to be safe for filenames on Windows/Linux."""
    import re
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    # Keep only alphanumeric, underscores, hyphens, and dots
    name = re.sub(r'[^\w\.\-]', '', name)
    return name[:30]


# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = PROJECT_ROOT / "config.yaml"
    
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
    
    # Inject API keys from environment if config fields are empty
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        api_cfg = config.setdefault("script", {}).setdefault("api", {})
        if not api_cfg.get("api_key"):
            api_cfg["api_key"] = gemini_key

    pexels_key = os.getenv("PEXELS_API_KEY")
    if pexels_key:
        broll_pexels = config.setdefault("broll", {}).setdefault("pexels", {})
        if not broll_pexels.get("api_key"):
            broll_pexels["api_key"] = pexels_key
        legacy_pexels = config.setdefault("pexels", {})
        if not legacy_pexels.get("api_key"):
            legacy_pexels["api_key"] = pexels_key

    tenor_key = os.getenv("TENOR_API_KEY")
    if tenor_key:
        broll_tenor = config.setdefault("broll", {}).setdefault("tenor", {})
        if not broll_tenor.get("api_key"):
            broll_tenor["api_key"] = tenor_key

    return config


# ============================================================================
# PRETTY DISPLAY
# ============================================================================

def print_banner():
    """Print the application banner with dynamic width padding and fallback compatibility."""
    import unicodedata

    # Fallback to simple layout if requested or if on Windows legacy terminal
    use_fallback = (
        os.environ.get("REEL_SIMPLE_BANNER") == "1" or
        os.environ.get("REEL_NO_EMOJI") == "1" or
        (sys.platform == "win32" and "WT_SESSION" not in os.environ and "VSCODE_GIT_IPC_HANDLE" not in os.environ)
    )

    # Define border tokens
    if use_fallback:
        box_top_left = "+"
        box_top_right = "+"
        box_bottom_left = "+"
        box_bottom_right = "+"
        box_horiz = "-"
        box_vert = "|"
    else:
        box_top_left = "╔"
        box_top_right = "╗"
        box_bottom_left = "╚"
        box_bottom_right = "╝"
        box_horiz = "═"
        box_vert = "║"

    width = 62  # Inner content width (total box width 64)

    # Raw lines inside the box
    lines_raw = [
        "",
        "🎬  R E E L   G E N E R A T O R",
        "",
        "AI-Powered Short-Form Video Creator",
        "─────────────────────────────────────" if not use_fallback else "-------------------------------------",
        "✦ Multi-Language NLLB Translation",
        "✦ Supertonic & Neural Voice Synthesis",
        "✦ Professional Oggy Chroma Key Overlay",
        "✦ Cinematic Video Composition",
        "✦ Word-by-Word Karaoke Subtitles",
        ""
    ]

    # Process replacements for emojis and symbols in fallback mode
    lines_processed = []
    for line in lines_raw:
        if use_fallback:
            line = line.replace("🎬", "[REEL]")
            line = line.replace("✦", "*")
        lines_processed.append(line)

    def get_char_width(c):
        o = ord(c)
        # Wide and Fullwidth characters occupy 2 cells
        if unicodedata.east_asian_width(c) in ('W', 'F'):
            return 2
        # Emojis block
        if (0x1F300 <= o <= 0x1F9FF) or (0x1F600 <= o <= 0x1F64F) or (0x1F680 <= o <= 0x1F6FF):
            return 2
        return 1

    def get_str_width(s):
        return sum(get_char_width(c) for c in s)

    # Construct the banner box
    banner_lines = []
    
    # Top Border
    banner_lines.append(box_top_left + box_horiz * width + box_top_right)
    
    # Body Lines
    for line in lines_processed:
        if not line:
            padded = " " * width
        else:
            # Add standard 3 spaces indentation
            content = "   " + line
            current_width = get_str_width(content)
            needed_padding = width - current_width
            if needed_padding > 0:
                padded = content + " " * needed_padding
            else:
                padded = content
        banner_lines.append(box_vert + padded + box_vert)
        
    # Bottom Border
    banner_lines.append(box_bottom_left + box_horiz * width + box_bottom_right)
    
    banner = "\n" + "\n".join(banner_lines) + "\n"
    
    if HAS_RICH:
        console.print(banner, style="bold cyan")
    else:
        print(banner)


def print_section(title: str):
    """Print a section header."""
    line = "─" * 60
    print(f"\n{line}")
    print(f"  {title}")
    print(f"{line}")


def print_success(msg: str):
    """Print a success message."""
    if HAS_RICH:
        console.print(f"  [bold green]✓[/bold green] {msg}")
    else:
        print(f"  ✓ {msg}")


def print_info(msg: str):
    """Print an info message."""
    if HAS_RICH:
        console.print(f"  [bold blue]ℹ[/bold blue] {msg}")
    else:
        print(f"  ℹ {msg}")


def print_error(msg: str):
    """Print an error message."""
    if HAS_RICH:
        console.print(f"  [bold red]✗[/bold red] {msg}")
    else:
        print(f"  ✗ {msg}")


def print_warning(msg: str):
    """Print a warning message."""
    if HAS_RICH:
        console.print(f"  [bold yellow]⚠[/bold yellow] {msg}")
    else:
        print(f"  ⚠ {msg}")


# ============================================================================
# USER INPUT
# ============================================================================

CONTENT_TYPES = ["educational", "technology", "funny", "professional"]
AUDIENCES = ["common", "engineers", "kids"]
ANIMATION_STYLES = [
    ("ken_burns", "Ken Burns - Slow zoom & pan (documentary)"),
    ("fade_scale", "Fade & Scale - Smooth fade with subtle scale"),
    ("slide_pop", "Slide & Pop - Images slide from sides"),
    ("cinematic", "Cinematic - Letterbox + dramatic zoom + vignette"),
    ("minimal_clean", "Minimal Clean - Simple crossfade (professional)"),
    ("none", "None - Static image (no animation)"),
    ("random_mix", "Random Mix - Random combination each image"),
]
SUBTITLE_STYLES = [
    ("fade_up", "Fade Up - Subtitle fades in from below"),
    ("pop_in", "Pop In - Subtitle pops in with scale"),
    ("slide_left", "Slide Left - Subtitle slides from left"),
    ("typewriter", "Typewriter - Letters appear one by one"),
]


def get_choice(prompt: str, options: list, allow_default: int = None) -> int:
    """Get a numbered choice from user."""
    for i, opt in enumerate(options, 1):
        if isinstance(opt, tuple):
            print(f"    [{i}] {opt[1]}")
        else:
            print(f"    [{i}] {opt}")
    
    while True:
        try:
            default_hint = f" (default: {allow_default})" if allow_default else ""
            raw = input(f"\n  {prompt}{default_hint}: ").strip()
            
            if not raw and allow_default:
                return allow_default
            
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
            print(f"  Please enter 1-{len(options)}")
        except ValueError:
            print("  Please enter a number")
        except EOFError:
            sys.exit(0)


def get_text(prompt: str, default: str = "") -> str:
    """Get text input from user."""
    while True:
        try:
            default_hint = f" (default: {default})" if default else ""
            raw = input(f"  {prompt}{default_hint}: ").strip()
            if not raw and default:
                return default
            if raw:
                return raw
            print("  This field is required")
        except EOFError:
            sys.exit(0)


def get_number(prompt: str, default: int = None, min_val: int = 1, max_val: int = 9999) -> int:
    """Get a number from user."""
    while True:
        try:
            default_hint = f" (default: {default})" if default else ""
            raw = input(f"  {prompt}{default_hint}: ").strip()
            
            if not raw and default:
                return default
            
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"  Enter a number between {min_val}-{max_val}")
        except ValueError:
            print("  Please enter a number")
        except EOFError:
            sys.exit(0)


def get_multiline_text(prompt: str) -> str:
    """Get multi-line text input from user."""
    print(f"\n  {prompt}")
    print("  (Paste your text below. Type 'DONE' on a new blank line and press Enter to finish.)")
    print("  " + "─"*50)
    lines = []
    while True:
        try:
            line = input("  | ")
            if line.strip().upper() == "DONE":
                break
            lines.append(line)
        except EOFError:
            sys.exit(0)
    print("  " + "─"*50)
    
    text = "\n".join(lines).strip()
    if not text:
        print("  This field cannot be empty. Please try again.")
        return get_multiline_text(prompt)
    return text


def get_overlay_choice() -> Optional[str]:
    """Interactive menu for selecting green screen overlay."""
    print_section("🟢 GREEN SCREEN OVERLAY SELECTION")
    options = [
        ("oggy green screen video1.mp4", "Video 1 (Widescreen Professor variant 1)"),
        ("oggy green screen video2.mp4", "Video 2 (Widescreen Professor variant 2)"),
        ("cat.mp4", "Cat Overlay"),
        ("oggy horizontal.mp4", "Oggy Horizontal Overlay"),
        ("None", "No overlay"),
    ]
    choice = get_choice("Select an Oggy Green Screen Video Asset (1-5)", options, allow_default=1)
    
    if choice == 5:
        return None
    
    selected_file = options[choice - 1][0]
    return str(PROJECT_ROOT / "assets" / "green_screen" / selected_file)


# ============================================================================
# CORE PIPELINE LOGIC
# ============================================================================

def setup_voice_and_language(config: dict, is_series: bool = False):    options = [
        "Kokoro TTS (Premium Educational & International)",
        "Supertonic (English and other international languages)",
        "Indic TTS (Local Indian languages - CPU Optimized)"
    ]
    
    engine_idx = get_choice("Select TTS Engine (1-3)", options, allow_default=1)
    
    speaker_id = 0
    selected_lang_code = "en"
    script_source = "auto"
    
    # Initialize dictionary structures if missing
    if "voice" not in config:
        config["voice"] = {}
    if "english" not in config["voice"]:
        config["voice"]["english"] = {}
    if "telugu" not in config["voice"]:
        config["voice"]["telugu"] = {}
    if "indic" not in config["voice"]:
        config["voice"]["indic"] = {}
        
    if engine_idx == 1:
        # Kokoro TTS Setup
        config["voice"]["language"] = "en"
        config["voice"]["english"]["engine"] = "kokoro"
        config["voice"]["telugu"]["engine"] = "kokoro"
        
        # STEP A: Voice Selection
        print("\n  [KOKORO TTS CONFIGURATION]")
        print("  STEP A: Voice Selection")
        kokoro_voices = [
            ("am_adam", "Adam - Documentary Voice (Male, US)"),
            ("am_michael", "Michael - Casual Male (Male, US)"),
            ("bm_george", "George - British History (Male, UK)"),
            ("am_fenrir", "Fenrir - Deep Voice (Male, US)"),
            ("am_puck", "Puck - Energetic Male (Male, US)"),
            ("af_heart", "Heart - Default Educational (Female, US)"),
            ("af_sarah", "Sarah - Science Narrator (Female, US)"),
            ("af_bella", "Bella - Energetic Presenter (Female, US)"),
        ]
        voice_choice = get_choice("Select a Kokoro voice", kokoro_voices, allow_default=1)
        kokoro_voice_id = kokoro_voices[voice_choice - 1][0]
        
        # STEP B: Language Selection
        print("\n  STEP B: Language Selection")
        # Indic regional languages blocked from Kokoro
        KOKORO_BLOCKED_INDIC = {'te', 'ta', 'kn', 'ml', 'bn', 'mr', 'gu'}
        kokoro_langs = [
            ("en-us", "a", "English (US)"),
            ("en-gb", "b", "English (UK)"),
            ("es", "e", "Spanish"),
            ("fr", "f", "French"),
            ("it", "i", "Italian"),
            ("ja", "j", "Japanese"),
            ("zh", "z", "Chinese (Mandarin)"),
            ("pt-br", "p", "Portuguese (Brazil)"),
            ("hi", "h", "Hindi"),
        ]
        for i, (code, _, name) in enumerate(kokoro_langs, 1):
            print(f"    [{i}] {name} ({code})")
        
        while True:
            try:
                raw = input("\n  Select language (default: 1): ").strip()
                if not raw:
                    lang_idx = 0
                    break
                lang_idx = int(raw) - 1
                if 0 <= lang_idx < len(kokoro_langs):
                    break
                print(f"  Please enter 1-{len(kokoro_langs)}")
            except ValueError:
                print("  Please enter a number")
            except EOFError:
                sys.exit(0)
        
        kokoro_lang_code_display, kokoro_pipeline_code, kokoro_lang_name = kokoro_langs[lang_idx]
        
        # Map display code to 2-letter translation code for NLLB
        KOKORO_LANG_TO_TRANSLATION = {
            "en-us": "en", "en-gb": "en", "es": "es", "fr": "fr",
            "it": "it", "ja": "ja", "zh": "zh", "pt-br": "pt", "hi": "hi",
        }
        selected_lang_code = KOKORO_LANG_TO_TRANSLATION.get(kokoro_lang_code_display, "en")
        
        # Adjust voice prefix if non-English language selected
        # Japanese voices start with 'j', Chinese with 'z', etc.
        KOKORO_LANG_DEFAULT_VOICES = {
            'j': 'jf_alpha',   # Japanese
            'z': 'zf_xiaobei', # Chinese
            'e': 'ef_dora',    # Spanish
            'f': 'ff_siwis',   # French
            'i': 'if_sara',    # Italian
            'p': 'pf_dora',    # Portuguese
            'h': 'hf_alpha',   # Hindi
        }
        if kokoro_pipeline_code not in ('a', 'b'):
            # Override voice to a native-language voice for non-English
            kokoro_voice_id = KOKORO_LANG_DEFAULT_VOICES.get(kokoro_pipeline_code, kokoro_voice_id)
            print(f"  ℹ Using native {kokoro_lang_name} voice: {kokoro_voice_id}")
        
        # Store Kokoro config
        if "kokoro" not in config["voice"]:
            config["voice"]["kokoro"] = {}
        config["voice"]["kokoro"]["voice_id"] = kokoro_voice_id
        config["voice"]["kokoro"]["lang_code"] = kokoro_pipeline_code
        config["voice"]["kokoro"]["speed"] = 1.0
        config["voice"]["language"] = selected_lang_code
        
        print(f"  ✓ Kokoro TTS: Voice={kokoro_voice_id}, Lang={kokoro_lang_name}, Pipeline={kokoro_pipeline_code}")
        
        speaker_id = 0
 
    elif engine_idx == 2:
        # Supertonic Detailed Setup
        config["voice"]["language"] = "en"
        config["voice"]["english"]["engine"] = "supertonic"
        config["voice"]["telugu"]["engine"] = "supertonic"
        
        print("\n  [SUPERTONIC CONFIGURATION]")
        print("  STEP A: Voice Identity Selection")
        supertonic_voices = [
            ("M1.json", "Male Style 1 (Default Professional)"),
            ("M2.json", "Male Style 2 (Deep/Energetic)"),
            ("M3.json", "Male Style 3 (Casual Narrator)"),
            ("M4.json", "Male Style 4 (Smooth/Warm)"),
            ("M5.json", "Male Style 5 (Alternative)"),
            ("F1.json", "Female Style 1 (Clear Professional)"),
            ("F2.json", "Female Style 2 (Casual/Friendly)"),
            ("F3.json", "Female Style 3 (Soft Narrator)"),
            ("F4.json", "Female Style 4 (Bright/Upbeat)"),
            ("F5.json", "Female Style 5 (Alternative)"),
        ]
        voice_choice = get_choice("Select a voice", supertonic_voices, allow_default=1)
        config["voice"]["english"]["supertonic_voice"] = supertonic_voices[voice_choice - 1][0]
        
        print("\n  STEP B: Vibe/Emotion Characteristics")
        supertonic_vibes = [
            ("professional", "Professional / Corporate"),
            ("funny_comedic", "Funny / Comedic"),
            ("dramatic", "Dramatic / Storytelling"),
            ("sarcastic", "Sarcastic / Low Energy"),
            ("neutral", "Standard / Flat")
        ]
        vibe_choice = get_choice("Select a vibe", supertonic_vibes, allow_default=1)
        config["voice"]["english"]["supertonic_vibe"] = supertonic_vibes[vibe_choice - 1][0]
        
        print("\n  STEP C: Supertonic Language Selection")
        supertonic_langs = [
            "en", "hi", "ko", "ja", "ar", "bg", "cs", "da", "de", "el", "es", "et", "fi", "fr", 
            "hr", "hu", "id", "it", "lt", "lv", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi"
        ]
        print("  Available languages: " + ", ".join(supertonic_langs))
        while True:
            lang_choice = input("  Select a language code (default: en): ").strip().lower()
            if not lang_choice:
                config["voice"]["english"]["supertonic_lang"] = "en"
                selected_lang_code = "en"
                break
            if lang_choice in supertonic_langs:
                config["voice"]["english"]["supertonic_lang"] = lang_choice
                selected_lang_code = lang_choice
                break
            print("  Invalid language code. Please try again.")
 
    elif engine_idx == 3:
        # Indic TTS Setup
        # STEP A: Language Selection
        print("\n  STEP A: Language Selection")
        indic_langs_map = {
            "Telugu": "te",
            "Hindi": "hi",
            "English": "en",
            "Bengali": "bn",
            "Kannada": "kn",
            "Tamil": "ta"
        }
        indic_langs_options = list(indic_langs_map.keys())
        lang_choice = get_choice("Select language (1-6)", indic_langs_options, allow_default=1)
        selected_lang_name = indic_langs_options[lang_choice - 1]
        selected_lang_code = indic_langs_map[selected_lang_name]
        
        # STEP B: Speaker Selection
        print(f"\n  STEP B: Speaker Selection FOR {selected_lang_name.upper()}")
        supported_speakers = {
            'Telugu': ['Prakash', 'Lalitha'],
            'Hindi': ['Rohit', 'Divya'],
            'English': ['Thoma', 'Mary'],
            'Bengali': ['Arjun', 'Aditi'],
            'Kannada': ['Suresh', 'Anu'],
            'Tamil': ['Jaya']
        }
        speakers_options = supported_speakers[selected_lang_name]
        speaker_choice = get_choice("Select speaker", speakers_options, allow_default=1)
        selected_speaker = speakers_options[speaker_choice - 1]
        
        # STEP C: Vibe Profile Selection
        print("\n  STEP C: Vibe Profile Selection")
        vibe_options = [
            ("1", "Professional Lecturer"),
            ("2", "Energetic/Expressive"),
            ("3", "Calm Narrator")
        ]
        vibe_choice = get_choice("Select vibe (1-3)", vibe_options, allow_default=1)
        selected_vibe = vibe_options[vibe_choice - 1][0]
        
        # Populate config
        config["voice"]["language"] = selected_lang_code
        config["voice"]["engine"] = "indic"
        config["voice"]["telugu"]["engine"] = "indic"
        config["voice"]["english"]["engine"] = "indic"
        config["voice"]["indic"] = {
            "language": selected_lang_name,
            "lang_code": selected_lang_code,
            "speaker": selected_speaker,
            "vibe": selected_vibe,
            "engine": "indic"
        }
        
        speaker_id = 0

    # Determine script source (Auto/Manual)
    script_source = "auto"
    if selected_lang_code != "en":
        print_section(f"🌐 TRANSLATION CONFIGURATION: [{selected_lang_code.upper()}]")
        print(f"  Target language: {selected_lang_code}")
        source_idx = get_choice("Select script source", [
            "Auto-Generate English & Translate (NLLB-200)",
            "Provide Manual Custom Text (Highest Quality)"
        ], allow_default=1)
        if source_idx == 2:
            script_source = "manual"

    return selected_lang_code, script_source, speaker_id


def process_translation_layer(script_text: str, selected_lang_code: str, script_source: str, config: dict, topic: str):
    """Handles the translation or manual input of the script."""
    from src.translation import translate_text as nllb_translate, TranslationEngineOffline
    import re
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic_file = sanitize_filename(topic)
    script_dir = PROJECT_ROOT / "outputs/script"        # English originals
    trans_dir  = PROJECT_ROOT / "outputs/translation"   # NLLB / manual translations
    
    # Save original English script to outputs/script/
    script_dir.joinpath(f"{safe_topic_file}_{timestamp_str}_original.txt").write_text(script_text, encoding='utf-8')
    
    if script_source == "manual":
        print_info(f"Step 1.5: Waiting for manual {selected_lang_code.upper()} text...")
        voice_text = get_multiline_text(f"{selected_lang_code.upper()} Script")
        print_success("Manual script received!")
        # Save manual translation to outputs/translation/
        trans_dir.joinpath(f"{safe_topic_file}_{timestamp_str}_manual_{selected_lang_code}.txt").write_text(voice_text, encoding='utf-8')
        return voice_text
        
    elif selected_lang_code != "en":
        print_info(f"Step 1.5: Translating script to {selected_lang_code.upper()} via NLLB-200...")
        # Run pipeline sanity check lazily
        from src.translation import run_pipeline_sanity_check
        run_pipeline_sanity_check(config)
        try:
            sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
            translated_sentences = []
            for sent in sentences:
                if sent.strip():
                     trans = nllb_translate(sent, selected_lang_code, config)
                     translated_sentences.append(trans)
            voice_text = " ".join(translated_sentences)
            print_success("Translation completed!")
            # Save NLLB translation to outputs/translation/
            trans_dir.joinpath(f"{safe_topic_file}_{timestamp_str}_translated_{selected_lang_code}.txt").write_text(voice_text, encoding='utf-8')
            return voice_text
            
        except TranslationEngineOffline:
            print_warning("Local NLLB Engine offline. Forcing manual text entry mode.")
            voice_text = get_multiline_text(f"{selected_lang_code.upper()} Script (Local Engine Offline Fallback)")
            # Save manual fallback to outputs/translation/
            trans_dir.joinpath(f"{safe_topic_file}_{timestamp_str}_manual_fallback_{selected_lang_code}.txt").write_text(voice_text, encoding='utf-8')
            return voice_text
        except Exception as e:
            print_error(f"Translation failed: {e}")
            return None
    else:
        return script_text


# ============================================================================
# SINGLE VIDEO PIPELINE
# ============================================================================

def generate_single_video(config: dict, cli_args: Optional[argparse.Namespace] = None) -> Optional[str]:
    """Full pipeline for generating a single reel video."""
    from src.script_engine import generate_script
    from src.tts import synthesize_speech, get_audio_duration, split_text_to_sentences, estimate_sentence_timings
    from src.image_engine import extract_search_queries, scrape_images_for_video
    from src.video_engine import compose_video
    
    # ── Non-Interactive CLI Mode ──
    if cli_args and getattr(cli_args, "topic", None):
        topic = cli_args.topic
        content_type = getattr(cli_args, "content_type", None) or "educational"
        duration = getattr(cli_args, "duration", None) or 60
        audience = getattr(cli_args, "audience", None) or "common"
        animation_style = getattr(cli_args, "animation_style", None) or "none"
        subtitle_style = getattr(cli_args, "subtitle_style", None) or "fade_up"
        config.setdefault("subtitles", {})["entrance_animation"] = subtitle_style
        
        # Voice & Language Setup
        tts_engine = getattr(cli_args, "tts", None) or "kokoro"
        selected_lang_code = getattr(cli_args, "language", None) or "en"
        script_source = "auto"
        speaker_id = 0
        
        config.setdefault("voice", {})
        config["voice"]["language"] = selected_lang_code
        if tts_engine == "kokoro":
            config["voice"].setdefault("english", {})["engine"] = "kokoro"
            config["voice"].setdefault("telugu", {})["engine"] = "kokoro"
            voice_id = getattr(cli_args, "voice_id", None) or "am_adam"
            config["voice"].setdefault("kokoro", {})["voice_id"] = voice_id
            config["voice"]["kokoro"]["lang_code"] = "a"
        elif tts_engine == "supertonic":
            config["voice"].setdefault("english", {})["engine"] = "supertonic"
            config["voice"].setdefault("telugu", {})["engine"] = "supertonic"
            config["voice"].setdefault("supertonic", {})["voice"] = getattr(cli_args, "voice_id", None) or "M1.json"
        elif tts_engine == "indic":
            config["voice"].setdefault("english", {})["engine"] = "indic"
            config["voice"].setdefault("telugu", {})["engine"] = "indic"
            config["voice"].setdefault("indic", {})["engine"] = "indic"
            
        # Overlay Resolution
        raw_overlay = getattr(cli_args, "overlay", "4")
        overlay_map = {
            "1": "oggy green screen video1.mp4",
            "2": "oggy green screen video2.mp4",
            "3": "cat.mp4",
            "4": "oggy horizontal.mp4",
            "5": None,
            "none": None,
            "None": None,
        }
        if str(raw_overlay) in overlay_map:
            selected_file = overlay_map[str(raw_overlay)]
            overlay_path = str(PROJECT_ROOT / "assets" / "green_screen" / selected_file) if selected_file else None
        elif raw_overlay and os.path.exists(str(raw_overlay)):
            overlay_path = str(raw_overlay)
        elif raw_overlay and (PROJECT_ROOT / "assets" / "green_screen" / str(raw_overlay)).exists():
            overlay_path = str(PROJECT_ROOT / "assets" / "green_screen" / str(raw_overlay))
        else:
            overlay_path = str(PROJECT_ROOT / "assets" / "green_screen" / "oggy horizontal.mp4")
            
        # Oggy Intro
        raw_intro = getattr(cli_args, "intro", "1")
        use_oggy_intro = str(raw_intro).strip().lower() in ("1", "true", "yes")
        config["use_oggy_intro"] = use_oggy_intro

        # Visual Media Mode
        raw_visuals = getattr(cli_args, "visuals", None)
        if raw_visuals:
            config.setdefault("video", {})["visual_mode"] = raw_visuals
            config.setdefault("broll", {})["enabled"] = (raw_visuals == "hybrid")
        else:
            visual_mode = config.get("video", {}).get("visual_mode", "hybrid")
            config.setdefault("broll", {})["enabled"] = (visual_mode == "hybrid")
    else:
        # ── Interactive CLI Mode ──
        print_section("📝 SINGLE VIDEO SETUP")
        
        topic = get_text("Enter topic")

        # ── Script Generation Engine Selection ──
        if cli_args and getattr(cli_args, "llm", None):
            llm_mode = cli_args.llm
            config.setdefault("script", {})["llm_mode"] = llm_mode
        else:
            print("\n  Script Generation Engine:")
            llm_choices = [
                "Cloud API (Fast Reasoning via Google Gemini)",
                "Local Model (GGUF via llama-cpp-python)"
            ]
            llm_idx = get_choice("Select LLM mode", llm_choices, allow_default=1)
            llm_mode = "api" if llm_idx == 1 else "local"
            config.setdefault("script", {})["llm_mode"] = llm_mode
            if llm_mode == "api":
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or config.get("script", {}).get("api", {}).get("api_key", "")
                if not api_key:
                    print_error("[FATAL] Cloud API selected but no API key found in .env (GEMINI_API_KEY) or config.yaml")
                    print("    Set GEMINI_API_KEY in .env or paste into config.yaml → script.api.api_key and retry.")
                    sys.exit(1)
                model_name = config.get("script", {}).get("api", {}).get("model_name", "gemini-3.5-flash-lite")
                print_success(f"Google Gemini API configured → {model_name}")
            else:
                print_info("Local Model (GGUF via llama-cpp-python) selected")
        
        print("\n  Content Type:")
        ct_idx = get_choice("Select content type", CONTENT_TYPES, allow_default=1)
        content_type = CONTENT_TYPES[ct_idx - 1]
        
        duration = get_number("Approximate video length (seconds)", default=60, min_val=15, max_val=300)
        
        print("\n  Target Audience:")
        aud_idx = get_choice("Select audience", AUDIENCES, allow_default=1)
        audience = AUDIENCES[aud_idx - 1]
        
        print("\n  Animation Style:")
        anim_idx = get_choice("Select animation", ANIMATION_STYLES, allow_default=6)
        animation_style = ANIMATION_STYLES[anim_idx - 1][0]
        
        print("\n  Subtitle Style:")
        sub_idx = get_choice("Select subtitle style", SUBTITLE_STYLES, allow_default=1)
        subtitle_style = SUBTITLE_STYLES[sub_idx - 1][0]
        config["subtitles"]["entrance_animation"] = subtitle_style
        
        # NEW: Voice and Language Setup
        selected_lang_code, script_source, speaker_id = setup_voice_and_language(config)
        
        # Reject instantly if language is not supported
        from src.translation import VALID_LANGS
        if selected_lang_code not in ['en', 'te'] and selected_lang_code not in VALID_LANGS:
            print_error(f"Language code '{selected_lang_code}' is not supported.")
            sys.exit(1)
        
        # NEW: Interactive Overlay Selection
        overlay_path = get_overlay_choice()
        
        print("\n  OGGY INTRO:")
        intro_choices = ["ADD THE INTRO", "NO INTRO"]
        intro_idx = get_choice("Select intro option", intro_choices, allow_default=2)
        use_oggy_intro = (intro_idx == 1)
        config["use_oggy_intro"] = use_oggy_intro

        # Visual Media Mode Selection
        raw_visuals = getattr(cli_args, "visuals", None) if cli_args else None
        if raw_visuals:
            config.setdefault("video", {})["visual_mode"] = raw_visuals
            config.setdefault("broll", {})["enabled"] = (raw_visuals == "hybrid")
        else:
            print("\n  Visual Media Mode:")
            visual_choices = [
                "Videos + Images (Hybrid B-Roll + Technical Diagrams)",
                "Only Images (100% Static Technical Diagrams)"
            ]
            visual_idx = get_choice("Select visual mode", visual_choices, allow_default=1)
            visual_mode = "hybrid" if visual_idx == 1 else "images"
            config.setdefault("video", {})["visual_mode"] = visual_mode
            config.setdefault("broll", {})["enabled"] = (visual_mode == "hybrid")
    
    print_section("🚀 GENERATING REEL")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = sanitize_filename(topic)
    
    output_dir = PROJECT_ROOT / "outputs/videos"
    tts_dir = PROJECT_ROOT / "outputs/audio"
    persistent_images_dir = PROJECT_ROOT / "outputs/images"
    
    temp_dir = tts_dir / timestamp
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # ── STEP 1: Generate English Script ──
    print_info("Step 1/5: Generating English base script (for images & subtitles)...")
    script_text = generate_script(
        topic=topic,
        content_type=content_type,
        duration=duration,
        audience=audience,
        language="en", 
        config=config,
    )
    
    if not script_text:
        print_error("Script generation failed!")
        return None
    
    print_success(f"English script generated: {len(script_text.split())} words")
    
    # ── STEP 1.5: Prepare Voice Text ──
    voice_text = process_translation_layer(script_text, selected_lang_code, script_source, config, topic)
    if not voice_text: return None
    
    # ── STEP 2: Generate Voice ──
    print_info("Step 2/5: Synthesizing voiceover...")
    target_language = config["voice"]["language"]
    lang_key = "english" if target_language == "en" else "telugu"
    engine_name = config.get("voice", {}).get(lang_key, {}).get("engine", "unknown")
    
    # Save audio with descriptive name to persistent outputs/audio/
    audio_filename = f"{safe_topic}_{selected_lang_code}_{engine_name}_{timestamp}.wav"
    audio_path = str(tts_dir / audio_filename)
    result = synthesize_speech(text=voice_text, output_path=audio_path, speaker_id=speaker_id, config=config)
    if not result:
        print_error("Voice synthesis failed!")
        return None
    
    audio_duration = get_audio_duration(audio_path)
    print_success(f"Audio generated: {audio_duration:.1f} seconds → {audio_path}")
    
    # ── STEP 3: Parse sentences & extract keywords ──
    print_info("Step 3/5: Analyzing script & extracting keywords...")
    sentences = split_text_to_sentences(script_text)
    timings = estimate_sentence_timings(sentences, audio_duration)
    search_queries = extract_search_queries(timings, topic=topic, config=config)
    
    total_queries = sum(len(sq["queries"]) for sq in search_queries)
    print_success(f"Found {len(sentences)} sentences, {total_queries} search queries")
    
    # ── STEP 4: Scrape Images ──
    print_info("Step 4/5: Scraping images...")
    images_dir = str(persistent_images_dir / f"{safe_topic}_{timestamp}")
    target_images = max(1, int(audio_duration / 4))
    image_map = scrape_images_for_video(search_queries=search_queries, output_dir=images_dir, config=config, target_images=target_images)
    total_images = len([img for img in image_map.values() if img])
    downloaded_slots = 0
    fallback_slots = 0
    for path in image_map.values():
        if path:
            if "assets/icons" in path.replace("\\", "/") or "assets/templates" in path.replace("\\", "/"):
                fallback_slots += 1
            else:
                downloaded_slots += 1
    print_success(f"Saved {total_images} images ({downloaded_slots} downloaded, {fallback_slots} local fallbacks) → {images_dir}")
    
    # ── STEP 5: Compose Video ──
    print_info("Step 5/5: Composing video...")
    output_filename = f"{safe_topic}_{selected_lang_code}_{engine_name}_{timestamp}.mp4"
    output_path = str(output_dir / output_filename)
    
    video_path = compose_video(
        script_text=script_text,
        audio_path=audio_path,
        sentence_timings=timings,
        image_map=image_map,
        output_path=output_path,
        config=config,
        animation_style=animation_style,
        language=target_language,
        overlay_path=overlay_path,
        topic=topic,
    )
    
    # Temp dir cleanup (audio + images are now saved to persistent locations)
    if not config.get("output", {}).get("keep_temp_files", False):
        shutil.rmtree(str(temp_dir), ignore_errors=True)
    
    return video_path


# ============================================================================
# SERIES PIPELINE
# ============================================================================

def generate_series(config: dict, cli_args: Optional[argparse.Namespace] = None) -> List[str]:
    """Full pipeline for generating a video series."""
    from src.script_engine import generate_series_scripts
    from src.tts import synthesize_speech, get_audio_duration, split_text_to_sentences, estimate_sentence_timings
    from src.image_engine import extract_search_queries, scrape_images_for_video
    from src.video_engine import compose_video
    
    print_section("📺 VIDEO SERIES SETUP")
    
    topic = get_text("Enter series topic")

    # ── Script Generation Engine Selection ──
    if cli_args and getattr(cli_args, "llm", None):
        llm_mode = cli_args.llm
        config.setdefault("script", {})["llm_mode"] = llm_mode
    else:
        print("\n  Script Generation Engine:")
        llm_choices = [
            "Cloud API (Fast Reasoning via Google Gemini)",
            "Local Model (GGUF via llama-cpp-python)"
        ]
        llm_idx = get_choice("Select LLM mode", llm_choices, allow_default=1)
        llm_mode = "api" if llm_idx == 1 else "local"
        config.setdefault("script", {})["llm_mode"] = llm_mode
        if llm_mode == "api":
            api_key = os.environ.get("GEMINI_API_KEY") or config.get("script", {}).get("api", {}).get("api_key", "")
            if not api_key:
                print_error("[FATAL] Cloud API selected but no API key found in .env (GEMINI_API_KEY) or config.yaml")
                print("    Set GEMINI_API_KEY in .env or paste into config.yaml → script.api.api_key and retry.")
                sys.exit(1)
            model_name = config.get("script", {}).get("api", {}).get("model_name", "gemini-3.5-flash-lite")
            print_success(f"Google Gemini API configured → {model_name}")
        else:
            print_info("Local Model (GGUF via llama-cpp-python) selected")

    num_videos = get_number("Number of videos in series", default=3, min_val=2, max_val=20)
    duration_each = get_number("Duration per video (seconds)", default=60, min_val=15, max_val=300)
    
    print("\n  Content Type:")
    ct_idx = get_choice("Select content type", CONTENT_TYPES, allow_default=1)
    content_type = CONTENT_TYPES[ct_idx - 1]
    
    print("\n  Target Audience:")
    aud_idx = get_choice("Select audience", AUDIENCES, allow_default=1)
    audience = AUDIENCES[aud_idx - 1]
    
    print("\n  Animation Style:")
    anim_idx = get_choice("Select animation", ANIMATION_STYLES, allow_default=6)
    animation_style = ANIMATION_STYLES[anim_idx - 1][0]
    
    print("\n  Subtitle Style:")
    sub_idx = get_choice("Select subtitle style", SUBTITLE_STYLES, allow_default=1)
    subtitle_style = SUBTITLE_STYLES[sub_idx - 1][0]
    config["subtitles"]["entrance_animation"] = subtitle_style
    
    # NEW: Voice and Language Setup
    selected_lang_code, script_source, speaker_id = setup_voice_and_language(config, is_series=True)
    
    # Reject instantly if language is not supported
    from src.translation import VALID_LANGS
    if selected_lang_code not in ['en', 'te'] and selected_lang_code not in VALID_LANGS:
        print_error(f"Language code '{selected_lang_code}' is not supported.")
        sys.exit(1)
    
    # NEW: Interactive Overlay Selection
    overlay_path = get_overlay_choice()
    
    print("\n  OGGY INTRO:")
    intro_choices = ["ADD THE INTRO", "NO INTRO"]
    intro_idx = get_choice("Select intro option", intro_choices, allow_default=2)
    use_oggy_intro = (intro_idx == 1)
    config["use_oggy_intro"] = use_oggy_intro

    # Visual Media Mode Selection
    print("\n  Visual Media Mode:")
    visual_choices = [
        "Videos + Images (Hybrid B-Roll + Technical Diagrams)",
        "Only Images (100% Static Technical Diagrams)"
    ]
    visual_idx = get_choice("Select visual mode", visual_choices, allow_default=1)
    visual_mode = "hybrid" if visual_idx == 1 else "images"
    config.setdefault("video", {})["visual_mode"] = visual_mode
    config.setdefault("broll", {})["enabled"] = (visual_mode == "hybrid")
    
    print_section("🚀 GENERATING VIDEO SERIES")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = sanitize_filename(topic)
    output_dir = PROJECT_ROOT / "outputs/videos"
    tts_dir = PROJECT_ROOT / "outputs/audio"
    persistent_images_dir = PROJECT_ROOT / "outputs/images"
    
    scripts = generate_series_scripts(
        topic=topic,
        num_videos=num_videos,
        duration_per_video=duration_each,
        content_type=content_type,
        audience=audience,
        language="en", 
        config=config,
    )
    
    completed_videos = []
    for ep_idx, (ep_title, ep_script) in enumerate(scripts):
        ep_num = ep_idx + 1
        print_section(f"🎬 Episode {ep_num}/{num_videos}: {ep_title}")
        
        safe_ep_title = sanitize_filename(ep_title)
        temp_dir = tts_dir / f"{timestamp}_ep{ep_num:02d}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        target_language = config["voice"]["language"]
        lang_key = "english" if target_language == "en" else "telugu"
        engine_name = config.get("voice", {}).get(lang_key, {}).get("engine", "unknown")
        
        # ── STEP 1.5: Prepare Voice Text ──
        voice_text = process_translation_layer(ep_script, selected_lang_code, script_source, config, ep_title)
        if not voice_text: continue
        
        # ── STEP 2: Generate Voice ──
        # Save audio with descriptive name to persistent outputs/audio/
        audio_filename = f"{safe_ep_title}_EP{ep_num:02d}_{selected_lang_code}_{engine_name}_{timestamp}.wav"
        audio_path = str(tts_dir / audio_filename)
        synthesize_speech(text=voice_text, output_path=audio_path, speaker_id=speaker_id, config=config)
        audio_duration = get_audio_duration(audio_path)
        
        # ── STEP 3: Analysis ──
        sentences = split_text_to_sentences(ep_script)
        timings = estimate_sentence_timings(sentences, audio_duration)
        search_queries = extract_search_queries(timings, topic=ep_title, config=config)
        
        # ── STEP 4: Scrape ──
        images_dir = str(persistent_images_dir / f"{safe_ep_title}_EP{ep_num:02d}_{timestamp}")
        target_images = max(1, int(audio_duration / 4))
        image_map = scrape_images_for_video(search_queries=search_queries, output_dir=images_dir, config=config, target_images=target_images)
        
        # ── STEP 5: Compose ──
        output_filename = f"{safe_topic}_EP{ep_num:02d}_{selected_lang_code}_{engine_name}_{timestamp}.mp4"
        output_path = str(output_dir / output_filename)
        
        ep_style = animation_style
        if animation_style == "random_mix":
            ep_style = random.choice([s[0] for s in ANIMATION_STYLES if s[0] != "random_mix"])
            
        video_path = compose_video(
            script_text=ep_script,
            audio_path=audio_path,
            sentence_timings=timings,
            image_map=image_map,
            output_path=output_path,
            config=config,
            animation_style=ep_style,
            language=target_language,
            overlay_path=overlay_path,
            topic=ep_title,
        )
        
        if video_path:
            completed_videos.append(video_path)
            print_success(f"Episode {ep_num} saved: {video_path}")
            
        # Temp dir cleanup (audio + images are now in persistent locations)
        if not config.get("output", {}).get("keep_temp_files", False):
            shutil.rmtree(str(temp_dir), ignore_errors=True)
            
    return completed_videos


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    # ── Parse CLI arguments ──
    parser = argparse.ArgumentParser(
        description="🎬 Reel Generator - AI-Powered Short-Form Video Creator",
        add_help=True,
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Reel topic (runs non-interactively when specified)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Target video duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--content-type",
        type=str,
        default="educational",
        choices=["educational", "technology", "funny", "professional"],
        help="Content type (default: educational)",
    )
    parser.add_argument(
        "--audience",
        type=str,
        default="common",
        choices=["common", "engineers", "kids"],
        help="Target audience (default: common)",
    )
    parser.add_argument(
        "--animation-style",
        type=str,
        default="none",
        help="Animation style (default: none)",
    )
    parser.add_argument(
        "--subtitle-style",
        type=str,
        default="fade_up",
        choices=["fade_up", "pop_in", "slide_left", "typewriter"],
        help="Subtitle entrance style (default: fade_up)",
    )
    parser.add_argument(
        "--tts",
        type=str,
        default="kokoro",
        choices=["kokoro", "supertonic", "indic"],
        help="TTS engine (default: kokoro)",
    )
    parser.add_argument(
        "--voice-id",
        type=str,
        default=None,
        help="TTS voice ID (e.g. am_adam for kokoro, M1.json for supertonic)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Spoken language code (default: en)",
    )
    parser.add_argument(
        "--overlay",
        type=str,
        default="4",
        help="Overlay option: 1-5, filename, or 'none' (default: 4 / oggy horizontal.mp4)",
    )
    parser.add_argument(
        "--intro",
        type=str,
        default="1",
        help="Include Oggy intro: 1/true or 2/0/false (default: 1)",
    )
    parser.add_argument(
        "--llm",
        "--llm-mode",
        dest="llm",
        choices=["api", "local"],
        default=None,
        help="LLM execution mode: 'api' (Cloud API via Google Gemini) or 'local' (Local GGUF model)",
    )
    parser.add_argument(
        "--visuals",
        "--media-mode",
        dest="visuals",
        choices=["images", "hybrid"],
        default=None,
        help="Visual mode: 'images' (only static images) or 'hybrid' (videos + images)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Force non-interactive execution (requires --topic)",
    )
    args = parser.parse_args()

    print_banner()
    config = load_config()

    # ── Override visual_mode from CLI ──
    if args.visuals:
        config.setdefault("video", {})["visual_mode"] = args.visuals
        config.setdefault("broll", {})["enabled"] = (args.visuals == "hybrid")
        print_info(f"Visual media mode overridden via CLI: {args.visuals}")

    # ── Override llm_mode from CLI ──
    if args.llm:
        if "script" not in config:
            config["script"] = {}
        config["script"]["llm_mode"] = args.llm
        print_info(f"LLM mode overridden via CLI: {args.llm}")
        
        # Fail-fast if api mode selected but no API key configured
        if args.llm == "api":
            api_key = os.environ.get("GEMINI_API_KEY") or config.get("script", {}).get("api", {}).get("api_key", "")
            if not api_key:
                print_error("[FATAL] --llm api selected but no API key found in .env (GEMINI_API_KEY) or config.yaml")
                print("    Set GEMINI_API_KEY in .env or paste into config.yaml → script.api.api_key and retry.")
                sys.exit(1)
            model_name = config.get("script", {}).get("api", {}).get("model_name", "gemini-3.5-flash-lite")
            print_success(f"Google Gemini API configured → {model_name}")

    print_success("Configuration loaded")
    
    # ── Non-Interactive Execution Branch ──
    if args.topic or args.non_interactive:
        if not args.topic:
            print_error("[FATAL] --non-interactive mode requires --topic '<topic>'")
            sys.exit(1)
        
        print_section(f"🤖 AUTOMATED NON-INTERACTIVE RUN: {args.topic}")
        result = generate_single_video(config, cli_args=args)
        
        if result and os.path.exists(result) and os.path.getsize(result) > 0:
            print_section("🎉 DONE!")
            print_success(f"[SUCCESS] Reel generated successfully: {result}")
            # Machine-readable output for parent batch scripts & orchestrators:
            print(f"OUTPUT_VIDEO_PATH={result}")
            sys.exit(0)
        else:
            print_error(f"[FATAL] Reel generation failed or output invalid for topic: {args.topic}")
            sys.exit(1)

    # ── Interactive Execution Branch ──
    options = [
        "Single Video - Generate one reel",
        "Video Series - Generate multiple episode reels",
        "Exit",
    ]
    
    choice = get_choice("Select mode", options)
    
    if choice == 1:
        result = generate_single_video(config, cli_args=args)
        if result:
            print_section("🎉 DONE!")
            print_success(f"Your reel is ready: {result}")
    elif choice == 2:
        results = generate_series(config, cli_args=args)
        if results:
            print_section("🎉 SERIES COMPLETE!")
    elif choice == 3:
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n  ✗ Fatal error: {e}")
        sys.exit(1)
