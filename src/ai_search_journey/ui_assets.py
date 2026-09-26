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

    html_content = (
        '<div style="display: flex; align-items: center; gap: 16px; '
        'margin-bottom: 12px;">'
        f'{"".join(elements)}'
        '</div>'
    )
    st.markdown(html_content, unsafe_allow_html=True)


DEFAULT_APP_SUBTITLE = (
    "See how a question becomes intent, fan-out queries, grounded evidence, "
    "deterministic constraint evaluation, ranking, and recommendations."
)


def render_app_title(
    title: str = "🔍 AI Search Journey Lab",
    subtitle: Optional[str] = DEFAULT_APP_SUBTITLE,
) -> None:
    """Render primary title card with compact padding, subtle border, and wrapped subtitle."""
    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<p class="app-header-subtitle">{subtitle}</p>'

    html_content = textwrap.dedent(f"""
        <style>
        .app-title-container {{
            display: inline-flex;
            align-items: center;
            width: fit-content;
            max-width: 100%;
            padding: 6px 16px;
            background: linear-gradient(
                180deg, rgba(30, 34, 45, 0.85) 0%, rgba(18, 22, 30, 0.95) 100%
            );
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            box-shadow: 0 0 18px rgba(66, 133, 244, 0.14),
                0 2px 6px rgba(0, 0, 0, 0.35),
                inset 0 1px 0 rgba(255, 255, 255, 0.08);
            margin-top: 0;
            margin-bottom: 6px;
        }}
        .app-title-text {{
            margin: 0 !important;
            padding: 0 !important;
            font-size: 1.85rem;
            font-weight: 700;
            line-height: 1.25;
            color: #ffffff;
            letter-spacing: -0.015em;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                Roboto, Helvetica, Arial, sans-serif;
        }}
        .app-header-subtitle {{
            max-width: 680px;
            font-size: 0.95rem;
            line-height: 1.5;
            color: rgba(250, 250, 250, 0.7);
            margin: 6px 0 34px 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                Roboto, Helvetica, Arial, sans-serif;
        }}
        .stTextArea label,
        .stTextArea label p,
        .stSelectbox label,
        .stSelectbox label p,
        div[data-testid="stWidgetLabel"] label,
        div[data-testid="stWidgetLabel"] label p {{
            color: #DADCE0 !important;
            font-weight: 500 !important;
            font-size: 0.92rem !important;
            letter-spacing: -0.005em !important;
            text-shadow: none !important;
            box-shadow: none !important;
            background: none !important;
            -webkit-text-fill-color: #DADCE0 !important;
        }}

        /* Run Search Journey primary button typography enhancement */
        button[data-testid="stBaseButton-primary"],
        button[kind="primary"] {{
            font-size: 1.02rem !important;
            font-weight: 600 !important;
            letter-spacing: -0.005em !important;
            height: 44px !important;
        }}

        button[data-testid="stBaseButton-primary"] p,
        button[kind="primary"] p {{
            font-size: 1.02rem !important;
            font-weight: 600 !important;
        }}

        /* Primary Capability Tabs: Top-level stTabs sequence navigation */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] {{
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 12px !important;
            border-bottom: none !important;
            padding: 8px 12px !important;
            background: rgba(15, 23, 42, 0.75) !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 12px !important;
            margin-bottom: 22px !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05),
                0 4px 16px rgba(0, 0, 0, 0.3) !important;
        }}

        /* Primary Tab items */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"] {{
            flex: 1 1 0 !important;
            min-width: 0 !important;
            height: 48px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            border-radius: 8px !important;
            padding: 0 10px !important;
            background-color: rgba(255, 255, 255, 0.04) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            color: rgba(255, 255, 255, 0.85) !important;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            box-sizing: border-box !important;
            position: relative !important;
        }}

        /* Prominent progression arrow between primary stages (omitted after last stage) */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"]:not(:last-child)::after {{
            content: "→" !important;
            position: absolute !important;
            right: -14px !important;
            font-size: 1.15rem !important;
            font-weight: 600 !important;
            line-height: 1 !important;
            color: rgba(255, 255, 255, 0.45) !important;
            pointer-events: none !important;
            z-index: 2 !important;
            user-select: none !important;
        }}

        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"] p,
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"] div[data-testid="stMarkdownContainer"] p {{
            color: rgba(255, 255, 255, 0.85) !important;
            margin: 0 !important;
            padding: 0 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            font-size: 0.95rem;
            font-weight: 600;
            transition: color 0.15s ease !important;
        }}

        /* Primary Tab hover */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"]:hover {{
            background-color: rgba(255, 255, 255, 0.09) !important;
            border-color: rgba(255, 255, 255, 0.25) !important;
            color: #ffffff !important;
            transform: translateY(-1px) !important;
        }}

        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"]:hover p,
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"]:hover
            div[data-testid="stMarkdownContainer"] p {{
            color: #ffffff !important;
        }}

        /* Primary Tab active / selected */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"][aria-selected="true"] {{
            background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%) !important;
            border: 1px solid #ef4444 !important;
            color: #ffffff !important;
            box-shadow: 0 0 16px rgba(220, 38, 38, 0.45),
                inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
        }}

        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"][aria-selected="true"] p,
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"][aria-selected="true"]
            div[data-testid="stMarkdownContainer"] p {{
            color: #ffffff !important;
            font-weight: 700 !important;
        }}

        /* Primary Tab focus ring for keyboard accessibility */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"]:focus-visible {{
            outline: 2px solid #ef4444 !important;
            outline-offset: 2px !important;
        }}

        /* Hide default Streamlit bottom bar indicator for primary tabs */
        div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
            [role="tablist"] > div[data-testid="stTab"] .react-aria-SelectionIndicator {{
            display: none !important;
        }}

        /* V1 Workspace Contextual Label */
        .v1-workspace-header {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.74rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: rgba(255, 255, 255, 0.55);
            margin-top: 4px;
            margin-bottom: 8px;
            user-select: none;
            padding-left: 2px;
        }}

        /* Secondary Tabs (V1 Workspace Sub-Navigation: compact segmented pills) */
        div[data-testid="stTabPanel"] div[data-testid="stTabs"] [role="tablist"] {{
            display: inline-flex !important;
            flex-wrap: wrap !important;
            align-items: center !important;
            gap: 6px !important;
            background: rgba(255, 255, 255, 0.03) !important;
            border: 1px solid rgba(255, 255, 255, 0.07) !important;
            border-radius: 8px !important;
            padding: 4px 6px !important;
            margin-top: 0 !important;
            margin-bottom: 20px !important;
            box-shadow: none !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"] {{
            flex: 0 0 auto !important;
            height: 28px !important;
            padding: 0 10px !important;
            border-radius: 5px !important;
            background-color: transparent !important;
            border: 1px solid transparent !important;
            color: rgba(255, 255, 255, 0.65) !important;
            font-size: 0.80rem !important;
            font-weight: 500 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: all 0.15s ease-in-out !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"] p,
        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"] div[data-testid="stMarkdownContainer"] p {{
            color: rgba(255, 255, 255, 0.65) !important;
            margin: 0 !important;
            padding: 0 !important;
            font-size: 0.80rem !important;
            font-weight: 500 !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"]:hover {{
            background-color: rgba(255, 255, 255, 0.06) !important;
            border-color: rgba(255, 255, 255, 0.1) !important;
            color: #ffffff !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"]:hover p,
        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"]:hover
            div[data-testid="stMarkdownContainer"] p {{
            color: #ffffff !important;
        }}

        /* Secondary active tab: pill with red left accent & bright text */
        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"][aria-selected="true"] {{
            background: rgba(220, 38, 38, 0.15) !important;
            border: 1px solid rgba(239, 68, 68, 0.4) !important;
            border-left: 3px solid #ef4444 !important;
            color: #ffffff !important;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"][aria-selected="true"] p,
        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"][aria-selected="true"]
            div[data-testid="stMarkdownContainer"] p {{
            color: #ffffff !important;
            font-weight: 600 !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"]:focus-visible {{
            outline: 2px solid #ef4444 !important;
            outline-offset: 1px !important;
        }}

        div[data-testid="stTabPanel"] div[data-testid="stTabs"]
            [role="tablist"] > div[data-testid="stTab"] .react-aria-SelectionIndicator {{
            display: none !important;
        }}

        /* Mobile / Narrow screen responsiveness */
        @media (max-width: 768px) {{
            div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
                [role="tablist"] {{
                flex-wrap: wrap !important;
                gap: 8px !important;
            }}
            div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
                [role="tablist"] > div[data-testid="stTab"] {{
                flex: 1 1 calc(50% - 10px) !important;
                min-width: 130px !important;
                height: 38px !important;
                font-size: 0.80rem !important;
            }}
            div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
                [role="tablist"] > div[data-testid="stTab"]:not(:last-child)::after {{
                display: none !important;
            }}
            div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
                [role="tablist"] > div[data-testid="stTab"] p,
            div[data-testid="stTabs"]:not([data-testid="stTabPanel"] div[data-testid="stTabs"])
                [role="tablist"] > div[data-testid="stTab"]
                div[data-testid="stMarkdownContainer"] p {{
                font-size: 0.80rem !important;
            }}
        }}

        /* Accessibility: prefers-reduced-motion fallback */
        @media (prefers-reduced-motion: reduce) {{
            div[data-testid="stTabs"] > div[role="tablist"] > div[data-testid="stTab"] {{
                transition: none !important;
            }}
        }}
        </style>
        <div>
            <div class="app-title-container">
                <h1 class="app-title-text">{title}</h1>
            </div>
            {subtitle_html}
        </div>
    """).strip()
    st.markdown(html_content, unsafe_allow_html=True)


def render_journey_hint(
    message: str = "Run the journey to inspect the end-to-end execution.",
) -> None:
    """Render a visually quiet, dark neutral helper hint below the run button."""
    html_content = (
        '<div style="display: flex; align-items: center; gap: 8px; padding: 8px 14px; '
        'background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); '
        'border-radius: 8px; color: rgba(255, 255, 255, 0.72); font-size: 0.88rem; '
        'line-height: 1.4; margin-top: 6px; margin-bottom: 8px;">'
        '<span style="font-size: 0.95rem; line-height: 1;">💡</span>'
        f'<span>{message}</span>'
        '</div>'
    )
    st.markdown(html_content, unsafe_allow_html=True)


def render_demo_context() -> None:
    """Render compact demo context caption if needed."""
    pass


# Backwards compatibility alias
render_header_sponsor_badges = render_header_logos

