"""
Video Composer - Assembles the final reel video from:
- Background image
- Scraped images (with animations)
- Audio voiceover
- Subtitles (word-by-word karaoke)

Uses Pillow for frame rendering and MoviePy for video assembly.
"""

import os
import math
import random
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ============================================================================
# IMAGE PROCESSING UTILITIES
# ============================================================================

def _load_and_resize_background(bg_path: str, width: int, height: int, config: Dict) -> Image.Image:
    """Load background image, resize to fill, apply effects."""
    bg_cfg = config.get("background", {})
    
    img = Image.open(bg_path).convert("RGB")
    
    # Resize to fill (cover mode)
    img_ratio = img.width / img.height
    target_ratio = width / height
    
    if img_ratio > target_ratio:
        # Image is wider proportionally
        new_height = height
        new_width = int(height * img_ratio)
    else:
        new_width = width
        new_height = int(width / img_ratio)
    
    img = img.resize((new_width, new_height), Image.LANCZOS)
    
    # Center crop
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    img = img.crop((left, top, left + width, top + height))
    
    # Apply blur
    blur_radius = bg_cfg.get("blur_radius", 3)
    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    
    # Apply brightness
    brightness = bg_cfg.get("brightness", 0.85)
    if brightness < 1.0:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness)
    
    # Apply dark overlay
    overlay_color = tuple(bg_cfg.get("overlay_color", [0, 0, 0]))
    overlay_opacity = bg_cfg.get("overlay_opacity", 0.25)
    if overlay_opacity > 0:
        overlay = Image.new("RGBA", (width, height), overlay_color + (int(255 * overlay_opacity),))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")
    
    return img


def _prepare_content_image(
    img_or_path: Any,
    max_w: int,
    max_h: int,
    min_w: int,
    corner_radius: int = 20,
    border_width: int = 4,
    border_color: Tuple = (255, 255, 255),
) -> Optional[Image.Image]:
    """Load, resize, style, center and pad a content image within transparent max boundaries."""
    try:
        if isinstance(img_or_path, str):
            img = Image.open(img_or_path)
        else:
            img = img_or_path.copy()
            
        if img.mode != "RGBA":
            img = img.convert("RGBA")
    except Exception as e:
        logger.warning(f"[Composer] Cannot open image {img_or_path}: {e}")
        return None
    
    # Calculate target size preserving aspect ratio, using 90% of max bounds as padding
    safe_max_w = int(max_w * 0.9)
    safe_max_h = int(max_h * 0.9)
    
    img_ratio = img.width / img.height
    target_w = min(safe_max_w, int(safe_max_h * img_ratio))
    target_h = min(safe_max_h, int(safe_max_w / img_ratio))
    
    # Enforce minimum but clamp to safe maximum
    target_w = max(target_w, min_w)
    target_w = min(target_w, safe_max_w)
    
    target_h = int(target_w / img_ratio) if img_ratio > 0 else target_h
    target_h = min(target_h, safe_max_h)
    
    # Final aspect ratio correction
    if target_w / target_h != img_ratio:
        # Re-calculate maintaining aspect ratio
        if img_ratio > 1:
            target_w = min(target_w, safe_max_w)
            target_h = int(target_w / img_ratio)
        else:
            target_h = min(target_h, safe_max_h)
            target_w = int(target_h * img_ratio)
            
    img = img.resize((target_w, target_h), Image.LANCZOS)
    
    # Create rounded corners on resized image itself before padding
    if corner_radius > 0:
        mask = Image.new("L", (target_w, target_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            [0, 0, target_w - 1, target_h - 1],
            radius=corner_radius,
            fill=255,
        )
        img.putalpha(mask)
        
    # Add border
    if border_width > 0:
        bordered_w = target_w + 2 * border_width
        bordered_h = target_h + 2 * border_width
        bordered = Image.new("RGBA", (bordered_w, bordered_h), (0, 0, 0, 0))
        
        border_draw = ImageDraw.Draw(bordered)
        border_draw.rounded_rectangle(
            [0, 0, bordered_w - 1, bordered_h - 1],
            radius=corner_radius + border_width,
            fill=border_color + (255,),
        )
        bordered.paste(img, (border_width, border_width), img)
        img = bordered
        target_w, target_h = bordered.size
        
    # Create final padded transparent canvas of exactly max_w x max_h
    canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
    paste_x = (max_w - target_w) // 2
    paste_y = (max_h - target_h) // 2
    canvas.paste(img, (paste_x, paste_y), img)
    
    return canvas


def _add_shadow(
    base: Image.Image,
    content_img: Image.Image,
    x: int,
    y: int,
    shadow_offset: Tuple[int, int] = (6, 6),
    shadow_color: Tuple[int, int, int] = (0, 0, 0),
    shadow_opacity: float = 0.5,
    shadow_blur: int = 15,
) -> Image.Image:
    """Add drop shadow behind content image."""
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    
    # Create shadow shape
    shadow_img = Image.new("RGBA", content_img.size,
                           shadow_color + (int(255 * shadow_opacity),))
    
    if content_img.mode == 'RGBA':
        shadow_img.putalpha(content_img.split()[-1])
    
    shadow.paste(shadow_img, (x + shadow_offset[0], y + shadow_offset[1]), shadow_img)
    
    # Blur shadow
    if shadow_blur > 0:
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    
    # Composite: background -> shadow -> image
    if base.mode != 'RGBA':
        base = base.convert('RGBA')
    
    base = Image.alpha_composite(base, shadow)
    
    return base


# ============================================================================
# ANIMATION FUNCTIONS
# ============================================================================

def _apply_ken_burns(
    img: Image.Image,
    progress: float,
    config: Dict,
) -> Image.Image:
    """Apply Ken Burns (slow zoom + pan) effect."""
    style_cfg = config.get("animations", {}).get("styles", {}).get("ken_burns", {})
    zoom_start = style_cfg.get("zoom_start", 1.0)
    zoom_end = style_cfg.get("zoom_end", 1.15)
    pan_range = style_cfg.get("pan_range", 0.05)
    
    # Interpolate zoom
    zoom = zoom_start + (zoom_end - zoom_start) * progress
    
    # Pan direction (use hash of image size as seed for consistency)
    pan_x = math.sin(progress * math.pi) * pan_range
    pan_y = math.cos(progress * math.pi * 0.5) * pan_range * 0.5
    
    w, h = img.size
    new_w = int(w * zoom)
    new_h = int(h * zoom)
    
    img_zoomed = img.resize((new_w, new_h), Image.LANCZOS)
    
    # Calculate crop for pan
    cx = int((new_w - w) / 2 + pan_x * w)
    cy = int((new_h - h) / 2 + pan_y * h)
    
    cx = max(0, min(cx, new_w - w))
    cy = max(0, min(cy, new_h - h))
    
    return img_zoomed.crop((cx, cy, cx + w, cy + h))


def _apply_fade_scale(
    img: Image.Image,
    progress: float,
    total_progress: float,
    config: Dict,
) -> Tuple[Image.Image, float]:
    """Apply fade-in with subtle scale effect. Returns (image, alpha)."""
    style_cfg = config.get("animations", {}).get("styles", {}).get("fade_scale", {})
    fade_dur = style_cfg.get("fade_duration", 0.5)
    scale_start = style_cfg.get("scale_start", 1.05)
    scale_end = style_cfg.get("scale_end", 1.0)
    
    # Fade in/out
    alpha = 1.0
    if progress < fade_dur:
        alpha = progress / fade_dur
    elif progress > (1.0 - fade_dur):
        alpha = (1.0 - progress) / fade_dur
    alpha = max(0.0, min(1.0, alpha))
    
    # Scale
    scale = scale_start + (scale_end - scale_start) * min(1.0, progress / 0.5)
    
    if abs(scale - 1.0) > 0.01:
        w, h = img.size
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        
        # Center crop back
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        img = img.crop((left, top, left + w, top + h))
    
    return img, alpha


def _apply_slide_pop(
    x: int,
    y: int,
    img_w: int,
    screen_w: int,
    progress: float,
    direction: str,
    config: Dict,
) -> Tuple[int, int, float]:
    """Apply slide-in animation. Returns (x, y, alpha)."""
    style_cfg = config.get("animations", {}).get("styles", {}).get("slide_pop", {})
    slide_dur = style_cfg.get("slide_duration", 0.4)
    
    alpha = 1.0
    
    if progress < slide_dur:
        t = progress / slide_dur
        # Ease-out cubic
        t = 1 - (1 - t) ** 3
        
        if direction == "left":
            x = int(-img_w + (x + img_w) * t)
        elif direction == "right":
            x = int(screen_w - (screen_w - x) * t)
        
        alpha = t
    elif progress > (1.0 - slide_dur):
        t = (1.0 - progress) / slide_dur
        alpha = t
    
    return x, y, alpha


def _apply_cinematic(
    frame: Image.Image,
    progress: float,
    config: Dict,
) -> Image.Image:
    """Apply cinematic letterbox and vignette effect."""
    style_cfg = config.get("animations", {}).get("styles", {}).get("cinematic", {})
    letterbox = style_cfg.get("letterbox_ratio", 0.08)
    vignette = style_cfg.get("vignette_strength", 0.3)
    
    w, h = frame.size
    
    # Letterbox
    if letterbox > 0:
        bar_h = int(h * letterbox)
        draw = ImageDraw.Draw(frame)
        draw.rectangle([0, 0, w, bar_h], fill=(0, 0, 0))
        draw.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0))
    
    # Vignette
    if vignette > 0:
        vignette_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        vdraw = ImageDraw.Draw(vignette_overlay)
        
        cx, cy = w // 2, h // 2
        max_r = math.sqrt(cx ** 2 + cy ** 2)
        
        for i in range(20):
            r = max_r * (1 - i / 20)
            alpha = int(255 * vignette * (1 - i / 20) ** 2)
            vdraw.ellipse(
                [int(cx - r), int(cy - r), int(cx + r), int(cy + r)],
                fill=(0, 0, 0, alpha),
            )
        
        frame = frame.convert("RGBA")
        frame = Image.alpha_composite(frame, vignette_overlay)
        frame = frame.convert("RGB")
    
    return frame


def get_supporting_image(sent_idx: int, image_map: Dict[int, str], config: Dict) -> str:
    # Try to get next image from image_map
    next_img = image_map.get(sent_idx + 1)
    if next_img and os.path.exists(next_img):
        return os.path.abspath(next_img)
    # Try to get any other image from image_map
    for k, v in image_map.items():
        if k != sent_idx and v and os.path.exists(v):
            return os.path.abspath(v)
    # Try to load local hardware icons
    local_icons = []
    icons_dir = Path(PROJECT_ROOT) / "assets/icons"
    if icons_dir.exists():
        local_icons = [str(f.resolve()) for f in icons_dir.glob("*.png")]
    if local_icons:
        return os.path.abspath(local_icons[sent_idx % len(local_icons)])
    # Fallback to technical_fallback.jpg
    fallback_path = os.path.abspath("assets/templates/technical_fallback.jpg")
    return fallback_path


# ============================================================================
# MAIN COMPOSER
# ============================================================================

def compose_video(
    script_text: str,
    audio_path: str,
    sentence_timings: List[Dict],
    image_map: Dict[int, str],
    output_path: str,
    config: Dict,
    animation_style: str = "ken_burns",
    language: str = "en",
    overlay_path: Optional[str] = None,
    topic: Optional[str] = None,
) -> Optional[str]:
    """
    Compose the final reel video.
    
    Args:
        script_text: Full voiceover script
        audio_path: Path to WAV audio file
        sentence_timings: List of sentence timing dicts
        image_map: Dict mapping sentence index to image paths
        output_path: Path for output MP4 file
        config: Full config dict
        animation_style: Animation style name
        language: Target language
        overlay_path: Optional path to green screen overlay video
        
    Returns:
        Path to output video, or None on failure
    """
    from moviepy import AudioFileClip, VideoClip, VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
    from src.subtitle_engine import render_subtitle_frame
    
    video_cfg = config.get("video", {})
    img_cfg = config.get("images", {})
    
    width = video_cfg.get("width", 1080)
    height = video_cfg.get("height", 1920)
    fps = video_cfg.get("fps", 30)
    
    # Load audio
    try:
        audio_clip = AudioFileClip(audio_path)
        
        # Try importing moviepy audio effects dynamically to support both moviepy v1 and v2
        volumex = None
        audio_normalize = None
        
        # First try MoviePy v1 imports
        try:
            from moviepy.audio.fx.all import volumex, audio_normalize
            logger.info("[Composer] Imported volumex and audio_normalize from moviepy.audio.fx.all")
        except ImportError:
            # Try MoviePy v2 imports
            try:
                from moviepy.audio.fx import AudioNormalize, MultiplyVolume
                # Wrap MoviePy v2 classes to behave like MoviePy v1 functions for .fx()
                audio_normalize = lambda clip: clip.with_effects([AudioNormalize()])
                volumex = lambda clip, factor: clip.with_effects([MultiplyVolume(factor)])
                logger.info("[Composer] Loaded MoviePy v2 AudioNormalize and MultiplyVolume as wrappers")
            except ImportError:
                logger.warning("[Composer] Could not import moviepy audio effects; will fallback to built-in methods")
        
        # 1. Apply audio normalization if available
        if audio_normalize is not None:
            try:
                import inspect
                if callable(audio_normalize) and not isinstance(audio_normalize, type):
                    sig = inspect.signature(audio_normalize)
                    if len(sig.parameters) == 1:
                        audio_clip = audio_normalize(audio_clip)
                    else:
                        audio_clip = audio_clip.fx(audio_normalize)
                else:
                    audio_clip = audio_clip.fx(audio_normalize)
                logger.info("[Composer] Applied audio normalization pass to prevent clipping.")
            except Exception as norm_err:
                logger.warning(f"[Composer] Normalization failed: {norm_err}")
                
        # 2. Apply volume boost (double the volume)
        if volumex is not None:
            try:
                import inspect
                if callable(volumex) and not isinstance(volumex, type):
                    sig = inspect.signature(volumex)
                    if len(sig.parameters) == 2:
                        audio_clip = volumex(audio_clip, 2.0)
                    else:
                        audio_clip = audio_clip.fx(volumex, 2.0)
                else:
                    audio_clip = audio_clip.fx(volumex, 2.0)
                logger.info("[Composer] Applied volume boost (2.0x multiplier) via fx(volumex).")
            except Exception as vol_err:
                logger.warning(f"[Composer] volumex fx failed: {vol_err}; falling back to built-in methods")
                try:
                    if hasattr(audio_clip, "with_volume_scaled"):
                        audio_clip = audio_clip.with_volume_scaled(2.0)
                        logger.info("[Composer] Applied volume boost (2.0x multiplier) via with_volume_scaled.")
                    elif hasattr(audio_clip, "volumex"):
                        audio_clip = audio_clip.volumex(2.0)
                        logger.info("[Composer] Applied volume boost (2.0x multiplier) via volumex method.")
                except Exception as vol_err2:
                    logger.error(f"[Composer] Volume boost failed: {vol_err2}")
        else:
            try:
                if hasattr(audio_clip, "with_volume_scaled"):
                    audio_clip = audio_clip.with_volume_scaled(2.0)
                    logger.info("[Composer] Applied volume boost (2.0x multiplier) via with_volume_scaled.")
                elif hasattr(audio_clip, "volumex"):
                    audio_clip = audio_clip.volumex(2.0)
                    logger.info("[Composer] Applied volume boost (2.0x multiplier) via volumex method.")
            except Exception as vol_err:
                logger.error(f"[Composer] Volume boost failed: {vol_err}")

        total_duration = audio_clip.duration
    except Exception as e:
        logger.error(f"[Composer] Cannot load audio: {e}")
        return None
    
    logger.info(f"[Composer] Audio duration: {total_duration:.1f}s")
    
    # Load background
    bg_path = config.get("background", {}).get("image_path", "assets/templates/background.jpeg")
    if not os.path.isabs(bg_path):
        bg_path = str(PROJECT_ROOT / bg_path)
    
    try:
        background = _load_and_resize_background(bg_path, width, height, config)
    except Exception as e:
        logger.warning(f"[Composer] Cannot load background: {e}, using solid color")
        background = Image.new("RGB", (width, height), (20, 20, 35))
    
    # Prepare content images
    max_img_w = int(width * img_cfg.get("max_width_ratio", 0.80))
    max_img_h = int(height * img_cfg.get("max_height_ratio", 0.36))
    min_img_w = int(width * img_cfg.get("min_width_ratio", 0.50))
    corner_radius = img_cfg.get("corner_radius", 20)
    border_width = img_cfg.get("border_width", 4)
    border_color = tuple(img_cfg.get("border_color", [255, 255, 255]))
    
    # Build timeline: which image shows when
    image_timeline = []  # List of (start, end, image_path) tuples
    
    for sent_idx, sent_data in enumerate(sentence_timings):
        sent_start = sent_data["start"]
        sent_end = sent_data["end"]
        sent_duration = sent_end - sent_start
        
        if sent_duration <= 0:
            continue
            
        img_path = image_map.get(sent_idx)
        if img_path:
            img_path = os.path.abspath(img_path)
            
        # Add check: if image path does not exist, trigger a copy of technical_fallback.jpg
        if not img_path or not os.path.exists(img_path):
            logger.error(f"CRITICAL IMAGE MISSING: Image for sentence {sent_idx} does not exist: {img_path}")
            
            fallback_src = os.path.abspath(os.path.join(PROJECT_ROOT, "assets", "templates", "technical_fallback.jpg"))
            if not os.path.exists(fallback_src):
                os.makedirs(os.path.dirname(fallback_src), exist_ok=True)
                # Locally imported PIL removed to fix NameError closure
                fallback_img = Image.new("RGB", (width, height), (20, 24, 33))
                draw = ImageDraw.Draw(fallback_img)
                # Draw grid lines for high-quality technical look
                for grid_x in range(0, width, 80):
                    draw.line([(grid_x, 0), (grid_x, height)], fill=(40, 50, 70), width=1)
                for grid_y in range(0, height, 80):
                    draw.line([(0, grid_y), (width, grid_y)], fill=(40, 50, 70), width=1)
                fallback_img.save(fallback_src, "JPEG")
                logger.info(f"[Composer] Generated technical fallback template at {fallback_src}")
                
            img_dir = os.path.dirname(os.path.abspath(audio_path))
            fallback_dest = os.path.abspath(os.path.join(img_dir, f"technical_fallback_{sent_idx}.jpg"))
            import shutil
            try:
                shutil.copy(fallback_src, fallback_dest)
                img_path = fallback_dest
                logger.info(f"[Composer] Handled missing image for sentence {sent_idx} using copy of technical fallback: {fallback_dest}")
            except Exception as e:
                logger.error(f"[Composer] Failed to copy technical fallback: {e}")
                img_path = fallback_src
                
        # Timeline duration bounds enforcement: min = 3s, preferred = 4s, max = 6s
        if sent_duration < 3.0 and len(image_timeline) > 0:
            # Merge with previous concept visually (reuse the previous image)
            image_timeline[-1]["end"] = sent_end
            logger.info(f"[Composer] Segment {sent_idx} duration ({sent_duration:.2f}s) < 3.0s: Merged with previous slot (new end: {sent_end:.2f}s)")
        else:
            # Check if duration > 6.0s
            if sent_duration > 6.0:
                # Split duration to prevent static screen
                N = 1
                while sent_duration / N > 6.0:
                    N += 1
                seg_len = sent_duration / N
                logger.info(f"[Composer] Segment {sent_idx} duration ({sent_duration:.2f}s) > 6.0s: Splitting into {N} slots of {seg_len:.2f}s each")
                
                for j in range(N):
                    slot_start = sent_start + j * seg_len
                    slot_end = slot_start + seg_len
                    if j == N - 1:
                        slot_end = sent_end
                        
                    if j == 0:
                        path_to_use = img_path
                    else:
                        path_to_use = get_supporting_image(sent_idx, image_map, config)
                        
                    image_timeline.append({
                        "start": slot_start,
                        "end": slot_end,
                        "path": path_to_use,
                        "sentence_idx": sent_idx,
                    })
            else:
                # Normal slot
                image_timeline.append({
                    "start": sent_start,
                    "end": sent_end,
                    "path": img_path,
                    "sentence_idx": sent_idx,
                })
        
    # B-roll insertion
    try:
        from src.image_engine import fetch_generic_broll
        import random
        import re
        # Use the actual topic string passed to compose_video.
        # Fallback to extracting from output filename stem before language/episode/metadata.
        # NEVER infer the topic from outputs/videos directory name!
        broll_topic = topic if (topic and str(topic).strip() and str(topic).strip().lower() not in ("videos", "video")) else None
        if not broll_topic:
            stem = Path(output_path).stem
            # Strip language code (_en_, _te_, etc.) or episode tags (_EP01_) and subsequent parts
            match = re.split(r'_(?:[a-z]{2}|EP\d+)_', stem, flags=re.IGNORECASE)
            raw_stem = match[0] if match else stem
            if raw_stem == stem and len(stem.split('_')) > 2:
                raw_stem = '_'.join(stem.split('_')[:-2])
            broll_topic = raw_stem.replace('_', ' ')
        broll_topic = re.sub(r'\bEP\d+\b', '', broll_topic, flags=re.IGNORECASE).strip()
        broll_topic = re.sub(r'\s+', ' ', broll_topic).strip()
        if broll_topic.lower() in ("videos", "video", ""):
            broll_topic = topic or ""
        
        visual_mode = config.get("video", {}).get("visual_mode", "hybrid")
        broll_videos = []
        if visual_mode != "images" and config.get("broll", {}).get("enabled", True):
            broll_videos = fetch_generic_broll(broll_topic, total_duration, config, str(Path(output_path).parent))
        
        if not broll_videos or visual_mode == "images":
            logger.info("[INFO] [Composer] Using 100% static technical images (0 B-roll clips).")
        else:
            max_inserts = config.get("video", {}).get("max_broll_inserts", 3)
            eligible_indices = [i for i in range(1, len(image_timeline) - 1)]
            if not eligible_indices:
                eligible_indices = [i for i in range(len(image_timeline))]
                
            if eligible_indices:
                num_inserts = min(len(broll_videos), max_inserts, len(eligible_indices))
                # Select evenly spaced, non-adjacent slots matching the exact number of available clips
                step = max(1, len(eligible_indices) // (num_inserts + 1))
                valid_slots = []
                for i in range(1, num_inserts + 1):
                    idx = eligible_indices[min(i * step, len(eligible_indices) - 1)]
                    if not valid_slots or idx > valid_slots[-1] + 1:
                        valid_slots.append(idx)
                
                # Backfill from eligible_indices if spacing skipped any
                for idx in eligible_indices:
                    if len(valid_slots) >= num_inserts:
                        break
                    if idx not in valid_slots and all(abs(idx - s) > 1 for s in valid_slots):
                        valid_slots.append(idx)
                valid_slots = sorted(valid_slots[:num_inserts])
                
                for slot, video_path in zip(valid_slots, broll_videos):
                    image_timeline[slot]["original_path"] = image_timeline[slot]["path"]
                    image_timeline[slot]["path"] = video_path
                    logger.info(f"[Composer] Inserted B-roll at slot {slot}: {video_path}")
    except Exception as e:
        logger.warning(f"[Composer] B-roll insertion failed: {e}")
        
    # Pre-load and prepare content images
    prepared_images = {}
    video_clips_overlay = []
    broll_intervals = []
    from moviepy import VideoFileClip, ImageClip
    
    for item in image_timeline:
        path = item["path"]
        sent_duration = item["end"] - item["start"]
        start_time = item["start"]
        end_time = item["end"]
        
        broll_processed = False
        if path.lower().endswith(".mp4"):
            try:
                clip = VideoFileClip(path).without_audio()
                slot_duration = sent_duration
                
                # Duration matching against slot_duration strictly
                if clip.duration >= slot_duration:
                    clip = clip.subclipped(0, slot_duration) if hasattr(clip, "subclipped") else clip.subclip(0, slot_duration)
                elif clip.duration >= slot_duration * 0.65:
                    logger.info(f"[Composer] Slowing B-roll clip ({clip.duration:.2f}s -> {slot_duration:.2f}s) to fill slot continuously")
                    try:
                        from moviepy.video.fx import MultiplySpeed
                        clip = clip.with_effects([MultiplySpeed(final_duration=slot_duration)])
                    except Exception:
                        try:
                            from moviepy.video.fx import MultiplySpeed
                            clip = clip.with_effects([MultiplySpeed(factor=clip.duration / slot_duration)])
                        except Exception:
                            import moviepy.video.fx.all as vfx
                            clip = clip.fx(vfx.speedx, factor=clip.duration / slot_duration)
                else:
                    logger.info(f"[INFO] [Composer] B-roll clip too short ({clip.duration:.1f}s < {slot_duration:.1f}s), keeping static diagram.")
                    clip.close()
                    raise ValueError(f"B-roll clip duration {clip.duration:.1f}s is less than 65% of slot duration {slot_duration:.1f}s")
                
                # Target sizing logic: 9:16 vertical fit
                h = height
                w = width
                clip_ratio = clip.w / clip.h
                target_ratio = w / h
                
                if clip_ratio > target_ratio:
                    clip = clip.resized(height=h) if hasattr(clip, "resized") else clip.resize(height=h)
                    x_center = clip.w / 2
                    clip = clip.cropped(x1=x_center - w/2, y1=0, x2=x_center + w/2, y2=h) if hasattr(clip, "cropped") else clip.crop(x1=x_center - w/2, y1=0, x2=x_center + w/2, y2=h)
                else:
                    clip = clip.resized(width=w) if hasattr(clip, "resized") else clip.resize(width=w)
                    y_center = clip.h / 2
                    clip = clip.cropped(x1=0, y1=y_center - h/2, x2=w, y2=y_center + h/2) if hasattr(clip, "cropped") else clip.crop(x1=0, y1=y_center - h/2, x2=w, y2=y_center + h/2)
                    
                if hasattr(clip, "with_position"):
                    clip = clip.with_position(("center", "center"))
                elif hasattr(clip, "set_position"):
                    clip = clip.set_position(("center", "center"))
                    
                if hasattr(clip, "with_start"):
                    clip = clip.with_start(start_time)
                elif hasattr(clip, "set_start"):
                    clip = clip.set_start(start_time)
                    
                if hasattr(clip, "with_end"):
                    clip = clip.with_end(end_time)
                elif hasattr(clip, "set_end"):
                    clip = clip.set_end(end_time)

                if hasattr(clip, "with_duration"):
                    clip = clip.with_duration(slot_duration)
                elif hasattr(clip, "set_duration"):
                    clip = clip.set_duration(slot_duration)
                    
                prepared_images[path] = {"type": "video_overlay"}
                video_clips_overlay.append(clip)
                broll_intervals.append((start_time, end_time))
                broll_processed = True
                logger.info(f"[Composer] Added full-screen B-roll for [{start_time:.2f}s - {end_time:.2f}s]: {path}")
            except Exception as e:
                logger.warning(f"[Composer] Failed to process B-roll video clip {path}, falling back to static image: {e}")
                fallback_path = item.get("original_path")
                if not fallback_path or not os.path.exists(fallback_path):
                    fallback_path = get_supporting_image(item.get("sentence_idx", 0), image_map, config)
                item["path"] = fallback_path
                path = fallback_path

        if not broll_processed:
            if path not in prepared_images:
                try:
                    clip = ImageClip(path)
                    frame_np = clip.get_frame(0)
                    pil_frame = Image.fromarray(frame_np)
                    prepared = _prepare_content_image(
                        pil_frame, max_img_w, max_img_h, min_img_w,
                        corner_radius, border_width, border_color,
                    )
                    prepared_images[path] = {"type": "image", "img": prepared}
                except Exception as e:
                    logger.warning(f"[Composer] Failed to load image {path}: {e}")
    
    logger.info(f"[Composer] Prepared {len(prepared_images)} unique images")
    logger.info(f"[Composer] Image timeline: {len(image_timeline)} slots")
    
    # Image position
    img_pos_x_ratio = img_cfg.get("position_x", 0.5)
    img_pos_y_ratio = img_cfg.get("position_y", 0.28)
    
    # Shadow config
    shadow_offset = tuple(img_cfg.get("shadow_offset", [6, 6]))
    shadow_color = tuple(img_cfg.get("shadow_color", [0, 0, 0]))
    shadow_opacity = img_cfg.get("shadow_opacity", 0.5)
    shadow_blur = img_cfg.get("shadow_blur", 15)
    
    # Transition
    transition_dur = img_cfg.get("transition_duration", 0.6)
    
    # Track direction for slide animations
    slide_directions = ["left", "right"]
    
    def make_frame(t):
        """Generate a single video frame at time t."""
        # Start with background copy
        frame = background.copy()
        
        # Find which image(s) to show at time t
        current_img_data = None
        prev_img_data = None
        
        for idx, item in enumerate(image_timeline):
            if item["start"] <= t < item["end"]:
                current_img_data = item
                if idx > 0:
                    prev_img_data = image_timeline[idx - 1]
                break
        
        # If no image at this time, check if we're in transition
        if current_img_data is None and image_timeline:
            # Find nearest future image
            for item in image_timeline:
                if item["start"] > t and item["start"] - t < transition_dur:
                    current_img_data = item
                    break
        
        if current_img_data:
            img_path = current_img_data["path"]
            prep_data = prepared_images.get(img_path)
            
            if prep_data:
                img_start = current_img_data["start"]
                img_end = current_img_data["end"]
                img_duration = img_end - img_start
                
                if img_duration > 0:
                    img_progress = (t - img_start) / img_duration
                    img_progress = max(0.0, min(1.0, img_progress))
                else:
                    img_progress = 0.5
                
                if prep_data["type"] == "video":
                    clip = prep_data["clip"]
                    clip_t = min(t - img_start, clip.duration - 0.01)
                    try:
                        frame_np = clip.get_frame(clip_t)
                        pil_frame = Image.fromarray(frame_np)
                        content_img = _prepare_content_image(
                            pil_frame, max_img_w, max_img_h, min_img_w,
                            corner_radius, border_width, border_color
                        )
                    except Exception:
                        content_img = None
                elif prep_data["type"] == "video_overlay":
                    content_img = None
                else:
                    content_img = prep_data["img"]
                    
                if content_img:
                    display_img = content_img.copy()
                    alpha = 1.0
                    
                    # Apply animation based on style
                    if animation_style == "ken_burns":
                        display_img = _apply_ken_burns(display_img, img_progress, config)
                    
                    elif animation_style == "fade_scale":
                        display_img, alpha = _apply_fade_scale(display_img, img_progress, img_progress, config)
                    
                    elif animation_style == "cinematic":
                        pass  # Cinematic applied to entire frame later
                    
                    # Crossfade transition
                    if img_progress < transition_dur / max(img_duration, 0.01):
                        # Fade in
                        fade_progress = img_progress / (transition_dur / max(img_duration, 0.01))
                        alpha *= min(1.0, fade_progress)
                    elif img_progress > 1.0 - transition_dur / max(img_duration, 0.01):
                        # Fade out
                        fade_progress = (1.0 - img_progress) / (transition_dur / max(img_duration, 0.01))
                        alpha *= min(1.0, fade_progress)
                    
                    # Calculate position
                    img_w, img_h = display_img.size
                    x = int(width * img_pos_x_ratio - img_w / 2)
                    y = int(height * img_pos_y_ratio - img_h / 2) + 200
                    
                    # Slide animation position adjustment
                    if animation_style == "slide_pop":
                        sent_idx = current_img_data.get("sentence_idx", 0)
                        direction = slide_directions[sent_idx % 2]
                        x, y, alpha = _apply_slide_pop(x, y, img_w, width, img_progress, direction, config)
                    
                    # Clamp position
                    x = max(-img_w // 2, min(width - img_w // 2, x))
                    y = max(-img_h // 2, min(height - img_h // 2, y))
                    
                    # Add shadow
                    frame = _add_shadow(
                        frame, display_img, x, y,
                        shadow_offset, shadow_color, shadow_opacity, shadow_blur,
                    )
                    
                    # Composite image onto frame
                    frame = frame.convert("RGBA")
                    
                    if alpha < 1.0:
                        # Apply alpha to content image
                        if display_img.mode == 'RGBA':
                            r, g, b, a = display_img.split()
                            a = a.point(lambda p: int(p * alpha))
                            display_img = Image.merge('RGBA', (r, g, b, a))
                        else:
                            display_img = display_img.convert("RGBA")
                            r, g, b, a = display_img.split()
                            a = a.point(lambda p: int(p * alpha))
                            display_img = Image.merge('RGBA', (r, g, b, a))
                    
                    if display_img.mode != 'RGBA':
                        display_img = display_img.convert("RGBA")
                    
                    frame.paste(display_img, (x, y), display_img)
                    frame = frame.convert("RGB")
        
        # Apply cinematic effect to full frame
        if animation_style == "cinematic":
            frame = _apply_cinematic(frame, t / max(total_duration, 0.01), config)
        
        # Subtitles are composited as a dedicated top-level layer (subtitle_clip)
        # ensuring they stay visible on top of both static diagrams and full-screen B-roll.
        
        # Convert to numpy array for MoviePy
        return np.array(frame)
    
    # Create video clip
    logger.info(f"[Composer] Rendering video at {width}x{height} @ {fps}fps...")
    logger.info(f"[Composer] Animation style: {animation_style}")
    
    # Track all MoviePy clip objects for guaranteed cleanup on Windows
    _clips_to_close = []
    
    try:
        base_video_clip = VideoClip(make_frame, duration=total_duration)
        _clips_to_close.append(base_video_clip)
        
        # ── Dedicated transparent subtitle layer on top of all images and B-roll ──
        dummy_sub_frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        def make_subtitle_frame(t):
            current_sentence = None
            for sent_data in sentence_timings:
                if sent_data["start"] <= t < sent_data["end"]:
                    current_sentence = sent_data
                    break
            
            if current_sentence:
                sub_img = render_subtitle_frame(dummy_sub_frame, current_sentence, t, config, return_rgba=True)
                return np.array(sub_img)
            return np.zeros((height, width, 4), dtype=np.uint8)

        subtitle_clip = VideoClip(make_subtitle_frame, duration=total_duration)
        _clips_to_close.append(subtitle_clip)
        
        # Layering: base slideshow -> full-screen B-roll -> subtitles on top
        from moviepy import CompositeVideoClip
        all_layers = [base_video_clip] + video_clips_overlay + [subtitle_clip]
        comp = CompositeVideoClip(all_layers, size=(width, height))
        base_video_clip = comp.with_duration(total_duration) if hasattr(comp, "with_duration") else comp.set_duration(total_duration)
        _clips_to_close.append(base_video_clip)
        for c in video_clips_overlay:
            _clips_to_close.append(c)
            
        base_video_clip = base_video_clip.with_fps(fps)
        base_video_clip = base_video_clip.with_audio(audio_clip)
        _clips_to_close.append(audio_clip)
        
        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Always write the base slideshow video clip directly to output_path
        base_video_clip.write_videofile(
            output_path,
            fps=fps,
            codec=video_cfg.get("codec", "libx264"),
            audio_codec=video_cfg.get("audio_codec", "aac"),
            bitrate=video_cfg.get("bitrate", "8000k"),
            logger="bar",
            threads=4,
        )
        
        # Close base clips early to release file locks before FFmpeg steps
        for c in _clips_to_close:
            try:
                c.close()
            except Exception:
                pass
        _clips_to_close.clear()
        
        logger.info(f"[Composer] Base video saved: {output_path}")
        
        import subprocess
        from imageio_ffmpeg import get_ffmpeg_exe
        
        ffmpeg_exe = get_ffmpeg_exe()
        
        # 1. Apply green screen overlay if present
        try:
            effective_overlay = overlay_path
            # Legacy fallback if no overlay selected but oggy.mp4 exists
            if not effective_overlay:
                legacy_path = str(PROJECT_ROOT / "assets/green_screen/oggy.mp4")
                if os.path.exists(legacy_path):
                    effective_overlay = legacy_path
            
            if effective_overlay and os.path.exists(effective_overlay):
                logger.info(f"[Composer] Applying green screen overlay: {effective_overlay}")
                temp_overlay_path = output_path.replace(".mp4", "_overlay_temp.mp4")
                
                # ── Resolve overlay settings from config.yaml ──
                overlay_name = os.path.basename(effective_overlay)
                overlays_cfg = config.get("overlays", {})
                file_cfg = overlays_cfg.get(overlay_name, {})
                default_cfg = overlays_cfg.get("default", {})
                
                def get_val(key, default_fallback):
                    return file_cfg.get(key, default_cfg.get(key, default_fallback))
                
                colorkey_hex = get_val("colorkey_hex", get_val("chromakey_hex", "0x2E9043"))
                similarity = get_val("similarity", get_val("chroma_similarity", 0.20))
                blend = get_val("blend", get_val("chroma_blend", 0.02))
                despill_val = get_val("despill", None)
                eq_val = get_val("eq", None)
                scale_w = get_val("scale_width", -1)
                ov_pos = get_val("position", "x=(W-w)/2:y=H-h")
                crop_val = get_val("crop", None)
                
                # Resolve scale_height, utilizing ffmpeg probe if not configured in the specific file block
                if "scale_height" in file_cfg:
                    scale_h = file_cfg["scale_height"]
                else:
                    # ── Detect overlay dimensions using ffmpeg (ffprobe may not exist on Windows) ──
                    is_vertical = False
                    try:
                        probe_cmd = [
                            ffmpeg_exe, "-i", effective_overlay,
                            "-hide_banner",
                        ]
                        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
                        probe_output = probe_res.stderr  # ffmpeg prints info to stderr
                        
                        import re as _re
                        dim_match = _re.search(r'(\d{2,5})x(\d{2,5})', probe_output)
                        if dim_match:
                            ov_w = int(dim_match.group(1))
                            ov_h = int(dim_match.group(2))
                            is_vertical = ov_h > ov_w
                            logger.info(f"[Composer] Overlay dimensions: {ov_w}x{ov_h} ({'vertical' if is_vertical else 'widescreen'})")
                        else:
                            logger.warning("[Composer] Could not parse overlay dimensions from ffmpeg output, defaulting to widescreen")
                    except Exception as probe_err:
                        logger.warning(f"[Composer] Overlay dimension probe failed: {probe_err}, defaulting to widescreen")
                    
                    scale_h = default_cfg.get("scale_height", 950 if is_vertical else 580)
                
                logger.info(f"[Composer] Resolved overlay '{overlay_name}' settings: scale={scale_w}:{scale_h}, pos={ov_pos}, key={colorkey_hex}:{similarity}:{blend}")
                
                # ── Construct the chroma key filter chain ──
                filters = []
                filters.append("format=rgba")
                if crop_val:
                    filters.append(f"crop={crop_val}")
                filters.append(f"colorkey={colorkey_hex}:{similarity}:{blend}")
                if despill_val and str(despill_val).lower() not in ("none", "null", ""):
                    filters.append(despill_val if despill_val.startswith("despill=") else f"despill={despill_val}")
                if eq_val and str(eq_val).lower() not in ("none", "null", ""):
                    filters.append(eq_val if eq_val.startswith("eq=") else f"eq={eq_val}")
                filters.append(f"scale={scale_w}:{scale_h}")
                filters.append("format=yuva420p")
                
                chroma_filter = ",".join(filters)
                
                enable_clause = ""
                if broll_intervals:
                    betweens = "+".join([f"between(t,{start:.2f},{end:.2f})" for start, end in broll_intervals])
                    enable_clause = f":enable='not({betweens})'"
                    logger.info(f"[Composer] Hiding Oggy during B-roll intervals: {broll_intervals}")
                
                cmd_overlay = [
                    ffmpeg_exe, "-y",
                    "-i", output_path,
                    "-stream_loop", "-1", "-i", effective_overlay,
                    "-filter_complex",
                    f"[1:v]{chroma_filter}[oggy];[0:v][oggy]overlay={ov_pos}{enable_clause}:shortest=1[v]",
                    "-map", "[v]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    temp_overlay_path
                ]
                
                logger.info(f"[Composer] FFmpeg overlay command: {' '.join(cmd_overlay)}")
                overlay_result = subprocess.run(cmd_overlay, capture_output=True, text=True)
                
                if overlay_result.returncode != 0:
                    logger.error(f"[Composer] FFmpeg overlay FAILED (exit {overlay_result.returncode})")
                    logger.error(f"[Composer] FFmpeg stderr:\n{overlay_result.stderr[-2000:]}")
                else:
                    if os.path.exists(temp_overlay_path) and os.path.getsize(temp_overlay_path) > 0:
                        os.replace(temp_overlay_path, output_path)
                        logger.info(f"[Composer] Final video with overlay ready.")
                    else:
                        logger.error("[Composer] Overlay temp file missing or empty after FFmpeg ran successfully")
            
        except Exception as overlay_err:
            logger.error(f"[Composer] Overlay application failed: {overlay_err}")
            import traceback
            logger.error(traceback.format_exc())
            
        # ── Prepend Intro if enabled ──
        if config.get("use_oggy_intro"):
            logger.info("[Composer] Prepending Oggy intro sequence...")
            intro_path = str(PROJECT_ROOT / "assets/oggy_video/oggy_intro.mp4")
            if not os.path.exists(intro_path):
                intro_path = "assets/oggy_video/oggy_intro.mp4"
                
            if os.path.exists(intro_path):
                try:
                    from moviepy import VideoFileClip, TextClip, CompositeVideoClip
                    intro_clip = VideoFileClip(intro_path)
                    _clips_to_close.append(intro_clip)
                    
                    # Resize/crop to match dimensions of base video clip
                    if hasattr(intro_clip, "resized"):
                        intro_clip = intro_clip.resized((width, height))
                    elif hasattr(intro_clip, "resize"):
                        intro_clip = intro_clip.resize(newsize=(width, height))
                        
                    # Prepare topic text to overlay on the chalkboard
                    intro_text = topic if topic else "Today's Topic"
                    
                    # Find a valid font to prevent ValueError/cannot open resource on Windows
                    font_choices = [
                        "impact.ttf", "Impact.ttf", "arialbd.ttf", "Arial Bold.ttf", "arial.ttf", "Arial.ttf",
                        "calibrib.ttf", "segoeui.ttf", "DejaVuSans.ttf"
                    ]
                    valid_font = "impact.ttf"
                    from PIL import ImageFont
                    for f_name in font_choices:
                        try:
                            ImageFont.truetype(f_name, 24)
                            valid_font = f_name
                            break
                        except Exception:
                            continue
                            
                    # Chalkboard box size: (680, 360)
                    box_w = 680
                    box_h = 360
                    
                    # TextClip with caption method for automatic word wrap
                    text_clip = TextClip(
                        text=intro_text,
                        font=valid_font,
                        font_size=75,
                        color="yellow",
                        stroke_color="black",
                        stroke_width=2.5,
                        method="caption",
                        size=(box_w, box_h),
                    )
                    _clips_to_close.append(text_clip)
                    
                    # Timing: start 8.5s, duration intro_clip.duration - 8.5s
                    text_start = 8.5
                    text_dur = intro_clip.duration - text_start
                    
                    if hasattr(text_clip, "with_start"):
                        text_clip = text_clip.with_start(text_start)
                    elif hasattr(text_clip, "set_start"):
                        text_clip = text_clip.set_start(text_start)
                        
                    if hasattr(text_clip, "with_duration"):
                        text_clip = text_clip.with_duration(text_dur)
                    elif hasattr(text_clip, "set_duration"):
                        text_clip = text_clip.set_duration(text_dur)
                        
                    # Position centered horizontally, y = 320
                    if hasattr(text_clip, "with_position"):
                        text_clip = text_clip.with_position(('center', 320))
                    elif hasattr(text_clip, "set_position"):
                        text_clip = text_clip.set_position(('center', 320))
                        
                    # Composite intro segment
                    final_intro_segment = CompositeVideoClip([intro_clip, text_clip])
                    _clips_to_close.append(final_intro_segment)
                    
                    # Render the intro segment to a unique temporary file
                    intro_temp_path = output_path.replace(".mp4", "_intro_temp.mp4")
                    logger.info(f"[Composer] Rendering intro segment to: {intro_temp_path}")
                    final_intro_segment.write_videofile(
                        intro_temp_path,
                        fps=fps,
                        codec=video_cfg.get("codec", "libx264"),
                        audio_codec=video_cfg.get("audio_codec", "aac"),
                        bitrate=video_cfg.get("bitrate", "8000k"),
                        logger=None,
                        threads=4,
                    )
                    
                    # Close intro clips immediately to release Windows file locks
                    for c in _clips_to_close:
                        try:
                            c.close()
                        except Exception:
                            pass
                    _clips_to_close.clear()
                    
                    # Concatenate the intro video and the overlaid base video using FFmpeg
                    if os.path.exists(intro_temp_path):
                        concat_temp_path = output_path.replace(".mp4", "_concat_temp.mp4")
                        logger.info("[Composer] Concatenating intro and base video using FFmpeg...")
                        
                        cmd_concat = [
                            ffmpeg_exe, "-y",
                            "-i", intro_temp_path,
                            "-i", output_path,
                            "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                            "-map", "[v]", "-map", "[a]",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                            "-c:a", "aac", "-b:a", "192k",
                            concat_temp_path
                        ]
                        logger.info(f"[Composer] FFmpeg concat command: {' '.join(cmd_concat)}")
                        concat_res = subprocess.run(cmd_concat, capture_output=True, text=True)
                        
                        if concat_res.returncode != 0:
                            logger.error(f"[Composer] FFmpeg concat FAILED: {concat_res.stderr}")
                        else:
                            if os.path.exists(concat_temp_path) and os.path.getsize(concat_temp_path) > 0:
                                os.replace(concat_temp_path, output_path)
                                logger.info("[Composer] Final concatenated video ready.")
                            else:
                                logger.error("[Composer] Concatenated temp file missing or empty.")
                                
                        # Clean up intro temp file
                        try:
                            os.remove(intro_temp_path)
                        except Exception:
                            pass
                except Exception as intro_err:
                    logger.error(f"[Composer] Intro processing failed: {intro_err}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.error(f"[Composer] Intro source video not found at: {intro_path}")
                
        return output_path
        
    except Exception as e:
        logger.error(f"[Composer] Video rendering failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
    finally:
        # ── GUARANTEED CLEANUP: Release all MoviePy file handles on Windows ──
        for c in _clips_to_close:
            try:
                c.close()
            except Exception:
                pass
        _clips_to_close.clear()
        logger.info("[Composer] All MoviePy clip handles released.")
