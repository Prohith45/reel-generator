# 🎬 Reel Generator & Social Publisher — Command Reference Manual

A complete reference guide for generating educational reels and publishing them to YouTube Shorts and Instagram Reels.

---

## 📌 Table of Contents
1. [Environment Activation](#1-environment-activation)
2. [Unified 1-Line Pipelines (Generation + Upload)](#2-unified-1-line-pipelines-generation--upload)
3. [Video Generation Only (`main.py`)](#3-video-generation-only-mainpy)
4. [YouTube Shorts Uploading (`youtube_uploader.py`)](#4-youtube-shorts-uploading-youtube_uploaderpy)
5. [Instagram Reels Uploading (`instagram_uploader.py`)](#5-instagram-reels-uploading-instagram_uploaderpy)
6. [Complete CLI Flags Reference](#6-complete-cli-flags-reference)
7. [Helpful Troubleshooting Commands](#7-helpful-troubleshooting-commands)

---

## 1. Environment Activation

Always activate the project virtual environment before running commands:

### Windows PowerShell:
```powershell
.\venv\Scripts\Activate.ps1
```

### Windows Command Prompt (CMD):
```cmd
.\venv\Scripts\activate.bat
```

---

## 2. Unified 1-Line Pipelines (Generation + Upload)

Executes the complete 3-step automation:
1. **[STEP 1/3]** Generate script, voiceover, images, and video.
2. **[STEP 2/3]** Verify output artifact (existence, duration, stream validity, file size > 0).
3. **[STEP 3/3]** Upload to selected social media platforms.

### 🐍 Python Orchestrator (`orchestrate.py`):

```powershell
# Generate video and publish to BOTH YouTube Shorts & Instagram Reels:
python orchestrate.py --topic "what is capacitor"

# Publish to YouTube Shorts ONLY:
python orchestrate.py --topic "what is capacitor" --upload youtube

# Publish to Instagram Reels ONLY:
python orchestrate.py --topic "what is capacitor" --upload instagram

# Generate video only (skip uploading):
python orchestrate.py --topic "what is capacitor" --upload none

# Dry-run test (generates video, simulates upload without posting live):
python orchestrate.py --topic "what is capacitor" --dry-run

# Auto-Topic Selection (picks from predefined topic pool automatically):
python orchestrate.py --upload youtube
```

### ⚡ Windows Batch Runners (`.bat`):

```cmd
# Standard 1-click execution:
run_pipeline.bat "what is capacitor"

# Upload to YouTube only:
run_pipeline.bat "what is capacitor" --upload youtube

# Dry-run test:
run_pipeline.bat "what is capacitor" --dry-run

# Alternative batch runner:
automate.bat "what is capacitor"
automate.bat "what is capacitor" --upload youtube
```

---

## 3. Video Generation Only (`main.py`)

Generate videos without triggering the social media uploader scripts.

### 🤖 Automated / Headless CLI Mode:

```powershell
# Standard 60-Second Educational Reel:
python main.py --topic "what is capacitor" --duration 60 --tts kokoro --llm api --overlay 4 --intro 1

# 30-Second Short Reel:
python main.py --topic "how transistors amplify" --duration 30 --tts kokoro --llm api

# Without Green Screen Character Overlay:
python main.py --topic "what is capacitor" --overlay none

# Without Oggy Classroom Intro Sequence:
python main.py --topic "what is capacitor" --intro 0

# Using Local Offline GGUF Model (llama.cpp):
python main.py --topic "what is capacitor" --llm local

# Telugu Narration via Indic TTS:
python main.py --topic "what is capacitor" --tts indic --language te
```

### 🎮 Interactive Wizard:

```powershell
# Launches interactive menu for topic, narrator, character, and settings:
python main.py
```

---

## 4. YouTube Shorts Uploading (`youtube_uploader.py`)

Upload any `.mp4` file directly to YouTube Shorts with auto-formatted titles, descriptions, and hashtags.

```powershell
# Public Upload:
python youtube_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --topic "What is a Capacitor"

# Unlisted Upload (for preview before going public):
python youtube_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --topic "What is a Capacitor" --privacy unlisted

# Private Upload:
python youtube_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --topic "What is a Capacitor" --privacy private

# Custom Video Title:
python youtube_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --title "How Capacitors Store Energy #shorts" --category 28

# Dry-Run (Verifies OAuth authentication without uploading):
python youtube_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --dry-run
```

### 🔑 YouTube OAuth Token Management:

```powershell
# Opens browser to authenticate Google account and saves token to config/token.json & .env:
python get_youtube_token.py
```

---

## 5. Instagram Reels Uploading (`instagram_uploader.py`)

Upload any `.mp4` file directly to Instagram Reels using Instagrapi (private mobile API) or Meta Graph API.

```powershell
# Direct Upload to Instagram Reels:
python instagram_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --topic "What is a Capacitor"

# Upload with Custom Caption:
python instagram_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --caption "⚡ Learn how capacitors work in 60s! #tech #engineering"

# Dry-Run Test:
python instagram_uploader.py --video "outputs/videos/what_is_capacitor_en_kokoro_20260929_224344.mp4" --dry-run
```

> **Note:** Requires `INSTAGRAM_USERNAME` and `INSTAGRAM_PASSWORD` configured in `.env`. Sessions are cached automatically in `config/session.json`.

---

## 6. Complete CLI Flags Reference

| Flag | Supported Values | Default | Description |
| :--- | :--- | :--- | :--- |
| `--topic` | Any string (e.g., `"what is capacitor"`) | None (auto-selects from pool) | Video topic to research, script, and narrate |
| `--upload` | `both`, `youtube`, `instagram`, `none` | `both` | Destination social media platforms |
| `--duration` | Integer (seconds, 15 to 300) | `60` | Target length (calculates target words at 130 WPM) |
| `--llm` | `api`, `local` | `api` | Script engine (`api` = Gemini, `local` = GGUF) |
| `--tts` | `kokoro`, `supertonic`, `indic` | `kokoro` | Voice synthesis engine |
| `--voice-id` | `am_adam`, `af_heart`, `bm_george`, etc. | `am_adam` | Specific voice narrator ID |
| `--language` | `en`, `te`, `hi`, `es`, `fr`, `ja`, etc. | `en` | Spoken narration language |
| `--overlay` | `1`, `2`, `3`, `4`, `none` | `4` | Character overlay (`4` = Oggy Horizontal) |
| `--intro` | `1` (yes), `0` (no) | `1` | Oggy chalkboard intro sequence |
| `--privacy` | `public`, `unlisted`, `private` | `public` | YouTube video privacy status |
| `--category` | `28` (Science/Tech), `27` (Education) | `28` | YouTube video category ID |
| `--dry-run` | Flag | Off | Tests workflow and credentials without live publishing |

---

## 7. Helpful Troubleshooting Commands

```powershell
# Check YouTube & Instagram module imports:
python -c "from youtube_uploader import upload_to_youtube; from instagram_uploader import upload_to_instagram; print('Uploaders ready')"

# View recent publishing history in database:
python -c "from automation.pipeline.history_db import init_db; db = init_db(); [print(r.id, r.topic, r.overall_status, r.youtube_url) for r in db.get_history(5)]"

# Check available videos in output directory:
Get-ChildItem "outputs\videos\*.mp4" | Select-Object Name, Length
```
