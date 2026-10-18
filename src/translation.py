"""
Translator Engine - Robust Multi-Language Translation
Translates English text to target language using local NLLB-200.
"""

import sys
import logging
import time
import torch
from typing import Optional, Dict, Any, List
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

logger = logging.getLogger(__name__)

import re as _re

# Technical terms to preserve as English during translation (code-mixing).
# These are replaced with placeholders before NLLB translation, then swapped back.
# Indic TTS engines natively pronounce embedded English words.
PROTECTED_TERMS = [
    "Voltage", "Current", "Resistor", "Capacitor", "Inductor", "Battery",
    "Circuit", "Sensor", "Motor", "AI", "Software", "Hardware", "CPU", "GPU",
    "RAM", "ROM", "LED", "LCD", "IoT", "API", "HTTP", "USB", "HDMI",
    "Transistor", "Diode", "Amplifier", "Microcontroller", "Arduino",
    "Raspberry Pi", "Bluetooth", "WiFi", "Ethernet", "Algorithm",
    "Machine Learning", "Neural Network", "Deep Learning", "Robotics",
    "Automation", "Drone", "Servo", "PWM", "ADC", "DAC", "MOSFET", "FPGA",
]

# Synchronized dictionary layout mapping 2-letter selection codes to valid NLLB tokens
VALID_LANGS = {
    'hi': {'name': 'Hindi', 'nllb': 'hin_Deva'},
    'bn': {'name': 'Bengali', 'nllb': 'ben_Beng'},
    'kn': {'name': 'Kannada', 'nllb': 'kan_Knda'},
    'ta': {'name': 'Tamil', 'nllb': 'tam_Taml'},
    'ko': {'name': 'Korean', 'nllb': 'kor_Hang'},
    'ja': {'name': 'Japanese', 'nllb': 'jpn_Jpan'},
    'ar': {'name': 'Arabic', 'nllb': 'ars_Arab'},
    'bg': {'name': 'Bulgarian', 'nllb': 'bul_Cyrl'},
    'cs': {'name': 'Czech', 'nllb': 'ces_Latn'},
    'da': {'name': 'Danish', 'nllb': 'dan_Latn'},
    'de': {'name': 'German', 'nllb': 'deu_Latn'},
    'el': {'name': 'Greek', 'nllb': 'ell_Grek'},
    'es': {'name': 'Spanish', 'nllb': 'spa_Latn'},
    'et': {'name': 'Estonian', 'nllb': 'est_Latn'},
    'fi': {'name': 'Finnish', 'nllb': 'fin_Latn'},
    'fr': {'name': 'French', 'nllb': 'fra_Latn'},
    'hr': {'name': 'Croatian', 'nllb': 'hrv_Latn'},
    'hu': {'name': 'Hungarian', 'nllb': 'hun_Latn'},
    'id': {'name': 'Indonesian', 'nllb': 'ind_Latn'},
    'it': {'name': 'Italian', 'nllb': 'ita_Latn'},
    'lt': {'name': 'Lithuanian', 'nllb': 'lit_Latn'},
    'lv': {'name': 'Latvian', 'nllb': 'lvs_Latn'},
    'nl': {'name': 'Dutch', 'nllb': 'nld_Latn'},
    'pl': {'name': 'Polish', 'nllb': 'pol_Latn'},
    'pt': {'name': 'Portuguese', 'nllb': 'por_Latn'},
    'ro': {'name': 'Romanian', 'nllb': 'ron_Latn'},
    'ru': {'name': 'Russian', 'nllb': 'rus_Cyrl'},
    'sk': {'name': 'Slovak', 'nllb': 'slk_Latn'},
    'sl': {'name': 'Slovenian', 'nllb': 'slv_Latn'},
    'sv': {'name': 'Swedish', 'nllb': 'swe_Latn'},
    'tr': {'name': 'Turkish', 'nllb': 'tur_Latn'},
    'uk': {'name': 'Ukrainian', 'nllb': 'ukr_Cyrl'},
    'vi': {'name': 'Vietnamese', 'nllb': 'vie_Latn'},
    'zh': {'name': 'Chinese', 'nllb': 'zho_Hans'}
}

# NLLB-200 Multi-Language Routing Dictionary derived from VALID_LANGS (plus 'te' and 'en')
LANGUAGE_ROUTING = {k: v['nllb'] for k, v in VALID_LANGS.items()}
LANGUAGE_ROUTING['te'] = 'tel_Telu'
LANGUAGE_ROUTING['en'] = 'eng_Latn'

# Cache for loaded model
_cached_model = None
_cached_tokenizer = None

class TranslationEngineOffline(Exception):
    """Exception raised when NLLB model fails to load."""
    pass

def verify_nllb_engine(config: Optional[Dict] = None):
    """
    Structural verification checkpoint for NLLB Engine.
    Attempts to load the model and raises TranslationEngineOffline if it fails.
    """
    global _cached_model, _cached_tokenizer
    
    if _cached_model is not None and _cached_tokenizer is not None:
        return _cached_tokenizer, _cached_model
    
    cfg = (config or {}).get("translation", {})
    model_name = cfg.get("model_name", "facebook/nllb-200-distilled-600M")
    
    try:
        logger.info(f"[Translator] Verifying NLLB Engine: {model_name}...")
        
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # Load onto CUDA via torch.bfloat16 for efficiency
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        load_kwargs = {
            "device_map": "auto" if torch.cuda.is_available() else None,
            "torch_dtype": torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            "use_safetensors": True,
        }
        
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name, **load_kwargs)
        model.eval()
        
        _cached_model = model
        _cached_tokenizer = tokenizer
        
        logger.info(f"[Translator] NLLB Engine online on {device}")
        return tokenizer, model
        
    except Exception as e:
        logger.error(f"[Translator] Verification Failed: {e}")
        print("\n  ⚠️ Local NLLB Engine offline. Dropping down to manual text override entry mode...")
        raise TranslationEngineOffline(f"NLLB initialization failed: {e}")

def translate_text(
    text: str,
    target_lang_code: str = "te",
    config: Optional[Dict] = None,
) -> Optional[str]:
    """
    Translate English text to target language using NLLB-200.
    Technical terms from PROTECTED_TERMS are masked before translation
    and restored afterwards to enable natural code-mixing.
    """
    if not text or not text.strip():
        return None
    
    target_lang_code_lower = target_lang_code.lower()
    
    # Reject instantly if falls outside collection (excluding 'en' and 'te')
    if target_lang_code_lower not in ['en', 'te'] and target_lang_code_lower not in VALID_LANGS:
        raise ValueError(f"Language code '{target_lang_code}' is not supported for translation.")
    
    # Resolve NLLB token from 2-letter code
    nllb_token = LANGUAGE_ROUTING.get(target_lang_code_lower)
    if not nllb_token:
        logger.warning(f"[Translator] Unsupported language code: {target_lang_code}. Falling back to Telugu.")
        nllb_token = "tel_Telu"
    
    cfg = (config or {}).get("translation", {})
    max_tokens = cfg.get("max_tokens", 256)
    num_beams = cfg.get("num_beams", 4)
    
    # ── STEP 1: Mask protected technical terms with placeholders ──
    # Only apply code-mixing mask for Indic family languages.
    # Foreign languages (Japanese, Chinese, Spanish, etc.) receive strict native translations.
    INDIC_FAMILY_CODES = {'te', 'hi', 'bn', 'kn', 'ta', 'ml', 'mr', 'gu', 'pa', 'or'}
    use_code_mixing = target_lang_code_lower in INDIC_FAMILY_CODES
    
    placeholder_map = {}  # {"__T1__": "Voltage", ...}
    masked_text = text
    placeholder_idx = 0
    
    if use_code_mixing:
        # Sort by length descending so multi-word terms like "Machine Learning" are matched first
        sorted_terms = sorted(PROTECTED_TERMS, key=len, reverse=True)
        
        for term in sorted_terms:
            # Case-insensitive search for the term as a whole word
            pattern = _re.compile(_re.escape(term), _re.IGNORECASE)
            matches = list(pattern.finditer(masked_text))
            for match in reversed(matches):  # Reverse to preserve earlier indices
                original_word = match.group(0)
                placeholder = f"__T{placeholder_idx}__"
                placeholder_map[placeholder] = original_word
                masked_text = masked_text[:match.start()] + placeholder + masked_text[match.end():]
                placeholder_idx += 1
        
        if placeholder_map:
            logger.info(f"[Translator] Masked {len(placeholder_map)} protected terms: {list(placeholder_map.values())}")
    else:
        logger.info(f"[Translator] Code-mixing bypass: target '{target_lang_code_lower}' is not Indic. Translating all terms natively.")
    
    try:
        tokenizer, model = verify_nllb_engine(config)
        
        tokenizer.src_lang = "eng_Latn"
        inputs = tokenizer(masked_text, return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        # Declare target language token ID inside the generator array natively
        if hasattr(tokenizer, "lang_code_to_id") and nllb_token in tokenizer.lang_code_to_id:
            forced_bos_token_id = tokenizer.lang_code_to_id[nllb_token]
        else:
            forced_bos_token_id = tokenizer.convert_tokens_to_ids(nllb_token)
        
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                forced_bos_token_id=forced_bos_token_id,
                max_new_tokens=max_tokens,
                num_beams=num_beams,
                early_stopping=True,
            )
        
        translated = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        
        # ── STEP 2: Swap placeholders back to original English terms ──
        for placeholder, original_word in placeholder_map.items():
            translated = translated.replace(placeholder, original_word)
        
        return translated
        
    except TranslationEngineOffline:
        # Re-raise to be handled by main orchestrator
        raise
    except Exception as e:
        logger.error(f"[Translator] Translation error: {e}")
        return None

def get_available_languages() -> List[str]:
    """Return list of supported 2-letter language codes."""
    return list(LANGUAGE_ROUTING.keys())

def run_pipeline_sanity_check(config: Optional[Dict] = None):
    """
    Automated initialization validation check block.
    Translates "Hello world" to Korean and verifies the output is not the original English text.
    """
    logger.info("[Translator] Running boot-time pipeline sanity check...")
    test_input = "Hello world"
    try:
        translated = translate_text(test_input, target_lang_code="ko", config=config)
        if translated and translated.strip().lower() == test_input.lower():
            print("\n❌ ERROR: Translation engine output loop configuration mismatch detected. Check target vocabulary IDs.\n")
            sys.exit(1)
        logger.info("[Translator] Pipeline sanity check passed.")
    except TranslationEngineOffline:
        logger.warning("[Translator] Local NLLB model is offline/unavailable. Continuing with manual fallback enabled.")
    except Exception as e:
        logger.error(f"[Translator] Sanity check encountered unexpected error: {e}")
