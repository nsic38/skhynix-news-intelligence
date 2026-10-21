from __future__ import annotations

import json
import re
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from yt_dlp import YoutubeDL


GENERIC_TAGS = {
    "채용",
    "취업",
    "sk하이닉스",
    "sk하이닉스 앰버서더",
    "앰버서더",
    "story",
    "tech",
    "tech&ai",
    "press",
    "media",
}


def clean_text(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(text or "")
    ).strip()


def normalize(text: str) -> str:
    return re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        clean_text(text).lower()
    )


def build_search_queries(
    article_title: str,
    tags: list[str] | None = None,
) -> list[str]:

    queries = []

    # 1. 제목 안의 따옴표 핵심어 우선
    quoted = re.findall(
        r"[‘'“\"]([^’'”\"]{2,30})[’'”\"]",
        article_title
    )

    for word in quoted:
        word = clean_text(word)

        if word:
            queries.append(
                f"SK하이닉스 {word}"
            )

    # 2. 구체적인 태그
    for tag in tags or []:
        tag = clean_text(tag)

        if not tag:
            continue

        if tag.lower() in GENERIC_TAGS:
            continue

        queries.append(
            f"SK하이닉스 {tag}"
        )

    # 3. 제목에서 시리즈명 제거
    stripped = re.sub(
        r"^\[[^\]]+\]\s*",
        "",
        article_title
    )

    stripped = clean_text(stripped)

    if stripped:
        queries.append(
            f"SK하이닉스 {stripped}"
        )

    # 4. 제목의 주요 단어만 압축한 검색어
    words = re.findall(
        r"[A-Za-z0-9가-힣]+",
        stripped
    )

    stop = {
        "sk하이닉스",
        "개발부터",
        "고객까지",
        "반도체",
        "전",
        "생애주기",
        "책임지는",
        "the",
        "a",
        "an",
    }

    useful = [
        word
        for word in words
        if word.lower() not in stop
        and len(word) >= 2
    ]

    if useful:
        compact = " ".join(
            useful[-5:]
        )

        queries.append(
            f"SK하이닉스 {compact}"
        )

    # 중복 제거
    result = []

    for query in queries:
        query = clean_text(query)

        if query not in result:
            result.append(query)

    return result


def score_video(
    article_title: str,
    video_title: str,
) -> float:

    a = normalize(article_title)
    v = normalize(video_title)

    score = SequenceMatcher(
        None,
        a,
        v
    ).ratio()

    article_words = set(
        re.findall(
            r"[0-9A-Za-z가-힣]+",
            article_title.lower()
        )
    )

    video_words = set(
        re.findall(
            r"[0-9A-Za-z가-힣]+",
            video_title.lower()
        )
    )

    score += (
        len(
            article_words
            & video_words
        )
        * 0.18
    )

    return score


def is_official(info: dict) -> bool:

    text = " ".join(
        [
            str(info.get("channel", "")),
            str(info.get("uploader", "")),
            str(info.get("channel_id", "")),
            str(info.get("uploader_id", "")),
        ]
    ).lower()

    return (
        "sk hynix" in text
        or "sk하이닉스" in text
    )



TITLE_STOPWORDS = {
    "sk",
    "sk하이닉스",
    "하이닉스",
    "뉴스룸",
    "newsroom",
    "vod",
    "tech",
    "ai",
    "반도체",
    "메모리",
    "기술",
    "시대",
    "글로벌",
    "관련",
    "최근",
    "보도",
    "대한",
    "대해",
    "기사",
    "개최",
    "참가",
    "공개",
    "제시",
    "새로운",
    "미래",
}


def extract_years(
    text: str,
) -> set[str]:

    return set(
        re.findall(
            r"(?<!\d)(20\d{2})(?!\d)",
            text or "",
        )
    )


def strip_korean_particle(
    token: str,
) -> str:

    suffixes = (
        "으로",
        "에서",
        "에게",
        "까지",
        "부터",
        "이라는",
        "라는",
        "과",
        "와",
        "을",
        "를",
        "은",
        "는",
        "이",
        "가",
        "의",
        "에",
        "로",
    )

    for suffix in suffixes:

        if (
            token.endswith(suffix)
            and len(token) - len(suffix) >= 2
        ):
            return token[
                :-len(suffix)
            ]

    return token


def meaningful_title_tokens(
    text: str,
) -> set[str]:

    raw = re.findall(
        r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣.+-]*",
        clean_text(text).lower(),
    )

    result = set()

    for token in raw:

        token = strip_korean_particle(
            token
        )

        if not token:
            continue

        if token in TITLE_STOPWORDS:
            continue

        if re.fullmatch(
            r"20\d{2}",
            token
        ):
            continue

        if len(token) < 2:
            continue

        result.add(token)

    return result


def technical_title_tokens(
    text: str,
) -> set[str]:

    tokens = re.findall(
        r"\b[A-Za-z][A-Za-z0-9.+-]{1,}\b",
        text or "",
    )

    ignored = {
        "SK",
        "AI",
        "EP",
        "VOD",
        "TECH",
        "CLASS",
        "INSIDE",
        "RESEARCH",
    }

    result = set()

    for token in tokens:

        upper = token.upper()

        if upper in ignored:
            continue

        if len(token) < 3:
            continue

        result.add(
            token.lower()
        )

    return result


def quoted_title_anchors(
    text: str,
) -> list[str]:

    found = re.findall(
        r"[‘'“\"]([^’'”\"]{3,50})[’'”\"]",
        text or "",
    )

    result = []

    for value in found:

        value = normalize(
            value
        )

        if len(value) >= 4:
            result.append(value)

    return result


def validate_video_candidate(
    article_title: str,
    video_title: str,
    info: dict,
) -> tuple[bool, str]:

    # 1. 공식 SK hynix 채널만 허용
    if not is_official(info):
        return False, "not_official"

    article_years = extract_years(
        article_title
    )

    video_years = extract_years(
        video_title
    )

    # 2. 양쪽에 연도가 있는데 다르면 즉시 거절
    if (
        article_years
        and video_years
        and article_years.isdisjoint(
            video_years
        )
    ):
        return (
            False,
            "year_mismatch:"
            + ",".join(
                sorted(article_years)
            )
            + "!="
            + ",".join(
                sorted(video_years)
            )
        )

    article_norm = normalize(
        article_title
    )

    video_norm = normalize(
        video_title
    )

    # 3. 따옴표 안의 고유 제목/행사명이
    # 영상 제목에 그대로 존재하면 강한 일치
    quoted_match = any(
        anchor in video_norm
        for anchor in quoted_title_anchors(
            article_title
        )
    )

    article_tokens = meaningful_title_tokens(
        article_title
    )

    video_tokens = meaningful_title_tokens(
        video_title
    )

    shared_tokens = (
        article_tokens
        & video_tokens
    )

    article_tech = technical_title_tokens(
        article_title
    )

    video_tech = technical_title_tokens(
        video_title
    )

    shared_tech = (
        article_tech
        & video_tech
    )

    # 4. 팩트체크/해명 성격 기사는
    # 일반적인 전망·교육 영상으로 대체하지 않음
    factcheck_cues = (
        "확정된 사실이 아닙니다",
        "확정된 사실이 아니다",
        "설명드립니다",
        "보도는",
    )

    if any(
        cue in article_title
        for cue in factcheck_cues
    ):

        video_factcheck = any(
            cue in video_title
            for cue in factcheck_cues
        )

        if not (
            video_factcheck
            or quoted_match
        ):
            return (
                False,
                "factcheck_article_without_matching_video"
            )

    # 5. 연도가 기사에만 있고 영상에는 없을 경우,
    # 더 강한 제목 일치를 요구
    if (
        article_years
        and not video_years
        and not quoted_match
        and not shared_tech
        and len(shared_tokens) < 3
    ):
        return (
            False,
            "article_year_requires_stronger_match"
        )

    # 6. 고유/기술 anchor 중 하나는 반드시 충족
    if quoted_match:
        return True, "quoted_anchor"

    if shared_tech:
        return (
            True,
            "technical_anchor:"
            + ",".join(
                sorted(shared_tech)
            )
        )

    if len(shared_tokens) >= 2:

        base_score = score_video(
            article_title,
            video_title,
        )

        if base_score >= 0.50:
            return (
                True,
                "title_overlap:"
                + ",".join(
                    sorted(shared_tokens)
                )
            )

    return (
        False,
        "weak_title_match:"
        + ",".join(
            sorted(shared_tokens)
        )
    )


def json3_to_text(
    path: Path
) -> str:

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    parts = []
    previous = ""

    for event in data.get(
        "events",
        []
    ):
        text = "".join(
            str(
                seg.get(
                    "utf8",
                    ""
                )
            )
            for seg in event.get(
                "segs",
                []
            )
        )

        text = clean_text(text)

        if not text:
            continue

        if text == previous:
            continue

        parts.append(text)
        previous = text

    transcript = " ".join(parts)

    transcript = re.sub(
        r"\[(?:음악|웃음|박수)\]",
        " ",
        transcript
    )

    transcript = transcript.replace(
        ">>",
        " "
    )

    return clean_text(
        transcript
    )


def download_korean_caption(
    video_url: str,
) -> tuple[str, str]:

    with tempfile.TemporaryDirectory() as tmp:

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,

            "writeautomaticsub": True,
            "writesubtitles": True,

            "subtitleslangs": [
                "ko-orig",
                "ko",
            ],

            "subtitlesformat":
                "json3",

            "outtmpl":
                str(
                    Path(tmp)
                    / "caption.%(ext)s"
                ),
        }

        with YoutubeDL(
            options
        ) as ydl:

            ydl.download(
                [video_url]
            )

        files = list(
            Path(tmp).glob(
                "caption*.json3"
            )
        )

        if not files:
            return "", ""

        files.sort(
            key=lambda path: (
                0
                if "ko-orig"
                in path.name
                else 1
            )
        )

        selected = files[0]

        language = (
            "ko-orig"
            if "ko-orig"
            in selected.name
            else "ko"
        )

        return (
            json3_to_text(
                selected
            ),
            language,
        )


def find_youtube_transcript(
    article_title: str,
    tags: list[str] | None = None,
) -> dict | None:

    # ARTICLE-ONLY MODE
    # 기사 본문 외의 YouTube/외부 자료는 사용하지 않는다.
    return None

    queries = build_search_queries(
        article_title,
        tags
    )

    print(
        "  -> YouTube 검색어: "
        + " / ".join(queries)
    )

    found = {}

    search_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }

    with YoutubeDL(
        search_options
    ) as ydl:

        for query in queries:

            try:
                result = ydl.extract_info(
                    "ytsearch5:" + query,
                    download=False
                )
            except Exception:
                continue

            for entry in (
                result.get(
                    "entries",
                    []
                )
                if result
                else []
            ):
                video_id = entry.get(
                    "id"
                )

                if video_id:
                    found[
                        video_id
                    ] = entry

    if not found:
        return None

    candidates = []

    detail_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with YoutubeDL(
        detail_options
    ) as ydl:

        for video_id in found:

            video_url = (
                "https://www.youtube.com/"
                f"watch?v={video_id}"
            )

            try:
                info = ydl.extract_info(
                    video_url,
                    download=False
                )
            except Exception:
                continue

            title = clean_text(
                info.get(
                    "title",
                    ""
                )
            )

            accepted, reject_reason = (
                validate_video_candidate(
                    article_title,
                    title,
                    info,
                )
            )

            if not accepted:
                print(
                    "  -> YouTube 후보 제외: "
                    f"{title} "
                    f"[{reject_reason}]"
                )
                continue

            score = score_video(
                article_title,
                title
            )

            if is_official(info):
                score += 2.0

            candidates.append(
                (
                    score,
                    video_url,
                    info,
                )
            )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    for score, video_url, info in candidates[:5]:

        print(
            "  -> YouTube 후보: "
            f"{info.get('title', '')} "
            f"(score={score:.2f})"
        )

        try:
            transcript, language = (
                download_korean_caption(
                    video_url
                )
            )
        except Exception:
            continue

        if len(transcript) < 500:
            continue

        return {
            "text":
                transcript,

            "video_title":
                clean_text(
                    info.get(
                        "title",
                        ""
                    )
                ),

            "video_url":
                video_url,

            "caption_language":
                language,

            "match_score":
                round(
                    score,
                    3
                ),
        }

    return None
