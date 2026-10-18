"""
Script Engine - Voiceover script generation.

Pipeline modes (configured via config.yaml script.llm_mode):
  1. "local"  →  llama-cpp-python GGUF direct load (fastest, GPU/CPU)
  2. "api"    →  Google Gemini API via OpenAI-compatible endpoint (cloud)
"""

import os
import sys
import re
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SCRIPT_DIR = PROJECT_ROOT / "src" / "script"

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def _is_reasoning_model(model_name: str, model_path: str = "") -> bool:
    """Determine if a model is a reasoning model based on its name or path."""
    name = (model_name or "").lower()
    path = (model_path or "").lower()
    return "r1" in name or "deepseek" in name or "r1" in path or "deepseek" in path


def _clean_thinking_tags(text: str) -> str:
    """Robustly clean up matching and unmatched/stray <think> and </think> tags."""
    # Case 1: No opening <think> tag at all, but closing </think> exists.
    # Discard everything before the first </think> tag.
    if "<think>" not in text and "</think>" in text:
        text = text.split("</think>", 1)[1]
        
    # Case 2: Standard matching loops for <think>...</think>
    while "</think>" in text:
        idx = text.find("</think>")
        open_idx = text.find("<think>")
        if open_idx != -1 and open_idx < idx:
            # Matched block: remove it completely
            text = text[:open_idx] + text[idx + 8:]
        else:
            # Stray closing tag: just remove the tag itself
            text = text[:idx] + text[idx + 8:]
            
    # Case 3: Unclosed opening <think> tag
    if "<think>" in text:
        text = text.split("<think>")[0]
        
    return text.strip()


def sanitize_script(raw_output: str) -> str:
    """Sanitize the raw LLM output to strip reasoning thoughts and meta-commentary."""
    # 1. Remove all think tags robustly
    clean = _clean_thinking_tags(raw_output)
    
    # Remove prefix scene/segment headers at the line level
    clean = re.sub(r'^(?:topic|audience|duration|content type|script|role|target|scene|segment):\s*.*$', '', clean, flags=re.IGNORECASE | re.MULTILINE)
    
    # 2. Remove meta-commentary lines (lines/sentences starting with 'Let me...', 'Wait', 'I need to')
    # If the output is a single long paragraph without newlines, we also split by sentences to prevent dropping the whole text.
    if '\n' not in clean.strip() and '.' in clean:
        lines = re.split(r'(?<=[.!?])\s+', clean)
    else:
        lines = clean.split('\n')
        
    filtered = []
    conversational_triggers = [
        'let me', 'wait,', 'i need to', 'thought:', 'reasoning:', 'user has given', 
        'constraints', 'how do i', 'let me count', 'let me break', 'i should focus', 
        'i have to structure', 'no fluff', 'analogies', 'introductory fluff', 
        'i\'ll start', 'then move', 'each section', 'i\'ll aim', 'list out possible', 
        'this covers', 'let\'s see', 'condense more', 'perhaps', 'combine phrases', 
        'redundant words', 'adding up:', 'total word count', 'over the limit', 
        'make it shorter', 'possible sentences', 'words)', 'word count', 'target duration'
    ]
    header_triggers = [
        'and definition', 'and basics', 'and automation', 'and monitoring', 
        'and safety', 'and positioning', 'and algorithms', 'infrastructure integration', 
        'and ethics', 'and technology', 'and technology', 'and innovation', 'human well-being'
    ]
    
    for line in lines:
        lower = line.lower().strip()
        if not lower:
            continue
            
        # Drop conversational leaks
        if any(trigger in lower for trigger in conversational_triggers):
            continue
            
        # Drop generic headers if they are short (<= 4 words)
        words_in_line = lower.split()
        if len(words_in_line) <= 4 and any(trigger in lower for trigger in header_triggers):
            continue
            
        filtered.append(line)
        
    if '\n' not in clean.strip() and '.' in clean:
        return ' '.join(filtered).strip()
    return '\n'.join(filtered).strip()


def _calculate_tokens(duration: int, words_per_second: float = 2.5) -> int:
    """Calculate approximate tokens from duration."""
    return int(duration * words_per_second * 1.3)


def _build_prompt(topic: str, content_type: str, duration: int, audience: str, language: str = "en", words_per_second: float = 2.5, is_reasoning: bool = False) -> str:
    """Build the generation prompt with audience-specific adjustments.
    
    Strict rules:
      - No few-shot examples, no fruit analogies, no "why the sky is blue".
      - Topic must be addressed from the very first word.
      - Word count is strictly target-constrained.
    """
    audience_guidance = {
        "engineers": "Professional, exam-focused, practical insights. Explain with real-world applications and technical depth.",
        "common": "Simple, clear, easy to understand. Avoid jargon. Explain like talking to a friend.",
        "kids": "Very simple, friendly tone. Use easy words. Make it fun and engaging.",
    }
    guidance = audience_guidance.get(audience, audience_guidance["common"])

    target_words = int(duration * words_per_second)
    min_words = int(target_words * 0.90)
    max_words = int(target_words * 1.10)

    if is_reasoning:
        think_instruction = """If you are a reasoning model, you MUST put all your planning, counting, self-correction, and constraint checks inside <think>...</think> tags.
Outside of <think> tags (or in your final response), you MUST output ONLY the clean, final spoken script text. No meta-commentary, no prefix like "Here is the script", no explanations."""
    else:
        think_instruction = """You MUST output ONLY the clean, final spoken script text. No planning, no thoughts, no reasoning, no meta-commentary, no prefix like "Here is the script", no explanations. Do NOT use <think> or </think> tags."""

    return f"""You are an elite engineering professor creating a fast-paced, high-retention technical short video.

{think_instruction}

Write the script as a continuous, flowing spoken narrative. DO NOT use bullet points, dashes, or numbered lists. Every sentence must end with standard punctuation.

TOPIC: "{topic}"
Content Type: {content_type}
Duration: EXACTLY {duration} seconds
Target Audience: {audience} (Tone/Guidance: {guidance})

ABSOLUTE CONSTRAINTS for the spoken script:
1. Stay 100% focused on "{topic}" from word one. Discuss its core physics, mechanics, components, or architecture IMMEDIATELY. No filler hooks, no generic analogies (e.g., "imagine this", "have you ever wondered"), no introductory fluff.
2. Write the script as a continuous, flowing spoken narrative. DO NOT use bullet points, dashes, or numbered lists. Every sentence must end with standard punctuation.
3. Explain the process step-by-step in detail to ensure high retention. Expand on each step (mechanisms, inputs, outputs, conversion) with multiple sentences.
4. Structure the output as short, impactful spoken sentences. Max 12 words per sentence. Use commas every 5-7 words for TTS pacing.
5. Use "..." (three dots) for dramatic pauses. Example: "And the result... is stunning."
6. Do NOT output markdown headers, section names, bullet points, numbered lists (no "1.", "2.", no "Hook:", no "Segment:"). Output ONLY raw spoken text sentences separated by spaces.
7. CRITICAL: Aim for a length of approximately {target_words} words. You must write between {min_words} and {max_words} words. Do not summarize or end early.
8. Do NOT repeat the prompt, do NOT say "Here is the script", do NOT include any meta-commentary. Begin the spoken script IMMEDIATELY.

OUTPUT FORMAT:
Plain spoken text only. Ready for Text-to-Speech. Nothing else."""


def _strip_ansi_artifacts(text: str) -> str:
    """Remove ANSI cursor control / escape artifacts from LLM output.
    
    LLaMA.cpp and Ollama token streams can inject raw ANSI cursor codes
    such as [4D [K, [6D [K, [1D [K. This strips them completely.
    """
    import re
    # Strip real ESC (0x1b) sequences: ESC[...letter
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    # Strip literal bracket-digit-letter patterns: [4D, [6D [K, [1D [K
    text = re.sub(r'\[\d+[a-zA-Z](?:\s*\[[a-zA-Z])?', '', text)
    # Remove stray escape chars and empty brackets
    text = text.replace('\x1b', '').replace('[]', '')
    # Collapse multiple spaces left behind
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_prompt_echo(text: str) -> bool:
    """Detect if the LLM returned its own prompt instead of generating a script.
    
    Heuristic: if the text contains multiple prompt-structural phrases
    it is almost certainly an echo of the system/user prompt.
    """
    prompt_markers = [
        'CRITICAL CONSTRAINTS',
        'ABSOLUTE CONSTRAINTS',
        'OUTPUT REQUIREMENTS',
        'OUTPUT FORMAT',
        'LENGTH CONTROL',
        'You are an expert video script writer',
        'You are an elite engineering professor',
        'Target Audience:',
        'Content Type:',
        'You MUST do all your reasoning',
    ]
    hits = sum(1 for m in prompt_markers if m.lower() in text.lower())
    return hits >= 2


def _is_meta_commentary(s: str) -> bool:
    """Detect if a sentence is LLM meta-commentary or conversational leak."""
    import re
    s_lower = s.lower().strip()
    
    # Common starting phrases or substrings of conversational/meta comments
    meta_patterns = [
        r"^this script\b",
        r"^here is\b",
        r"^here's a\b",
        r"^hope this\b",
        r"^let me know\b",
        r"^note that\b",
        r"^the target audience\b",
        r"^the word count\b",
        r"^the requested\b",
        r"^word count\b",
        r"^suitable for\b",
        r"^designed for\b",
        r"^focusing on\b",
        r"^conveys the\b",
        r"^let me\b",
        r"^let's\b",
        r"^i need to\b",
        r"^i will\b",
        r"^i should\b",
        r"^i'll\b",
        r"^each sentence\b",
        r"^wait,?\b",
        r"^maybe\b",
        r"^perhaps\b",
        r"suitable for .* audience",
        r"here is the final spoken script",
        r"spoken script",
        r"ready for text-to-speech",
        r"ready for tts",
    ]
    
    for pattern in meta_patterns:
        if re.search(pattern, s_lower):
            return True
            
    # If the sentence looks exactly like system rules/prompts
    if "spoken script" in s_lower or "word count" in s_lower or "target audience" in s_lower or "duration" in s_lower:
        # Check if it has hallmarks of system commentary
        if "this script" in s_lower or "conveys" in s_lower or "focusing" in s_lower or "suitable" in s_lower or "constraint" in s_lower or "limit" in s_lower:
            return True
            
    return False


def _sanitize_sentences(text: str) -> str:
    """Post-generation sentence sanitizer.
    
    1. Strip list markers ("1.", "2)", etc.).
    2. Strip structural labels ("Hook:", "Segment 3:", etc.).
    3. Drop any sentence that is meta-commentary or conversational leak.
    4. Drop any sentence with fewer than 3 alphanumeric words.
    5. Rejoin into clean paragraph text.
    """
    import re
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    for raw in raw_sentences:
        s = re.sub(r'^\s*\d+[\.)\-]\s*', '', raw).strip()
        s = re.sub(r'^(Hook:|Segment\s*\d+:|Intro:|Outro:|Opening:|Closing:)\s*', '', s, flags=re.IGNORECASE).strip()
        
        # Check for meta-commentary
        if _is_meta_commentary(s):
            continue
            
        # Count real alphanumeric words
        word_count = len(re.findall(r'\b[a-zA-Z]{2,}\b', s))
        if word_count >= 3:
            cleaned.append(s)
    return ' '.join(cleaned)


def _clean_output(text: str) -> str:
    """Clean and format the LLM output."""
    import re
    text = text.strip()
    
    # ── FIRST: Strip ANSI escape artifacts from LLM token stream ──
    text = _strip_ansi_artifacts(text)

    # ── PROMPT-ECHO DETECTION ──
    # If the LLM returned its own prompt, reject it entirely.
    if _is_prompt_echo(text):
        logger.warning("[Script] PROMPT ECHO DETECTED — LLM returned its own instructions. Rejecting.")
        return ""

    # Remove thinking/reasoning text robustly
    text = _clean_thinking_tags(text)
        
    if "...done thinking." in text:
        text = text.split("...done thinking.")[-1].strip()
        
    # Nuke common conversational leaks just in case
    text = re.sub(r"^(Okay, let's see\.|Here is the|Here's a|The user wants).*?(\n\n|$)", "", text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Remove any remaining thinking prefixes
    if text.startswith("Thinking..."):
        lines = text.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (not stripped.startswith("Thinking") and
                not stripped.startswith("The user") and
                not stripped.startswith("I'm") and
                not stripped.startswith("For") and
                not stripped.startswith("Engineers") and i > 0):
                text = '\n'.join(lines[i:])
                break

    # ── PREFIX & METADATA REMOVAL ──
    # Strip lines starting with metadata at the beginning
    text = re.sub(r'^(?:topic|audience|duration|content type|script|role|target|scene|segment):\s*.*?(?:\n|$)', '', text, flags=re.IGNORECASE)
    # Strip common conversational intro prefixes (e.g. "Here is the script: ", "Sure, here's a short video...")
    text = re.sub(r'^(?:Okay,?\s+)?(?:let\'s\s+.*?|here\s+is|here\'s|this\s+is|sure,?\s+.*?)\s+.*?(?:script|video|short|reel|voiceover)(?:\s+.*?)?:\s*', '', text, flags=re.IGNORECASE)

    # ── SUFFIX & COMMENTS REMOVAL ──
    # Strip trailing text starting with --- or - or * followed by words like "Each", "This", "Word count", "Flows", "Enjoy", "Covers"
    text = re.sub(r'\s*(?:---| - |\b(?:Note|Disclaimer|Explanation):\s+)\s*(?:Each sentence|This script|Word count|The script|Here is|Note|Disclaimer|It is|Enjoy|Flows|Covers|I hope).*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Strip word count markers (e.g., "- 7 words", "(7 words)", "[7 words]", "7 words")
    text = re.sub(r'\s*(?:-|\(|\[)?\s*\d+\s+words?\s*(?:\)|\]|\b)?', '', text, flags=re.IGNORECASE)
    
    # Strip parenthetical commentaries that contain words like "condense", "shorter", "covers", "sentence", "limit", etc.
    text = re.sub(r'\s*\([^)]*(?:word|sentence|limit|pause|second|phrase|intro|outro|segment|line|add|short|condense|check|count|explanation|\b\d+\b)[^)]*\)', '', text, flags=re.IGNORECASE)

    # Remove markdown formatting
    text = re.sub(r'\*\*|__|##|###', '', text)
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+[\.)\-]\s*', '', text, flags=re.MULTILINE)

    # Remove any JSON-array wrapping the LLM might have added
    text = re.sub(r'^\s*\[\s*"', '', text)
    text = re.sub(r'"\s*\]\s*$', '', text)

    # Strip double quotes wrapping sentences, but keep apostrophes
    text = text.replace('"', '').replace('“', '').replace('”', '')

    # Join into single paragraph
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = ' '.join(lines)

    # Fix multiple spaces
    while '  ' in text:
        text = text.replace('  ', ' ')

    # ── POST-GENERATION SENTENCE SANITIZER ──
    text = _sanitize_sentences(text)

    return text.strip()


# ============================================================================
# METHOD 1: llama-cpp-python (Primary - GGUF direct load)
# ============================================================================

def _generate_via_llama_cpp(prompt: str, model_path: str, tokens: int, config: Dict, duration: int = 60, words_per_second: float = 2.5, is_reasoning: bool = False) -> Optional[str]:
    """Generate using llama-cpp-python (native bindings for llama.cpp).
    
    This is the fastest path: loads the local .gguf model directly into
    memory with optional GPU offload.
    """
    try:
        from llama_cpp import Llama

        script_cfg = config.get("script", {})

        logger.info(f"[Script] Loading model via llama-cpp-python: {Path(model_path).name}")

        llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=script_cfg.get("threads", 8),
            n_gpu_layers=script_cfg.get("gpu_layers", 50),
            verbose=False,
        )

        if is_reasoning:
            system_content = (
                f"You are an expert video script writer. You MUST do all your reasoning inside <think> tags first. "
                f"After the </think> tag, output ONLY the final spoken script. Write the script as a continuous, flowing spoken narrative. "
                f"DO NOT use bullet points, dashes, or numbered lists. Every sentence must end with standard punctuation. "
                f"Begin the spoken script immediately. CRITICAL: Output approximately {int(duration * words_per_second)} words. "
                f"Total duration must be {duration} seconds."
            )
        else:
            system_content = (
                f"You are an expert video script writer. You MUST output ONLY the final spoken script. Write the script as a continuous, "
                f"flowing spoken narrative. DO NOT use bullet points, dashes, or numbered lists. Every sentence must end with standard punctuation. "
                f"Begin the spoken script immediately. CRITICAL: Output approximately {int(duration * words_per_second)} words. "
                f"Total duration must be {duration} seconds. Do NOT output any thinking or reasoning in <think> tags."
            )

        output = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            max_tokens=script_cfg.get("num_predict", 2048),
            temperature=script_cfg.get("temperature", 0.8),
            top_p=script_cfg.get("top_p", 0.9),
            repeat_penalty=script_cfg.get("repetition_penalty", 1.1),
        )

        # Extract text from response
        if output and "choices" in output:
            text = output["choices"][0]["message"].get("content", "").strip()
            if text:
                return sanitize_script(text)

        logger.warning("[Script] llama-cpp-python returned empty output")
        return None

    except ImportError:
        logger.info("[Script] llama-cpp-python not installed, skipping GGUF")
        return None
    except Exception as e:
        logger.warning(f"[Script] llama-cpp-python error: {e}")
        return None


# ============================================================================
# METHOD 2: NVIDIA NIM API (Cloud fallback - OpenAI-compatible)
# ============================================================================

def _generate_via_api(
    prompt: str,
    config: Dict,
    topic: str = "",
    duration: int = 60,
    min_words: Optional[int] = None,
    max_words: Optional[int] = None,
    words_per_second: float = 130.0 / 60.0,
) -> Optional[str]:
    """Generate script using Cloud API (Google Gemini / OpenAI-compatible endpoint).
    
    This is the cloud fallback path for when the local GPU (e.g. Blackwell)
    is unsupported by current llama-cpp-python wheels.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.critical("[Script] 'openai' package not installed. Run: pip install openai")
        print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
        print("  Error: 'openai' package is not installed. Run: pip install openai")
        sys.exit(1)
    
    script_cfg = config.get("script", {})
    api_cfg = script_cfg.get("api", {})
    
    base_url = api_cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")
    # Resolve API Key from .env first, then config.yaml
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or api_cfg.get("api_key", "")
    model_name = api_cfg.get("model_name", "gemini-3.5-flash-lite")
    
    if not api_key:
        logger.critical("[Script] API key is empty in .env (GEMINI_API_KEY) and config.yaml → script.api.api_key")
        print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
        print("  Error: GEMINI_API_KEY missing. Set it in .env or paste into config.yaml → script.api.api_key.")
        sys.exit(1)
    
    # 130 WPM conversion: target duration mathematically converted to target word count (e.g., 130 words for 60 seconds)
    if min_words is None or max_words is None:
        target_words = int(round(duration * (130.0 / 60.0)))
        min_words = int(round(target_words * 0.90))
        max_words = int(round(target_words * 1.10))
    else:
        target_words = int(round((min_words + max_words) / 2.0))
    
    system_content = (
        f"You are writing a voiceover script for a {duration}-second video about {topic}. "
        f"You MUST write exactly between {min_words} and {max_words} words. "
        f"Count your words carefully. Do not output any formatting, headers, or conversational text. "
        f"Output only the raw spoken script."
    )
    
    user_prompt = prompt
    
    logger.info(f"[Script] Calling Gemini API: {model_name} (Target: {target_words} words [{min_words}-{max_words}] for {duration}s)")
    
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.critical("[Script] 'google-genai' not installed. Run: pip install google-genai")
        print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    gen_config = types.GenerateContentConfig(
        system_instruction=system_content,
        thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
        temperature=script_cfg.get("temperature", 0.5),
    )
    last_err = None
    for attempt in range(5):
        try:
            chunks = []
            for chunk in client.models.generate_content_stream(
                model=model_name,
                contents=user_prompt,
                config=gen_config,
            ):
                if chunk.text:
                    chunks.append(chunk.text)
            
            text = "".join(chunks).strip()
            if text:
                logger.info(f"[Script] Gemini API returned {len(text.split())} words")
                return sanitize_script(text)
            break
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            status_code = getattr(e, "status_code", None)
            is_overloaded = (
                status_code in (503, 529)
                or "503" in err_str
                or "529" in err_str
                or "overloaded" in err_str
                or "unavailable" in err_str
                or "high demand" in err_str
                or "resource_exhausted" in err_str
            )
            if is_overloaded:
                if attempt < 4:
                    logger.warning(f"[WARNING] Google API overloaded. Retrying in 5 seconds (Attempt {attempt+1}/5)...")
                    print(f"\n  [WARNING] Google API overloaded. Retrying in 5 seconds (Attempt {attempt+1}/5)...")
                    time.sleep(5)
                    continue
                else:
                    logger.critical(f"[Script] Google API overloaded after 5 attempts: {e}")
                    print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
                    print(f"  Error details: {e}")
                    sys.exit(1)
            else:
                logger.critical(f"[Script] API error: {e}")
                print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
                print(f"  Error details: {e}")
                sys.exit(1)
    
    if last_err:
        logger.critical(f"[Script] Gemini API failed: {last_err}")
        print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
        print(f"  Error details: {last_err}")
        sys.exit(1)

    logger.critical("[Script] API returned empty output")
    print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
    print("  Error: API returned empty text.")
    sys.exit(1)



def _ensure_ends_on_complete_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text[-1] in ('.', '!', '?'):
        return text
    last_idx = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] in ('.', '!', '?'):
            last_idx = i
            break
    if last_idx != -1:
        deleted_len = len(text) - (last_idx + 1)
        deleted_percent = deleted_len / len(text)
        if deleted_percent <= 0.15:
            return text[:last_idx + 1].strip()
            
    if text[-1] not in ('.', '!', '?'):
        text += "."
    return text


def _detect_gguf_reasoning(model_path: str) -> bool:
    """Quickly parse GGUF model metadata in < 50ms using vocab_only=True to check if it's a reasoning model."""
    if not os.path.exists(model_path):
        return False
    try:
        from llama_cpp import Llama
        llm = Llama(model_path, vocab_only=True, verbose=False)
        metadata = getattr(llm, "metadata", {})
        model_name = metadata.get("general.name", "")
        return _is_reasoning_model(model_name, model_path)
    except Exception as e:
        logger.warning(f"[Script] Failed to detect GGUF metadata: {e}")
        return _is_reasoning_model("", model_path)


def generate_script(
    topic: str,
    content_type: str = "educational",
    duration: int = 60,
    audience: str = "common",
    language: str = "en",
    config: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    _depth: int = 0,
    retry_hint: str = "",
) -> Optional[str]:
    """
    Generate a voiceover script for the given topic.

    Modes (controlled by config['script']['llm_mode']):
      "local"  →  llama-cpp-python GGUF direct load (default)
      "api"    →  NVIDIA NIM OpenAI-compatible endpoint (cloud fallback)

    Args:
        topic: The topic to generate a script about
        content_type: "technology", "funny", "professional", or "educational"
        duration: Target duration in seconds
        audience: "engineers", "common", or "kids"
        config: Optional config dict with model params
        max_retries: Number of retry attempts

    Returns:
        Generated script text, or None on failure
    """
    if config is None:
        config = {}

    script_cfg = config.get("script", {})
    llm_mode = script_cfg.get("llm_mode", "local")
    
    # Mathematical conversion for target duration:
    # In API mode, use 130 WPM (130 words per 60s, e.g. 65 words for 30s, 87 words for 40s)
    if llm_mode == "api":
        words_per_second = 130.0 / 60.0
        target_words = int(round(duration * words_per_second))
        min_words = int(round(target_words * 0.90))
        max_words = int(round(target_words * 1.10))
    else:
        words_per_second = script_cfg.get("words_per_second", 2.5)
        target_words = int(duration * words_per_second)
        min_words = int(target_words * 0.90)
        max_words = int(target_words * 1.10)

    reject_min = int(min_words * 0.90)
    reject_max = int(max_words * 1.10)

    model_path = script_cfg.get("model_path", str(SCRIPT_DIR / "model.gguf"))

    # Resolve relative paths against project root
    if not os.path.isabs(model_path):
        model_path = str(PROJECT_ROOT / model_path)

    # ── API KEY VALIDATION (fail-fast for api mode) ──
    if llm_mode == "api":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or script_cfg.get("api", {}).get("api_key", "")
        if not api_key:
            logger.critical("[Script] API key missing in .env (GEMINI_API_KEY) and config.yaml (script.api.api_key).")
            print("\n  [FATAL] API Access Denied. Check your endpoint and API key.")
            print("    Set GEMINI_API_KEY in .env or paste into config.yaml → script.api.api_key, or use --llm local.")
            sys.exit(1)

    # ── DETECT IF REASONING MODEL IS ACTIVE (local mode only) ──
    is_reasoning = False
    if llm_mode == "local" and os.path.exists(model_path):
        is_reasoning = _detect_gguf_reasoning(model_path)
        logger.info(f"[Script] Detected GGUF reasoning mode: {is_reasoning}")

    prompt = _build_prompt(topic, content_type, duration, audience, language, words_per_second, is_reasoning)
    if retry_hint:
        prompt += f"\n\n{retry_hint}"
    tokens = _calculate_tokens(duration, words_per_second)

    for attempt in range(1, max_retries + 1):
        logger.info(f"[Script] Attempt {attempt}/{max_retries} (depth: {_depth}, mode: {llm_mode}) — Generating script for: {topic}")

        output = None

        # ── PATH A: Cloud API (Google Gemini / OpenAI-compatible) ──
        if llm_mode == "api":
            # 130 WPM word count bounds calculated from target duration
            api_target_words = int(round(duration * (130.0 / 60.0)))
            api_min_words = int(round(api_target_words * 0.90))
            api_max_words = int(round(api_target_words * 1.10))
            output = _generate_via_api(
                prompt=prompt,
                config=config,
                topic=topic,
                duration=duration,
                min_words=api_min_words,
                max_words=api_max_words,
                words_per_second=130.0 / 60.0,
            )
        # ── PATH B: llama-cpp-python (GGUF direct load - local) ──
        elif os.path.exists(model_path):
            output = _generate_via_llama_cpp(prompt, model_path, tokens, config, duration, words_per_second, is_reasoning)
        else:
            logger.info(f"[Script] GGUF model not found at {model_path}")

        if output:
            clean = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)
            cleaned = _clean_output(clean)
            if cleaned and len(cleaned) > 20:
                actual_words = len(cleaned.split())
                if _depth < 2 and (actual_words > reject_max or actual_words < reject_min):
                    logger.info(f"[Script] Word count {actual_words} out of tolerance range [{reject_min}, {reject_max}]. Retrying with stricter limit...")
                    hint = f"CRITICAL: Your previous generation was too long ({actual_words} words). You MUST write a shorter script. Aim for approximately {target_words} words." if actual_words > target_words else f"CRITICAL: Your previous generation was too short ({actual_words} words). You MUST write a longer script. Aim for approximately {target_words} words."
                    rec_script = generate_script(
                        topic=topic,
                        content_type=content_type,
                        duration=duration,
                        audience=audience,
                        language=language,
                        config=config,
                        max_retries=max_retries,
                        _depth=_depth + 1,
                        retry_hint=hint
                    )
                    if rec_script:
                        if _depth == 0 and len(rec_script.split()) < min(30, min_words):
                            logger.critical(f"[Script] Recursive script under minimum words ({len(rec_script.split())})")
                            print("\n  [FATAL] API Access Denied. Check your endpoint and API key. Do not let the video pipeline continue if script generation fails.")
                            sys.exit(1)
                        return rec_script

                # Hard-clamp (truncate) to max_words to ensure audio finishes exactly at target time
                if len(cleaned.split()) > max_words:
                    cleaned = ' '.join(cleaned.split()[:max_words])
                cleaned = _ensure_ends_on_complete_sentence(cleaned)

                actual_count = len(cleaned.split())
                if _depth == 0 and actual_count < min(30, min_words):
                    logger.critical(f"[Script] Final script under minimum words ({actual_count} < {min(30, min_words)})")
                    print("\n  [FATAL] API Access Denied. Check your endpoint and API key. Do not let the video pipeline continue if script generation fails.")
                    sys.exit(1)

                logger.info(f"[DURATION] Target: {duration}s | Actual: {actual_count} | Mode: {llm_mode} | Status: SCRIPT_ACCEPTED")
                return cleaned
            logger.warning(f"[Script] {llm_mode} output too short or empty after cleaning")

        # Exponential backoff between retries
        if attempt < max_retries:
            delay = 2 ** attempt
            logger.info(f"[Script] Retrying in {delay}s...")
            time.sleep(delay)

    logger.critical(f"[Script] Failed to generate script after {max_retries} attempts (mode: {llm_mode})")
    if _depth == 0:
        print("\n  [FATAL] API Access Denied. Check your endpoint and API key. Do not let the video pipeline continue if script generation fails.")
        sys.exit(1)
    return None



def generate_series_scripts(
    topic: str,
    num_videos: int,
    duration_per_video: int = 60,
    content_type: str = "educational",
    audience: str = "common",
    language: str = "en",
    config: Optional[Dict[str, Any]] = None,
) -> list:
    """
    Generate scripts for a video series.
    Each episode covers a different aspect of the topic.

    Returns:
        List of (episode_title, script_text) tuples
    """
    scripts = []

    subtopics = []

    # Try to generate sub-topics via LLM
    try:
        raw = generate_script(
            topic=f"Generate {num_videos} sub-topics for: {topic}",
            content_type=content_type,
            duration=30,
            audience=audience,
            language=language,
            config=config,
        )
        if raw:
            import re
            lines = raw.strip().split('\n')
            for line in lines:
                line = line.strip()
                match = re.match(r'^\d+[.\)]\s*(.+)', line)
                if match:
                    subtopics.append(match.group(1).strip())
    except Exception as e:
        logger.warning(f"[Script] Failed to generate sub-topics: {e}")

    # Fallback: generate simple numbered episodes
    if len(subtopics) < num_videos:
        subtopics = [f"{topic} - Part {i+1}" for i in range(num_videos)]

    # Trim to exact count
    episode_topics = subtopics[:num_videos]

    # Generate script for each sub-topic with narrative continuity
    for i, subtopic in enumerate(episode_topics):
        logger.info(f"[Script] Generating episode {i+1}/{num_videos}: {subtopic}")

        # ── Build continuity context for the LLM prompt ──
        is_first = (i == 0)
        is_last = (i == num_videos - 1)
        prev_topic = episode_topics[i - 1] if i > 0 else None
        next_topic = episode_topics[i + 1] if i < num_videos - 1 else None

        continuity_parts = []
        continuity_parts.append(f'This is Episode {i+1} of {num_videos} in a series about "{topic}".')

        if is_first and next_topic:
            continuity_parts.append(
                f'SERIES CONTINUITY: This is the first episode. '
                f'End the script with a brief teaser hinting at the next episode\'s topic: "{next_topic}". '
                f'Example ending: "In our next episode... we dive into {next_topic}."'
            )
        elif is_last and prev_topic:
            continuity_parts.append(
                f'SERIES CONTINUITY: This is the final episode. '
                f'Start with a 1-sentence recap referencing the previous episode\'s topic: "{prev_topic}". '
                f'End the script with a concluding wrap-up for the entire series about "{topic}". '
                f'Example ending: "And that wraps up our complete series on {topic}."'
            )
        elif prev_topic and next_topic:
            continuity_parts.append(
                f'SERIES CONTINUITY: This is a middle episode. '
                f'Start with a 1-sentence recap referencing the previous episode\'s topic: "{prev_topic}". '
                f'End with a brief teaser hinting at the next episode\'s topic: "{next_topic}". '
                f'Example recap: "Previously, we explored {prev_topic}." '
                f'Example teaser: "Next time... we tackle {next_topic}."'
            )

        continuity_hint = '\n'.join(continuity_parts)

        script = generate_script(
            topic=subtopic,
            content_type=content_type,
            duration=duration_per_video,
            audience=audience,
            language=language,
            config=config,
            retry_hint=continuity_hint,
        )

        if script:
            scripts.append((subtopic, script))
        else:
            logger.critical(f"[Script] Failed to generate episode {i+1}")
            print("\n  [FATAL] API Access Denied. Check your endpoint and API key. Do not let the video pipeline continue if script generation fails.")
            sys.exit(1)

    return scripts
