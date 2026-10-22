
from __future__ import annotations

import re
from difflib import SequenceMatcher


class ImageEvidenceError(RuntimeError):
    pass


BANNED = (
    "the image shows",
    "the image depicts",
    "the text on the",
    "the text reads",
    "translates to",
    "the accompanying",
    "exhibition context",
    "forward-looking statements",
    "sec filings",
    "korea exchange",
    "disclaimer",
    "? ????",
    "????",
    "?? ?? ??",
    "??? ??",
    "??????",
    "????? ??",
)


def clean(value: str) -> str:

    value = str(value or "")

    value = value.replace(
        "**",
        "",
    ).replace(
        "__",
        "",
    )

    value = re.sub(
        r"^[#>*\-]+\s*",
        "",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def norm(value: str) -> str:

    return re.sub(
        r"[^0-9A-Za-z?-?]+",
        "",
        value.lower(),
    )


def similar(a: str, b: str) -> float:

    return SequenceMatcher(
        None,
        norm(a),
        norm(b),
    ).ratio()


def units_from_source(source: str) -> list[str]:

    source = source.replace(
        "---",
        "\n",
    )

    raw = re.split(
        r"\n+|(?<=[.!?])\s+",
        source,
    )

    output = []

    for item in raw:

        item = clean(item)

        if len(item) < 15:
            continue

        low = item.lower()

        if any(
            x in low
            for x in BANNED
        ):
            continue

        if re.fullmatch(
            r"(?:??\s*)?(?:??\s*)?"
            r"(?:??\s*)?[:?]?\s*\d+[.)]?",
            item,
        ):
            continue

        # ? ?? ???? OCR ??? ???
        # ?? ??? ???? ?? ??
        hangul = len(
            re.findall(
                r"[?-?]",
                item,
            )
        )

        latin = len(
            re.findall(
                r"[A-Za-z]",
                item,
            )
        )

        if (
            hangul == 0
            and latin >= 35
        ):
            continue

        if any(
            similar(
                item,
                old,
            ) >= 0.86
            for old in output
        ):
            continue

        output.append(item)

    return output


def score(text: str, title: str) -> float:

    low = text.lower()

    result = 0.0

    if re.search(r"\d", text):
        result += 3.0

    for word in (
        "ai",
        "???",
        "hbm",
        "nand",
        "fenand",
        "???",
        "??",
        "??",
        "??",
        "??",
        "??",
        "???",
        "??",
        "??",
        "??",
        "??",
        "??",
    ):
        if word in low:
            result += 1.5

    title_words = set(
        re.findall(
            r"[0-9A-Za-z?-?]{3,}",
            title.lower(),
        )
    )

    words = set(
        re.findall(
            r"[0-9A-Za-z?-?]{3,}",
            low,
        )
    )

    result += (
        len(title_words & words)
        * 1.8
    )

    if 25 <= len(text) <= 180:
        result += 2.0

    return result


def analyze_image_evidence(
    title: str,
    source: str,
    tags=None,
):

    units = units_from_source(
        source
    )

    if len(units) < 3:
        raise ImageEvidenceError(
            "????? ?? ??? ??? 3? ??"
        )

    ranked = sorted(
        units,
        key=lambda x: score(
            x,
            title,
        ),
        reverse=True,
    )

    selected = []

    for text in ranked:

        if any(
            similar(
                text,
                old,
            ) >= 0.62
            for old in selected
        ):
            continue

        selected.append(text)

        if len(selected) == 5:
            break

    if len(selected) < 3:
        raise ImageEvidenceError(
            "?? ?? ??? ??? 3? ??"
        )

    return {
        "main_point":
            " ".join(
                selected[:2]
            ),

        "one_liner":
            " ".join(
                selected[:2]
            ),

        "key_points":
            selected,

        "why_it_matters":
            " ".join(
                selected[-2:]
            ),

        "category":
            "??",

        "_evidence": [
            {
                "id": f"IMG{i + 1}",
                "text": text,
            }
            for i, text
            in enumerate(selected)
        ],
    }
