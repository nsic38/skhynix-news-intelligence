from __future__ import annotations

import re

from bs4 import BeautifulSoup


SHELL_MARKERS = (
    "\uc5f0\uad00 \uae30\uc0ac",
    "Homepage",
    "INSTAGRAM",
    "YOUTUBE",
    "Heritage",
    "Media Library",
    "\ubaa9\ub85d \ubcf4\uae30",
    "\uba54\ub274 \ud1a0\uae00",
    "\ub9e8 \uc704\ub85c",
    "\ubb38\uc758\ud558\uae30",
    "\uac1c\uc778\uc815\ubcf4\ucc98\ub9ac\ubc29\uce68",
    "\ub274\uc2a4\ub8f8 \uc6b4\uc601\uc815\ucc45",
    "\ub274\uc2a4\ub8f8 \uc774\uc6a9\uc548\ub0b4",
    "\ub274\uc2a4\ub808\ud130 \uad6c\ub3c5\ud558\uae30",
)

VISUAL_NARRATION_MARKERS = (
    "the image shows",
    "the image depicts",
    "this image shows",
    "in the image",
    "the text on the",
    "the text reads",
    "the accompanying",
    "this translates to",
    "translates to",
    "appears to show",
    "exhibition booth",
)


def plain_text(value: str) -> str:

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


def sanitize_article_source(
    value: str,
    title: str = "",
) -> str:

    text = plain_text(
        value
    )

    if not text:
        return ""

    # If page chrome exists before the real heading,
    # start from the current article heading.
    if title:

        pos = text.find(
            title
        )

        if 0 <= pos <= 700:

            text = text[
                pos + len(title):
            ].strip(
                " -|:;"
            )

    # Never let related articles / footer / site chrome
    # enter the analyzer.
    positions = []

    for marker in SHELL_MARKERS:

        pos = text.find(
            marker
        )

        if pos >= 0:
            positions.append(
                pos
            )

    if positions:

        text = text[
            :min(positions)
        ]

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def source_is_safe(
    value: str,
    title: str = "",
    min_chars: int = 300,
) -> bool:

    text = sanitize_article_source(
        value,
        title,
    )

    if len(text) < min_chars:
        return False

    low = text.lower()

    if any(
        marker.lower() in low
        for marker in SHELL_MARKERS
    ):
        return False

    if any(
        marker in low
        for marker in VISUAL_NARRATION_MARKERS
    ):
        return False

    # Vision-model prose / markdown is not source evidence.
    if "**" in text:
        return False

    if re.search(
        r"(^|\s)>\s*[\"']?",
        text,
    ):
        return False

    return True
