from __future__ import annotations

import base64
import html
import json
import os
import re
from io import BytesIO
from typing import Any
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

MAX_IMAGES = 20
MAX_IMAGE_BYTES = 30 * 1024 * 1024


def clean_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("\u200b", " ")
    text = re.sub(r"```[a-zA-Z]*", "", text)
    text = text.replace("```", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_image_url(url: str) -> bool:

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


def normalize_image_url(
    url: str,
    article_url: str,
) -> str:

    url = html.unescape(
        str(url or "")
    )

    url = (
        url
        .replace("\\/", "/")
        .strip()
    )

    if not url:
        return ""

    return urljoin(
        article_url,
        url,
    )


def walk_content_urls(
    value: Any,
    output: list[str],
) -> None:

    if isinstance(value, dict):

        for key, child in value.items():

            key_low = str(
                key
            ).lower()

            if (
                isinstance(child, str)
                and key_low
                in (
                    "contenturl",
                    "url",
                    "image",
                    "thumbnailurl",
                )
            ):
                output.append(child)

            walk_content_urls(
                child,
                output,
            )

    elif isinstance(value, list):

        for child in value:

            walk_content_urls(
                child,
                output,
            )


def extract_urls_from_html(
    source: str,
    article_url: str,
) -> list[str]:

    soup = BeautifulSoup(
        source,
        "html.parser",
    )

    raw_urls: list[str] = []

    # --------------------------------------------------
    # 1. JSON-LD
    # --------------------------------------------------
    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
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

        walk_content_urls(
            data,
            raw_urls,
        )

    # --------------------------------------------------
    # 2. 실제 img 태그
    # --------------------------------------------------
    for img in soup.find_all("img"):

        for attr in (
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
        ):

            value = img.get(attr)

            if value:
                raw_urls.append(value)

        for attr in (
            "srcset",
            "data-srcset",
        ):

            value = img.get(attr)

            if not value:
                continue

            for item in str(value).split(","):

                candidate = (
                    item
                    .strip()
                    .split(" ")[0]
                )

                if candidate:
                    raw_urls.append(
                        candidate
                    )

    # --------------------------------------------------
    # 3. source 태그 / picture
    # --------------------------------------------------
    for node in soup.find_all("source"):

        value = (
            node.get("srcset")
            or node.get("src")
        )

        if not value:
            continue

        for item in str(value).split(","):

            candidate = (
                item
                .strip()
                .split(" ")[0]
            )

            if candidate:
                raw_urls.append(
                    candidate
                )

    # --------------------------------------------------
    # 4. HTML 안에 직접 들어있는 uploads 이미지
    # --------------------------------------------------
    for match in re.findall(
        r'https?:\\?/\\?/[^"\'<>\s]+?'
        r'\.(?:jpg|jpeg|png|webp)'
        r'(?:\?[^"\'<>\s]*)?',
        source,
        flags=re.IGNORECASE,
    ):

        raw_urls.append(
            match.replace("\\/", "/")
        )

    # --------------------------------------------------
    # 정리
    # --------------------------------------------------
    result: list[str] = []

    blocked_words = (
        "logo",
        "icon",
        "favicon",
        "sns",
        "facebook",
        "youtube",
        "instagram",
        "kakao",
        "profile",
        "avatar",
        "banner",
        "footer",
        "header",
    )

    for raw_url in raw_urls:

        url = normalize_image_url(
            raw_url,
            article_url,
        )

        if not is_image_url(url):
            continue

        low = url.lower()

        if any(
            word in low
            for word in blocked_words
        ):
            continue

        # 뉴스룸 실제 업로드 자료 우선
        if (
            "/wp-content/uploads/"
            not in low
            and "skhynix-prd-data"
            not in low
        ):
            continue

        # 워드프레스 자동 생성 thumbnail 제외
        if re.search(
            r"-\d{2,4}x\d{2,4}\.(jpg|jpeg|png|webp)",
            low,
        ):
            continue

        if url not in result:
            result.append(url)

    return result


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

            browser = p.chromium.launch(
                channel="msedge",
                headless=True,
            )

            page = browser.new_page(
                viewport={
                    "width": 1600,
                    "height": 1200,
                }
            )

            try:

                page.goto(
                    article_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                page.wait_for_timeout(
                    5000
                )

                # lazy-load 이미지까지 로딩
                page.evaluate("""
                async () => {
                    for (
                        let y = 0;
                        y < document.body.scrollHeight;
                        y += 1000
                    ) {
                        window.scrollTo(0, y);
                        await new Promise(
                            r => setTimeout(r, 150)
                        );
                    }
                    window.scrollTo(0, 0);
                }
                """)

                page.wait_for_timeout(
                    2000
                )

                return page.content()

            finally:

                page.close()
                browser.close()

    except Exception as exc:

        print(
            "  -> Edge 이미지 탐색 실패: "
            f"{exc}"
        )

        return ""


def image_exists(
    url: str,
    article_url: str,
) -> bool:

    try:

        response = requests.head(
            url,
            headers={
                **HEADERS,
                "Referer": article_url,
            },
            allow_redirects=True,
            timeout=15,
        )

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        if (
            response.status_code == 200
            and (
                content_type.startswith("image/")
                or is_image_url(url)
            )
        ):
            return True

    except Exception:
        pass

    return False


def expand_numbered_article_images(
    seed_url: str,
    article_url: str,
) -> list[str]:

    # ?:
    # ..._05_???_2026.jpg
    # ..._2026_06.jpg
    #
    # URL?? "_?????_" ??
    # "_?????.???" ??? ??
    # 01~12?? ?? ???? ???? ????.

    path = urlsplit(seed_url).path

    matches = list(
        re.finditer(
            r"_(\d{2})(?=_|(?:\.(?:jpg|jpeg|png|webp))$)",
            path,
            flags=re.IGNORECASE,
        )
    )

    if not matches:
        return [seed_url]

    # ??? ??? ??? ??? ???? ??
    match = matches[-1]

    number_start = match.start(1)
    number_end = match.end(1)

    prefix = seed_url[:number_start]
    suffix = seed_url[number_end:]

    found = []

    for index in range(1, 13):

        candidate = (
            prefix
            + f"{index:02d}"
            + suffix
        )

        if image_exists(
            candidate,
            article_url,
        ):
            found.append(candidate)

    if seed_url not in found:
        found.append(seed_url)

    # URL ?? ??
    result = []

    for url in found:
        if url not in result:
            result.append(url)

    return result


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

    except Exception as exc:

        print(
            "  -> HTML ??? ?? ??: "
            f"{exc}"
        )

    direct_urls = extract_urls_from_html(
        source,
        article_url,
    )

    # ??? DOM? ??
    rendered = render_html_with_edge(
        article_url
    )

    if rendered:

        rendered_urls = extract_urls_from_html(
            rendered,
            article_url,
        )

        for url in rendered_urls:
            if url not in direct_urls:
                direct_urls.append(url)

    if not direct_urls:

        return []

    # --------------------------------------------------
    # ?? ?? ??? seed ??
    # --------------------------------------------------
    # ???/???? ?? ??? ?? ?? ???
    # ???? content ???? ??? ???? ??? ??.
    seed = None

    for url in direct_urls:

        low = url.lower()

        if not (
            "/wp-content/uploads/"
            in low
            or "skhynix-prd-data"
            in low
        ):
            continue

        if any(
            x in low
            for x in (
                "thumb",
                "thmb",
                "thumbnail",
                "ico_",
                "favicon",
                "logo",
                "banner",
            )
        ):
            continue

        seed = url
        break

    if not seed:
        return []

    print(
        "  -> ?? ??? ?? ??: "
        + seed.split("/")[-1][:100]
    )

    # --------------------------------------------------
    # 01, 02, 03... ?? ??? ?? ??
    # --------------------------------------------------
    expanded = expand_numbered_article_images(
        seed,
        article_url,
    )

    # ?? ?? seed? ?? ??? ??? ??
    seed_parent = (
        seed.rsplit("/", 1)[0]
        + "/"
    )

    result = []

    for url in expanded:

        if not url.startswith(seed_parent):
            continue

        low = url.lower()

        if any(
            x in low
            for x in (
                "thumb",
                "thmb",
                "thumbnail",
                "ico_",
                "favicon",
                "logo",
            )
        ):
            continue

        if url not in result:
            result.append(url)

    return result[:MAX_IMAGES]



def download_image(
    image_url: str,
    article_url: str,
) -> bytes | None:

    response = requests.get(
        image_url,
        headers={
            **HEADERS,
            "Referer": article_url,
        },
        timeout=60,
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get("Content-Type", "")
        .lower()
    )

    if (
        not content_type.startswith("image/")
        and not is_image_url(image_url)
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
        BytesIO(image_bytes)
    )

    image.load()

    image = image.convert(
        "RGB"
    )

    original_width, original_height = (
        image.size
    )

    print(
        "     ?? ??? ??: "
        f"{original_width}x{original_height}"
    )

    # ?? ?? ?? ??:
    # ?? ??? ?? 2? ???? ??
    target_width = 1600

    if original_width < target_width:

        scale = min(
            target_width
            / original_width,
            2.0,
        )

        new_width = int(
            original_width
            * scale
        )

        new_height = int(
            original_height
            * scale
        )

        try:
            resample = (
                Image.Resampling.LANCZOS
            )
        except AttributeError:
            resample = Image.LANCZOS

        image = image.resize(
            (
                new_width,
                new_height,
            ),
            resample,
        )

    width, height = image.size

    # ? ?????? ?? ??
    tile_height = 1600
    overlap = 120

    # ???? ? ???? ?? ? 18??
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

        # ??? ??? ?? ???
        # ?? ??? ???.
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
        "     ??? ??: "
        f"{len(ranges)}??"
    )

    tiles: list[bytes] = []

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

        # ?? ??? ??? JPEG ??? ?? PNG ??
        crop.save(
            buffer,
            format="PNG",
            optimize=True,
        )

        tiles.append(
            buffer.getvalue()
        )

    return tiles


def read_image_with_ollama(
    image_bytes: bytes,
    title: str,
    index: int,
    total: int,
) -> str:

    image_b64 = base64.b64encode(
        image_bytes
    ).decode("ascii")

    prompt = f"""
? ???? SK???? ???? ???? ?? ?
? ????.

?? ??:
{title}

?? ??? ??:
{index}/{total}

? ??? ??? ??? ??? ?? ???
??? ? ???? ?? ???? ???.

?? ??:
- ???? ???.
- ???? ??? ??? ??? ???.
- ??? ?? ?? ??? ???? ???.
- ?? ??? ???? ???.
- ?? ?? ??? ??? ??? ???? ???.
- ??, ??, ?? ??, ?? ??? ????.
- ???, ???, ???, ???? ????.
- ?? ??? ?? ??? ?? ? ??? ????.
- ??? ??? ?? ??? ????.
- ?? ??? ??? ??? ??? ??? ??? ???.
- ??, ??, SNS ???? ?? ??? ????.
- ?? ? ?? ??? ????.
- Markdown ????? ???? ???.

???? ?? ??? ?? ???
NO_ARTICLE_TEXT
??? ????.
""".strip()

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": VISION_MODEL,
            "stream": False,
            "think": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [
                        image_b64
                    ],
                }
            ],
            "options": {
                "temperature": 0.05,
                "num_ctx": 8192,
                "num_predict": 2200,
            },
        },
        timeout=300,
    )

    response.raise_for_status()

    result = response.json()

    text = (
        result
        .get("message", {})
        .get("content", "")
    )

    text = clean_text(
        text
    )

    if (
        not text
        or text
        == "NO_ARTICLE_TEXT"
    ):
        return ""

    return text


def extract_article_image_text(
    article_url: str,
    title: str,
) -> dict | None:

    urls = find_article_image_urls(
        article_url
    )

    if not urls:

        print(
            "  -> ??? ?? ??? URL ??"
        )

        return None

    print(
        "  -> ??? ?? ??? "
        f"{len(urls)}? ??"
    )

    extracted_parts: list[str] = []
    used_urls: list[str] = []

    for image_index, image_url in enumerate(
        urls,
        1,
    ):

        print(
            "  -> ?? ??? ?? "
            f"{image_index}/{len(urls)}"
        )

        try:

            image_bytes = download_image(
                image_url,
                article_url,
            )

            if not image_bytes:

                print(
                    "     ??? ???? ??"
                )

                continue

            tiles = make_image_tiles(
                image_bytes
            )

        except Exception as exc:

            print(
                "     ??? ?? ??: "
                f"{exc}"
            )

            continue

        image_parts = []

        for tile_index, tile_bytes in enumerate(
            tiles,
            1,
        ):

            print(
                "     ?? ?? "
                f"{tile_index}/{len(tiles)}"
            )

            try:

                text = (
                    read_image_with_ollama(
                        tile_bytes,
                        title,
                        tile_index,
                        len(tiles),
                    )
                )

            except Exception as exc:

                print(
                    "       ?? ??: "
                    f"{exc}"
                )

                continue

            print(
                "       ??: "
                f"{len(text):,}?"
            )

            if len(text) < 30:
                continue

            # ??? ??? ??? ??
            if text in image_parts:
                continue

            image_parts.append(
                text
            )

        if not image_parts:
            continue

        combined_image_text = (
            "\n\n".join(
                image_parts
            )
        )

        extracted_parts.append(
            combined_image_text
        )

        used_urls.append(
            image_url
        )

    if not extracted_parts:

        return None

    combined = "\n\n".join(
        extracted_parts
    ).strip()

    print(
        "  -> ??? ?? ?? ? ??: "
        f"{len(combined):,}?"
    )

    # ?? 300? ?????? ?? ?? ??
    if len(combined) < 300:
        return None

    return {
        "text": combined,
        "image_urls": used_urls,
        "model": VISION_MODEL,
    }
