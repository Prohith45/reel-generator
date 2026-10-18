"""
Topic Planner
Automatically selects suitable topics for reel generation.
Avoids duplicates and recently used topics.
"""

import json
import logging
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


@dataclass
class TopicConfig:
    """Structured topic configuration for the generator."""
    topic: str
    title: str
    hook: str
    description: str
    hashtags: List[str]
    generation_options: Dict[str, Any]


class TopicPlanner:
    """Selects topics for reel generation, avoiding duplicates."""
    
    def __init__(self, config: Dict[str, Any], history_db=None):
        self.config = config
        self.history_db = history_db
        self.topic_config = config.get("topics", {})
        self.niche = self.topic_config.get("niche", "technology")
        self.fallback_pool = self.topic_config.get("fallback_pool", [])
        self.similarity_threshold = self.topic_config.get("similarity_threshold", 0.75)
        self.lookback_count = self.topic_config.get("lookback_count", 20)
        self.generate_hook = self.topic_config.get("generate_hook", True)
        self.generate_hashtags = self.topic_config.get("generate_hashtags", True)
        
        # Generation defaults
        self.gen_defaults = config.get("generation", {})
    
    def select_topic(self) -> TopicConfig:
        """Select a suitable topic for the next reel."""
        # Get recently published topics
        recent_topics = []
        if self.history_db:
            recent_topics = self.history_db.get_recent_topics(self.lookback_count)
        
        # Try to generate a new topic using LLM
        generated_topic = self._generate_topic_with_llm(recent_topics)
        if generated_topic and not self._is_duplicate(generated_topic, recent_topics):
            return self._create_topic_config(generated_topic)
        
        # Fallback to pool
        for topic in self.fallback_pool:
            if not self._is_duplicate(topic, recent_topics):
                return self._create_topic_config(topic)
        
        # Last resort: pick random from pool (even if duplicate)
        topic = random.choice(self.fallback_pool)
        logger.warning(f"All topics recently used, picking anyway: {topic}")
        return self._create_topic_config(topic)
    
    def _generate_topic_with_llm(self, recent_topics: List[str]) -> Optional[str]:
        """Generate a new topic using the existing script engine."""
        try:
            from src.script_engine import generate_script
            
            # Build prompt for topic generation
            recent_str = "\n".join([f"- {t}" for t in recent_topics[-10:]]) if recent_topics else "None"
            
            prompt = f"""Generate ONE specific, engaging technical topic for a 60-second educational short video.

Niche: {self.niche}

Recently covered topics (AVOID these and similar):
{recent_str}

Requirements:
- Specific, not generic (e.g., "How a MOSFET switches" not "What is a transistor")
- Technical depth suitable for engineers/common audience
- Can be explained in 60 seconds with visuals
- High retention potential (surprising mechanism, counter-intuitive fact, etc.)

Output ONLY the topic title. No extra text."""
            
            # Use the script engine with a simple prompt
            # We'll use a minimal config to generate just a topic
            temp_config = {
                "script": self.config.get("script", {}),
                "voice": self.config.get("voice", {})
            }
            
            # Use a simpler approach: ask the LLM directly
            topic = generate_script(
                topic=prompt,
                content_type="educational",
                duration=10,  # Short - just need the topic
                audience="engineers",
                language="en",
                config=temp_config,
                max_retries=1
            )
            
            if topic:
                # Extract first line as topic
                lines = topic.strip().split('\n')
                topic = lines[0].strip()
                # Clean up
                topic = topic.replace("Topic:", "").replace("topic:", "").strip()
                if len(topic) > 10 and len(topic) < 100:
                    return topic
                    
        except Exception as e:
            logger.warning(f"LLM topic generation failed: {e}")
        
        return None
    
    def _is_duplicate(self, topic: str, recent_topics: List[str]) -> bool:
        """Check if topic is too similar to recent topics."""
        topic_lower = topic.lower()
        
        for recent in recent_topics:
            # Exact match
            if topic_lower == recent.lower():
                return True
            
            # Similarity check
            similarity = SequenceMatcher(None, topic_lower, recent.lower()).ratio()
            if similarity >= self.similarity_threshold:
                logger.info(f"Topic '{topic}' too similar to '{recent}' (similarity: {similarity:.2f})")
                return True
        
        return False
    
    def _create_topic_config(self, topic: str) -> TopicConfig:
        """Create full topic configuration from base topic."""
        # Generate title (can be same as topic or enhanced)
        title = self._generate_title(topic)
        
        # Generate hook
        hook = ""
        if self.generate_hook:
            hook = self._generate_hook(topic)
        
        # Generate description
        description = self._generate_description(topic)
        
        # Generate hashtags
        hashtags = []
        if self.generate_hashtags:
            hashtags = self._generate_hashtags(topic)
        
        # Build generation options
        generation_options = {
            "content_type": self.gen_defaults.get("content_type", "educational"),
            "duration_seconds": self.gen_defaults.get("duration_seconds", 60),
            "audience": self.gen_defaults.get("audience", "common"),
            "animation_style": self.gen_defaults.get("animation_style", "none"),
            "subtitle_style": self.gen_defaults.get("subtitle_style", "fade_up"),
            "tts_engine": self.gen_defaults.get("tts_engine", "kokoro"),
            "kokoro_voice": self.gen_defaults.get("kokoro_voice", "am_adam"),
            "kokoro_language": self.gen_defaults.get("kokoro_language", "en-us"),
            "kokoro_pipeline": self.gen_defaults.get("kokoro_pipeline", "a"),
            "overlay": self.gen_defaults.get("overlay", "oggy horizontal.mp4"),
            "use_intro": self.gen_defaults.get("use_intro", True),
        }
        
        return TopicConfig(
            topic=topic,
            title=title,
            hook=hook,
            description=description,
            hashtags=hashtags,
            generation_options=generation_options
        )
    
    def _generate_title(self, topic: str) -> str:
        """Generate click-worthy title from topic."""
        # Simple enhancement - can be expanded with LLM
        title = topic
        if not title[0].isupper():
            title = title[0].upper() + title[1:]
        return title
    
    def _generate_hook(self, topic: str) -> str:
        """Generate a hook for the video."""
        hooks = [
            f"What if I told you {topic.lower()} works completely differently than you think?",
            f"Most engineers get {topic.lower()} wrong. Here's why.",
            f"The hidden mechanism behind {topic.lower()} will blow your mind.",
            f"Stop guessing how {topic.lower()} works. Let me show you.",
            f"This one concept about {topic.lower()} changes everything.",
        ]
        return random.choice(hooks)
    
    def _generate_description(self, topic: str) -> str:
        """Generate video description."""
        return f"In this short, we dive deep into {topic.lower()}. Understand the core mechanism, see it in action, and learn why it matters for modern technology. Perfect for engineers, students, and curious minds!"
    
    def _generate_hashtags(self, topic: str) -> List[str]:
        """Generate relevant hashtags."""
        base_tags = ["#tech", "#education", "#engineering", "#shorts", "#learn"]
        
        # Topic-specific tags
        topic_lower = topic.lower()
        specific_tags = []
        
        if any(kw in topic_lower for kw in ["cpu", "processor", "instruction", "execute"]):
            specific_tags.extend(["#cpu", "#computerscience", "#architecture"])
        elif any(kw in topic_lower for kw in ["gpu", "graphics", "render"]):
            specific_tags.extend(["#gpu", "#graphics", "#rendering"])
        elif any(kw in topic_lower for kw in ["ram", "memory", "cache"]):
            specific_tags.extend(["#memory", "#ram", "#cache"])
        elif any(kw in topic_lower for kw in ["transistor", "mosfet", "amplif"]):
            specific_tags.extend(["#electronics", "#transistor", "#hardware"])
        elif any(kw in topic_lower for kw in ["bluetooth", "wifi", "wireless", "frequency"]):
            specific_tags.extend(["#wireless", "#bluetooth", "#networking"])
        elif any(kw in topic_lower for kw in ["http", "dns", "url", "web"]):
            specific_tags.extend(["#webdev", "#networking", "#internet"])
        elif any(kw in topic_lower for kw in ["ai", "neural", "transformer", "ml"]):
            specific_tags.extend(["#ai", "#machinelearning", "#deeplearning"])
        elif any(kw in topic_lower for kw in ["ssd", "storage", "flash"]):
            specific_tags.extend(["#storage", "#ssd", "#hardware"])
        elif any(kw in topic_lower for kw in ["pwm", "motor", "control"]):
            specific_tags.extend(["#embedded", "#motorcontrol", "#pwm"])
        elif any(kw in topic_lower for kw in ["git", "version", "control"]):
            specific_tags.extend(["#git", "#devtools", "#versioncontrol"])
        elif any(kw in topic_lower for kw in ["jwt", "auth", "token", "security"]):
            specific_tags.extend(["#security", "#authentication", "#webdev"])
        elif any(kw in topic_lower for kw in ["react", "vue", "svelte", "frontend"]):
            specific_tags.extend(["#frontend", "#webdev", "#javascript"])
        
        return base_tags + specific_tags[:5]  # Limit to ~10 total


def create_topic_planner(config: Dict[str, Any], history_db=None) -> TopicPlanner:
    """Factory function to create TopicPlanner."""
    return TopicPlanner(config, history_db)