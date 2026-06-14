"""Generates a realistic A4 NEET exam paper page as a numpy uint8 grayscale array.

Pure computation — no I/O, no HTTP, no database access.
Content stays within the safe zone (x=200–2280, y=200–3300) so watermark
corner grids placed by encoder.embed_markers() are never overwritten.
"""

from typing import Final

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_PAGE_W: Final[int] = 2480
_PAGE_H: Final[int] = 3508
_SAFE_X0: Final[int] = 200
_SAFE_X1: Final[int] = 2280
_SAFE_Y0: Final[int] = 200
_SAFE_Y1: Final[int] = 3300
_SUBTLE_GRAY: Final[int] = 180

_PHYSICS: Final[list[tuple[str, str]]] = [
    ("A particle moves with velocity v = 3t² - 2t + 1 m/s. The acceleration at t = 2s is:",
     "(A) 10 m/s²    (B) 12 m/s²    (C) 8 m/s²    (D) 14 m/s²"),
    ("The work done by a force F = 2î + 3ĵ N over displacement d = 4î + ĵ m is:",
     "(A) 11 J    (B) 13 J    (C) 9 J    (D) 15 J"),
    ("A block of mass 2 kg slides down a frictionless incline of 30°. Its acceleration is:",
     "(A) 4.9 m/s²    (B) 9.8 m/s²    (C) 2.5 m/s²    (D) 6.2 m/s²"),
    ("The escape velocity from Earth's surface is approximately:",
     "(A) 7.9 km/s    (B) 11.2 km/s    (C) 3.1 km/s    (D) 15.4 km/s"),
    ("In a photoelectric experiment, increasing the intensity of light increases:",
     "(A) stopping potential    (B) photoelectron count    (C) work function    (D) threshold frequency"),
]

_CHEMISTRY: Final[list[tuple[str, str]]] = [
    ("The IUPAC name of CH₃CH₂CHO is:",
     "(A) Propanal    (B) Propanone    (C) Propanoic acid    (D) Propanol"),
    ("Which has the highest boiling point?",
     "(A) CH₄    (B) C₂H₆    (C) C₃H₈    (D) C₄H₁₀"),
    ("The hybridization of carbon in CO₂ is:",
     "(A) sp    (B) sp²    (C) sp³    (D) sp³d"),
    ("0.1 M NaOH solution has pH equal to:",
     "(A) 1    (B) 7    (C) 13    (D) 9"),
    ("Which is a strong electrolyte in aqueous solution?",
     "(A) CH₃COOH    (B) NH₄OH    (C) NaCl    (D) C₆H₁₂O₆"),
]

_BIOLOGY: Final[list[tuple[str, str]]] = [
    ("The powerhouse of the cell is:",
     "(A) Nucleus    (B) Mitochondria    (C) Ribosome    (D) Golgi body"),
    ("DNA replication occurs during which phase of the cell cycle?",
     "(A) G₁    (B) S    (C) G₂    (D) M"),
    ("Which enzyme fixes atmospheric nitrogen in leguminous plants?",
     "(A) Nitrogenase    (B) RuBisCO    (C) Amylase    (D) Ligase"),
    ("The functional unit of the kidney is:",
     "(A) Neuron    (B) Nephron    (C) Alveolus    (D) Villus"),
    ("Mendel's law of independent assortment applies to genes on:",
     "(A) Same chromosome    (B) Homologous pairs    (C) Different chromosomes    (D) Sex chromosomes only"),
]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size,
            )
        except OSError:
            return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_header(
    draw: ImageDraw.ImageDraw,
    center_code: str,
    page_num: int,
) -> None:
    title_font = _get_font(36)
    body_font = _get_font(24)
    subtle_font = _get_font(18)
    y = _SAFE_Y0
    draw.text((_SAFE_X0, y), "NEET-UG 2026", fill=0, font=title_font)
    conf = "CONFIDENTIAL"
    draw.text((_SAFE_X1 - _text_width(draw, conf, title_font), y), conf, fill=0, font=title_font)
    y += 50
    draw.text((_SAFE_X0, y), "Physics, Chemistry, Biology", fill=0, font=body_font)
    y += 40
    draw.text((_SAFE_X0, y), "Time: 3 Hours", fill=0, font=body_font)
    marks = "Max Marks: 720"
    draw.text((_SAFE_X1 - _text_width(draw, marks, body_font), y), marks, fill=0, font=body_font)
    center_line = f"Center: {center_code}    Page {page_num}"
    draw.text(
        (_SAFE_X1 - _text_width(draw, center_line, subtle_font), y + 35),
        center_line, fill=_SUBTLE_GRAY, font=subtle_font,
    )


def _draw_section(
    draw: ImageDraw.ImageDraw,
    y: int,
    title: str,
    questions: list[tuple[str, str]],
    section_font: ImageFont.ImageFont,
    q_font: ImageFont.ImageFont,
) -> int:
    draw.text((_SAFE_X0, y), title, fill=0, font=section_font)
    y += 45
    for idx, (stem, options) in enumerate(questions, start=1):
        draw.text((_SAFE_X0, y), f"Q{idx}. {stem}", fill=0, font=q_font)
        y += 32
        draw.text((_SAFE_X0 + 20, y), options, fill=0, font=q_font)
        y += 48
    return y


def _draw_questions(draw: ImageDraw.ImageDraw) -> None:
    section_font = _get_font(26)
    q_font = _get_font(20)
    y = 420
    y = _draw_section(draw, y, "Section A — Physics (Q1–15)", _PHYSICS, section_font, q_font)
    y += 10
    y = _draw_section(draw, y, "Section B — Chemistry (Q16–30)", _CHEMISTRY, section_font, q_font)
    y += 10
    _draw_section(draw, y, "Section C — Biology (Q31–45)", _BIOLOGY, section_font, q_font)


def _draw_footer(draw: ImageDraw.ImageDraw, page_num: int) -> None:
    footer_font = _get_font(18)
    y = _SAFE_Y1 - 60
    line1 = "NEET-UG 2026 | Strictly Confidential | Do not photograph or distribute"
    draw.text((_SAFE_X0, y), line1, fill=0, font=footer_font)
    page_line = f"Page {page_num}"
    draw.text(
        (_SAFE_X1 - _text_width(draw, page_line, footer_font), y + 30),
        page_line, fill=0, font=footer_font,
    )


def generate_page() -> np.ndarray:
    """Return a realistic NEET-UG A4 grayscale page (3508 × 2480, uint8)."""
    page_num = 1
    center_code = "—"
    image = Image.new("L", (_PAGE_W, _PAGE_H), 255)
    draw = ImageDraw.Draw(image)
    _draw_header(draw, center_code, page_num)
    _draw_questions(draw)
    _draw_footer(draw, page_num)
    return np.array(image, dtype=np.uint8)
