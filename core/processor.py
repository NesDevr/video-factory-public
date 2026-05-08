"""Stage 3: Image processing — crop/resize with face detection.

Prepares images for video assembly. Geometry only — no visual effects here.
Visual effects (grain, vignette) are applied at video level in Stage 4.
"""

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from core.utils import ChannelConfig

logger = logging.getLogger("video_factory")

# OpenCV face detection cascade (ships with opencv-python)
_face_cascade = None


def _get_face_cascade():
    global _face_cascade
    if _face_cascade is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_cascade = cv2.CascadeClassifier(cascade_path)
    return _face_cascade


def process_images(
    workspace: Path,
    config: ChannelConfig,
    target_size: tuple[int, int] = (1920, 1080),
    watermark_path: Path | None = None,
) -> list[Path]:
    """Process all raw images into ready-for-assembly images.

    Steps per image:
    1. Smart crop to 16:9 using face/subject detection
    2. Resize to target resolution
    3. Apply channel watermark (optional)

    Returns list of output paths.
    """
    raw_dir = workspace / "images" / "raw"
    ready_dir = workspace / "images" / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)

    output_paths = []
    for img_path in sorted(raw_dir.glob("section_*")):
        out_path = ready_dir / img_path.with_suffix(".png").name
        if out_path.exists():
            output_paths.append(out_path)
            continue

        try:
            img = Image.open(img_path).convert("RGB")
            img = _fit_to_canvas(img, target_size)

            if watermark_path and watermark_path.exists():
                img = _apply_watermark(
                    img,
                    watermark_path,
                    position=config.style.watermark.get("position", "bottom_right"),
                    opacity=config.style.watermark.get("opacity", 0.3),
                )

            img.save(out_path, "PNG")
            output_paths.append(out_path)
            logger.info(f"Processed: {img_path.name} → {out_path.name}")

        except Exception as e:
            logger.error(f"Failed to process {img_path.name}: {e}")

    logger.info(f"Processed {len(output_paths)} images")
    return output_paths


def _fit_to_canvas(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Fit full image to target canvas — no cropping, ever.

    If the image exactly matches the target aspect ratio, resize directly.
    Otherwise, scale to fit inside the canvas and fill the rest with a
    blurred version of the image.
    """
    tw, th = target_size
    iw, ih = img.size
    target_ratio = tw / th
    img_ratio = iw / ih

    # If aspect ratio matches (within tolerance), just resize
    if abs(img_ratio - target_ratio) < 0.05:
        return img.resize(target_size, Image.Resampling.LANCZOS)

    from PIL import ImageFilter

    # Create blurred background by stretching the image to fill the canvas
    bg = img.resize(target_size, Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))

    # Scale the original to fit entirely within the canvas (no crop)
    scale = min(tw / iw, th / ih)
    new_w = max(1, int(iw * scale))
    new_h = max(1, int(ih * scale))
    sharp = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Center on the blurred background
    x = (tw - new_w) // 2
    y = (th - new_h) // 2
    bg.paste(sharp, (x, y))

    return bg


def _smart_crop(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Crop image to target aspect ratio, centering on detected faces."""
    target_w, target_h = target_size
    target_ratio = target_w / target_h
    img_w, img_h = img.size
    img_ratio = img_w / img_h

    if abs(img_ratio - target_ratio) < 0.01:
        return img  # Already correct ratio

    # Detect faces to find crop center
    center_x, center_y = img_w // 2, img_h // 2
    faces = _detect_faces(img)
    if faces:
        # Center crop on the average face position
        avg_x = int(np.mean([f[0] + f[2] // 2 for f in faces]))
        avg_y = int(np.mean([f[1] + f[3] // 2 for f in faces]))
        center_x, center_y = avg_x, avg_y

    # Calculate crop box
    if img_ratio > target_ratio:
        # Image is wider — crop sides
        new_w = int(img_h * target_ratio)
        new_h = img_h
    else:
        # Image is taller — crop top/bottom
        new_w = img_w
        new_h = int(img_w / target_ratio)

    # Position crop centered on the detection point
    left = max(0, min(center_x - new_w // 2, img_w - new_w))
    top = max(0, min(center_y - new_h // 2, img_h - new_h))

    return img.crop((left, top, left + new_w, top + new_h))


def _detect_faces(img: Image.Image) -> list:
    """Detect faces using OpenCV Haar cascade."""
    try:
        cascade = _get_face_cascade()
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        # Downscale for faster detection
        scale = max(1, min(cv_img.shape) // 500)
        if scale > 1:
            small = cv2.resize(cv_img, None, fx=1/scale, fy=1/scale)
        else:
            small = cv_img
        faces = cascade.detectMultiScale(small, 1.1, 4, minSize=(30, 30))
        # Scale back up
        return [(int(x*scale), int(y*scale), int(w*scale), int(h*scale))
                for (x, y, w, h) in faces]
    except Exception:
        return []


def _apply_watermark(
    img: Image.Image,
    watermark_path: Path,
    position: str = "bottom_right",
    opacity: float = 0.3,
) -> Image.Image:
    """Overlay a watermark image with transparency."""
    try:
        wm = Image.open(watermark_path).convert("RGBA")
        # Scale watermark to ~10% of image width
        wm_w = img.size[0] // 10
        wm_h = int(wm.size[1] * (wm_w / wm.size[0]))
        wm = wm.resize((wm_w, wm_h), Image.Resampling.LANCZOS)

        # Apply opacity
        alpha = wm.getchannel("A")
        alpha = alpha.point(lambda a: int(a * opacity))
        wm.putalpha(alpha)

        # Position
        margin = 20
        pos_map = {
            "bottom_right": (img.size[0] - wm_w - margin, img.size[1] - wm_h - margin),
            "bottom_left": (margin, img.size[1] - wm_h - margin),
            "top_right": (img.size[0] - wm_w - margin, margin),
            "top_left": (margin, margin),
        }
        pos = pos_map.get(position, pos_map["bottom_right"])

        result = img.copy().convert("RGBA")
        result.paste(wm, pos, wm)
        return result.convert("RGB")

    except Exception as e:
        logger.warning(f"Watermark failed: {e}")
        return img
