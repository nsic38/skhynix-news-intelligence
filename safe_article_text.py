
from __future__ import annotations

import re
from bs4 import BeautifulSoup

BAD_MARKERS = (
    "?? ??",
    "Homepage",
    "Media Library",
    "INSTAGRAM",
    "YOUTUBE",
    "The image shows",
    "The image depicts",
    "The text on the",
    "The text reads",
    "This translates to",
    "translates to",
    "The accompanying",
    "Exhibition Context",
    "?? ?? ??",
    "? ????",
    "????",
    "??? ??",
    "??????",
    "????? ??",
    "forward-looking statements",
    "SEC filings",
    "Korea Exchange",
    "Disclaimer",
)


def clean_text(value: str) -> str:
    if not value:
        return ""

    text = BeautifulSoup(
        str(value),
        "html.parser",
    ).get_text(
        " ",
        strip=True,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def sanitize_html_source(
    value: str,
    title: str = "",
) -> str:

    text = clean_text(value)

    if not text:
        return ""

    if title:
        pos = text.find(title)

        if 0 <= pos <= 800:
            text = text[
                pos + len(title):
            ].strip()

    tail = (
        "?? ??",
        "Homepage",
        "INSTAGRAM",
        "YOUTUBE",
        "Heritage",
        "Media Library",
        "??? ????",
        "??? ????",
    )

    positions = [
        text.find(x)
        for x in tail
        if text.find(x) >= 0
    ]

    if positions:
        text = text[:min(positions)]

    return clean_text(text)


def contaminated(value) -> bool:

    if isinstance(value, list):
        text = " ".join(
            str(x)
            for x in value
        )
    else:
        text = str(value or "")

    low = text.lower()

    if any(
        marker.lower() in low
        for marker in BAD_MARKERS
    ):
        return True

    if "**" in text:
        return True

    return False
