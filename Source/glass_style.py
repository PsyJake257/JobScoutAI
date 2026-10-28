"""Lightweight frosted-glass material: static edge lighting, no live blur."""
from functools import lru_cache

from PIL import Image, ImageDraw

BACKGROUND = ("#E9EFF8", "#0C1424")
SIDEBAR = ("#F3F7FD", "#18273D")
SURFACE = ("#F9FBFF", "#21324A")
SURFACE_SECONDARY = ("#EEF4FC", "#19293F")
BORDER = ("#BDCCE0", "#4A607D")
SECONDARY_TEXT = ("#475B74", "#BCCCE0")
PRIMARY = ("#1769AA", "#91CCFF")
PRIMARY_HOVER = ("#12558C", "#B7DEFF")
SURFACE_COLORS = frozenset((*SIDEBAR, *SURFACE, *SURFACE_SECONDARY))


def blend(color, light, fraction):
    rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    target = tuple(int(light[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(round(a + (b - a) * fraction) for a, b in zip(rgb, target))


@lru_cache(maxsize=48)
def glass_edge(width, height, radius, color, top=True):
    """Only a thin edge bitmap is allocated, independent of card content height."""
    band = min(20, height // 2)
    image = Image.new("RGBA", (width, band))
    mask = Image.new("L", (width, band))
    draw, clip = ImageDraw.Draw(image), ImageDraw.Draw(mask)
    # Clip using the full panel's rounded outline; the bitmap stays <=20 pixels tall.
    offset = 0 if top else height - band
    clip.rounded_rectangle((2, 2 - offset, width - 3, height - 3 - offset),
                           radius=max(0, radius - 2), fill=255)
    dark = sum(int(color[i:i + 2], 16) for i in (1, 3, 5)) < 384
    for y in range(band):
        distance = y if top else band - y - 1
        amount = max(0, 1 - distance / max(1, band - 1)) ** 2
        target = "#B9DDFF" if top else "#020813"
        strength = (0.26 if dark else 0.55) if top else (0.18 if dark else 0.06)
        draw.line((0, y, width, y), fill=blend(color, target, amount * strength) + (255,))
    image.putalpha(mask)
    return image


def apply_theme(theme):
    """Update the existing theme; semantic status colors remain owned by the app."""
    theme["CTk"]["fg_color"] = BACKGROUND
    theme["CTkToplevel"]["fg_color"] = BACKGROUND
    theme["CTkFrame"].update(fg_color=SURFACE, top_fg_color=SURFACE_SECONDARY,
                             border_color=BORDER, corner_radius=16)
    theme["CTkLabel"]["text_color"] = ("#17283E", "#F2F7FF")
    theme["CTkButton"].update(corner_radius=11, border_width=1, border_color=("#3D7FAF", "#B5DCFF"),
                              fg_color=PRIMARY, hover_color=PRIMARY_HOVER)
    for name in ("CTkEntry", "CTkComboBox", "CTkTextbox"):
        theme[name].update(fg_color=("#FFFFFF", "#14243A"), border_color=BORDER,
                           border_width=1, corner_radius=10, text_color=("#17283E", "#F2F7FF"))
    theme["CTkEntry"]["placeholder_text_color"] = SECONDARY_TEXT
    theme["CTkComboBox"].update(button_color=("#DCE7F5", "#344C69"),
                                button_hover_color=("#CBDDF1", "#48688D"))
    theme["CTkSegmentedButton"].update(corner_radius=10, border_width=3,
        fg_color=SURFACE_SECONDARY, unselected_color=SURFACE_SECONDARY,
        unselected_hover_color=("#DAE8F8", "#344C69"), selected_color=("#D2E8FF", "#9CCFFF"),
        selected_hover_color=("#BBDDFC", "#B7DEFF"), text_color=("#17283E", "#F2F7FF"))
    theme["CTkProgressBar"].update(fg_color=("#CDDBED", "#344B67"), progress_color=PRIMARY)
    theme["CTkCheckBox"].update(fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
                                border_color=BORDER, checkmark_color=("#FFFFFF", "#0C2036"), border_width=2)
    theme["CTkScrollbar"].update(button_color=("#9AAEC9", "#577393"),
                                button_hover_color=("#6F8DAE", "#91B8DF"))
    theme["DropdownMenu"].update(fg_color=SURFACE_SECONDARY, hover_color=("#D2E8FF", "#344C69"),
                                text_color=("#17283E", "#F2F7FF"))
