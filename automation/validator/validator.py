"""
Video Validator
Validates generated MP4 files before publishing.
Checks: existence, size, format, resolution, duration, audio/video streams.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


@dataclass
class ValidationResult:
    """Result of video validation."""
    valid: bool
    video_path: str
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    codec_video: str = ""
    codec_audio: str = ""
    errors: list = None
    warnings: list = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class VideoValidator:
    """Validates generated reel videos."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.val_config = config.get("validation", {})
        self.enabled = self.val_config.get("enabled", True)
        self.checks = self.val_config.get("checks", {})
        self.max_retries = self.val_config.get("max_retries", 2)
        self.retry_delay = self.val_config.get("retry_delay_seconds", 30)
        
        # Expected values
        self.expected_width = config.get("video", {}).get("width", 1080)
        self.expected_height = config.get("video", {}).get("height", 1920)
        self.expected_fps = config.get("video", {}).get("fps", 30)
        self.duration_tolerance = 0.10  # 10%
    
    def validate(self, video_path: str, expected_duration: float = None) -> ValidationResult:
        """Run all validation checks on a video file."""
        if not self.enabled:
            return ValidationResult(valid=True, video_path=video_path)
        
        result = ValidationResult(valid=True, video_path=video_path)
        
        # Check 1: File exists
        if self.checks.get("file_exists", True):
            if not self._check_file_exists(video_path, result):
                return result  # Can't continue if file doesn't exist
        
        # Check 2: File not empty
        if self.checks.get("file_not_empty", True):
            self._check_file_not_empty(video_path, result)
        
        # Check 3: Valid MP4 (ffprobe)
        if self.checks.get("valid_mp4", True):
            self._check_valid_mp4(video_path, result)
        
        # Check 4: Correct resolution
        if self.checks.get("correct_resolution", True):
            self._check_resolution(video_path, result)
        
        # Check 5: Correct duration
        if self.checks.get("correct_duration", True) and expected_duration:
            self._check_duration(video_path, result, expected_duration)
        
        # Check 6: Has audio
        if self.checks.get("has_audio", True):
            self._check_audio(video_path, result)
        
        # Check 7: Has video stream
        if self.checks.get("has_video_stream", True):
            self._check_video_stream(video_path, result)
        
        # Overall validity
        result.valid = len(result.errors) == 0
        
        if result.valid:
            logger.info(f"Video validation PASSED: {video_path}")
        else:
            logger.error(f"Video validation FAILED: {video_path} - Errors: {result.errors}")
        
        return result
    
    def _check_file_exists(self, video_path: str, result: ValidationResult) -> bool:
        """Check if file exists."""
        if not os.path.exists(video_path):
            result.errors.append(f"File does not exist: {video_path}")
            result.valid = False
            return False
        return True
    
    def _check_file_not_empty(self, video_path: str, result: ValidationResult):
        """Check if file is not empty."""
        size = os.path.getsize(video_path)
        result.file_size_bytes = size
        if size == 0:
            result.errors.append("File is empty (0 bytes)")
            result.valid = False
        elif size < 1024:  # Less than 1KB
            result.warnings.append(f"File suspiciously small: {size} bytes")
    
    def _check_valid_mp4(self, video_path: str, result: ValidationResult):
        """Check if file is a valid MP4 using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,r_frame_rate",
                "-of", "json",
                video_path
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if proc.returncode != 0:
                result.errors.append(f"ffprobe failed: {proc.stderr}")
                result.valid = False
                return
            
            import json
            data = json.loads(proc.stdout)
            if not data.get("streams"):
                result.errors.append("No video streams found")
                result.valid = False
                return
            
            stream = data["streams"][0]
            result.codec_video = stream.get("codec_name", "")
            result.width = stream.get("width", 0)
            result.height = stream.get("height", 0)
            
            # Parse frame rate
            fps_str = stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                result.fps = float(num) / float(den) if float(den) > 0 else 0
            
            result.has_video = True
            
        except subprocess.TimeoutExpired:
            result.errors.append("ffprobe timed out")
            result.valid = False
        except json.JSONDecodeError:
            result.errors.append("ffprobe output not valid JSON")
            result.valid = False
        except Exception as e:
            result.errors.append(f"ffprobe error: {e}")
            result.valid = False
    
    def _check_resolution(self, video_path: str, result: ValidationResult):
        """Check if resolution matches expected (9:16 aspect ratio)."""
        if result.width == 0 or result.height == 0:
            return  # Already captured in valid_mp4 check
        
        # Check exact resolution
        if result.width != self.expected_width or result.height != self.expected_height:
            result.errors.append(
                f"Resolution mismatch: got {result.width}x{result.height}, "
                f"expected {self.expected_width}x{self.expected_height}"
            )
            result.valid = False
        
        # Check aspect ratio (9:16 = 0.5625)
        aspect = result.width / result.height if result.height > 0 else 0
        expected_aspect = self.expected_width / self.expected_height
        if abs(aspect - expected_aspect) > 0.01:
            result.warnings.append(f"Aspect ratio {aspect:.4f} differs from expected {expected_aspect:.4f}")
    
    def _check_duration(self, video_path: str, result: ValidationResult, expected_duration: float):
        """Check if duration is within tolerance of expected."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                video_path
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if proc.returncode == 0:
                import json
                data = json.loads(proc.stdout)
                duration = float(data.get("format", {}).get("duration", 0))
                result.duration_seconds = duration
                
                if expected_duration > 0:
                    min_dur = expected_duration * (1 - self.duration_tolerance)
                    max_dur = expected_duration * (1 + self.duration_tolerance)
                    if duration < min_dur or duration > max_dur:
                        result.errors.append(
                            f"Duration {duration:.1f}s outside tolerance "
                            f"[{min_dur:.1f}s, {max_dur:.1f}s] for expected {expected_duration}s"
                        )
                        result.valid = False
            else:
                result.warnings.append(f"Could not get duration: {proc.stderr}")
                
        except Exception as e:
            result.warnings.append(f"Duration check failed: {e}")
    
    def _check_audio(self, video_path: str, result: ValidationResult):
        """Check if video has audio stream."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "json",
                video_path
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if proc.returncode == 0:
                import json
                data = json.loads(proc.stdout)
                if data.get("streams"):
                    result.has_audio = True
                    result.codec_audio = data["streams"][0].get("codec_name", "")
                else:
                    result.errors.append("No audio stream found")
                    result.valid = False
            else:
                result.errors.append(f"Audio stream check failed: {proc.stderr}")
                result.valid = False
                
        except Exception as e:
            result.errors.append(f"Audio check error: {e}")
            result.valid = False
    
    def _check_video_stream(self, video_path: str, result: ValidationResult):
        """Check if video has video stream (redundant with valid_mp4 but explicit)."""
        if not result.has_video:
            result.errors.append("No video stream found")
            result.valid = False


def create_validator(config: Dict[str, Any]) -> VideoValidator:
    """Factory function to create VideoValidator."""
    return VideoValidator(config)