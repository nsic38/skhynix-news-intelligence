from __future__ import annotations

import argparse

from ai_analyzer_v4 import (
    analyze_with_ollama_v4,
)

from image_article import (
    extract_article_image_text,
)

from source_guard import (
    sanitize_article_source,
    source_is_safe,
)

from update_news import (
    DATA_FILE,
    fetch_article_data,
    html_to_text,
    load_json,
    save_json,
)

from update_news_ai import (
    AI_ENGINE,
    enrich_role_analysis,
    usable_article_body,
)


BAD_ANALYSIS_FIELDS = (
    "main_point",
    "one_liner",
    "key_points",
    "why_it_matters",
    "category",
    "_evidence",
    "role_analysis",
    "career_relevance",
    "analysis_engine",
    "content_source",
    "media_title",
    "media_url",
    "caption_language",
)


def parse_args():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--match",
        default="",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--all",
        action="store_true",
    )

    return parser.parse_args()


def mark_pending(
    article: dict,
    reason: str,
):

    for key in BAD_ANALYSIS_FIELDS:

        article.pop(
            key,
            None,
        )

    article[
        "analysis_status"
    ] = "pending"

    article[
        "analysis_error"
    ] = reason


def main():

    args = parse_args()

    if (
        not args.match
        and not args.all
    ):

        print(
            "Use --match or --all"
        )

        return 0

    articles = load_json(
        DATA_FILE,
        [],
    )

    targets = [
        article
        for article in articles
        if article.get(
            "analysis_engine"
        ) != AI_ENGINE
    ]

    if args.match:

        keyword = (
            args.match.lower()
        )

        targets = [
            article
            for article in targets
            if keyword
            in article.get(
                "title",
                "",
            ).lower()
        ]

    if args.limit > 0:

        targets = targets[
            :args.limit
        ]

    print(
        f"articles: {len(articles)}"
    )

    print(
        f"targets: {len(targets)}"
    )

    success = 0
    failed = 0

    for index, article in enumerate(
        targets,
        1,
    ):

        title = article.get(
            "title",
            "",
        )

        url = article.get(
            "url",
            "",
        )

        tags = list(
            article.get(
                "tags",
                [],
            )
            or []
        )

        print()
        print("=" * 70)

        print(
            f"[{index}/{len(targets)}] "
            f"{title}"
        )

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

            tags = list(
                dict.fromkeys(
                    tags
                    + (
                        page_tags
                        or []
                    )
                )
            )

        except Exception as exc:

            print(
                "  -> page request failed: "
                f"{exc}"
            )

        source = ""
        content_source = ""

        if usable_article_body(
            body
        ):

            source = html_to_text(
                body
            )

            content_source = (
                "article"
            )

            print(
                "  -> HTML source"
            )

        else:

            print(
                "  -> HTML rejected; "
                "checking current-page image"
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
                    "  -> image source failed: "
                    f"{exc}"
                )

            if image_info:

                source = image_info[
                    "text"
                ]

                content_source = (
                    "article-image"
                )

        source = sanitize_article_source(
            source,
            title,
        )

        if not source_is_safe(
            source,
            title,
            min_chars=300,
        ):

            failed += 1

            mark_pending(
                article,
                "source integrity guard rejected input",
            )

            save_json(
                DATA_FILE,
                articles,
            )

            print(
                "  -> PENDING: unsafe or "
                "insufficient source"
            )

            continue

        try:

            analysis = (
                analyze_with_ollama_v4(
                    title,
                    html_to_text(
                        description
                    ),
                    source,
                    tags,
                )
            )

            analysis = (
                enrich_role_analysis(
                    analysis,
                    title,
                    source,
                    tags,
                )
            )

        except Exception as exc:

            failed += 1

            mark_pending(
                article,
                str(exc),
            )

            save_json(
                DATA_FILE,
                articles,
            )

            print(
                "  -> PENDING: "
                f"{exc}"
            )

            continue

        article.update(
            analysis
        )

        article[
            "tags"
        ] = tags

        article[
            "analysis_engine"
        ] = AI_ENGINE

        article[
            "content_source"
        ] = content_source

        article[
            "analysis_status"
        ] = "complete"

        article.pop(
            "analysis_error",
            None,
        )

        if page_date:

            article[
                "published"
            ] = page_date

            article[
                "date_source"
            ] = "page"

        save_json(
            DATA_FILE,
            articles,
        )

        success += 1

        print(
            "  -> saved"
        )

    print()
    print("=" * 70)

    print(
        f"done: success={success}, "
        f"pending={failed}"
    )

    remaining = sum(
        1
        for article in articles
        if article.get(
            "analysis_engine"
        ) != AI_ENGINE
    )

    print(
        f"remaining={remaining}"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
