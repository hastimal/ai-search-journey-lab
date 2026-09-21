"""UI asset and sponsor branding helpers for Streamlit Search Journey Inspector.

Provides clean logo rendering in the header with auto-cropping using images from assets/.
"""

import base64
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Optional

import streamlit as st
from PIL import Image, ImageChops

ASSETS_DIR = Path("assets")

# Sponsor asset paths based on files in assets/
GDG_SVG_ASSET = ASSETS_DIR / "gdg.svg"
GDG_JPEG_ASSET = ASSETS_DIR / "gdg.jpeg"
GOOGLE_STARTUP_ASSET = ASSETS_DIR / "google-for-startup.webp"


def autocrop_image(im: Image.Image, padding: int = 4) -> Image.Image:
    """Automatically trim empty or uniform background margins from an image."""
    try:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            im_rgba = im.convert("RGBA")
            alpha = im_rgba.split()[-1]
            bbox = alpha.getbbox()
        else:
            im_rgb = im.convert("RGB")
            bg = Image.new("RGB", im_rgb.size, im_rgb.getpixel((0, 0)))
            diff = ImageChops.difference(im_rgb, bg)
            diff = ImageChops.add(diff, diff, 2.0, -10)
            bbox = diff.getbbox()

        if bbox:
            w, h = im.size
            padded_bbox = (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(w, bbox[2] + padding),
                min(h, bbox[3] + padding),
            )
            return im.crop(padded_bbox)
    except Exception:
        pass
    return im


def load_optional_image(path: Path | str) -> Optional[Path]:
    """Return Path if image file exists and is accessible, else None."""
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return p
    return None


def load_and_autocrop_image(path: Path | str, padding: int = 4) -> Optional[Image.Image]:
    """Load image from path and auto-crop surrounding margins if valid."""
    p = Path(path)
    if not (p.is_file() and p.stat().st_size > 0):
        return None
    try:
        with Image.open(p) as img:
            img_copy = img.copy()
            return autocrop_image(img_copy, padding=padding)
    except Exception:
        return None


def get_image_data_uri(path_or_img: Path | str | Image.Image) -> Optional[str]:
    """Encode Path or PIL Image to a base64 data URI for safe HTML rendering."""
    if isinstance(path_or_img, Image.Image):
        buf = BytesIO()
        path_or_img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"

    p = Path(path_or_img)
    if not (p.is_file() and p.stat().st_size > 0):
        return None

    ext = p.suffix.lower()
    mime = "image/svg+xml" if ext == ".svg" else ("image/webp" if ext == ".webp" else "image/png")
    encoded = base64.b64encode(p.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def get_available_branding_assets() -> dict[str, Optional[Path]]:
    """Return dictionary of available branding image paths."""
    return {
        "gdg": load_optional_image(GDG_SVG_ASSET) or load_optional_image(GDG_JPEG_ASSET),
        "gdg_svg": load_optional_image(GDG_SVG_ASSET),
        "google_startup": load_optional_image(GOOGLE_STARTUP_ASSET),
        "sa_logo": load_optional_image(ASSETS_DIR / "sa_logo.png"),
        "geekdom_logo": load_optional_image(ASSETS_DIR / "geekdom_logo.png"),
        "context_logo": load_optional_image(ASSETS_DIR / "context_logo.png"),
    }


def render_header_logos() -> None:
    """Render GDG (SVG) and Google for Startups logos aligned on the exact same center axis."""
    gdg_svg = load_optional_image(GDG_SVG_ASSET)
    gdg_jpeg = load_optional_image(GDG_JPEG_ASSET)
    google_img = load_and_autocrop_image(GOOGLE_STARTUP_ASSET)

    elements = []
    if gdg_svg:
        gdg_uri = get_image_data_uri(gdg_svg)
        if gdg_uri:
            elements.append(
                f'<img src="{gdg_uri}" alt="GDG" '
                'style="height: 36px; width: auto; object-fit: contain; '
                'display: inline-block; vertical-align: middle;" />'
            )
    elif gdg_jpeg:
        cropped = load_and_autocrop_image(gdg_jpeg)
        if cropped:
            gdg_uri = get_image_data_uri(cropped)
            if gdg_uri:
                elements.append(
                    f'<img src="{gdg_uri}" alt="GDG" '
                    'style="height: 36px; width: auto; object-fit: contain; '
                    'display: inline-block; vertical-align: middle;" />'
                )

    if google_img:
        google_uri = get_image_data_uri(google_img)
        if google_uri:
            elements.append(
                f'<img src="{google_uri}" alt="Google for Startups" '
                'style="height: 30px; width: auto; object-fit: contain; '
                'display: inline-block; vertical-align: middle;" />'
            )

    if not elements:
        return

    html_content = textwrap.dedent(f"""
        <style>
        @keyframes g-rotate-border {{
            0% {{
                transform: translate(-50%, -50%) rotate(0deg);
            }}
            100% {{
                transform: translate(-50%, -50%) rotate(360deg);
            }}
        }}
        @keyframes g-sparkle-pulse {{
            0%, 100% {{
                box-shadow: 0 0 14px rgba(66, 133, 244, 0.45), 0 0 24px rgba(234, 67, 53, 0.25);
                filter: brightness(1.0);
            }}
            25% {{
                box-shadow: 0 0 20px rgba(234, 67, 53, 0.6), 0 0 30px rgba(251, 188, 5, 0.35);
                filter: brightness(1.08);
            }}
            50% {{
                box-shadow: 0 0 18px rgba(251, 188, 5, 0.5), 0 0 28px rgba(52, 168, 83, 0.35);
                filter: brightness(1.04);
            }}
            75% {{
                box-shadow: 0 0 20px rgba(52, 168, 83, 0.6), 0 0 30px rgba(66, 133, 244, 0.35);
                filter: brightness(1.08);
            }}
        }}
        @keyframes g-sparkle-sweep {{
            0% {{
                left: -140%;
                opacity: 0;
            }}
            20% {{
                opacity: 0.5;
            }}
            45% {{
                left: 140%;
                opacity: 0;
            }}
            100% {{
                left: 140%;
                opacity: 0;
            }}
        }}
        .g-sponsor-badge-outer {{
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 2px;
            border-radius: 14px;
            overflow: hidden;
            margin-bottom: 14px;
            animation: g-sparkle-pulse 3.6s ease-in-out infinite;
            background: transparent;
            transition: transform 0.2s ease;
        }}
        .g-sponsor-badge-outer:hover {{
            transform: translateY(-1px);
        }}
        .g-sponsor-badge-rotating-bg {{
            position: absolute;
            top: 50%;
            left: 50%;
            width: 350%;
            aspect-ratio: 1 / 1;
            background: conic-gradient(
                from 0deg,
                #4285F4 0deg,
                #EA4335 90deg,
                #FBBC05 180deg,
                #34A853 270deg,
                #4285F4 360deg
            );
            animation: g-rotate-border 4s linear infinite;
            z-index: 1;
            transform-origin: center center;
        }}
        .g-sponsor-badge-inner {{
            position: relative;
            z-index: 2;
            display: inline-flex;
            align-items: center;
            gap: 16px;
            padding: 8px 20px;
            background: linear-gradient(135deg, #131722 0%, #0d1017 100%);
            border-radius: 12px;
            overflow: hidden;
        }}
        .g-sponsor-badge-shimmer {{
            position: absolute;
            top: 0;
            left: -140%;
            width: 80%;
            height: 100%;
            background: linear-gradient(
                90deg,
                transparent 0%,
                rgba(255, 255, 255, 0.22) 50%,
                transparent 100%
            );
            transform: skewX(-20deg);
            animation: g-sparkle-sweep 4.5s ease-in-out infinite;
            pointer-events: none;
            z-index: 3;
        }}
        </style>
        <div class="g-sponsor-badge-outer">
            <div class="g-sponsor-badge-rotating-bg"></div>
            <div class="g-sponsor-badge-inner">
                <div class="g-sponsor-badge-shimmer"></div>
                {"".join(elements)}
            </div>
        </div>
    """).strip()
    st.markdown(html_content, unsafe_allow_html=True)


def render_demo_context() -> None:
    """Render compact demo context caption if needed."""
    pass


# Backwards compatibility alias
render_header_sponsor_badges = render_header_logos

