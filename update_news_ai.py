from __future__ import annotations

from source_guard import (
    sanitize_article_source,
    source_is_safe,
)

from image_article import (
    extract_article_image_text,
)

import hashlib

from ai_analyzer_v4 import (
    analyze_with_ollama_v4,
)
from analyzer import (
    refresh_saved_role_analysis,
)
from media_source import (
    find_youtube_transcript,
)
from update_news import (
    BOOTSTRAP_COUNT,
    DATA_FILE,
    STATE_FILE,
    REPAIR_VERSION,
    clean_text,
    extract_rss_text,
    fetch_article_data,
    fetch_rss_entries,
    html_to_text,
    is_blocked_item,
    is_junk_summary_text,
    load_json,
    normalize_title,
    normalize_url,
    now_iso,
    parse_rss_date,
    save_json,
)


AI_ENGINE = "ollama-qwen3-4b-article-only-v2"


def usable_article_body(
    body: str
) -> bool:

    text = sanitize_article_source(
        body
    )

    return source_is_safe(
        text,
        min_chars=350,
    )


def enrich_role_analysis(
    analysis: dict,
    title: str,
    source: str,
    tags: list[str],
) -> dict:

    source = sanitize_article_source(
        source,
        title,
    )


    temp = {
        "title": title,
        "main_point":
            analysis[
                "main_point"
            ],
        "one_liner":
            analysis[
                "main_point"
            ],
        "key_points":
            analysis[
                "key_points"
            ],
        "tags": tags,
    }

    refresh_saved_role_analysis(
        temp,
        source
    )

    analysis[
        "one_liner"
    ] = analysis[
        "main_point"
    ]

    for key in (
        "role_analysis",
        "job_relevance",
        "takeaway",
        "importance",
    ):
        analysis[key] = temp[key]

    return analysis


def build_record_ai(
    entry
) -> dict:

    title = clean_text(
        getattr(
            entry,
            "title",
            ""
        )
    )

    url = normalize_url(
        getattr(
            entry,
            "link",
            ""
        )
    )

    rss_text = extract_rss_text(
        entry
    )

    rss_tags = [
        getattr(
            x,
            "term",
            ""
        )
        for x in (
            getattr(
                entry,
                "tags",
                []
            )
            or []
        )
        if getattr(
            x,
            "term",
            ""
        )
    ]

    description = ""
    body = ""
    page_tags = []
    page_date = ""

    try:
        (
            description,
            body,
            page_tags,
            page_date,
        ) = fetch_article_data(
            url
        )

    except Exception as exc:
        print(
            "  -> 뉴스룸 본문 요청 실패: "
            f"{exc}"
        )

    tags = list(
        dict.fromkeys(
            [
                x
                for x
                in (
                    rss_tags
                    + page_tags
                )
                if x
            ]
        )
    )

    analysis_source = ""
    content_source = ""
    media_info = None

    if usable_article_body(
        body
    ):
        analysis_source = (
            html_to_text(
                body
            )
        )

        content_source = (
            "article"
        )

        print(
            "  -> ??? ?? ??: "
            f"{len(analysis_source):,}?"
        )

    else:

        print(
            "  -> HTML ?? ?? ??"
        )

        image_info = None

        try:

            image_info = (
                extract_article_image_text(
                    url,
                    title,
                )
            )

        except Exception as exc:

            print(
                "  -> ??? ??? ?? ?? ??: "
                f"{exc}"
            )

        if image_info:

            analysis_source = (
                image_info[
                    "text"
                ]
            )

            content_source = (
                "article-image"
            )

            print(
                "  -> ??? ??? ?? ??: "
                f"{len(analysis_source):,}?"
            )

        else:

            print(
                "  -> ??? ??? ??? ?? "
                "-> ?? ??"
            )

    # ARTICLE-ONLY MODE:
    # ?? ??? ??? HTML ?? ??
    # ??? ?? ??? ?????.
    if (
        analysis_source
        and content_source
        not in (
            "article",
            "article-image",
        )
    ):
        analysis_source = ""
        media_info = None

    if False and not analysis_source:

        # ARTICLE-ONLY MODE:
        # RSS/description은 기사 본문 대신 사용하지 않는다.
        fallback = html_to_text(
            rss_text
            or description
        )

        if (
            len(fallback) >= 1500
            and not is_junk_summary_text(
                fallback
            )
        ):
            analysis_source = (
                fallback
            )

            content_source = (
                "rss/content"
            )

            print(
                "  -> RSS 본문 사용"
            )

    if not analysis_source:
        raise RuntimeError(
            "분석 가능한 기사 본문을 찾지 못했습니다."
        )

    description_for_ai = (
        html_to_text(
            description
        )
    )

    analysis = (
        analyze_with_ollama_v4(
            title,
            description_for_ai,
            analysis_source,
            tags,
        )
    )

    analysis = (
        enrich_role_analysis(
            analysis,
            title,
            analysis_source,
            tags,
        )
    )

    record = {
        "id": hashlib.sha1(
            url.encode(
                "utf-8"
            )
        ).hexdigest()[:12],

        "title": title,
        "url": url,

        "published":
            page_date
            or parse_rss_date(
                entry
            ),

        "date_source":
            "page"
            if page_date
            else "rss",

        "source":
            "SK hynix Newsroom",

        "tags":
            tags,

        "created_at":
            now_iso(),

        "content_source":
            content_source,

        "repair_version":
            REPAIR_VERSION,

        "analysis_engine":
            AI_ENGINE,

        **analysis,
    }

    if media_info:

        record[
            "media_title"
        ] = media_info[
            "video_title"
        ]

        record[
            "media_url"
        ] = media_info[
            "video_url"
        ]

        record[
            "caption_language"
        ] = media_info[
            "caption_language"
        ]

    return record


def main() -> int:

    articles = load_json(
        DATA_FILE,
        []
    )

    state = load_json(
        STATE_FILE,
        {
            "last_checked_at": None,
            "last_updated_at": None,
            "last_new_count": 0,
            "total_articles":
                len(articles),
        }
    )

    try:
        entries = (
            fetch_rss_entries()
        )

        print(
            "RSS 정상: "
            f"기사 {len(entries)}개 확인"
        )

    except Exception as exc:
        print(
            f"RSS 확인 실패: {exc}"
        )
        return 1

    existing_urls = {
        normalize_url(
            article.get(
                "url",
                ""
            )
        )
        for article
        in articles
    }

    existing_titles = {
        normalize_title(
            article.get(
                "title",
                ""
            )
        )
        for article
        in articles
    }

    if not articles:
        targets = entries[
            :BOOTSTRAP_COUNT
        ]
    else:
        targets = [
            entry
            for entry in entries
            if normalize_url(
                getattr(
                    entry,
                    "link",
                    ""
                )
            )
            not in existing_urls

            and normalize_title(
                getattr(
                    entry,
                    "title",
                    ""
                )
            )
            not in existing_titles
        ]

    print(
        f"기존 기사 {len(articles)}개 / "
        f"새 기사 {len(targets)}개"
    )

    added = []
    failed = 0

    for index, entry in enumerate(
        reversed(targets),
        1
    ):

        title = clean_text(
            getattr(
                entry,
                "title",
                ""
            )
        )

        print()
        print(
            f"[{index}/{len(targets)}] "
            f"새 기사 처리: {title}"
        )

        try:
            record = (
                build_record_ai(
                    entry
                )
            )

        except Exception as exc:
            failed += 1

            print(
                "  -> 처리 보류: "
                f"{exc}"
            )

            continue

        url_key = normalize_url(
            record[
                "url"
            ]
        )

        title_key = normalize_title(
            record[
                "title"
            ]
        )

        if (
            is_blocked_item(
                record[
                    "title"
                ],
                record[
                    "url"
                ]
            )
            or url_key
            in existing_urls
            or title_key
            in existing_titles
        ):
            continue

        articles.append(
            record
        )

        added.append(
            record
        )

        existing_urls.add(
            url_key
        )

        existing_titles.add(
            title_key
        )

    articles.sort(
        key=lambda x: (
            x.get(
                "published",
                ""
            ),
            x.get(
                "created_at",
                ""
            ),
        ),
        reverse=True,
    )

    save_json(
        DATA_FILE,
        articles
    )

    checked_at = now_iso()

    state[
        "last_checked_at"
    ] = checked_at

    state[
        "last_new_count"
    ] = len(
        added
    )

    state[
        "total_articles"
    ] = len(
        articles
    )

    if added:
        state[
            "last_updated_at"
        ] = checked_at

    save_json(
        STATE_FILE,
        state
    )

    print()
    print(
        "완료: "
        f"새 기사 {len(added)}개 / "
        f"보류 {failed}개 / "
        f"누적 {len(articles)}개"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

