# Agent Setup Guide

This file is for coding agents and IDE assistants that receive this repository and need to set it up on a Windows machine. Follow this file before modifying app behavior.

## Objective

Make the project runnable from a fresh clone on Windows. Do not assume large local assets were committed. Recreate them using documented downloads/builds.

Primary repo:

```text
https://github.com/Bitradevendra/reel-generater.git
```

## Non-Negotiable Rules

- Do not commit `venv/`, caches, generated videos, logs, model binaries, or downloaded `.gguf` files.
- Do not vendor the raw `script/llama.cpp` directory into the parent repo. It is a Git submodule.
- Do not replace `script/model.gguf` in `config.yaml` with a machine-specific absolute path.
- Keep setup commands Windows PowerShell compatible.
- If a model download fails, report the failing URL/model name and the exact command that failed.
- If you change setup docs, test or at least syntax-check the commands you touched.

## Expected Local-Only Assets

These are intentionally not stored in Git:

```text
venv/
outputs/
src/script/*.gguf
src/voice/models/
src/language_converter/.hf_cache/
src/script/.cache/
src/script/llama.cpp/build/
*.log
```

They are recreated during setup.

## Fresh Windows Setup

Run in PowerShell.

> [!TIP]
> You can automate steps 3 through 8 by running the one-click **[setup.bat](file:///C:/Users/papan/downloads/reel/setup.bat)** script after cloning the repo.

### 1. Install system dependencies

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
winget install --id Kitware.CMake -e
winget install --id Google.Chrome -e
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

Open a new PowerShell window after installing these.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. Clone with submodules

```powershell
cd $env:USERPROFILE\Downloads
git clone --recurse-submodules https://github.com/Bitradevendra/reel-generater.git
cd reel-generater
git submodule update --init --recursive
```

### 3. Create venv and install Python dependencies

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
# Note: PyTorch with CUDA 12.1 is enforced automatically via requirements.txt
pip install --prefer-binary -r requirements.txt
```

### 4. Build llama.cpp CLI fallback with GPU acceleration

```powershell
cd src\script\llama.cpp
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DGGML_CUDA=ON
cmake --build build --config Release
cd ..\..\..
```

Verify:

```powershell
Test-Path .\src\script\llama.cpp\build\bin\Release\llama-cli.exe
```

Expected: `True`.

### 5. Download the GGUF script model

```powershell
cd src\script
python get_model.py
cd ..\..
```

The required file is:

```text
src/script/model.gguf
```

If the automatic downloader fails, manually download a GGUF model from one of:

```text
https://huggingface.co/bartowski/deepseek-r1-distill-qwen-7b-gguf
https://huggingface.co/QuantFactory/Phi-3-5-mini-instruct-GGUF
```

Then rename it to `model.gguf` and place it in `src/script/`.

### 6. Preload translation model

Translation uses Facebook NLLB:

```powershell
python -c "from transformers import AutoModelForSeq2SeqLM, AutoTokenizer; AutoTokenizer.from_pretrained('facebook/nllb-200-distilled-600M', src_lang='eng_Latn'); AutoModelForSeq2SeqLM.from_pretrained('facebook/nllb-200-distilled-600M', use_safetensors=True); print('NLLB translation model ready')"
```

### 7. Verify Chrome/Selenium image scraping

```powershell
python -c "from selenium import webdriver; from selenium.webdriver.chrome.options import Options; o=Options(); o.add_argument('--headless=new'); d=webdriver.Chrome(options=o); print('Chrome started'); d.quit(); print('Chrome/Selenium ready')"
```

## Full Verification Checklist

Run from repo root with venv active:

```powershell
python --version
python -c "import torch, transformers, moviepy, selenium, yaml; print('Python packages ready')"
Test-Path .\src\script\model.gguf
Test-Path .\src\script\llama.cpp\build\bin\Release\llama-cli.exe
python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('facebook/nllb-200-distilled-600M', src_lang='eng_Latn'); print('HF tokenizers ready')"
```

Expected:

- Python is `3.11.x`.
- Imports succeed.
- All `Test-Path` checks return `True`.
- Hugging Face tokenizer loads.

## Run The App

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

## Important Architecture Notes

- `src/script_engine.py` tries `llama-cpp-python` first, then falls back to compiled `llama-cli.exe`, then can fall back to Ollama if enabled.
- `config.yaml` must keep `script.model_path` as `src/script/model.gguf` for portable setup.
- English/International voice uses Kokoro TTS (local via python package).
- Indian regional languages voice uses Indic TTS (local via transformer model).
- Translation uses `facebook/nllb-200-distilled-600M`.
- Image scraping uses Selenium and Chrome.
- Video rendering uses MoviePy and `imageio-ffmpeg`.

## Known Risks To Report

Report these clearly instead of silently changing project behavior:

- `llama-cpp-python` wheel build failure.
- Visual Studio C++ Build Tools missing or incomplete.
- Hugging Face download/network failure.
- Low disk space for `.gguf` or NLLB models.
- Chrome/Selenium driver mismatch.
- GPU-specific PyTorch or CUDA mismatch.

## Git Hygiene

Before committing, run:

```powershell
git status -sb
git diff --stat
```

Make sure no generated or model files are staged:

```powershell
git diff --cached --name-only
```

If any of these appear staged, unstage them:

```text
venv/
outputs/
src/script/*.gguf
src/voice/models/
src/language_converter/.hf_cache/
src/script/llama.cpp/build/
*.log
```

Use normal commits for docs/setup fixes. Keep `script/llama.cpp` as a submodule pointer, not copied source.
