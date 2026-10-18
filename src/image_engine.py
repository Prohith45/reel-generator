"""
Image Engine - Wraps the web_scraping/ module with NLP keyword extraction.
Scrapes images per sentence/keyword with aggressive retry logic.
"""

import os
import sys
import re
import time
import json
import random
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ── Monkey-patch undetected_chromedriver to silence WinError 6 on garbage collection ──
try:
    import undetected_chromedriver as uc
    _orig_uc_del = getattr(uc.Chrome, "__del__", None)
    def _safe_uc_del(self):
        try:
            if _orig_uc_del:
                _orig_uc_del(self)
        except OSError:
            pass
        except Exception:
            pass
    uc.Chrome.__del__ = _safe_uc_del
except Exception:
    pass

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
]


def match_local_vector_asset(keywords: List[str]) -> Optional[str]:
    """
    Check if any keyword matches our local premium icon database.
    If matched, generates the icon if missing, and returns the path.
    """
    mapping = {
        'cli': 'assets/icons/terminal.png',
        'terminal': 'assets/icons/terminal.png',
        'commands': 'assets/icons/terminal.png',
        'interface': 'assets/icons/terminal.png',
        
        'database': 'assets/icons/server.png',
        'gguf': 'assets/icons/server.png',
        'quantization': 'assets/icons/server.png',
        'server': 'assets/icons/server.png',
        
        'tts': 'assets/icons/audio.png',
        'speech': 'assets/icons/audio.png',
        'voice': 'assets/icons/audio.png',
        'audio': 'assets/icons/audio.png',
        
        'ai': 'assets/icons/cpu.png',
        'network': 'assets/icons/cpu.png',
        'neural': 'assets/icons/cpu.png',
        'chip': 'assets/icons/cpu.png',
        'processor': 'assets/icons/cpu.png'
    }
    
    for kw in keywords:
        kw_clean = kw.lower().strip()
        if kw_clean in mapping:
            icon_rel_path = mapping[kw_clean]
            icon_path = PROJECT_ROOT / icon_rel_path
            
            # ponytail: Assumes assets/icons exist. Upgrade: handle missing assets gracefully
            if icon_path.exists():
                return str(icon_path)
                
    return None


# ============================================================================
# KEYWORD EXTRACTION — Script-Aware, Topic-Contextualized
# ============================================================================

# Comprehensive stop words — common verbs, pronouns, prepositions, fillers.
# These NEVER carry visual meaning for image searches.
_STOP_WORDS = {
    # articles / determiners
    'the', 'a', 'an', 'this', 'that', 'these', 'those',
    # pronouns
    'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his',
    'she', 'her', 'it', 'its', 'they', 'them', 'their', 'who', 'whom',
    # be / have / do / modal
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'shall', 'can', 'need', 'dare',
    # prepositions / conjunctions
    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
    'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'out', 'off', 'over', 'under', 'up', 'down',
    'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'if', 'than',
    # ── FILLER ADVERBS / TRANSITION WORDS ──
    'again', 'further', 'then', 'once', 'also', 'just', 'very',
    'too', 'only', 'even', 'really', 'actually', 'ever', 'well',
    'here', 'there', 'where', 'when', 'how', 'what', 'which', 'why',
    'about', 'because', 'both', 'each', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'own', 'same', 'every', 'all',
    'basically', 'simply', 'normally', 'usually', 'generally',
    'literally', 'obviously', 'therefore', 'however', 'moreover',
    'furthermore', 'meanwhile', 'nevertheless', 'otherwise',
    'consequently', 'essentially', 'particularly', 'especially',
    'probably', 'perhaps', 'maybe', 'almost', 'already', 'always',
    'never', 'often', 'sometimes', 'rarely', 'certainly', 'definitely',
    'clearly', 'apparently', 'entirely', 'completely', 'absolutely',
    'exactly', 'mostly', 'mainly', 'primarily', 'incredibly',
    'extremely', 'quite', 'rather', 'pretty', 'fairly', 'hardly',
    # generic verbs (too vague to search images)
    'let', 'like', 'think', 'know', 'make', 'get', 'say', 'tell',
    'give', 'take', 'come', 'go', 'see', 'look', 'want', 'use',
    'find', 'put', 'try', 'ask', 'work', 'seem', 'feel', 'leave',
    'call', 'keep', 'start', 'show', 'hear', 'play', 'run', 'move',
    'live', 'believe', 'hold', 'bring', 'happen', 'write', 'provide',
    'sit', 'stand', 'lose', 'pay', 'meet', 'include', 'continue',
    'set', 'learn', 'change', 'lead', 'understand', 'watch', 'follow',
    'stop', 'create', 'speak', 'read', 'allow', 'add', 'spend',
    'grow', 'open', 'walk', 'win', 'offer', 'remember', 'love',
    'consider', 'appear', 'buy', 'wait', 'serve', 'die', 'send',
    'expect', 'build', 'stay', 'fall', 'cut', 'reach', 'kill',
    'remain', 'suggest', 'raise', 'pass', 'sell', 'require', 'report',
    'means', 'mean', 'meant', 'imagine', 'wonder', 'wondered',
    # generic adjectives/adverbs (too vague for visual searches)
    'good', 'great', 'best', 'better', 'bad', 'worse', 'worst',
    'big', 'small', 'large', 'long', 'short', 'high', 'low',
    'old', 'new', 'young', 'first', 'last', 'next', 'different',
    'important', 'real', 'true', 'full', 'whole', 'little',
    'rich', 'helps', 'help', 'helped', 'helping', 'makes',
    'made', 'making', 'used', 'using', 'uses', 'called',
    'become', 'became', 'becoming', 'turn', 'turned', 'known',
    'cool', 'crazy', 'insane', 'amazing', 'incredible', 'awesome',
    'interesting', 'surprising', 'special', 'perfect', 'simple',
    'easy', 'hard', 'fast', 'slow', 'able', 'possible', 'impossible',
    # ── GENERIC STRUCTURE WORDS (visually meaningless) ──
    'file', 'type', 'size', 'number', 'result', 'level', 'point',
    'step', 'example', 'case', 'answer', 'question', 'problem',
    'reason', 'idea', 'concept', 'process', 'method', 'approach',
    'version', 'form', 'format', 'kind', 'bit', 'stuff',
    # number words
    'one', 'two', 'three', 'four', 'five', 'six', 'seven',
    'eight', 'nine', 'ten', 'hundred', 'thousand', 'million',
    # reel-script filler
    'right', 'now', 'today', 'thing', 'things', 'way', 'ways',
    'time', 'times', 'fact', 'much', 'many', 'people', 'something',
    'everything', 'nothing', 'anything', 'someone', 'everyone',
    'lot', 'lots', 'part', 'parts',
    'gonna', 'gotta', 'wanna', 'yeah', 'okay',
    'hey', 'listen', 'guess', 'check', 'ready', 'sure',
    'welcome', 'hello', 'alright', 'video', 'reel', 'watch',
    'subscribe', 'like', 'comment', 'share',
    # narration action words
    'talk', 'explain', 'discuss', 'cover', 'mention', 'describe',
    'explore', 'dive', 'break', 'breaking', 'talking', 'explaining',
    'discussed', 'covered', 'mentioned', 'described', 'explored',
    'reduces', 'reduce', 'reduced', 'reducing',
}

# ── Technical terms to PRESERVE even if short (2+ chars) ──
# These are domain-specific acronyms/keywords that must survive filtering.
_TECHNICAL_TERMS = {
    'ai', 'ml', 'dl', 'nlp', 'llm', 'gpu', 'cpu', 'tpu', 'ram', 'rom',
    'api', 'sdk', 'ide', 'cli', 'gui', 'sql', 'css', 'dns', 'tcp', 'udp',
    'gguf', 'ggml', 'onnx', 'vits', 'tts', 'stt', 'asr', 'ocr',
    'bert', 'gpt', 'lstm', 'rnn', 'cnn', 'gan', 'vae', 'rlhf',
    'cuda', 'vulkan', 'opengl', 'directx', 'webgl',
    'pytorch', 'tensorflow', 'keras', 'numpy', 'pandas',
    'docker', 'kubernetes', 'linux', 'windows', 'macos',
    'bitcoin', 'ethereum', 'blockchain',
    'python', 'javascript', 'rust', 'golang',
    'transformer', 'attention', 'embedding', 'tokenizer', 'tokenization',
    'quantization', 'quantized', 'distillation', 'pruning', 'inference',
    'backpropagation', 'gradient', 'optimizer', 'hyperparameter',
    'neural', 'network', 'neuron', 'perceptron', 'convolution',
    'encoder', 'decoder', 'autoencoder', 'diffusion',
    'deepseek', 'llama', 'mistral', 'falcon', 'gemma', 'phi',
    'openai', 'anthropic', 'huggingface',
    'semiconductor', 'transistor', 'microchip', 'processor',
    'algorithm', 'heuristic', 'optimization',
    'database', 'server', 'cloud', 'microservice',
    'photosynthesis', 'mitochondria', 'chromosome', 'genome',
    'astronomy', 'physics', 'chemistry', 'biology', 'mathematics',
    'satellite', 'telescope', 'microscope', 'spectrum',
    'vaccine', 'antibiotic', 'protein', 'enzyme', 'molecule',
    'encryption', 'decryption', 'cryptography', 'hash', 'cipher',
    'robot', 'robotics', 'automation', 'sensor', 'actuator',
    # ── HARDWARE / ELECTRONICS TERMS ──
    'mosfet', 'igbt', 'bjt', 'diode', 'capacitor', 'inductor',
    'resistor', 'relay', 'smps', 'buck', 'boost', 'flyback',
    'arduino', 'esp32', 'raspberry', 'stm32', 'pic',
    'h-bridge', 'hbridge', 'motor', 'driver', 'pwm',
    'oscillator', 'amplifier', 'rectifier', 'inverter',
    'voltage', 'current', 'impedance', 'frequency',
    'pcb', 'schematic', 'circuit', 'breadboard',
    'soldering', 'multimeter', 'oscilloscope',
    'mppt', 'solar', 'battery', 'charger',
    'http', 'https', 'ssl', 'tls', 'dns', 'tcp', 'udp', 'ip', 'protocol', 'network', 'web', 'internet', 'client', 'server', 'handshake', 'port', 'sockets', 'socket', 'request', 'response', 'header', 'headers', 'payload', 'packet', 'packets', 'routing', 'router', 'gateway', 'dhcp', 'ftp', 'ssh'}


def _naive_singular(word: str) -> str:
    """Cheap singular form for dedup only.
    Only strips the most obvious English plural endings.
    Intentionally conservative to avoid mangling words like 'nutritious'."""
    w = word.lower()
    # Never touch words ending in -ss, -us, -ous, -is, -ies (5+ chars only)
    if w.endswith(('ss', 'us', 'ous', 'is', 'ness')):
        return w
    # berries -> berry, studies -> study
    if w.endswith('ies') and len(w) > 5:
        return w[:-3] + 'y'
    # boxes -> box, watches -> watch (but NOT 'es' at len <= 4 or if stem < 3)
    if w.endswith('es') and len(w) > 5 and w[-3] in 'shxz':
        return w[:-2]
    # bananas -> banana, cats -> cat (simple -s only)
    if w.endswith('s') and not w.endswith('ss') and len(w) > 4:
        return w[:-1]
    return w


def _score_keyword(word: str, original_text: str) -> int:
    """Score a keyword by technical importance. Higher = more relevant for image search.
    
    Scoring:
        +10 : Known technical term (from _TECHNICAL_TERMS)
        +5  : Appears UPPERCASE/CamelCase in original text (likely acronym/proper noun)
        +3  : Word is 7+ chars (longer words tend to be more specific)
        +1  : Base score for any surviving content word
    """
    score = 1  # base
    w_lower = word.lower()
    
    # Known technical term
    if w_lower in _TECHNICAL_TERMS:
        score += 10
    
    # Check if it was uppercase in the original text (acronym/proper noun)
    for orig_word in original_text.split():
        clean_orig = re.sub(r'[^a-zA-Z]', '', orig_word)
        if clean_orig.lower() == w_lower:
            if clean_orig.isupper() and len(clean_orig) >= 2:
                score += 5  # Acronym like GGUF, LLM, AI
            elif clean_orig[0].isupper() and len(clean_orig) > 1:
                score += 2  # Proper noun like Quantization, Transformer
            break
    
    # Longer words tend to be more specific
    if len(w_lower) >= 7:
        score += 3
    elif len(w_lower) >= 5:
        score += 1
    
    return score


def _extract_main_words(text: str, max_words: int = 3) -> List[str]:
    """
    Extract the most meaningful *technical content* words from a sentence.

    Strategy:
        1. Tokenize (2+ chars for acronyms, alpha only).
        2. Preserve known technical terms even if short.
        3. Strip every stop-word / filler.
        4. Score remaining words by technical importance.
        5. Return top-scoring words (max 3).

    Example:
        "GGUF is a file format used for quantized large language models"
        -> ['gguf', 'quantized', 'language']
    """
    # Allow 2+ char words to capture acronyms (AI, ML, DL, etc.)
    # FIRST: strip filler words and numeric headers from the raw text before tokenizing
    fillers = ["basically", "actually", "now", "so", "therefore", "let's see", "in this video"]
    for filler in fillers:
        text = re.sub(r'\b' + re.escape(filler) + r'\b', '', text, flags=re.IGNORECASE)
        
    text = re.sub(r'^\s*\d+[\.)\-]\s*', '', text)
    text = re.sub(r'^(Hook:|Segment\s*\d+:)\s*', '', text, flags=re.IGNORECASE)
    raw_words = re.findall(r'\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*\b', text)
    all_words_lower = [w.lower() for w in raw_words]
    filtered_out = []
    content = []

    for w_lower in all_words_lower:
        # Always keep known technical terms regardless of stop list
        if w_lower in _TECHNICAL_TERMS:
            content.append(w_lower)
        elif w_lower in _STOP_WORDS:
            filtered_out.append(w_lower)
        elif len(w_lower) < 3:
            filtered_out.append(w_lower)  # Too short and not technical
        else:
            content.append(w_lower)

    logger.info(f"[KEYWORDS] Extracted words: {content}")
    logger.info(f"[FILTERED_WORDS] Filtered out stop words: {filtered_out}")

    # Deduplicate while collapsing plurals
    seen_stems = set()
    unique = []
    for w in content:
        stem = _naive_singular(w)
        if stem not in seen_stems:
            seen_stems.add(stem)
            unique.append(stem)

    # Score and sort by technical importance (descending)
    scored = [(w, _score_keyword(w, text)) for w in unique]
    scored.sort(key=lambda x: x[1], reverse=True)

    selected = [w for w, _ in scored[:max_words]]
    logger.info(f"[SELECTED KEYWORDS] Scored: {[(w, s) for w, s in scored[:max_words+2]]} → Selected: {selected}")

    return selected


def _extract_main_words_rake(text: str, max_words: int = 3) -> List[str]:
    """
    Extract main words using RAKE, falling back to the simple extractor.
    RAKE can find multi-word phrases like "neural network" or "blood pressure".
    Post-filters RAKE results through stop-word and technical-term gates.
    """
    # Strip filler words and headers before passing to RAKE
    fillers = ["basically", "actually", "now", "so", "therefore", "let's see", "in this video"]
    for filler in fillers:
        text = re.sub(r'\b' + re.escape(filler) + r'\b', '', text, flags=re.IGNORECASE)
        
    text = re.sub(r'^\s*\d+[\.)\-]\s*', '', text)
    text = re.sub(r'^(Hook:|Segment\s*\d+:)\s*', '', text, flags=re.IGNORECASE)

    try:
        from rake_nltk import Rake
        r = Rake(min_length=1, max_length=3)
        r.extract_keywords_from_text(text)
        phrases = r.get_ranked_phrases()

        # Post-filter: only keep phrases whose words pass the stop-word gate
        result = []
        for phrase in phrases:
            phrase_words = phrase.lower().split()
            # Keep phrase if at least one word is a technical term or content word
            meaningful = [w for w in phrase_words
                          if (w in _TECHNICAL_TERMS or
                              (w not in _STOP_WORDS and len(w) >= 3))]
            if meaningful and len(phrase) > 2:
                result.append(phrase)
            if len(result) >= max_words:
                break

        if result:
            logger.info(f"[KEYWORD EXTRACTION] RAKE phrases: {result}")
            return result[:max_words]

        # RAKE returned nothing useful → fall back
        logger.info("[KEYWORD EXTRACTION] RAKE found nothing, falling back to simple extractor")
        return _extract_main_words(text, max_words)

    except ImportError:
        logger.debug("[KEYWORD EXTRACTION] rake-nltk not installed, using simple extractor")
        return _extract_main_words(text, max_words)
    except Exception as e:
        logger.debug(f"[KEYWORD EXTRACTION] RAKE error: {e}")
        return _extract_main_words(text, max_words)


def _build_search_query(topic: str, main_words: List[str], add_context: bool) -> str:
    """
    Combine topic + main words into ONE search query string.

    Examples (topic = "GGUF model quantization"):
        main_words = ['gguf', 'quantized', 'language']
        → "gguf quantization quantized language"

    If the topic itself already contains one of the words, we avoid duplication.
    """
    # Extract topic's own content words so we can prepend the most meaningful part
    topic_words = _extract_main_words(topic, max_words=2) if topic else []

    if not add_context or not topic_words:
        # No context requested or no topic — just join the sentence words
        return ' '.join(main_words) if main_words else topic

    # Merge topic words + sentence words, avoiding duplication
    merged = list(topic_words)  # start with topic context
    for w in main_words:
        if w.lower() not in {tw.lower() for tw in merged}:
            merged.append(w)

    return ' '.join(merged)


def extract_search_queries(
    sentences: List[Dict],
    topic: str = "",
    config: Optional[Dict] = None,
) -> List[Dict]:
    """
    Extract image search queries for each sentence in the script.

    For each sentence we:
      1. Use NLP / stop words filtering to extract distinct keywords from the sentence text.
      2. Prioritize sentence-only distinct keywords.
      3. Combine dynamically with visual engineering modifiers.

    Returns:
        List of dicts with 'sentence', 'queries', 'start', 'end' keys
    """
    cfg = (config or {}).get("scraping", {}).get("keyword_extraction", {})
    max_kw = cfg.get("max_keywords_per_sentence", 3)

    results = []
    for sent_idx, sent_data in enumerate(sentences):
        text = sent_data.get("text", "")
        
        import re
        text = re.sub(r'^\s*\d+[\.\)]\s*', '', text).strip()
        text = re.sub(r'^Hook:\s*|^Segment\s*\d+:\s*', '', text, flags=re.IGNORECASE).strip()
        
        # Validation filter
        alnum_chars = re.sub(r'[^a-zA-Z0-9]', '', text)
        if len(alnum_chars) < 4:
            logger.info(f"[Image] Skipping query extraction for sentence {sent_idx + 1} with insufficient content: '{text}'")
            continue

        logger.info(f"[SEGMENT] Sentence {sent_idx + 1}: \"{text[:80]}\"")

        # Extract distinct keywords purely from the sentence text
        main_words = _extract_main_words(text, max_words=max_kw)

        # Build search queries purely from the sentence keywords combined with visual modifiers
        queries = []
        if main_words:
            segment_keywords = ' '.join(main_words)
            query = f"{topic} {segment_keywords}".strip()
            queries.append(query)
        else:
            fallback_words = [w for w in text.split()[:5] if w.lower() not in _STOP_WORDS]
            if not fallback_words:
                fallback_words = text.split()[:5]
            if fallback_words:
                segment_keywords = ' '.join(fallback_words)
                query = f"{topic} {segment_keywords}".strip()
                queries.append(query)

        logger.info(f"[IMAGE SEARCH] Final queries for sentence {sent_idx + 1}: {queries}")

        results.append({
            "sentence": text,
            "queries": queries,
            "start": sent_data.get("start", 0),
            "end": sent_data.get("end", 0),
        })

    return results


# ============================================================================
# IMAGE SCRAPING
# ============================================================================

def is_technical_domain(url: str) -> bool:
    whitelist = [
        'wikimedia.org', 'wikipedia.org', 'circuitdigest.com', 'allaboutcircuits.com', 
        'electronics-tutorials.ws', 'researchgate.net', 'ieee.org', 'ti.com', 'analog.com',
        'cloudflare.com', 'geeksforgeeks.org', 'medium.com', 'tutorialspoint.com', 
        'javatpoint.com', 'w3schools.com', 'gitconnected.com', 'mdn.mozilla.net', 
        'dev.to', 'github.com', 'cheapsslsecurity.com', 'thesslstore.com', 
        'namtech.com.au', 'linkgraph.com', 'teachoo.com', 'researchhubs.com'
    ]
    blacklist = ['pinterest', 'shutterstock', 'freepik', 'vector', 'poster', 'gettyimages', 'dreamstime', 'alamy']
    url_lower = url.lower()
    if any(b in url_lower for b in blacklist):
        return False
    return any(w in url_lower for w in whitelist)

def safe_scrape(query: str, count: int, session: requests.Session, keywords: list = None, mode: str = 'default') -> list:
    max_retries = 3
    import time
    for attempt in range(1, max_retries + 1):
        urls = []
        try:
            urls = _scrape_ddg_api(query, count=count, keywords=keywords, mode=mode)
        except Exception as e:
            logger.warning(f"[Image] DDG scrape failed: {e}")
            
        if not urls:
            try:
                urls = _scrape_google_api(query, count=count, session=session)
            except Exception as e:
                pass
                
        if not urls:
            try:
                urls = _scrape_bing_api(query, count=count, session=session)
            except Exception as e:
                pass
                
        filtered_urls = []
        for u in urls:
            # Check score of fallback URLs too
            score = score_image_relevance({'image': u}, keywords or [], mode)
            if score >= MIN_IMAGE_SCORE and is_technical_domain(u) and u not in filtered_urls:
                logger.info(f"[FALLBACK_ACCEPTED] [IMAGE_SCORE: {score}] URL: {u}")
                filtered_urls.append(u)
            else:
                if score < MIN_IMAGE_SCORE:
                    logger.info(f"[FALLBACK_REJECTED] [IMAGE_SCORE: {score} < {MIN_IMAGE_SCORE}] URL: {u}")
                
        if filtered_urls:
            return filtered_urls
            
        delay = (2 ** attempt) * 5
        logger.warning(f"[Image] Rate limit or empty results. Retrying in {delay} seconds (Attempt {attempt}/{max_retries})")
        time.sleep(delay)
        
    return []



def _create_session() -> requests.Session:
    """Create a robust requests session with retry logic."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    ua = random.choice(USER_AGENTS)
    session.headers.update({
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml',
        'Accept-Language': 'en-US,en;q=0.9',
        'DNT': '1',
    })
    
    return session


# ────────────────────────────────────────────────────────────
# THREE-TIER VISUAL MODE ROUTER
# ────────────────────────────────────────────────────────────

# Hardware components/electronics
_HARDWARE_KEYWORDS = {
    'mosfet', 'transistor', 'buck', 'boost', 'converter', 'esp32', 'arduino',
    'relay', 'smps', 'resistor', 'capacitor', 'inductor', 'diode', 'rectifier',
    'h-bridge', 'hbridge', 'motor', 'driver', 'circuit', 'schematic', 'pcb',
    'breadboard', 'soldering', 'oscilloscope', 'multimeter', 'amplifier',
    'inverter', 'regulator', 'voltage', 'current', 'impedance', 'frequency',
    'pwm', 'igbt', 'bjt', 'flyback', 'mppt', 'solar', 'battery', 'charger',
    'stm32', 'pic', 'microcontroller', 'raspberry', 'semiconductor', 'switch',
    'led', 'oled', 'lcd', 'adc', 'dac', 'sensor', 'actuator',
}

# Abstract software / CS / AI concepts
_SOFTWARE_KEYWORDS = {
    'gguf', 'quantization', 'llm', 'transformer', 'neural', 'network', 'rag',
    'algorithm', 'attention', 'embedding', 'tokenizer', 'inference', 'diffusion',
    'gradient', 'backpropagation', 'optimizer', 'encoder', 'decoder',
    'autoencoder', 'convolution', 'perceptron', 'distillation', 'pruning',
    'bert', 'gpt', 'lstm', 'rnn', 'cnn', 'gan', 'vae', 'rlhf',
    'kubernetes', 'docker', 'microservice', 'api', 'database', 'sql',
    'encryption', 'cryptography', 'blockchain', 'hash', 'cipher',
    'software', 'architecture', 'pipeline', 'framework', 'library',
}

# Brand names / companies / platforms
_BRAND_KEYWORDS = {
    'github', 'whatsapp', 'google', 'openai', 'microsoft', 'meta', 'youtube',
    'instagram', 'facebook', 'twitter', 'tiktok', 'linkedin', 'nvidia',
    'amd', 'intel', 'apple', 'samsung', 'huggingface', 'anthropic',
    'deepseek', 'mistral', 'tesla', 'spacex', 'amazon', 'aws', 'azure',
    'pytorch', 'tensorflow', 'keras',
}


def preprocess_search_query(query: str) -> str:
    """Preprocess query to refine ambiguous terms like 'mobile charger'."""
    # Refine "mobile charger" or "mobile chargers" to "mobile phone charger(s)"
    q = re.sub(r'\bmobile\s+charger', 'mobile phone charger', query, flags=re.IGNORECASE)
    return q


def determine_image_search_mode(keywords: List[str]) -> str:
    """Evaluate keywords and return the appropriate search mode.
    
    Priority order: HARDWARE > SOFTWARE > BRAND > DEFAULT
    """
    kws = [k.lower().strip() for k in keywords]
    query_lower = ' '.join(kws)
    
    if any(k in _HARDWARE_KEYWORDS for k in kws):
        return 'hardware'
    if (any(k in _SOFTWARE_KEYWORDS for k in kws) or 
        'neural network' in query_lower or 
        ('neural' in kws and 'network' in kws)):
        return 'software'
    if any(k in _BRAND_KEYWORDS for k in kws):
        return 'brand'
    return 'default'


def engineer_visual_query(raw_query) -> str:
    if isinstance(raw_query, list):
        query_str = ' '.join(raw_query).strip()
    else:
        query_str = str(raw_query).strip()
    return query_str



TRUSTED_DOMAINS = {
    # Technology & Software
    'github.com', 'raw.githubusercontent.com', 'docs.github.com',
    'microsoft.com', 'learn.microsoft.com',
    'openai.com',
    'google.com', 'developers.google.com',
    'meta.com', 'engineering.fb.com',
    'huggingface.co',
    'ollama.com',
    'docker.com', 'docs.docker.com',
    'kubernetes.io',
    'python.org',
    'mozilla.org',
    'ubuntu.com',
    'linux.org',
    'redhat.com',
    'cloudflare.com',
    'nginx.org',
    'apache.org',
    'tensorflow.org',
    'pytorch.org',
    'arduino.cc', 'raspberrypi.com', 'espressif.com', 'platformio.org',
    'autodesk.com', 'solidworks.com', 'onshape.com', 'ansys.com',
    # Engineering & Electronics
    'allaboutcircuits.com', 'electronics-tutorials.ws', 'circuitdigest.com',
    'electronicshub.org', 'sparkfun.com', 'adafruit.com',
    'ti.com', 'analog.com', 'microchip.com', 'st.com', 'infineon.com', 'nxp.com',
    'maximintegrated.com',
    # Scientific & Educational
    'wikipedia.org', 'wikimedia.org', 'commons.wikimedia.org',
    'britannica.com', 'nasa.gov', 'esa.int', 'nist.gov',
    'mit.edu', 'stanford.edu', 'harvard.edu', 'berkeley.edu',
    'coursera.org', 'edx.org', 'khanacademy.org',
    # Logos & Brand Assets
    'logo.clearbit.com', 'brandfetch.io', 'simpleicons.org', 'vectorlogo.zone', 'worldvectorlogo.com',
    # AI & Machine Learning
    'anthropic.com', 'deepseek.com', 'mistral.ai', 'stability.ai', 'llama.com', 'ai.meta.com'
}

MIN_IMAGE_SCORE = 20

def score_image_relevance(result: dict, keywords: list, mode: str, topic: str = "") -> int:
    score = 0
    title = result.get('title', '').lower()
    img_url = result.get('image', '').lower()
    
    # If title is empty, try to extract words from the URL filename
    if not title and img_url:
        import os
        filename = os.path.basename(img_url)
        filename_no_ext, _ = os.path.splitext(filename)
        title = filename_no_ext.replace('-', ' ').replace('_', ' ').lower()
        
    # 1. Domain Trust Score (+40)
    from urllib.parse import urlparse
    try:
        parsed_url = urlparse(img_url)
        domain = parsed_url.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        is_trusted = False
        for td in TRUSTED_DOMAINS:
            if domain == td or domain.endswith("." + td):
                is_trusted = True
                break
        if is_trusted:
            score += 40
            logger.debug(f"[IMAGE_SCORE] Domain {domain} is trusted (+40)")
    except Exception:
        pass
        
    # 2. Keyword Match (+30)
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in title or kw_lower in img_url:
            score += 30
            logger.debug(f"[IMAGE_SCORE] Keyword '{kw_lower}' matched in title/url (+30)")
            break
            
    # 3. Page Title Match (+20)
    if topic:
        topic_words = [w.lower() for w in topic.split() if len(w) > 2]
        matched_topic_words = [tw for tw in topic_words if tw in title]
        if matched_topic_words:
            score += 20
            logger.debug(f"[IMAGE_SCORE] Topic words {matched_topic_words} matched title (+20)")
            
    # 4. Metadata Match (+10)
    meta_keywords = ['diagram', 'schematic', 'architecture', 'illustration', 'vector', 'logo', 'educational', 'tutorial', 'learn']
    for mk in meta_keywords:
        if mk in title or mk in img_url:
            score += 10
            logger.debug(f"[IMAGE_SCORE] Technical metadata '{mk}' matched (+10)")
            break
            
    stock_terms = ['stock', 'pinterest', 'shutterstock', 'vector', 'alamy', 'dreamstime', 'getty', 'depositphotos', '123rf', 'freepik']
    if any(st in img_url for st in stock_terms) or any(st in title for st in stock_terms):
        score -= 100
        logger.debug(f"[IMAGE_SCORE] Rejected due to stock/blacklist term")
        
    return score

def _scrape_ddg_api(query: str, count: int = 5, keywords: list = None, mode: str = 'default') -> list:
    query = preprocess_search_query(query)
    wait_time = 1.0  # Reduced wait time since library handles rate limits better
    logger.info(f"[DUCKDUCKGO_SEARCH] Query: '{query}', Sleeping {wait_time:.1f}s")
    import time
    time.sleep(wait_time)
    
    urls = []
    
    def perform_search(search_query):
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
                
            with DDGS() as ddgs:
                # We fetch a larger pool to score
                results = list(ddgs.images(search_query, region="wt-wt", safesearch="off", max_results=count*4))
                
                scored_results = []
                for r in results:
                    score = score_image_relevance(r, keywords or [], mode)
                    scored_results.append((score, r))
                    
                # Sort highest scores first
                scored_results.sort(key=lambda x: x[0], reverse=True)
                
                valid_urls = []
                for score, r in scored_results:
                    img_url = r.get('image')
                    if score < MIN_IMAGE_SCORE:
                        logger.info(f"[IMAGE_REJECTED] [IMAGE_SCORE: {score} < {MIN_IMAGE_SCORE}] Title: '{r.get('title')}'")
                        continue
                        
                    if img_url and img_url not in valid_urls:
                        logger.info(f"[IMAGE_ACCEPTED] [IMAGE_SCORE: {score}] Title: '{r.get('title')}' URL: {img_url}")
                        valid_urls.append(img_url)
                    if len(valid_urls) >= count:
                        break
                return valid_urls
        except Exception as e:
            logger.warning(f"[DUCKDUCKGO_SEARCH] Search failed for '{search_query}': {e}")
            return []

    urls = perform_search(query)
    return urls


def _scrape_bing_api(query: str, count: int = 5, session: requests.Session = None) -> List[str]:
    """Scrape image URLs from Bing using Selenium."""
    query = preprocess_search_query(query)
    wait_time = random.uniform(8, 12)
    logger.info(f"[Image] Respecting rate limit, sleeping for {wait_time:.2f} seconds before Bing call for: '{query}'")
    time.sleep(wait_time)
    urls = []
    
    engineered_query = query
    logger.info(f"[Image] Searching Bing query: '{engineered_query}'")
    
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        # Inject randomized User-Agent and headers
        ua = random.choice(USER_AGENTS)
        options.add_argument(f'--user-agent={ua}')
        options.add_argument('--lang=en-US')
        
        driver = uc.Chrome(options=options)
        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml'
            }
        })
        driver.set_page_load_timeout(15)
        driver.implicitly_wait(4)
        
        try:
            # Append &qft=+filterui:aspect-wide to rigidly ask Bing for landscape images
            search_url = f"https://www.bing.com/images/search?q={quote(engineered_query)}&qft=+filterui:aspect-wide"
            driver.get(search_url)
            time.sleep(random.uniform(2, 3))
            
            # Scroll to load images
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            
            # Extract image URLs
            elements = driver.find_elements(By.CSS_SELECTOR, "a.iusc")
            
            for elem in elements:
                if len(urls) >= count:
                    break
                try:
                    m_attr = elem.get_attribute('m')
                    if m_attr:
                        metadata = json.loads(m_attr)
                        url = metadata.get('murl') or metadata.get('turl')
                        if url and is_technical_domain(url) and url not in urls:
                            urls.append(url)
                except Exception:
                    try:
                        driver.execute_script("window.stop();")
                    except Exception:
                        pass
                    continue
        finally:
            driver.quit()
    except Exception as e:
        logger.warning(f"[Image] Bing scrape failed for '{query}': {e}")
    
    return urls


def _download_single_image(
    url: str,
    save_path: str,
    session: requests.Session,
    max_retries: int = 1,
    retry_delay: float = 1.0,
    retry_backoff: float = 1.0,
    min_width: int = 400,
    min_height: int = 300,
    timeout: float = 4.0,
    seen_hashes: Optional[set] = None,
) -> Optional[str]:
    from PIL import Image
    from io import BytesIO
    import imagehash
    import binascii
    import time
    from pathlib import Path
    
    CACHE_DIR = PROJECT_ROOT / "cache" / "images"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Use binascii.crc32 to generate a deterministic cache filename hash
    url_hash_val = binascii.crc32(url.encode('utf-8')) & 0xffffffff
    url_hash = f"{url_hash_val:08x}"
    cache_path = CACHE_DIR / f"{url_hash}.jpg"
    
    if cache_path.exists():
        if seen_hashes is not None:
            try:
                # Open cached image to calculate pHash
                with Image.open(cache_path) as img_obj:
                    img_hash = imagehash.phash(img_obj)
                
                # Check Hamming distance against all seen hashes
                duplicate_found = False
                for existing_hash in seen_hashes:
                    if img_hash - existing_hash <= 5:
                        duplicate_found = True
                        break
                
                if duplicate_found:
                    logger.info(f"[Image] Duplicate image detected via cache pHash (Hamming distance <= 5): {url}")
                    return None
                seen_hashes.add(img_hash)
            except Exception as e:
                logger.warning(f"[Image] Failed to read cache for pHash check: {e}")
        import shutil
        shutil.copy(cache_path, save_path)
        logger.info(f"[CACHE] Reused existing image: {url}")
        return save_path

    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type.lower() and 'octet-stream' not in content_type.lower():
                return None
            
            image_bytes = response.content
            
            # Load the image to verify size, format, and calculate pHash
            img = Image.open(BytesIO(image_bytes))
            
            if img.width < min_width or img.height < min_height:
                return None
                
            if img.height > img.width:
                return None
                
            # Calculate pHash
            img_hash = imagehash.phash(img)
            
            if seen_hashes is not None:
                duplicate_found = False
                for existing_hash in seen_hashes:
                    if img_hash - existing_hash <= 5:
                        duplicate_found = True
                        break
                
                if duplicate_found:
                    logger.info(f"[Image] Duplicate image detected via image pHash (Hamming distance <= 5): {url}")
                    return None
                seen_hashes.add(img_hash)
            
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            img.save(save_path, 'JPEG', quality=90)
            
            # Save to cache
            import shutil
            shutil.copy(save_path, cache_path)
            
            logger.debug(f"[Image] Downloaded: {Path(save_path).name}")
            return save_path
            
        except requests.exceptions.Timeout:
            pass
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            pass
        
        if attempt < max_retries:
            delay = retry_delay * (retry_backoff ** (attempt - 1))
            time.sleep(delay)
    
    return None


def filter_url(url: str, strict: bool = True) -> bool:
    forbidden = ['gettyimages', 'stockphoto', 'clipart', 'shutterstock', 'dreamstime', '123rf', 'istockphoto', 'alamy', 'vectorstock', 'depositphotos']
    if any(bad in url.lower() for bad in forbidden):
        return False
        
    if strict:
        allowed = ['wikimedia.org', 'wikipedia.org', 'circuitdigest.com', 'allaboutcircuits.com', 'electronics-tutorials.ws']
        allowed_domains = allowed + ['.edu']
        if not any(domain in url.lower() for domain in allowed_domains):
            return False
            
    return True


def prioritize_urls(urls: List[str]) -> List[str]:
    priority_domains = ['wikimedia.org', 'wikipedia.org', '.edu']
    priority = []
    others = []
    for url in urls:
        if any(dom in url.lower() for dom in priority_domains):
            priority.append(url)
        else:
            others.append(url)
    return priority + others


def _scrape_google_api(query: str, count: int = 5, session: requests.Session = None) -> List[str]:
    """Scrape image URLs from Google Images using Selenium."""
    query = preprocess_search_query(query)
    wait_time = random.uniform(8, 12)
    logger.info(f"[Image] Respecting rate limit, sleeping for {wait_time:.2f} seconds before Google call for: '{query}'")
    time.sleep(wait_time)
    urls = []
    engineered_query = query
    logger.info(f"[Image] Searching Google query: '{engineered_query}'")
    
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        # Inject randomized User-Agent and headers
        ua = random.choice(USER_AGENTS)
        options.add_argument(f'--user-agent={ua}')
        options.add_argument('--lang=en-US')
        
        driver = uc.Chrome(options=options)
        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml'
            }
        })
        driver.set_page_load_timeout(15)
        driver.implicitly_wait(4)
        
        try:
            search_url = f"https://www.google.com/search?q={quote(engineered_query)}&tbm=isch"
            try:
                driver.get(search_url)
            except Exception as e:
                logger.warning(f"[Image] Google page load timeout or issue (continuing anyway): {e}")
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass
            time.sleep(random.uniform(2, 3))
            
            for _ in range(2):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            
            elements = driver.find_elements(By.CSS_SELECTOR, "img")
            for elem in elements:
                if len(urls) >= count:
                    break
                try:
                    src = elem.get_attribute('src') or elem.get_attribute('data-src')
                    if src and src.startswith('http') and 'google' not in src:
                        if is_technical_domain(src) and src not in urls:
                            urls.append(src)
                except Exception:
                    continue
                    
            if len(urls) < count:
                elements = driver.find_elements(By.CSS_SELECTOR, "a img")
                for elem in elements:
                    if len(urls) >= count:
                        break
                    try:
                        src = elem.get_attribute('src') or elem.get_attribute('data-src')
                        if src and src.startswith('http') and is_technical_domain(src) and src not in urls:
                            urls.append(src)
                    except Exception:
                        continue
        finally:
            driver.quit()
    except Exception as e:
        logger.warning(f"[Image] Google scrape failed for '{query}': {e}")
    return urls


def scrape_primary_topic_images(
    topic: str,
    count: int = 15,
    output_path: Optional[Path] = None,
    session: Optional[requests.Session] = None,
    config: Optional[Dict] = None,
    global_scraped_urls: Optional[set] = None
) -> List[str]:
    logger.info(f"[Image] Phase 1 (Topic Anchor): Scraping primary topic images for '{topic}'")
    
    if output_path is None:
        output_path = PROJECT_ROOT / "outputs" / "images" / topic.replace(" ", "_")
    output_path = Path(os.path.abspath(str(output_path)))
    output_path.mkdir(parents=True, exist_ok=True)
    
    if session is None:
        session = _create_session()
        
    topic_keywords = _extract_main_words(topic, max_words=5)
    mode = determine_image_search_mode(topic_keywords)
    urls = safe_scrape(topic, count=count * 2, session=session, keywords=topic_keywords, mode=mode)
        
    topic_assets = []
    if not urls:
        logger.warning(f"[Image] No URLs found for topic anchor '{topic}'")
        return topic_assets

    processed_urls = urls
    
    cfg = (config or {}).get("scraping", {})
    min_width = cfg.get("min_image_width", 400)
    min_height = cfg.get("min_image_height", 300)
    
    seen_hashes = set()
    for url in processed_urls:
        if len(topic_assets) >= count:
            break
        if global_scraped_urls is not None and url in global_scraped_urls:
            continue
        filename = f"topic_anchor_{len(topic_assets):02d}.jpg"
        save_path = str(output_path / filename)
        try:
            downloaded = _download_single_image(
                url, save_path, session,
                max_retries=1,
                timeout=4.0,
                min_width=min_width,
                min_height=min_height,
                seen_hashes=seen_hashes
            )
            if downloaded:
                topic_assets.append(downloaded)
                if global_scraped_urls is not None:
                    global_scraped_urls.add(url)
        except Exception as e:
            logger.warning(f"[Image] Failed to download primary topic anchor image {url}: {e}")
            
    logger.info(f"[Image] Phase 1 completed. Collected {len(topic_assets)} primary topic images.")
    return topic_assets


def _fetch_mixkit_broll(core_topic: str, needed_count: int, output_dir: str, config: Dict, seen_urls: Optional[set] = None, seen_sizes: Optional[set] = None) -> List[str]:
    """
    Tier 1: Mixkit Free Stock Video Scraper.
    Parses HTML for video cards matching core_topic keywords and downloads highest available resolution.
    """
    if needed_count <= 0:
        return []
    mixkit_cfg = config.get("broll", {}).get("mixkit", {})
    if not mixkit_cfg.get("enabled", True):
        return []

    downloaded = []
    topic_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]+\b', core_topic) if len(w) > 2]
    if not topic_words:
        topic_words = [core_topic.lower()]

    slug_topic = core_topic.replace(' ', '-')
    urls = [
        f"https://mixkit.co/free-stock-video/{slug_topic}/",
        f"https://mixkit.co/free-stock-video/search/?q={quote(core_topic)}",
    ]

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    candidates = []
    local_seen = set() if seen_urls is None else seen_urls

    for url in urls:
        if len(candidates) >= needed_count:
            break
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            html = resp.text
            video_matches = list(re.finditer(r'<video[^>]+src=[\'"](https://assets\.mixkit\.co/videos/[^\'"]+\.mp4)[\'"][^>]*>', html, re.IGNORECASE))
            for vm in video_matches:
                video_url = vm.group(1)
                if video_url in local_seen:
                    continue

                start = max(0, vm.start() - 600)
                end = min(len(html), vm.end() + 600)
                chunk = html[start:end]

                alt_match = re.search(r'alt=[\'"]([^\'"]+)[\'"]', chunk, re.IGNORECASE)
                alt_text = alt_match.group(1).lower() if alt_match else ""

                link_match = re.search(r'<a[^>]+href=[\'"](/free-stock-video/[^\'"]+)[\'"][^>]*>(.*?)</a>', chunk, re.DOTALL | re.IGNORECASE)
                slug = link_match.group(1).lower() if link_match else ""
                title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip().lower() if link_match else ""

                combined_text = f"{alt_text} {slug} {title}"
                # Strict Relevance Check: Require at least one word from core_topic to appear in title, alt text, or URL slug
                if any(w in combined_text for w in topic_words):
                    local_seen.add(video_url)
                    candidates.append(video_url)
                    if len(candidates) >= needed_count:
                        break
        except Exception as e:
            logger.debug(f"[Mixkit] Request error for {url}: {e}")

    for idx, cand_url in enumerate(candidates):
        best_url = cand_url
        for res_suffix in ["-720.mp4", "-large.mp4"]:
            if "-360.mp4" in cand_url:
                target_cand = cand_url.replace("-360.mp4", res_suffix)
            elif "-preview.mp4" in cand_url:
                target_cand = cand_url.replace("-preview.mp4", res_suffix)
            elif "-small.mp4" in cand_url:
                target_cand = cand_url.replace("-small.mp4", res_suffix)
            else:
                target_cand = cand_url

            if target_cand != cand_url:
                try:
                    head_resp = requests.head(target_cand, headers=headers, timeout=5)
                    if head_resp.status_code == 200:
                        best_url = target_cand
                        break
                except Exception:
                    pass

        save_path = os.path.abspath(os.path.join(output_dir, f"broll_mixkit_{len(downloaded)}.mp4"))
        try:
            with requests.get(best_url, headers=headers, stream=True, timeout=15) as vr:
                if vr.status_code == 200:
                    with open(save_path, "wb") as f:
                        for chunk in vr.iter_content(chunk_size=8192):
                            f.write(chunk)
                    if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
                        fsize = os.path.getsize(save_path)
                        if seen_sizes is not None and fsize in seen_sizes:
                            logger.info(f"[Mixkit] Duplicate B-roll detected by file size ({fsize} bytes). Discarding: {save_path}")
                            try:
                                os.remove(save_path)
                            except Exception:
                                pass
                            continue
                        if seen_sizes is not None:
                            seen_sizes.add(fsize)
                        downloaded.append(save_path)
                        logger.info(f"[Mixkit] Downloaded relevant B-roll ({len(downloaded)}/{needed_count}): {save_path}")
        except Exception as e:
            logger.warning(f"[Mixkit] Failed downloading {best_url}: {e}")

    return downloaded


def _fetch_tenor_broll(core_topic: str, needed_count: int, output_dir: str, config: Dict, seen_urls: Optional[set] = None, seen_sizes: Optional[set] = None) -> List[str]:
    """
    Tier 2: Tenor API Scraper for technical MP4 loops with strict anti-meme, topic relevance, and duration filtering.
    """
    if needed_count <= 0:
        return []
    tenor_cfg = config.get("broll", {}).get("tenor", {})
    if not tenor_cfg.get("enabled", True):
        return []

    tenor_key = os.environ.get("TENOR_API_KEY") or tenor_cfg.get("api_key", "")
    if not tenor_key:
        logger.debug("[Tenor] TENOR_API_KEY not set. Skipping Tenor B-roll.")
        return []
    append_context = tenor_cfg.get("append_context", "animation")
    blocked_tags = [t.lower() for t in tenor_cfg.get("blocked_tags", ["meme", "funny", "reaction", "cartoon", "anime", "laugh", "cute"])]

    downloaded = []
    topic_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]+\b', core_topic) if len(w) > 2]
    if not topic_words:
        topic_words = [core_topic.lower()]

    query = f"{core_topic} {append_context}".strip()
    tenor_url = f"https://g.tenor.com/v1/search?q={quote(query)}&key={tenor_key}&limit=15&media_filter=minimal"

    local_seen = set() if seen_urls is None else seen_urls

    try:
        resp = requests.get(tenor_url, timeout=10)
        results = []
        if resp.status_code == 200:
            results = resp.json().get("results", [])
        else:
            # Fallback to Tenor v2 if user provided a Google Cloud key
            v2_url = f"https://tenor.googleapis.com/v2/search?q={quote(query)}&key={tenor_key}&limit=15"
            resp2 = requests.get(v2_url, timeout=10)
            if resp2.status_code == 200:
                results = resp2.json().get("results", [])

        for item in results:
            if len(downloaded) >= needed_count:
                break

            item_tags = [str(t).lower() for t in item.get("tags", [])]
            content_desc = item.get("content_description", "").lower()
            item_url = item.get("url", "").lower()

            # Anti-Meme Filter: Reject any result that contains any blocked tag
            if any(bt in content_desc for bt in blocked_tags) or any(bt in tag for tag in item_tags for bt in blocked_tags):
                continue

            # Topic Relevance Check: Require core_topic to appear in content_description or item['url']
            if not any(w in content_desc or w in item_url for w in topic_words):
                continue

            # Extract MP4 stream (never .gif, always native mp4 stream)
            mp4_url = None
            media_list = item.get("media", [])
            if media_list and isinstance(media_list, list):
                mp4_item = media_list[0].get("mp4", {})
                mp4_url = mp4_item.get("url")
                # Pre-check duration in JSON if available
                t_dur = mp4_item.get("duration", 0)
                if 0 < t_dur < 2.5:
                    logger.debug(f"[Tenor] Skipping clip: reported duration {t_dur:.1f}s < 2.5s")
                    continue
            if not mp4_url:
                media_formats = item.get("media_formats", {})
                mp4_url = media_formats.get("mp4", {}).get("url") or media_formats.get("tiny_mp4", {}).get("url")

            if not mp4_url or not mp4_url.split('?')[0].endswith(".mp4"):
                continue

            if mp4_url in local_seen:
                continue

            save_path = os.path.abspath(os.path.join(output_dir, f"broll_tenor_{len(downloaded)}.mp4"))
            try:
                vr = requests.get(mp4_url, stream=True, timeout=15)
                if vr.status_code == 200:
                    with open(save_path, "wb") as f:
                        for chunk in vr.iter_content(chunk_size=8192):
                            f.write(chunk)
                    if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
                        fsize = os.path.getsize(save_path)
                        if seen_sizes is not None and fsize in seen_sizes:
                            logger.info(f"[Tenor] Duplicate B-roll detected by file size ({fsize} bytes). Discarding: {save_path}")
                            try:
                                os.remove(save_path)
                            except Exception:
                                pass
                            continue

                        # Verify duration is >= 2.5 seconds using MoviePy
                        try:
                            from moviepy import VideoFileClip
                            with VideoFileClip(save_path) as tc:
                                clip_dur = tc.duration
                            if clip_dur < 2.5:
                                logger.info(f"[Tenor] Skipping clip {save_path}: duration {clip_dur:.2f}s < 2.5s")
                                try:
                                    os.remove(save_path)
                                except Exception:
                                    pass
                                continue
                        except Exception as dur_err:
                            logger.debug(f"[Tenor] Could not verify clip duration: {dur_err}")

                        local_seen.add(mp4_url)
                        if seen_sizes is not None:
                            seen_sizes.add(fsize)
                        downloaded.append(save_path)
                        logger.info(f"[Tenor] Downloaded relevant B-roll ({len(downloaded)}/{needed_count}): {save_path}")
            except Exception as e:
                logger.warning(f"[Tenor] Failed downloading {mp4_url}: {e}")

    except Exception as e:
        logger.warning(f"[Tenor] Failed to query Tenor API: {e}")

    return downloaded


def _fetch_pexels_broll(core_topic: str, needed_count: int, output_dir: str, config: Dict, seen_urls: Optional[set] = None, seen_sizes: Optional[set] = None) -> List[str]:
    """
    Tier 3: Pexels Video API with strict slug verification.
    Only accepts videos whose URL slug contains at least one word from core_topic.
    """
    if needed_count <= 0:
        return []
    pexels_cfg = config.get("broll", {}).get("pexels", {}) or config.get("pexels", {})
    if not pexels_cfg.get("enabled", True):
        return []

    api_key = os.environ.get("PEXELS_API_KEY") or pexels_cfg.get("api_key", "")
    if not api_key:
        return []

    downloaded = []
    topic_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]+\b', core_topic) if len(w) > 2]
    if not topic_words:
        topic_words = [core_topic.lower()]

    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={quote(core_topic)}&per_page=15"

    local_seen = set() if seen_urls is None else seen_urls

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            videos = resp.json().get("videos", [])
            for v in videos:
                if len(downloaded) >= needed_count:
                    break

                v_url = v.get("url", "")
                slug_match = re.search(r'/video/([^/]+)/?', v_url)
                slug = slug_match.group(1).lower() if slug_match else ""

                # Strict Slug Verification: Only accept if a word from core_topic is explicitly in slug
                if not any(w in slug for w in topic_words):
                    logger.debug(f"[Pexels] Rejecting irrelevant slug '{slug}' for topic words {topic_words}")
                    continue

                best_video = None
                best_res = 0
                for vf in v.get("video_files", []):
                    res = vf.get("width", 0) * vf.get("height", 0)
                    if res > best_res and vf.get("link"):
                        best_res = res
                        best_video = vf.get("link")

                if best_video:
                    if best_video in local_seen:
                        continue

                    save_path = os.path.abspath(os.path.join(output_dir, f"broll_pexels_{len(downloaded)}.mp4"))
                    vr = requests.get(best_video, stream=True, timeout=15)
                    if vr.status_code == 200:
                        with open(save_path, "wb") as f:
                            for chunk in vr.iter_content(chunk_size=8192):
                                f.write(chunk)
                        if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
                            fsize = os.path.getsize(save_path)
                            if seen_sizes is not None and fsize in seen_sizes:
                                logger.info(f"[Pexels] Duplicate B-roll detected by file size ({fsize} bytes). Discarding: {save_path}")
                                try:
                                    os.remove(save_path)
                                except Exception:
                                    pass
                                continue
                            if seen_sizes is not None:
                                seen_sizes.add(fsize)
                            local_seen.add(best_video)
                            downloaded.append(save_path)
                            logger.info(f"[Pexels] Downloaded relevant B-roll ({len(downloaded)}/{needed_count}): {save_path}")
    except Exception as e:
        logger.warning(f"[Pexels] Failed to fetch B-roll: {e}")

    return downloaded


def fetch_generic_broll(topic: str, target_duration: float, config: Dict, output_dir: str) -> List[str]:
    """
    Strict 3-Tier Waterfall B-Roll Engine (Mixkit -> Tenor -> Pexels).
    Enforces strict topic relevance and never falls back to generic unrelated footage.
    """
    broll_list = []
    if config.get("video", {}).get("visual_mode") == "images" or not config.get("broll", {}).get("enabled", True):
        logger.info("[INFO] [B-Roll] Visual mode set to 'Only Images'. Skipping B-roll video search.")
        return broll_list

    if target_duration < 15:
        logger.info(f"[INFO] [B-Roll] target_duration ({target_duration:.1f}s) < 15s. Skipping B-roll search.")
        return broll_list

    broll_cfg = config.get("broll", {})

    clean_topic = topic.replace('_', ' ')
    stop_words = r'\b(what|is|how|does|work|explain|the|a|an|to|why|of|and|in|on|at|for|are|do|can|video|videos|it)\b'
    core_topic = re.sub(stop_words, '', clean_topic, flags=re.IGNORECASE)
    core_topic = re.sub(r'[^\w\s]', '', core_topic)
    core_topic = re.sub(r'\s+', ' ', core_topic).strip().lower()

    logger.info(f"[INFO] [B-Roll] Searching 3-tier waterfall for core_topic='{core_topic}' (from raw_topic='{topic}')")

    if not core_topic or core_topic in ("video", "videos"):
        logger.info(f"[B-Roll] Empty core topic from '{topic}'. Returning 0 B-roll.")
        return broll_list

    broll_dir = os.path.join(output_dir, "broll")
    os.makedirs(broll_dir, exist_ok=True)

    max_inserts = config.get("video", {}).get("max_broll_inserts", 3)
    providers_order = broll_cfg.get("providers_order", ["mixkit", "tenor", "pexels"])

    logger.info(f"[B-Roll] Starting 3-tier waterfall search for core topic: '{core_topic}' (max {max_inserts} clips)")

    seen_broll_urls = set()
    seen_broll_sizes = set()

    for provider in providers_order:
        needed = max_inserts - len(broll_list)
        if needed <= 0:
            break

        prov_name = provider.lower().strip()
        new_clips = []
        if prov_name == "mixkit":
            new_clips = _fetch_mixkit_broll(core_topic, needed, broll_dir, config, seen_urls=seen_broll_urls, seen_sizes=seen_broll_sizes)
        elif prov_name == "tenor":
            new_clips = _fetch_tenor_broll(core_topic, needed, broll_dir, config, seen_urls=seen_broll_urls, seen_sizes=seen_broll_sizes)
        elif prov_name == "pexels":
            new_clips = _fetch_pexels_broll(core_topic, needed, broll_dir, config, seen_urls=seen_broll_urls, seen_sizes=seen_broll_sizes)

        if new_clips:
            logger.info(f"[B-Roll] Provider '{prov_name}' supplied {len(new_clips)} relevant video(s)")
            broll_list.extend(new_clips)

    if not broll_list:
        logger.info(f"[INFO] [B-Roll] 0 relevant videos found across Mixkit/Tenor/Pexels for '{core_topic}'. Using 100% static technical diagrams.")
    else:
        logger.info(f"[B-Roll] Waterfall complete. Acquired {len(broll_list)} strictly relevant B-roll video(s)")

    return broll_list


def scrape_images_for_video(
    search_queries: List[Dict],
    output_dir: str,
    config: Optional[Dict] = None,
    target_images: Optional[int] = None,
) -> Dict[int, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    session = _create_session()
    
    # Infer topic
    topic = ""
    dir_name = Path(output_dir).name
    parts = dir_name.split('_')
    if len(parts) > 2:
        if len(parts[-2]) == 8 and parts[-2].isdigit() and len(parts[-1]) == 6 and parts[-1].isdigit():
            topic = ' '.join(parts[:-2])
        else:
            topic = ' '.join(parts)
    else:
        topic = ' '.join(parts)
    topic = re.sub(r' EP\d+ ', '', topic, flags=re.IGNORECASE).strip()
    topic = re.sub(r'\s+', ' ', topic)
    logger.info(f"[Image] Inferred topic: '{topic}'")

    # Phase 1: Search the topic name and collect up to target_images general anchor images
    topic_query = topic
    topic_assets = []
    # Inject randomized sleep before Phase 1 HTTP request to bypass bot detection
    stealth_sleep = random.uniform(2.0, 5.0)
    logger.info(f"[Image] Injecting stealth delay: sleeping {stealth_sleep:.2f}s before Phase 1 query...")
    time.sleep(stealth_sleep)
    
    logger.info(f"[Image] Phase 1: Scraping general topic anchor images for query: '{topic_query}'")
    
    candidates = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(topic_query, region="wt-wt", safesearch="off", max_results=20))
            candidates = results
    except Exception as e:
        logger.warning(f"[DUCKDUCKGO_SEARCH] DDG failed for Phase 1: {e}")

    if not candidates:
        logger.info("[Image] DDG failed. Triggering Selenium Google Images...")
        google_urls = _scrape_google_api(topic_query, count=10, session=session)
        candidates = [{'image': u} for u in google_urls]
    if not candidates:
        logger.info("[Image] Google failed. Triggering Selenium Bing Images...")
        bing_urls = _scrape_bing_api(topic_query, count=10, session=session)
        candidates = [{'image': u} for u in bing_urls]

    topic_keywords = _extract_main_words(topic, max_words=5)
    mode = determine_image_search_mode(topic_keywords)

    # Scoring & download loop for Phase 1
    seen_hashes = set()
    for r in candidates:
        limit = target_images if target_images is not None else 5
        if len(topic_assets) >= limit:
            break
        img_url = r.get('image')
        if not img_url:
            continue
        
        score = score_image_relevance(r, topic_keywords, mode, topic)
        if score < MIN_IMAGE_SCORE:
            logger.info(f"[IMAGE_REJECTED] [IMAGE_SCORE: {score} < {MIN_IMAGE_SCORE}] Title: '{r.get('title', '')}'")
            continue
        
        filename = f"topic_anchor_{len(topic_assets):02d}.jpg"
        save_path = os.path.abspath(str(output_path / filename))
        
        try:
            downloaded = _download_single_image(
                img_url, save_path, session,
                max_retries=1,
                min_width=400,
                min_height=300,
                timeout=4.0,
                seen_hashes=seen_hashes
            )
            if downloaded:
                logger.info(f"[IMAGE_ACCEPTED] [IMAGE_SCORE: {score}] Title: '{r.get('title', '')}' Path: {downloaded}")
                topic_assets.append(downloaded)
        except Exception as ex:
            logger.warning(f"[Image] Failed to download {img_url}: {ex}")

    logger.info(f"[Image] Phase 1 completed. Collected {len(topic_assets)} general topic images.")

    # Phase 2: Collect sentence-specific images based on filtered words
    final_dict = {}
    fallback_path = os.path.abspath("assets/templates/technical_fallback.jpg")
    
    # Generate fallback image if needed
    if not topic_assets and not os.path.exists(fallback_path):
        os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
        try:
            from PIL import Image, ImageDraw
            fallback_img = Image.new("RGB", (1080, 1920), (20, 24, 33))
            draw = ImageDraw.Draw(fallback_img)
            for grid_x in range(0, 1080, 80):
                draw.line([(grid_x, 0), (grid_x, 1920)], fill=(40, 50, 70), width=1)
            for grid_y in range(0, 1920, 80):
                draw.line([(0, grid_y), (1080, grid_y)], fill=(40, 50, 70), width=1)
            fallback_img.save(fallback_path, "JPEG")
            logger.info(f"[Image] Generated technical fallback template at {fallback_path}")
        except Exception as e:
            logger.error(f"[Image] Failed to generate technical_fallback.jpg: {e}")

    # Fallback to local icons / technical_fallback if Phase 1 failed, disabling Phase 2 live scraping
    if not topic_assets:
        logger.warning("[Image] Phase 1 returned 0 images. Disabling Phase 2 live scraping to avoid web bans.")
        local_icons = []
        icons_dir = Path(PROJECT_ROOT) / "assets/icons"
        icons_dir.mkdir(parents=True, exist_ok=True)
        
        # ponytail: Assumes assets/icons exist. Upgrade: handle missing assets gracefully
        local_icons = [str(f.resolve()) for f in icons_dir.glob("*.png")]
        if not local_icons:
            local_icons = [fallback_path]
            
        for sent_idx in range(len(search_queries)):
            selected_icon = local_icons[sent_idx % len(local_icons)]
            final_dict[sent_idx] = selected_icon
            logger.info(f"[Image] Sentence {sent_idx}: Assigned Fallback: {selected_icon}")
            
        session.close()
        total_slots = len(final_dict)
        logger.info(f"✓ Saved {total_slots} images (0 downloaded, {total_slots} local fallbacks).")
        return final_dict

    for sent_idx, sent_data in enumerate(search_queries):
        queries = sent_data.get("queries", [])
        sentence_text = sent_data.get("sentence", "")
        sentence_words = _extract_main_words(sentence_text, max_words=3)
        sentence_mode = determine_image_search_mode(sentence_words)
        
        downloaded_sentence_img = None
        
        # Try to download image for sentence-specific queries
        for q in queries:
            q = preprocess_search_query(q)
            logger.info(f"[Image] Phase 2: Scraping image for sentence {sent_idx} with query: '{q}'")
            sentence_candidates = []
            try:
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    sentence_results = list(ddgs.images(q, region="wt-wt", safesearch="off", max_results=10))
                    sentence_candidates = sentence_results
            except Exception as e:
                logger.warning(f"[DUCKDUCKGO_SEARCH] DDG failed for sentence query '{q}': {e}")
                
            if not sentence_candidates:
                sentence_candidates = [{'image': u} for u in _scrape_google_api(q, count=5, session=session)]
            if not sentence_candidates:
                sentence_candidates = [{'image': u} for u in _scrape_bing_api(q, count=5, session=session)]
                
            for scr in sentence_candidates:
                s_url = scr.get('image')
                if not s_url:
                    continue
                s_score = score_image_relevance(scr, sentence_words, sentence_mode, topic)
                if s_score < MIN_IMAGE_SCORE:
                    logger.info(f"[IMAGE_REJECTED] [IMAGE_SCORE: {s_score} < {MIN_IMAGE_SCORE}] Title: '{scr.get('title', '')}'")
                    continue
                
                filename = f"sentence_{sent_idx:02d}.jpg"
                save_path = os.path.abspath(str(output_path / filename))
                
                try:
                    downloaded = _download_single_image(
                        s_url, save_path, session,
                        max_retries=1,
                        min_width=400,
                        min_height=300,
                        timeout=4.0,
                        seen_hashes=seen_hashes
                    )
                    if downloaded:
                        logger.info(f"[IMAGE_ACCEPTED] [IMAGE_SCORE: {s_score}] Title: '{scr.get('title', '')}' Path: {downloaded}")
                        downloaded_sentence_img = downloaded
                        break
                except Exception as ex:
                    logger.warning(f"[Image] Failed to download {s_url}: {ex}")
            
            if downloaded_sentence_img:
                break
                
        if downloaded_sentence_img:
            final_dict[sent_idx] = downloaded_sentence_img
            logger.info(f"[Image] Sentence {sent_idx}: Assigned specific image: {downloaded_sentence_img}")
        elif topic_assets:
            selected_image_path = topic_assets[sent_idx % len(topic_assets)]
            final_dict[sent_idx] = selected_image_path
            logger.info(f"[Image] Sentence {sent_idx}: Assigned Fallback via Round-Robin: {selected_image_path}")
        else:
            final_dict[sent_idx] = fallback_path
            logger.info(f"[Image] Sentence {sent_idx}: Assigned Fallback: {fallback_path}")

    session.close()
    
    total_slots = len(final_dict)
    downloaded_slots = 0
    fallback_slots = 0
    for path in final_dict.values():
        if "assets/icons" in path.replace("\\", "/") or "assets/templates" in path.replace("\\", "/"):
            fallback_slots += 1
        else:
            downloaded_slots += 1
            
    logger.info(f"✓ Saved {total_slots} images ({downloaded_slots} downloaded, {fallback_slots} local fallbacks).")
    return final_dict
