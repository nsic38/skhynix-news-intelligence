from __future__ import annotations

import base64
import html
import json
import os
import re
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

VISION_MODEL = os.getenv(
    "OLLAMA_VISION_MODEL",
    "qwen3-vl:4b-instruct",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_ASSETS = 4


def clean_text(text: str) -> str:

    text = str(
        text or ""
    )

    text = text.replace(
        "\u200b",
        " ",
    )

    text = re.sub(
        r"```[a-zA-Z]*",
        "",
        text,
    )

    text = text.replace(
        "```",
        "",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def normalize_url(
    value: str,
    article_url: str,
) -> str:

    value = html.unescape(
        str(value or "")
    )

    value = value.replace(
        "\\/",
        "/",
    ).strip()

    if not value:
        return ""

    return urljoin(
        article_url,
        value,
    )


def is_direct_image_url(
    url: str,
) -> bool:

    path = (
        urlsplit(url)
        .path
        .lower()
    )

    return path.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        )
    )


def walk_content_urls(
    value,
    output: list[str],
):

    if isinstance(
        value,
        dict,
    ):

        for key, child in value.items():

            if (
                str(key).lower()
                == "contenturl"
                and isinstance(
                    child,
                    str,
                )
            ):
                output.append(
                    child
                )

            walk_content_urls(
                child,
                output,
            )

    elif isinstance(
        value,
        list,
    ):

        for child in value:

            walk_content_urls(
                child,
                output,
            )


def extract_content_urls(
    source: str,
    article_url: str,
) -> list[str]:

    soup = BeautifulSoup(
        source,
        "html.parser",
    )

    raw_urls = []

    for script in soup.find_all(
        "script",
        attrs={
            "type":
                "application/ld+json"
        },
    ):

        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        try:

            data = json.loads(
                raw
            )

        except Exception:

            continue

        walk_content_urls(
            data,
            raw_urls,
        )

    # Some pages expose contentUrl in serialized data.
    for match in re.findall(
        r'"contentUrl"\s*:\s*"([^"]+)"',
        source,
        flags=re.IGNORECASE,
    ):

        raw_urls.append(
            match
        )

    result = []

    for raw_url in raw_urls:

        url = normalize_url(
            raw_url,
            article_url,
        )

        if not url:
            continue

        if not is_direct_image_url(
            url
        ):
            continue

        low = url.lower()

        if (
            "/wp-content/uploads/"
            not in low
            and "skhynix-prd-data"
            not in low
        ):
            continue

        if url not in result:
            result.append(
                url
            )

    return result[
        :MAX_ASSETS
    ]


def extract_current_download(
    source: str,
    article_url: str,
) -> str:

    soup = BeautifulSoup(
        source,
        "html.parser",
    )

    for node in soup.find_all(
        "a",
        href=True,
    ):

        text = node.get_text(
            " ",
            strip=True,
        )

        href = node.get(
            "href",
            "",
        )

        if (
            "\ub2e4\uc6b4\ub85c\ub4dc"
            in text
            or "download.php"
            in href
        ):

            return normalize_url(
                href,
                article_url,
            )

    return ""


def render_html_with_edge(
    article_url: str,
) -> str:

    try:

        from playwright.sync_api import (
            sync_playwright,
        )

    except Exception:

        return ""

    try:

        with sync_playwright() as p:

            browser = (
                p.chromium.launch(
                    channel="msedge",
                    headless=True,
                )
            )

            page = browser.new_page()

            try:

                page.goto(
                    article_url,
                    wait_until=(
                        "domcontentloaded"
                    ),
                    timeout=30000,
                )

                page.wait_for_timeout(
                    3000
                )

                return page.content()

            finally:

                page.close()
                browser.close()

    except Exception:

        return ""


def find_article_image_urls(
    article_url: str,
) -> list[str]:

    source = ""

    try:

        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        source = response.text

    except Exception:

        source = ""

    # IMPORTANT:
    # Use only contentUrl belonging to the current page.
    # Never scan arbitrary <img> tags because those include
    # related-article thumbnails and site assets.
    urls = extract_content_urls(
        source,
        article_url,
    )

    if urls:

        return urls

    # If no contentUrl exists, the page's own Download
    # button is the only accepted fallback.
    download_url = (
        extract_current_download(
            source,
            article_url,
        )
    )

    if download_url:

        return [
            download_url
        ]

    # Rendered DOM is only a final same-page fallback.
    rendered = render_html_with_edge(
        article_url
    )

    if rendered:

        urls = extract_content_urls(
            rendered,
            article_url,
        )

        if urls:
            return urls

        download_url = (
            extract_current_download(
                rendered,
                article_url,
            )
        )

        if download_url:
            return [
                download_url
            ]

    return []


def download_image(
    image_url: str,
    article_url: str,
) -> bytes | None:

    response = requests.get(
        image_url,
        headers={
            **HEADERS,
            "Referer":
                article_url,
        },
        allow_redirects=True,
        timeout=60,
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get(
            "Content-Type",
            "",
        )
        .lower()
    )

    if not content_type.startswith(
        "image/"
    ):

        return None

    data = response.content

    if not data:
        return None

    if len(data) > MAX_IMAGE_BYTES:
        return None

    return data


def make_image_tiles(
    image_bytes: bytes,
) -> list[bytes]:

    Image.MAX_IMAGE_PIXELS = None

    image = Image.open(
        BytesIO(
            image_bytes
        )
    )

    image.load()

    image = image.convert(
        "RGB"
    )

    original_width, original_height = (
        image.size
    )

    print(
        "     image size: "
        f"{original_width}x"
        f"{original_height}"
    )

    target_width = 1600

    if original_width < target_width:

        scale = min(
            target_width
            / original_width,
            2.0,
        )

        try:

            resample = (
                Image.Resampling.LANCZOS
            )

        except AttributeError:

            resample = (
                Image.LANCZOS
            )

        image = image.resize(
            (
                int(
                    original_width
                    * scale
                ),
                int(
                    original_height
                    * scale
                ),
            ),
            resample,
        )

    width, height = image.size

    tile_height = 1600
    overlap = 120
    max_tiles = 18

    if (
        height
        > max_tiles
        * (
            tile_height
            - overlap
        )
    ):

        tile_height = (
            (
                height
                + max_tiles
                - 1
            )
            // max_tiles
        ) + overlap

    ranges = []
    y = 0

    while y < height:

        y2 = min(
            y + tile_height,
            height,
        )

        if (
            ranges
            and y2 - y < 350
        ):

            old_start, _ = (
                ranges[-1]
            )

            ranges[-1] = (
                old_start,
                height,
            )

            break

        ranges.append(
            (
                y,
                y2,
            )
        )

        if y2 >= height:
            break

        y = (
            y2
            - overlap
        )

    print(
        "     tiles: "
        f"{len(ranges)}"
    )

    output = []

    for y1, y2 in ranges:

        crop = image.crop(
            (
                0,
                y1,
                width,
                y2,
            )
        )

        buffer = BytesIO()

        crop.save(
            buffer,
            format="PNG",
            optimize=True,
        )

        output.append(
            buffer.getvalue()
        )

    return output


def validate_transcription(
    value: str,
) -> str:

    text = clean_text(
        value
    )

    if not text:
        return ""

    if (
        text.strip()
        == "NO_ARTICLE_TEXT"
    ):
        return ""

    low = text.lower()

    forbidden = (
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

    if any(
        item in low
        for item in forbidden
    ):
        return ""

    if "**" in text:
        return ""

    if re.search(
        r"(^|\n)\s*>",
        text,
    ):
        return ""

    # The Korean newsroom source must contain
    # a meaningful amount of visible Korean text.
    hangul = len(
        re.findall(
            r"[\uac00-\ud7a3]",
            text,
        )
    )

    latin = len(
        re.findall(
            r"[A-Za-z]",
            text,
        )
    )

    if hangul < 30:
        return ""

    if (
        hangul < 80
        and latin
        > hangul * 3
    ):
        return ""

    if len(text) < 80:
        return ""

    return text


def read_image_with_ollama(
    image_bytes: bytes,
    title: str,
    index: int,
    total: int,
) -> str:

    image_b64 = (
        base64.b64encode(
            image_bytes
        )
        .decode(
            "ascii"
        )
    )

    # ASCII-only prompt intentionally used here.
    # This prevents Windows terminal/source encoding
    # from corrupting the instruction text.
    prompt = f"""
You are transcribing visible text from one image that
belongs to the current SK hynix Newsroom article.

Article title:
{title}

Image tile:
{index}/{total}

STRICT RULES:
1. Transcribe ONLY text that is visibly written in this image.
2. Do NOT describe the scene, people, objects, booth, background, or layout.
3. Do NOT summarize.
4. Do NOT translate Korean into English.
5. Do NOT add facts from the article title or from outside knowledge.
6. Preserve Korean wording, numbers, units, product names,
   technical terms, and acronyms as visibly written.
7. Do NOT write phrases such as "the image shows",
   "the text reads", "this translates to", or similar commentary.
8. Do NOT use Markdown, bullets created by you, blockquotes,
   bold markers, explanations, or headings that are not visible.
9. If the image is mainly a photograph or decorative graphic
   and does not contain enough substantive article text,
   output exactly:
NO_ARTICLE_TEXT

Return only the visible source text.
""".strip()

    response = requests.post(
        OLLAMA_URL,
        json={
            "model":
                VISION_MODEL,
            "stream":
                False,
            "think":
                False,
            "messages": [
                {
                    "role":
                        "user",
                    "content":
                        prompt,
                    "images": [
                        image_b64
                    ],
                }
            ],
            "options": {
                "temperature":
                    0.0,
                "num_ctx":
                    8192,
                "num_predict":
                    2400,
            },
        },
        timeout=300,
    )

    response.raise_for_status()

    result = response.json()

    text = (
        result
        .get(
            "message",
            {},
        )
        .get(
            "content",
            "",
        )
    )

    return validate_transcription(
        text
    )


def extract_article_image_text(
    article_url: str,
    title: str,
) -> dict | None:

    urls = find_article_image_urls(
        article_url
    )

    if not urls:

        print(
            "  -> no current-page "
            "image source"
        )

        return None

    print(
        "  -> current-page assets: "
        f"{len(urls)}"
    )

    extracted_parts = []
    used_urls = []

    for image_index, image_url in enumerate(
        urls,
        1,
    ):

        print(
            "  -> image asset "
            f"{image_index}/"
            f"{len(urls)}"
        )

        try:

            image_bytes = (
                download_image(
                    image_url,
                    article_url,
                )
            )

            if not image_bytes:

                print(
                    "     not an image; "
                    "rejected"
                )

                continue

            tiles = make_image_tiles(
                image_bytes
            )

        except Exception as exc:

            print(
                "     image load failed: "
                f"{exc}"
            )

            continue

        image_parts = []

        for tile_index, tile in enumerate(
            tiles,
            1,
        ):

            print(
                "     transcribing tile "
                f"{tile_index}/"
                f"{len(tiles)}"
            )

            try:

                text = (
                    read_image_with_ollama(
                        tile,
                        title,
                        tile_index,
                        len(tiles),
                    )
                )

            except Exception as exc:

                print(
                    "       vision failed: "
                    f"{exc}"
                )

                continue

            print(
                "       accepted chars: "
                f"{len(text):,}"
            )

            if not text:
                continue

            if text in image_parts:
                continue

            image_parts.append(
                text
            )

        if not image_parts:
            continue

        extracted_parts.append(
            "\n\n".join(
                image_parts
            )
        )

        used_urls.append(
            image_url
        )

    if not extracted_parts:
        return None

    combined = "\n\n".join(
        extracted_parts
    ).strip()

    if len(combined) < 300:
        return None

    return {
        "text":
            combined,
        "image_urls":
            used_urls,
        "model":
            VISION_MODEL,
    }


# === SAFE IMAGE PIPELINE V2 ===

def _safe_current_assets(
    article_url: str,
) -> list[str]:

    try:

        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

    except Exception:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # ?? ??? ?? ?? ???? ???? ??.
    # ???? img ??? ???? ???.
    for node in soup.find_all(
        "a",
        href=True,
    ):

        href = node.get(
            "href",
            "",
        )

        text = node.get_text(
            " ",
            strip=True,
        )

        if (
            "????" in text
            or "download.php"
            in href
        ):

            return [
                urljoin(
                    article_url,
                    href,
                )
            ]

    # ????? ?? ????
    # ?? NewsArticle JSON-LD image/contentUrl ??
    result = []

    def walk(value):

        if isinstance(value, dict):

            value_type = value.get(
                "@type",
                "",
            )

            if isinstance(
                value_type,
                list,
            ):
                types = [
                    str(x).lower()
                    for x in value_type
                ]
            else:
                types = [
                    str(
                        value_type
                    ).lower()
                ]

            if any(
                t in (
                    "newsarticle",
                    "article",
                    "blogposting",
                )
                for t in types
            ):

                image_value = value.get(
                    "image"
                )

                def collect_image(v):

                    if isinstance(v, str):
                        result.append(v)

                    elif isinstance(v, dict):

                        for key in (
                            "contentUrl",
                            "url",
                        ):
                            if isinstance(
                                v.get(key),
                                str,
                            ):
                                result.append(
                                    v[key]
                                )

                    elif isinstance(v, list):

                        for x in v:
                            collect_image(x)

                collect_image(
                    image_value
                )

            for child in value.values():
                walk(child)

        elif isinstance(value, list):

            for child in value:
                walk(child)

    for script in soup.find_all(
        "script",
        attrs={
            "type":
                "application/ld+json"
        },
    ):

        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        walk(data)

    final = []

    for value in result:

        url = normalize_image_url(
            value,
            article_url,
        )

        low = url.lower()

        if not (
            "/wp-content/uploads/"
            in low
            or "skhynix-prd-data"
            in low
        ):
            continue

        if url not in final:
            final.append(url)

    return final[:3]


def find_article_image_urls(
    article_url: str,
) -> list[str]:

    return _safe_current_assets(
        article_url
    )


def download_image(
    image_url: str,
    article_url: str,
) -> bytes | None:

    response = requests.get(
        image_url,
        headers={
            **HEADERS,
            "Referer":
                article_url,
        },
        allow_redirects=True,
        timeout=60,
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get(
            "Content-Type",
            "",
        )
        .lower()
    )

    if not content_type.startswith(
        "image/"
    ):
        return None

    data = response.content

    if (
        not data
        or len(data)
        > MAX_IMAGE_BYTES
    ):
        return None

    return data


def make_image_tiles(
    image_bytes: bytes,
) -> list[bytes]:

    Image.MAX_IMAGE_PIXELS = None

    image = Image.open(
        BytesIO(image_bytes)
    )

    image.load()

    image = image.convert(
        "RGB"
    )

    width, height = image.size

    print(
        "     image size: "
        f"{width}x{height}"
    )

    tile_w = min(
        900,
        width,
    )

    tile_h = min(
        900,
        height,
    )

    overlap = 120

    def positions(
        total,
        size,
    ):

        if total <= size:
            return [0]

        values = []
        pos = 0

        while True:

            if pos + size >= total:

                last = max(
                    0,
                    total - size,
                )

                if last not in values:
                    values.append(last)

                break

            values.append(pos)

            pos += (
                size
                - overlap
            )

        return values

    xs = positions(
        width,
        tile_w,
    )

    ys = positions(
        height,
        tile_h,
    )

    tiles = []

    for y in ys:

        for x in xs:

            crop = image.crop(
                (
                    x,
                    y,
                    min(
                        x + tile_w,
                        width,
                    ),
                    min(
                        y + tile_h,
                        height,
                    ),
                )
            )

            cw, ch = crop.size

            if cw < 1400:

                scale = min(
                    1600 / cw,
                    2.2,
                )

                try:
                    resample = (
                        Image.Resampling.LANCZOS
                    )
                except AttributeError:
                    resample = (
                        Image.LANCZOS
                    )

                crop = crop.resize(
                    (
                        int(
                            cw * scale
                        ),
                        int(
                            ch * scale
                        ),
                    ),
                    resample,
                )

            buffer = BytesIO()

            crop.save(
                buffer,
                format="PNG",
            )

            tiles.append(
                buffer.getvalue()
            )

    print(
        "     tiles: "
        f"{len(tiles)}"
    )

    return tiles[:12]


def _safe_vision_output(
    value: str,
) -> str:

    value = str(
        value or ""
    )

    if (
        not value
        or value.strip()
        == "NO_ARTICLE_TEXT"
    ):
        return ""

    banned = (
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

    output = []

    for raw in value.splitlines():

        line = raw.strip()

        line = re.sub(
            r"^[#>*\-]+\s*",
            "",
            line,
        )

        line = (
            line
            .replace(
                "**",
                "",
            )
            .replace(
                "__",
                "",
            )
            .strip()
        )

        if not line:
            continue

        low = line.lower()

        if any(
            item in low
            for item in banned
        ):
            continue

        hangul = len(
            re.findall(
                r"[?-?]",
                line,
            )
        )

        latin = len(
            re.findall(
                r"[A-Za-z]",
                line,
            )
        )

        if (
            hangul == 0
            and latin >= 35
        ):
            continue

        output.append(
            line
        )

    return "\n".join(
        output
    ).strip()


def read_image_with_ollama(
    image_bytes: bytes,
    title: str,
    index: int,
    total: int,
) -> str:

    image_b64 = base64.b64encode(
        image_bytes
    ).decode(
        "ascii"
    )

    prompt = f"""
Act only as an OCR transcription engine.

Article title:
{title}

Image tile:
{index}/{total}

STRICT RULES:
- Copy only text visibly written in the image.
- Do not summarize.
- Do not explain the image.
- Do not describe diagrams, people, objects, photos or layouts.
- Do not infer meaning.
- Do not translate Korean into English.
- Do not add information from the article title.
- Do not add outside knowledge.
- Do not generate Markdown.
- Preserve visible Korean wording, numbers, units,
  product names, technical terms and acronyms.
- Ignore generic presentation disclaimers.
- Never write phrases such as "the image shows",
  "the text reads", "this translates to", or "in conclusion".
- If substantive article text is not visibly present,
  output exactly NO_ARTICLE_TEXT.

Return only verbatim visible text.
""".strip()

    response = requests.post(
        OLLAMA_URL,
        json={
            "model":
                VISION_MODEL,
            "stream":
                False,
            "think":
                False,
            "messages": [
                {
                    "role":
                        "user",
                    "content":
                        prompt,
                    "images": [
                        image_b64
                    ],
                }
            ],
            "options": {
                "temperature":
                    0.0,
                "num_ctx":
                    8192,
                "num_predict":
                    2200,
            },
        },
        timeout=300,
    )

    response.raise_for_status()

    result = response.json()

    raw = (
        result
        .get(
            "message",
            {},
        )
        .get(
            "content",
            "",
        )
    )

    return _safe_vision_output(
        raw
    )
