"""
Subtitle Engine - Renders word-by-word karaoke-style subtitles
with multiple animation styles on video frames.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple, Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _get_font(font_family: str = "Arial", size: int = 48, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Load a font with fallbacks."""
    font_names = []
    
    if bold:
        font_names.extend([
            f"{font_family} Bold", f"{font_family}bd",
            "arialbd.ttf", "Arial Bold.ttf",
            "calibrib.ttf", "seguisb.ttf",
        ])
    
    font_names.extend([
        f"{font_family}", f"{font_family}.ttf",
        "arial.ttf", "Arial.ttf",
        "calibri.ttf", "segoeui.ttf",
        "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
    ])
    
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    
    logger.warning(f"[Subtitle] Could not load font '{font_family}', using default")
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        line = ' '.join(current_line)
        bbox = font.getbbox(line)
        if bbox[2] - bbox[0] > max_width and len(current_line) > 1:
            current_line.pop()
            lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines


def render_subtitle_frame(
    frame: Image.Image,
    sentence_data: Dict,
    current_time: float,
    config: Dict,
    return_rgba: bool = False,
) -> Image.Image:
    """
    Render subtitles onto a video frame with karaoke highlighting.
    
    Args:
        frame: PIL Image frame to render on
        sentence_data: Dict with 'text', 'words', 'start', 'end'
        current_time: Current timestamp in seconds
        config: Subtitle config from config.yaml
        
    Returns:
        Frame with subtitles rendered
    """
    sub_cfg = config.get("subtitles", {})
    video_cfg = config.get("video", {})
    
    width = video_cfg.get("width", 1080)
    height = video_cfg.get("height", 1920)
    
    # Position — default 0.12 places subtitles near the top, above content images.
    pos_y_ratio = sub_cfg.get("position_y", 0.12)
    max_width_ratio = sub_cfg.get("max_width_ratio", 0.88)
    
    # Font
    font_family = sub_cfg.get("font_family", "Arial")
    font_size = int(sub_cfg.get("font_size", 48) * 1.12)
    font_bold = sub_cfg.get("font_bold", True)
    
    # Colors
    text_color = tuple(sub_cfg.get("text_color", [255, 255, 255]))
    highlight_color = tuple(sub_cfg.get("highlight_color", [0, 191, 255]))
    outline_color = tuple(sub_cfg.get("outline_color", [0, 0, 0]))
    outline_width = sub_cfg.get("outline_width", 3)
    
    # Background
    bg_enabled = sub_cfg.get("bg_enabled", True)
    bg_color = tuple(sub_cfg.get("bg_color", [0, 0, 0]))
    bg_opacity = sub_cfg.get("bg_opacity", 0.65)
    bg_padding = sub_cfg.get("bg_padding", [15, 25, 15, 25])
    bg_corner_radius = sub_cfg.get("bg_corner_radius", 12)
    
    # Karaoke
    karaoke_enabled = sub_cfg.get("karaoke_enabled", True)
    words_per_line = sub_cfg.get("words_per_line", 6)
    
    # Animation
    entrance_anim = sub_cfg.get("entrance_animation", "fade_up")
    
    text = sentence_data.get("text", "")
    import re
    if text:
        text = re.sub(r'\[[a-zA-Z0-9]+\]', '', text)
        text = text.replace('[]', '').strip()
        
    words = sentence_data.get("words", [])
    if not words and text:
        words = text.split()
        
    cleaned_words = []
    for w in words:
        cleaned_w = re.sub(r'\[[a-zA-Z0-9]+\]', '', w)
        cleaned_w = cleaned_w.replace('[]', '').strip()
        if cleaned_w:
            cleaned_words.append(cleaned_w)
    words = cleaned_words
    start_time = sentence_data.get("start", 0)
    end_time = sentence_data.get("end", 0)
    
    if not text:
        return Image.new('RGBA', frame.size, (0, 0, 0, 0)) if return_rgba else frame
    
    # Calculate progress within this sentence
    duration = end_time - start_time
    if duration <= 0:
        return Image.new('RGBA', frame.size, (0, 0, 0, 0)) if return_rgba else frame
    
    elapsed = current_time - start_time
    progress = max(0.0, min(1.0, elapsed / duration))
    
    current_word_index = int(progress * len(words)) if karaoke_enabled else -1
    current_word_index = min(max(0, current_word_index), len(words) - 1)
    
    # Group words into chunks of maximum 45-50 characters per screen or sentence boundaries
    max_char_len = 48
    chunks = []
    current_chunk_words = []
    current_chunk_len = 0
    start_idx = 0
    
    for i, word in enumerate(words):
        added_len = len(word) + (1 if current_chunk_len > 0 else 0)
        ends_with_boundary = any(word.endswith(char) for char in ['.', '?', '!'])
        
        if current_chunk_len + added_len > max_char_len and current_chunk_words:
            chunks.append({
                "words": current_chunk_words,
                "start_idx": start_idx,
                "end_idx": i
            })
            current_chunk_words = [word]
            current_chunk_len = len(word)
            start_idx = i
        else:
            current_chunk_words.append(word)
            current_chunk_len += added_len
            
        if ends_with_boundary:
            chunks.append({
                "words": current_chunk_words,
                "start_idx": start_idx,
                "end_idx": i + 1
            })
            current_chunk_words = []
            current_chunk_len = 0
            start_idx = i + 1
            
    if current_chunk_words:
        chunks.append({
            "words": current_chunk_words,
            "start_idx": start_idx,
            "end_idx": len(words)
        })
        
    selected_chunk = chunks[0]
    for chunk in chunks:
        if chunk["start_idx"] <= current_word_index < chunk["end_idx"]:
            selected_chunk = chunk
            break
            
    chunk_words = selected_chunk["words"]
    start_idx = selected_chunk["start_idx"]
    end_idx = selected_chunk["end_idx"]
    chunk_text = " ".join(chunk_words)
    
    # Load font
    font = _get_font(font_family, font_size, font_bold)
    max_text_width = int(width * max_width_ratio)
    
    if not chunk_words:
        return Image.new('RGBA', frame.size, (0, 0, 0, 0)) if return_rgba else frame
    
    lines = _wrap_text(chunk_text, font, max_text_width)
    
    # Create overlay for rendering
    overlay = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Calculate text dimensions
    line_height = font_size + 8
    total_text_height = len(lines) * line_height
    
    # Position
    text_y = int(height * pos_y_ratio) - total_text_height // 2
    
    # Entrance animation calculations
    anim_progress = min(1.0, elapsed / 0.3) if elapsed >= 0 else 0  # 0.3s entrance
    exit_progress = min(1.0, (end_time - current_time) / 0.3)       # 0.3s exit
    
    alpha_multiplier = 1.0
    y_offset = 0
    
    if entrance_anim == "fade_up":
        alpha_multiplier = anim_progress * exit_progress
        y_offset = int((1 - anim_progress) * 30)  # Slide up from 30px below
    elif entrance_anim == "pop_in":
        scale = 0.5 + 0.5 * anim_progress
        alpha_multiplier = anim_progress * exit_progress
    elif entrance_anim == "slide_left":
        x_shift = int((1 - anim_progress) * width * 0.3)
        alpha_multiplier = exit_progress
    elif entrance_anim == "typewriter":
        alpha_multiplier = exit_progress
    
    text_y += y_offset
    
    # Draw background box
    if bg_enabled and alpha_multiplier > 0.1:
        # Calculate total text bounds
        max_line_width = 0
        for line in lines:
            bbox = font.getbbox(line)
            line_w = bbox[2] - bbox[0]
            max_line_width = max(max_line_width, line_w)
        
        pad = bg_padding  # [top, right, bottom, left]
        bg_x1 = (width - max_line_width) // 2 - pad[3]
        bg_y1 = text_y - pad[0]
        bg_x2 = (width + max_line_width) // 2 + pad[1]
        bg_y2 = text_y + total_text_height + pad[2]
        
        bg_alpha = int(255 * bg_opacity * alpha_multiplier)
        bg_rgba = bg_color + (bg_alpha,)
        
        draw.rounded_rectangle(
            [bg_x1, bg_y1, bg_x2, bg_y2],
            radius=bg_corner_radius,
            fill=bg_rgba,
        )
    
    # Draw text with karaoke highlighting
    word_index = start_idx
    # current_word_index is already calculated above
    
    for line_idx, line in enumerate(lines):
        y_pos = text_y + line_idx * line_height
        line_words = line.split()
        
        # Calculate line width for centering
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x_start = (width - line_width) // 2
        
        if karaoke_enabled:
            # Render word by word with highlighting
            x_pos = x_start
            for word in line_words:
                word_display = word + " "
                word_bbox = font.getbbox(word_display)
                word_width = word_bbox[2] - word_bbox[0]
                
                # Determine color
                is_current = word_index == current_word_index
                is_spoken = word_index <= current_word_index
                
                if is_current:
                    color = highlight_color
                elif is_spoken:
                    color = text_color
                else:
                    # Slightly dimmed for unspoken words
                    color = tuple(max(0, c - 40) for c in text_color)
                
                text_alpha = int(255 * alpha_multiplier)
                color_rgba = color + (text_alpha,)
                outline_rgba = outline_color + (text_alpha,)
                
                # Draw outline
                for ox in range(-outline_width, outline_width + 1):
                    for oy in range(-outline_width, outline_width + 1):
                        if ox == 0 and oy == 0:
                            continue
                        draw.text((x_pos + ox, y_pos + oy), word_display, font=font, fill=outline_rgba)
                
                # Draw text
                draw.text((x_pos, y_pos), word_display, font=font, fill=color_rgba)
                
                x_pos += word_width
                word_index += 1
        else:
            # Simple rendering without karaoke
            text_alpha = int(255 * alpha_multiplier)
            color_rgba = text_color + (text_alpha,)
            outline_rgba = outline_color + (text_alpha,)
            
            # Draw outline
            for ox in range(-outline_width, outline_width + 1):
                for oy in range(-outline_width, outline_width + 1):
                    if ox == 0 and oy == 0:
                        continue
                    draw.text((x_start + ox, y_pos + oy), line, font=font, fill=outline_rgba)
            
            draw.text((x_start, y_pos), line, font=font, fill=color_rgba)
    
    if return_rgba:
        return overlay

    # Composite overlay onto frame
    if frame.mode != 'RGBA':
        frame = frame.convert('RGBA')
    
    frame = Image.alpha_composite(frame, overlay)
    
    return frame.convert('RGB')
