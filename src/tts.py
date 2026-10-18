"""
Voice Engine - Wraps the voice/ module for importable use.
Generates WAV audio from text using various engines:
- English/International: Kokoro TTS or Supertonic (ONNX)
- Indian/Local: Indic TTS (Indic-Parler-TTS)
"""

import os
import sys
import logging
import time
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

_supertonic_engine = None
_indic_tts_model = None
_indic_tts_tokenizer = None
_indic_tts_description_tokenizer = None
_kokoro_pipeline = None
_kokoro_model = None

VIBE_PROFILES = {
    "1": {
        "name": "Professional Lecturer",
        "template": "{speaker}'s voice is clear, with a normal pace and a balanced pitch, delivered in a very clear audio recording, close-sounding, with absolutely no background noise."
    },
    "2": {
        "name": "Energetic/Expressive",
        "template": "{speaker}'s voice is highly expressive, with a slightly higher pitch and a fast-paced delivery, captured in a very clear audio recording close up with no background noise."
    },
    "3": {
        "name": "Calm Narrator",
        "template": "{speaker}'s voice is slightly slower in delivery and carries a neutral, monotone yet reassuring tone. The recording is clear, close up, with minimal background ambient noise."
    }
}

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
VOICE_DIR = PROJECT_ROOT / "src" / "voice"
MODELS_DIR = VOICE_DIR / "models"


def _ensure_model_dirs():
    """Ensure model directories exist."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)



def synthesize_indic_tts(
    text: str,
    output_path: str,
    language: str = "Telugu",
    speaker: str = "Prakash",
    vibe_profile: str = "1",
) -> Optional[str]:
    """
    Synthesize text using CPU-optimized Indic-Parler-TTS dual-tokenizer model.
    """
    global _indic_tts_model, _indic_tts_tokenizer, _indic_tts_description_tokenizer
    import torch
    import soundfile as sf
    import re
    from transformers import AutoTokenizer
    from parler_tts import ParlerTTSForConditionalGeneration

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        print("\n" + "="*80 + "\n[CRITICAL WARNING] CUDA NOT DETECTED! PyTorch is missing GPU support. Indic TTS will run extremely slowly on the CPU.\n" + "="*80 + "\n", flush=True)
        logger.warning("[CRITICAL WARNING] CUDA NOT DETECTED! PyTorch is missing GPU support. Indic TTS will run extremely slowly on the CPU.")
    torch_dtype = torch.float32
    model_id = "ai4bharat/indic-parler-tts"

    try:
        if _indic_tts_model is None:
            logger.info(f"[Voice] Loading Indic Parler model {model_id} on {device}...")
            _indic_tts_model = ParlerTTSForConditionalGeneration.from_pretrained(model_id).to(device, dtype=torch_dtype)
            _indic_tts_tokenizer = AutoTokenizer.from_pretrained(model_id)
            _indic_tts_description_tokenizer = AutoTokenizer.from_pretrained(_indic_tts_model.config.text_encoder._name_or_path)

        model = _indic_tts_model.to(device)
        tokenizer = _indic_tts_tokenizer
        description_tokenizer = _indic_tts_description_tokenizer

        # 1. Resolve description template based on vibe
        vibe_data = VIBE_PROFILES.get(str(vibe_profile), VIBE_PROFILES["1"])
        description_text = vibe_data['template'].format(speaker=speaker)

        logger.info(f"[Voice] Indic TTS Config -> Lang: {language}, Speaker: {speaker}, Vibe: {vibe_data['name']}")

        # 2. Chunk text to not exceed 300 characters
        def split_text(t, max_chars=300):
            if len(t) <= max_chars:
                return [t]
            sentences = re.split(r'(?<=[।\.!?])\s+', t)
            chunks = []
            current_chunk = ""
            for s in sentences:
                if len(current_chunk) + len(s) < max_chars:
                    current_chunk += (" " if current_chunk else "") + s
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = s
            if current_chunk:
                chunks.append(current_chunk)
            return chunks

        chunks = split_text(text)
        logger.info(f"[Voice] Splitting text into {len(chunks)} chunk(s)...")

        all_audio = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            logger.info(f"[Voice] Synthesizing chunk {i+1}/{len(chunks)}...")

            # FORCE GPU ACCELERATION:
            text_chunk = chunk
            description = description_text
            prompt_tokenizer = description_tokenizer
            
            input_ids = tokenizer(text_chunk, return_tensors="pt").input_ids.to(device)
            attention_mask = tokenizer(text_chunk, return_tensors="pt").attention_mask.to(device)
            prompt_input_ids = prompt_tokenizer(description, return_tensors="pt").input_ids.to(device)
            prompt_attention_mask = prompt_tokenizer(description, return_tensors="pt").attention_mask.to(device)

            with torch.no_grad():
                # Explicit dual-tokenizer tensors passed to generate()
                generation = model.generate(
                    input_ids=prompt_input_ids,
                    attention_mask=prompt_attention_mask,
                    prompt_input_ids=input_ids,
                    prompt_attention_mask=attention_mask
                )

            # Cast generation output to CPU and convert to numpy
            audio_arr = generation[0].cpu().numpy()
            audio_chunk = audio_arr
            all_audio.append(audio_chunk)

        if not all_audio:
            logger.warning("[Voice] Indic TTS generated no audio waveform.")
            return None

        # Concatenate audio chunks
        full_audio = np.concatenate(all_audio)

        # Normalize audio array
        if np.abs(full_audio).max() > 0:
            full_audio = full_audio / np.abs(full_audio).max()

        # Save to output path
        sf.write(output_path, full_audio, model.config.sampling_rate)
        logger.info(f"[Voice] Indic TTS synthesis successful: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"[Voice] Indic TTS generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def synthesize_kokoro(
    text: str,
    output_path: str,
    voice_id: str = "am_adam",
    speed: float = 1.0,
    lang_code: str = "a",
    config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Synthesize text using Kokoro TTS (82M parameter open-weight model).
    Supports: en-us(a), en-gb(b), es(e), fr(f), it(i), ja(j), zh(z), pt-br(p), hi(h).
    Output: WAV, 24000 Hz, Mono, 16-bit PCM.
    """
    global _kokoro_pipeline, _kokoro_model
    import torch
    import soundfile as sf

    if not text or not text.strip():
        logger.error("[Voice] Kokoro: Empty text provided")
        return None

    KOKORO_SAMPLE_RATE = 24000

    try:
        from kokoro import KModel, KPipeline
    except ImportError as e:
        logger.error(f"[Voice] Cannot import kokoro: {e}. Run: pip install 'kokoro>=0.9.4'")
        return None

    try:
        # Detect CUDA
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            print("\n" + "="*80 + "\n[CRITICAL WARNING] CUDA NOT DETECTED! Kokoro TTS will run extremely slowly on the CPU. Check your PyTorch installation.\n" + "="*80 + "\n", flush=True)
            logger.warning("[CRITICAL WARNING] CUDA NOT DETECTED! Kokoro TTS will run extremely slowly on the CPU. Check your PyTorch installation.")

        # Initialize model once (cached globally)
        if _kokoro_model is None:
            logger.info(f"[Voice] Loading Kokoro model on {device}...")
            _kokoro_model = KModel().to(device).eval()

        # Initialize pipeline (recreate if lang_code changed)
        if _kokoro_pipeline is None or getattr(_kokoro_pipeline, '_lang_code', None) != lang_code:
            logger.info(f"[Voice] Initializing Kokoro pipeline for lang_code='{lang_code}' on {device}")
            try:
                _kokoro_pipeline = KPipeline(lang_code=lang_code, model=_kokoro_model, device=device)
            except (ModuleNotFoundError, ImportError):
                logger.warning(f"[WARNING] Missing G2P dependencies for lang_code='{lang_code}'. Falling back to English ('a').")
                lang_code = 'a'
                voice_id = 'am_adam'
                _kokoro_pipeline = KPipeline(lang_code=lang_code, model=_kokoro_model, device=device)
            _kokoro_pipeline._lang_code = lang_code  # Tag for cache invalidation

        # Dynamic speed based on video duration hint from config
        cfg_duration = (config or {}).get("_video_duration_hint", 0)
        if cfg_duration > 0 and speed == 1.0:
            speed = 1.05 if cfg_duration <= 60 else 1.0
            logger.info(f"[Voice] Kokoro dynamic speed: {speed} (video hint: {cfg_duration}s)")

        logger.info(f"[Voice] Kokoro synthesis: voice={voice_id}, speed={speed}, lang={lang_code}, chars={len(text)}")

        # Generate audio chunks
        audio_chunks = []
        for gs, ps, audio in _kokoro_pipeline(text, voice=voice_id, speed=speed):
            if audio is not None:
                if torch.is_tensor(audio):
                    audio = audio.cpu().numpy()
                elif hasattr(audio, "numpy"):
                    audio = audio.cpu().numpy() if hasattr(audio, "cpu") else audio.numpy()
                
                if len(audio) > 0:
                    audio_chunks.append(audio)

        if not audio_chunks:
            raise ValueError("Kokoro generated no audio chunks")

        # Concatenate all chunks
        full_audio = np.concatenate(audio_chunks, axis=0)

        # Volume normalization (peak normalize to 0.95 to prevent clipping)
        peak = np.abs(full_audio).max()
        if peak > 0:
            full_audio = full_audio * (0.95 / peak)

        # Force 16-bit PCM WAV output
        full_audio_16 = (full_audio * 32767).astype(np.int16)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, full_audio_16, KOKORO_SAMPLE_RATE, subtype='PCM_16')

        duration_secs = len(full_audio) / KOKORO_SAMPLE_RATE
        logger.info(f"[Voice] Kokoro synthesis complete: {duration_secs:.1f}s -> {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"[Voice] Kokoro synthesis failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def synthesize_speech(
    text: str,
    output_path: str,
    speaker_id: int = 0,
    speed: float = 1.0,
    language: str = "en",
    config: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Synthesize text to speech and save as WAV file.
    
    Args:
        text: Text to synthesize
        output_path: Path to save WAV file
        speaker_id: Speaker ID (unused)
        speed: Speech speed multiplier
        language: "en" for English, "te" for Telugu
        config: Optional config dict
        max_retries: Number of retry attempts
        
    Returns:
        Path to saved WAV file, or None on failure
    """
    if not text or not text.strip():
        logger.error("[Voice] Empty text provided")
        return None

    if config is None:
        config = {}
    
    voice_cfg = config.get("voice", {})
    language = voice_cfg.get("language", language)
    lang = language
    
    if language == "te":
        lang_cfg = voice_cfg.get("telugu", {})
    else:
        lang_cfg = voice_cfg.get("english", {})
        
    speed = lang_cfg.get("speed", speed)
    engine = lang_cfg.get("engine", "kokoro" if language == "en" else "indic")

    _ensure_model_dirs()
    
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        logger.info(f"[Voice] Attempt {attempt}/{max_retries} - Synthesizing {len(text)} chars with {engine}")

        try:
            if engine == "kokoro":
                kokoro_cfg = voice_cfg.get("kokoro", {})
                kokoro_voice = kokoro_cfg.get("voice_id", "af_heart")
                kokoro_lang = kokoro_cfg.get("lang_code", "a")
                kokoro_speed = kokoro_cfg.get("speed", speed)
                
                res = synthesize_kokoro(
                    text=text,
                    output_path=output_path,
                    voice_id=kokoro_voice,
                    speed=kokoro_speed,
                    lang_code=kokoro_lang,
                    config=config,
                )
                if res:
                    return res
                else:
                    raise Exception("Kokoro TTS synthesis returned None")

            if engine == "indic":
                indic_cfg = voice_cfg.get("indic", {})
                indic_lang = indic_cfg.get("language", "Telugu")
                indic_speaker = indic_cfg.get("speaker", "Prakash")
                indic_vibe = indic_cfg.get("vibe", "1")
                
                res = synthesize_indic_tts(
                    text=text,
                    language=indic_lang,
                    speaker=indic_speaker,
                    vibe_profile=indic_vibe,
                    output_path=output_path
                )
                if res:
                    return res
                else:
                    raise Exception("Indic TTS synthesis returned None")

            # Enforce engine isolation gates & fallback routing
            SUPERTONIC_LANGS = {'en', 'ko', 'ja', 'ar', 'bg', 'cs', 'da', 'de', 'el', 'es', 'et', 'fi', 'fr', 'hi', 'hr', 'hu', 'id', 'it', 'lt', 'lv', 'nl', 'pl', 'pt', 'ro', 'ru', 'sk', 'sl', 'sv', 'tr', 'uk', 'vi'}
            if engine == "supertonic":
                supertonic_lang = lang_cfg.get("supertonic_lang", language)
                if supertonic_lang == "te" or language == "te":
                    lang = "te"
                else:
                    lang = supertonic_lang
                
                if lang == "te":
                    print("🔄 Target language is 'te' (Telugu). Bypassing Supertonic and routing payload directly to the Indic Voice Engine pipeline...")
                    indic_cfg = voice_cfg.get("indic", {})
                    indic_lang = indic_cfg.get("language", "Telugu")
                    indic_speaker = indic_cfg.get("speaker", "Prakash")
                    indic_vibe = indic_cfg.get("vibe", "1")
                    res = synthesize_indic_tts(
                        text=text,
                        language=indic_lang,
                        speaker=indic_speaker,
                        vibe_profile=indic_vibe,
                        output_path=output_path
                    )
                    if res:
                        return res
                    else:
                        raise Exception("Indic TTS synthesis returned None")
                elif lang in SUPERTONIC_LANGS:
                    language = "en"
                else:
                    raise ValueError(f"Language '{lang}' is not supported by Supertonic.")

            if language == "en":
                if engine == "supertonic":
                    import soundfile as sf
                    global _supertonic_engine
                    
                    supertonic_dir = PROJECT_ROOT / "supertonic" / "py"
                    if str(supertonic_dir) not in sys.path:
                        sys.path.append(str(supertonic_dir))
                        
                    try:
                        from helper import load_text_to_speech, load_voice_style
                    except ImportError as e:
                        logger.error(f"[Voice] Cannot import Supertonic: {e}. Ensure requirements in supertonic/py are installed.")
                        return None
                        
                    onnx_dir = PROJECT_ROOT / "supertonic" / "assets" / "onnx"
                    
                    style_file = lang_cfg.get("supertonic_voice", "M1.json")
                    super_lang = lang_cfg.get("supertonic_lang", "en")
                    super_vibe = lang_cfg.get("supertonic_vibe", "neutral")
                    
                    logger.info(f"[Voice] Supertonic Config -> Style: {style_file}, Vibe: {super_vibe}, Lang: {super_lang}")
                    
                    style_path = PROJECT_ROOT / "supertonic" / "assets" / "voice_styles" / style_file
                    
                    if _supertonic_engine is None:
                        logger.info("[Voice] Loading Supertonic TTS engine...")
                        import torch
                        use_gpu = torch.cuda.is_available()
                        if use_gpu:
                            logger.info("[Voice] GPU detected! Loading Supertonic TTS engine with GPU acceleration.")
                        else:
                            logger.info("[Voice] CUDA not detected. Loading Supertonic TTS engine on CPU.")
                        _supertonic_engine = load_text_to_speech(str(onnx_dir), use_gpu=use_gpu)
                            
                    style = load_voice_style([str(style_path)])
                    
                    import re
                    raw_sents = re.split(r'(?<=[.!?])\s+', text.strip())
                    chunks = []
                    current_chunk = []
                    current_len = 0
                    for sent in raw_sents:
                        if not sent.strip():
                            continue
                        if current_len + len(sent) > 250:
                            if current_chunk:
                                chunks.append(" ".join(current_chunk))
                            current_chunk = [sent]
                            current_len = len(sent)
                        else:
                            current_chunk.append(sent)
                            current_len += len(sent) + 1
                    if current_chunk:
                        chunks.append(" ".join(current_chunk))
                        
                    logger.info(f"[Voice] Split text into {len(chunks)} chunks for Supertonic synthesis")
                    
                    all_wavs = []
                    sample_rate = _supertonic_engine.sample_rate
                    for chunk_idx, chunk_text in enumerate(chunks, 1):
                        logger.info(f"[Voice] Synthesizing chunk {chunk_idx}/{len(chunks)}: \"{chunk_text[:50]}...\" ({len(chunk_text)} chars)")
                        wav, duration = _supertonic_engine(
                            chunk_text, super_lang, style, 8, speed
                        )
                        w = wav[0, : int(sample_rate * duration[0].item())]
                        all_wavs.append(w)
                        
                    if all_wavs:
                        final_wav = np.concatenate(all_wavs)
                        sf.write(output_path, final_wav, sample_rate)
                        return output_path
                    else:
                        raise ValueError("No audio was synthesized from chunks")
                else:
                    raise ValueError(f"Unsupported English engine '{engine}'")
            else:
                raise ValueError(f"Unsupported language '{language}' or engine '{engine}'")

        except ValueError as ve:
            print(f"\n[FATAL ERROR] ValueError encountered during text preprocessing/routing:")
            print(f"Details: {ve}")
            print(f"Text length: {len(text)} characters")
            print(f"Target language: {language} (original parameter: {lang})")
            print(f"Engine: {engine}")
            print("Gracefully exiting application to prevent further cascade failures.\n")
            sys.exit(1)
        except Exception as e:
            logger.warning(f"[Voice] Attempt {attempt} failed: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            
        if attempt < max_retries:
            logger.info(f"[Voice] Retrying in {2 ** attempt}s...")
            time.sleep(2 ** attempt)
            
    logger.error("[Voice] Failed after 3 attempts")
    return None


def get_audio_duration(wav_path: str) -> float:
    """Get duration of a WAV file in seconds."""
    try:
        from scipy.io import wavfile
        sample_rate, data = wavfile.read(wav_path)
        return len(data) / sample_rate
    except Exception as e:
        logger.error(f"[Voice] Error reading WAV: {e}")
        return 0.0


def split_text_to_sentences(text: str) -> list:
    """
    Split text into conceptual segments of 6 to 12 words each,
    deleting punctuation-based sentence splitting.
    """
    words = text.strip().split()
    if not words:
        return []
        
    segments = []
    i = 0
    total_words = len(words)
    
    while i < total_words:
        remaining = total_words - i
        if remaining <= 12:
            chunk_size = remaining
        elif remaining < 12 + 6:
            chunk_size = remaining // 2
        else:
            chunk_size = 9  # target 9 words per segment
            
        segment = " ".join(words[i : i + chunk_size])
        segments.append(segment)
        i += chunk_size
        
    return segments


def estimate_sentence_timings(sentences: list, total_duration: float) -> list:
    """
    Estimate start/end times for each sentence based on word count.
    
    Returns:
        List of (sentence, start_time, end_time) tuples
    """
    total_words = sum(len(s.split()) for s in sentences)
    if total_words == 0:
        return []
    
    timings = []
    current_time = 0.0
    
    for sentence in sentences:
        word_count = len(sentence.split())
        sentence_duration = (word_count / total_words) * total_duration
        
        timings.append({
            "text": sentence,
            "start": round(current_time, 3),
            "end": round(current_time + sentence_duration, 3),
            "words": sentence.split(),
        })
        current_time += sentence_duration
    
    return timings
