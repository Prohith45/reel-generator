# Reel Generator Project Instructions

This file tracks the setup status and architectural decisions made for this project to ensure continuity across sessions.

## 🚀 Setup Status
- **Environment:** Python 3.12 virtual environment created at `./venv`.
- **Primary LLM Engine:** **GGUF Direct Load** (`llama-cpp-python` with `Phi-3.5-mini-instruct.Q4_K_M.gguf` as primary; Ollama as fallback).
- **NLLB Engine:** Local `facebook/nllb-200-distilled-600M` model used for multi-language translation, accelerated with `torch.bfloat16` on CUDA.
- **Verification:** Full multi-language pipeline, advanced chroma keying, and GGUF duration constraints verified on 2026-06-16.

## 📂 Modular Structure
- **`main.py`**: Refactored orchestrator with unified logic for Single Video and Series.
  - Interactive language configuration with Manual Override support.
  - Exception-guarded NLLB loading with automatic fallback to manual input.
  - Comprehensive Supertonic TTS integration (Voice/Vibe/Language).
- **`src/`**: All processing sub-modules.
  - `translation.py`: New robust multi-language routing for 32+ languages.
  - `tts.py`: Audio generation supporting Sherpa-ONNX, Meta MMS, Sarvam AI, and Supertonic.
  - `video_engine.py`: Professional FFmpeg chroma key pipeline (Hex: `0x04F504`, Similarity: `0.32`, Blend: `0.08`, Despill: `enabled`, Scale: `450px`).
- **`assets/`**: Raw input files.
  - `green_screen/`: Professionally keyed Oggy assets.

## 🛠 Features & Bug Fixes Added
### 1. Professional Chroma Keying
- Upgraded the primitive FFmpeg `chromakey` filter to a high-precision matrix.
- **Settings:** Exact green hex `0x04F504`, similarity `0.32`, blend `0.08`.
- **Despill:** Added `despill=mode=colorkey:color=green` to neutralize reflections on character edges.
- **Dynamic Scaling:** Correctly handles 16:9 and 9:16 overlays with aspect ratio compliance.

### 2. Multi-Language Architecture
- **Routing:** Replaced hardcoded Telugu logic with a 32-language routing dictionary mapping CLI codes to NLLB-200 script tokens.
- **Interactive Layer:** `main.py` now pauses for every non-English language to offer a "Manual Text Override" option.
- **Reliability:** Structural verification checkpoint ensures that if the NLLB engine is offline, the user is immediately prompted for manual input, preventing pipeline crashes.

### 3. Audio Engine Optimization
- Integrated Supertonic as a high-fidelity local TTS option.
- Preserved Sarvam AI (Cloud) and Meta MMS (Local) for Telugu versatility.
- Conditional 1.25x speedup for MMS Telugu to maintain engaging pacing.

### 4. Image Validation and Scraper Pool Upgrades (2026-06-12)
- **Scraper Pool Separation**: Refactored `src/image_engine.py` to separate scraping into a Phase 1 Topic Asset Pool search (up to 15 images) and Phase 2 Round-Robin sentence mapping, completely eliminating slow, duplicate per-sentence live scraping loops.
- **Domain Trust Whitelist & Scoring Rules**: Integrated a robust set of trusted technology, engineering, and educational domains (e.g. GitHub, Microsoft, TI, Wikipedia). Implemented scoring weighting:
  - Trusted Domain: `+40`
  - Keyword Match: `+30`
  - Page Title Match: `+20`
  - Metadata Match: `+10`
- **Scoring Loop Resiliency**: Discards candidate images with scores `< 20` using a standard `continue` loop rather than raising exceptions or aborting the batch.
- **PIL NameError Closure Fix**: Solved Python compilation/closure scope NameErrors by cleaning up local conditional Pillow imports in `src/video_engine.py`.

### 5. Optional Video Intro Sequence (2026-06-16)
- **Interactive CLI Prompt:** Added a user toggle (`use_oggy_intro` / OGGY INTRO) in `main.py` allowing the user to select whether to include the intro sequence.
- **Chalkboard Text Overlay:** Dynamically renders the video's topic text onto the green blackboard in the intro clip (`assets/oggy_video/oggy_intro.mp4`) using MoviePy's `TextClip` with bold white font and size constraints for word wrap.
- **Curtain Delay & Alignment:** Delays chalkboard text appearance by exactly 7.0 seconds (matching curtain opening time) and positions the text at `('center', 'center')`.
- **Pre-FFmpeg Concatenation:** Combines the intro segment and base video using MoviePy's `concatenate_videoclips` prior to any downstream FFmpeg filters or overlays, preserving audio transitions.

### 6. Master Audio Volume Boost & Normalization (2026-06-16)
- **Audio Normalization:** Integrated an dynamic audio normalization pass using MoviePy's `AudioNormalize` (fully compatible with both MoviePy v1 and v2 class/function patterns) to maximize vocal peaks while preventing digital clipping or distortion.
- **Volume Boost:** Applied a 2.0x volume scale multiplier to the master voiceover track before compiling the final video frames. Supports `MultiplyVolume`, `volumex`, and `with_volume_scaled` methods dynamically as fallback chain depending on the active MoviePy version.

### 7. Scraper Stealth Integration (2026-06-16)
- **Undetected-Chromedriver & User-Agent Rotation**: Replaced standard Selenium with undetected-chromedriver and configured automated user-agent rotation from a pool of 10 modern browser headers.
- **CDP Header Injection**: Forces headers (`Accept-Language: en-US,en;q=0.9` and `Accept: text/html,application/xhtml+xml,application/xml`) using Chrome DevTools Protocol to mimic normal user browsers.
- **Stealth Delays**: Added randomized sleeps (2 to 5 seconds) before HTTP requests to mitigate bot detection.
- **Improved Logging**: Tracks and logs actual downloaded images vs. local fallbacks correctly (e.g. `✓ Saved X images (Y downloaded, Z local fallbacks)`).

### 8. Perceptual Hashing (pHash) Deduplication (2026-06-16)
- **Visual Duplicate Filtering**: Replaced MD5 cryptographic checks with Perceptual Hashing (`imagehash.phash`) to detect slightly resized, compressed, or transcoded visually duplicate images.
- **Hamming Distance Comparison**: Compares the pHash of each new candidate image against previously matched images. Rejects candidates that have a Hamming distance of 5 or less.
- **Deterministic CRC32 Cache**: Uses `binascii.crc32` for cache file naming instead of standard MD5, eliminating `hashlib` dependencies.

### 9. One-Click Setup & Launch (2026-06-16)
- **Automated setup.bat**: Refactored the one-click batch setup script to locate python binaries, create/activate the virtual environment, install requirements, download the deepseek GGUF model, build llama.cpp from source, preload all TTS/translation/browser models, and launch the application seamlessly.

### 10. Video Series Narrative Continuity (2026-06-30)
- **Episode-Aware Prompting**: `generate_series_scripts` in `src/script_engine.py` now injects contextual continuity hints into each episode's LLM prompt.
- **First Episode**: Ends with a teaser for the next episode's topic.
- **Middle Episodes**: Start with a 1-sentence recap of the previous episode, end with a teaser for the next.
- **Final Episode**: Starts with a recap and ends with a concluding series wrap-up.
- **Fallback Continuity**: Even emergency fallback scripts include recaps and teasers for a cohesive series experience.

### 11. Code-Mixing & Technical Word Masking (2026-06-30)
- **PROTECTED_TERMS List**: Added 40+ technical/engineering terms (Voltage, Capacitor, AI, Machine Learning, FPGA, etc.) to `src/translation.py`.
- **Placeholder Masking**: Before NLLB translation, protected terms are case-insensitively replaced with unique alphanumeric placeholders (`__T0__`, `__T1__`, ...).
- **Post-Translation Restoration**: After NLLB returns the translated output, placeholders are swapped back to their original English words.
- **Indic TTS Compatibility**: Embedded English terms are natively pronounced by TTS engines (Sherpa-ONNX, Meta MMS), producing natural code-mixed speech.

### 12. MoviePy File Lock Fix for Series (2026-06-30)
- **Clip Tracking List**: All MoviePy clip objects (`base_video_clip`, `audio_clip`, `intro_clip`, `text_clip`, `final_intro_segment`) are tracked in a `_clips_to_close` list.
- **Aggressive Early Close**: Clips are closed immediately after the base video write and again after the intro segment write, releasing Windows file handles before FFmpeg post-processing.
- **Guaranteed Cleanup**: A `finally` block ensures all remaining clip handles are released even if the compose function crashes mid-execution.
- **Unique Temp Files**: All temporary files (`_overlay_temp.mp4`, `_intro_temp.mp4`, `_concat_temp.mp4`) are derived from the unique per-episode `output_path`, preventing overwrites during series loops.

### 13. Dynamic Green Screen Overlay Mapping (2026-07-27)
- **Flexible Config Layout**: Added an `overlays` section in `config.yaml` mapping filenames to custom scale (height/width), crop, position, and chroma key parameters.
- **Hierarchical Resolution**: Refactored `compose_video` in `src/video_engine.py` to dynamically resolve overlay configuration properties by filename, falling back to a configured `default` section, with auto-detection of dimensions.
- **FFmpeg Filter Error Fix**: Pre-fixed custom filters correctly (e.g. `despill=` and `eq=`) to prevent filter chain syntax errors and video composition failures.

### 14. Indic TTS GPU Acceleration (2026-07-27)
- **Forced GPU Support**: Upgraded `synthesize_indic_tts` in `src/tts.py` and `india_tts/test_indic_tts.py` to auto-detect CUDA and move model/tokenizer input tensors to the GPU.
- **System Memory Retrieval**: Added `.cpu()` conversion to pull the generated audio tensor back to system memory before converting it to a NumPy array to avoid memory/device mismatch crashes.

### 15. Kokoro TTS Integration (2026-08-02)
- **High-Quality Educational Narration**: Integrated the lightweight 82M open-weight Kokoro TTS engine (`kokoro>=0.9.4`) for premium quality voice synthesis.
- **GPU Hardware Acceleration**: Configured explicit device matching (`device="cuda" if torch.cuda.is_available() else "cpu"`) for the Kokoro KModel and KPipeline. Injected a critical logging warning to immediately flag CPU fallbacks.
- **Safe Tensor Memory Routing**: Added logic to verify and route generated audio tensors safely back to host CPU memory (`.cpu().numpy()`) before WAV serialization, preventing memory access crashes on GPU environments.
- **Dynamic Speed Scheduling**: Implemented auto-scaling speeds: `1.05` multiplier for short-form video reels (<= 60 seconds) to maintain fast pacing, and `1.00` multiplier for long-form educational videos.
- **Strict Format Enforcements**: Configured audio outputs to export as mono 16-bit PCM WAV at exactly 24000 Hz. Normalized audio waveform peak values to `0.95` before file serialization to prevent digital clipping.
- **Indic Language Blocking & Routing**: Established strict regional Indic language routing constraints (such as Telugu, Tamil, Kannada, etc.) to bypass Kokoro and use localized dual-tokenizer models instead.
- **Translation Bridge & Code-Mixing Bypass**: Added `'zh'` to the `VALID_LANGS` routing table (resolved to `'zho_Hans'`). Added a bypass gate so that international target languages (Spanish, Japanese, French, Chinese, Italian, Portuguese) bypass the `PROTECTED_TERMS` code-mixing masking entirely, translating all technical terms natively before Kokoro speech synthesis.

### 16. Purge Obsolete Engines & Streamline Codebase (2026-08-02)
- **Cleaned Technical Debt**: Completely purged the obsolete `sherpa-onnx` (Sherpa English), `meta_mms` (Meta MMS Telugu), and `sarvam` (Sarvam AI API) TTS engines from the project to simplify environment setup and streamline execution logic.
- **CLI & Dispatch Consolidation**: Renumbered remaining active local/remote engine choices sequentially: 1. Kokoro TTS, 2. Supertonic, 3. Indic TTS. Consolidated `synthesize_speech` routing.
- **Diagnostics & Preloading Optimization**: Streamlined `setup.bat`, `AGENTS.md`, and `README.md` to remove VITS/MMS voice model downloads, preloading scripts, and diagnostics testing loops.
- **GPU Build Enforcement**: Enforced `-DGGML_CUDA=ON` for llama.cpp CMake build instructions across documentation to guarantee hardware acceleration on Nvidia GPUs. Enabled dynamic GPU/CUDA device configuration (`torch.cuda.is_available()`) for Supertonic TTS loading in `src/tts.py` to prevent CPU fallbacks.

### 17. Google Gemini API Integration for Script Generation (2026-09-28)
- **Dual LLM Mode**: Added `llm_mode` toggle (`"local"` / `"api"`) in `config.yaml` under `script:` to switch between local GGUF inference and cloud-based Google Gemini API via its official OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`).
- **Stable Model Selection**: Model set to `gemini-1.5-flash` (handles high-throughput free tier traffic with superior stability over experimental/heavy flash models). Configured via `config.yaml → script.api` with user's Google AI Studio API key.
- **Hard 5-Attempt Retry Loop for Overload (503/529)**: Wrapped API chat completions inside a 5-iteration retry loop. If Google's API returns a 503 Service Unavailable or 529 Overloaded error, it logs `[WARNING] Google API overloaded. Retrying in 5 seconds (Attempt {attempt+1}/5)...`, sleeps 5 seconds, and retries. If all 5 attempts fail, halts immediately with `sys.exit(1)`.
- **OpenAI-Compatible Client**: Implemented `_generate_via_api()` in `src/script_engine.py` using the standard `openai` Python SDK targeting Google's Gemini endpoint.
- **Elimination of Fallback Script**: Completely eliminated the emergency 36-word fallback script ("Today we are exploring the core concepts behind..."). If the API or script generation fails, the system immediately exits with `sys.exit(1)` and a critical error: `[FATAL] API Access Denied. Check your endpoint and API key. Do not let the video pipeline continue if script generation fails.`
- **CLI Override**: Added `--llm {local,api}` argparse argument to `main.py` that overrides `config.yaml` settings at runtime.
- **Fail-Fast Validation**: Both `main.py` and `script_engine.py` perform early API key validation — if `--llm api` is used but `script.api.api_key` is empty, the pipeline exits immediately with a clear error message.
- **130 WPM Duration Word Math & Strict System Command**: In API mode, target duration is mathematically converted to target words at 130 WPM (`target_words = int(round(duration * (130 / 60)))`, with `min_words` and `max_words` bounded at +/- 10%). The system prompt strictly enforces: *"You are writing a voiceover script for a {duration}-second video about {topic}. You MUST write exactly between {min_words} and {max_words} words. Count your words carefully. Do not output any formatting, headers, or conversational text. Output only the raw spoken script."* Scaled dynamically for any reel duration (e.g. 30s -> 58-72 words, 40s -> 78-96 words, 60s -> 117-143 words).

### 18. Intro Chalkboard Topic Bug Fix (2026-09-28)
- **Root Cause**: In `src/video_engine.py`, the B-roll insertion block at line 603 was overwriting the `topic` function parameter (`topic = Path(output_path).parent.name`) before the intro section used it at line 1098 (`intro_text = topic if topic else "Today's Topic"`). This caused the chalkboard to display the output directory name instead of the actual video topic.
- **Fix**: Renamed the B-roll variable from `topic` to `broll_topic` so the original `compose_video(topic=...)` parameter is preserved through to the intro overlay code.

### 19. Subtitle Positioning Fix (2026-09-28)
- **Root Cause**: In `src/subtitle_engine.py`, the default fallback for `position_y` was `0.78` (bottom of screen), even though `config.yaml` specifies `0.12` (top of screen). If the config value wasn't loaded for any reason, subtitles would render at the bottom instead of above the content images.
- **Fix**: Changed the hardcoded default fallback from `0.78` to `0.12` to match the config intent. Subtitles now consistently render above the content image zone (images at `position_y: 0.28 + 200px offset`).

### 20. End-to-End Automation & Social Publishing Pipeline (2026-09-29)
- **Non-Interactive CLI Support in `main.py`**: Added comprehensive command-line parameters (`--topic`, `--duration`, `--tts`, `--overlay`, `--intro`, `--llm`, `--language`, `--non-interactive`). When `--topic` is passed, `main.py` bypasses all interactive menu prompts, generates the video, verifies the output artifact > 0 bytes, prints `OUTPUT_VIDEO_PATH=...`, and exits with code 0.
- **YouTube Shorts Pipeline (`youtube_uploader.py`)**: Standalone and modular OAuth2 uploader for YouTube Shorts. Dynamically resolves `client_secret.json` relative to project root, caches credentials in `config/token.json`, refreshes expired tokens via `creds.refresh(Request())`, and automatically formats title (<100 chars), description, category (`28` Science & Tech), and tags.
- **Instagram Reels Pipeline (`instagram_uploader.py`)**: Dual-mode Instagram publisher. Prioritizes Instagrapi for local file uploads, caching authenticated mobile sessions in `config/session.json`. Supports Meta Graph API for hosted URLs. Wrapped in an isolated `try...except` so Instagram auth/network failures log a clear warning (`[WARNING] Instagram authentication failed. Skipping Instagram upload.`) without crashing or blocking the YouTube upload.
- **Unified 3-Step Orchestration (`orchestrate.py`)**: Unified Python runner structuring the entire pipeline into 3 distinct, logged stages:
  - `[STEP 1/3] Generating Reel for topic...`
  - `[STEP 2/3] Verifying output artifact...`
  - `[STEP 3/3] Uploading to YouTube & Instagram...`
- **One-Click Batch Runners (`run_pipeline.bat` & `automate.bat`)**: Automated batch scripts that validate virtual environments, run the video generator with exit-code capture (`IF %ERRORLEVEL% NEQ 0 exit /b`), verify the `.mp4` file size, and pass the exact resolved video path directly to uploaders.
- **Security Hardening**: Added `client_secret*.json`, `token.json`, `token.pickle`, `session.json`, and `config/automation.local.yaml` to `.gitignore`. Updated `.env` and `.env.example` templates to securely store all social credentials outside git tracking.

### 21. MoviePy v2 B-Roll Syntax Modernization (2026-09-29)
- **Root Cause**: In MoviePy v2, legacy setter and transformation methods on `VideoClip`/`VideoFileClip`/`CompositeVideoClip` were deprecated or removed (e.g. `.resize()`, `.crop()`, `.set_position()`, `.set_start()`, `.set_end()`, `.set_duration()`). When B-roll `.mp4` video clips were inserted, calling `.resize(height=h)` or `.set_duration()` threw `AttributeError: 'VideoFileClip' object has no attribute 'resize'`, falling back to static images or breaking video composition.
- **Modernized Methods**:
  - `.resize(...)` → `.resized(...)` (with fallback)
  - `.crop(...)` → `.cropped(...)` (with fallback)
  - `.set_position(...)` → `.with_position(...)` (with fallback)
  - `.set_start(...)` → `.with_start(...)` (with fallback)
  - `.set_end(...)` → `.with_end(...)` (with fallback)
  - `.set_duration(...)` → `.with_duration(...)` (with fallback, including `CompositeVideoClip` overlay layer)
### 22. Strict 3-Tier Waterfall B-Roll Engine (2026-10-11)
- **Multi-Provider Waterfall**: Replaced single-source Pexels fetcher with a 3-tier sequence (`Mixkit` -> `Tenor` -> `Pexels`) in `src/image_engine.py` governed by `config.yaml` (`broll:` section).
- **Core Topic Keyword Extraction**: Automatically strips conversational stop words (`what, is, how, does, work, explain, the, a, an, etc.`) from queries and eliminates generic fallback queries (such as `"technology"`).
- **Tier 1 (Mixkit)**: Scrapes video cards via regex, enforces that title/alt text or URL slug contains topic words, and automatically upgrades preview MP4s to high-resolution `-720.mp4` streams.
- **Tier 2 (Tenor)**: Queries technical MP4 loops (`query + " animation"`), rejects memes/reactions via `blocked_tags`, requires topic words in content description/URL, and extracts direct `.mp4` video streams (never `.gif`).
- **Tier 3 (Pexels)**: Enforces strict URL slug verification (`/video/<slug>/`), discarding videos unless core topic words appear explicitly in the slug.
- **Zero-Broll Graceful Fallback**: When 0 clips pass relevance checks, logs `[INFO] [B-Roll] 0 relevant videos found across Mixkit/Tenor/Pexels for '{core_topic}'. Using 100% static technical diagrams.` and returns `[]`.
### 23. Visual Media Mode Selector (2026-10-11)
- **Interactive & Headless Control**: Added `--visuals` / `--media-mode` CLI flag (`choices=['images', 'hybrid']`) and an interactive menu option in `main.py` allowing users to select between:
  - `[1] Videos + Images (Hybrid B-Roll + Technical Diagrams)`: Blends static diagrams with up to 3 relevant B-roll video inserts.
  - `[2] Only Images (100% Static Technical Diagrams)`: Skips all external video downloads and uses only scraped technical imagery.
- **Orchestration Passthrough**: `orchestrate.py` forwards `--visuals` / `--media-mode` directly into `generate_single_video()` and configuration dictionaries.

### 24. Interactive Script Generation Engine Selection (2026-10-11)
- **Menu Prompting**: Interactive setup in `main.py` (both Single Video and Series modes) prompts the user to choose between:
  - `[1] Cloud API (Fast Reasoning via Google Gemini)` (Default)
  - `[2] Local Model (GGUF via llama-cpp-python)`
- **CLI Precedence**: If `--llm` or `--llm-mode` (`choices=['api', 'local']`) is passed via command-line arguments, the interactive prompt is bypassed automatically.
- **Fail-Fast API Validation**: Immediate early verification ensures `GEMINI_API_KEY` is present before commencing script generation, halting cleanly if missing.
- **Orchestrator Default**: `orchestrate.py` defaults to `--llm api` for rapid cloud execution in batch/automated environments.

### 25. B-Roll Topic Resolution & Oggy Chroma Key Fix (2026-10-13)
- **B-Roll Topic Bug Fix**: Fixed an issue in `src/video_engine.py` where `broll_topic = Path(output_path).parent.name` extracted `"videos"` from `outputs/videos`, causing `fetch_generic_broll` to strip `"videos"` as a stop word and return 0 clips. Topic resolution now explicitly prioritizes the passed `topic` argument, falling back to output filename stem before language/episode tags (`re.split(r'_(?:[a-z]{2}|EP\d+)_', stem)`). In `src/image_engine.py`, added upfront logging of `raw_topic` and `core_topic` and guarded against empty or `"videos"` topics.
- **Oggy Overlay Grey Box Elimination**: Sampled pixel values of `assets/green_screen/oggy green screen video1.mp4` revealing background green is `0x2F9142` (RGB `[47, 145, 66]`), not neon green `0x04F504`. With `0x04F504` at similarity `0.20`, the chromakey failed to match, leaving the background opaque where the `despill` filter turned it into a dark grey/slate box. Updated `config.yaml` to use exact hex `0x2F9142`, similarity `0.15`, `crop: in_w-4:in_h-4:2:2`, and enforced `format=yuva420p` in `src/video_engine.py` filter chain for 100% clean alpha transparency.

### 26. Green Screen Colorkey Migration & Despill Slate Removal (2026-10-15)
- **Colorkey vs Chromakey Mathematical Separation**: Diagnosed why `chromakey` destroyed character bodies: `chromakey` operates in YUV space ignoring luma, causing dark greens with low chroma near neutral `(128, 128)` to engulf Oggy's black suit, white shirt, and blue fur. Replaced with `colorkey` in RGB Euclidean space (`format=rgba,colorkey=...`), where black, white, and cyan distances are vastly separated from green (`> 0.31`).
- **Despill Elimination**: `despill=type=green:mix=0.5` was turning unkeyed border pixels and blue fur into dark slate grey (`[40, 52, 61]`). Completely omitted `despill` (`despill: null`) from the filter chain to prevent color contamination.
- **Per-Asset Measured Calibration**:
  - `oggy green screen video1.mp4`: Hex `0x2E9043`, similarity `0.20`, blend `0.02`, crop `in_w-4:in_h-4:2:2`, scale `-1:950`.
  - `oggy horizontal.mp4`: Hex `0x0DA416`, similarity `0.20`, blend `0.02`, crop `null`, scale `-1:600`.
  - `oggy green screen video2.mp4`: Hex `0x00B11B`, similarity `0.20`, blend `0.02`, crop `null`, scale `-1:580`.
  - `cat.mp4`: Hex `0x069015`, similarity `0.20`, blend `0.02`, crop `null`, scale `-1:700`.
- **Mathematical Verification**: Verified across all 4 assets on a 1080x1920 canvas that background difference vs. raw baseline is `0` (100% transparency), and character regions remain 100% opaque and color-accurate (`diff > 75`).

### 27. B-Roll Continuous Duration Matching, Subtitle Layering & Overlay Visibility (2026-10-15)
- **Elimination of B-Roll Looping & Replays**: Removed all `Loop()` effects and modulo timestamp looping in `src/video_engine.py`. B-roll clips now strictly match `slot_duration`: trimmed once if `duration >= slot_duration`, smoothly slowed down via `vfx.MultiplySpeed(final_duration=slot_duration)` if `duration >= 0.65 * slot_duration`, or closed/skipped in favor of static diagrams if `< 0.65 * slot_duration`.
- **Top-Level Subtitle Layering**: Subtitles decoupled from `make_frame(t)` and composited as a dedicated top-level transparent RGBA `VideoClip` in `CompositeVideoClip([base_video_clip] + video_clips_overlay + [subtitle_clip])`. Subtitles are guaranteed 100% visible across both static slides and full-screen B-roll.
- **Dynamic Oggy Overlay Hiding during B-Roll**: In `src/video_engine.py`, recorded `(start_time, end_time)` intervals for all inserted full-screen B-roll clips and dynamically injected `:enable='not(between(t,...)+...)'` into the FFmpeg overlay filter to hide Oggy during B-roll playback while preserving the overlay during static slides.
- **Strict B-Roll Relevance & Deduplication**: Removed the `is_tag_page` keyword bypass in `_fetch_mixkit_broll()` in `src/image_engine.py`, requiring at least one core topic word in title, alt text, or slug. Filtered out Tenor loops with durations `< 2.5` seconds. Enforced global URL and file-size tracking across the 3-tier waterfall to prevent duplicate clips.
- **Silent Chrome Driver Exit**: Monkey-patched `uc.Chrome.__del__` at import time in `src/image_engine.py` to catch `OSError: [WinError 6]` during process garbage collection.

### 28. End-to-End Pipeline Verification & YouTube Shorts Upload (2026-10-15)
- **Diode Reel Generation**: Verified complete generation of "what is diode" reel (37.3s, 1080x1920 @ 30fps) with Gemini Flash Lite API script generation, Kokoro voiceover with 2.0x vocal boost, top-anchored karaoke subtitles, and Oggy colorkey green screen overlay.
- **Image Scraper Verification**: Successfully scraped and validated 10 high-resolution technical diagrams (`sentence_00.jpg` to `sentence_09.jpg`) + 9 topic anchor images with 0 local fallbacks.
- **Strict B-Roll Waterfall Verification**: Verified 3-tier waterfall behavior (Mixkit -> Tenor -> Pexels). Confirmed that unrelated stock footage lacking core topic words is strictly rejected, smoothly falling back to 100% static technical diagrams. Lowered B-roll target duration threshold in `src/image_engine.py` from 40s to 15s with explicit logging.
- **YouTube Shorts Publishing**: Authenticated OAuth credentials via local callback server and published directly to YouTube Shorts: `https://youtube.com/shorts/xi7v7esYtz8`. Run recorded in SQLite publishing history database.
- **Instagram Reels Publishing**: Completed 2FA verification for `oggy_theprofessor`, dumped authenticated session to `config/session.json`, and published the diode reel directly to Instagram: `https://www.instagram.com/reel/DehCTs7NP36/`. Future uploads will reuse this session without requiring 2FA.

## 📖 Operational Guidance

- **Translation:** To use a different language, choose a translation-supported voice engine (such as Kokoro or Supertonic) and select the corresponding language code. If a non-English language is chosen, the engine will automatically route script sentences to the local NLLB-200 engine for translation.
- **Kokoro Language Defaults**: For non-English Kokoro languages, the voice is automatically set to a native voice ID (e.g. `jf_alpha` for Japanese, `zf_xiaobei` for Chinese) to guarantee correct phonetic pronunciation.
- **Manual Override:** When prompted, you can paste high-quality native scripts to bypass AI translation entirely.
- **Oggy Selection:** Use the interactive menu at the start of `main.py` to pick between Widescreen or Vertical Oggy assets. The default is now `oggy green screen video1.mp4`.
- **Google Gemini API Mode:** Run `python main.py --llm api` to use the cloud LLM. Requires a valid Google AI Studio API key in `config.yaml → script.api.api_key`. Default mode is `local` (GGUF).
- **Automated Execution & Publishing:**
  - One-line command: `python orchestrate.py --topic "what is capacitor" --upload youtube`
  - Batch runner: `run_pipeline.bat "what is capacitor"`
  - Dry-run test: `python orchestrate.py --topic "what is capacitor" --dry-run`




