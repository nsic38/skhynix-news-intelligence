from __future__ import annotations

import argparse

from ai_analyzer_v4 import (
    analyze_with_ollama_v4,
)

from image_article import (
    extract_article_image_text,
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


def parse_args():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--match",
        default="",
        help="제목에 포함된 문자열만 처리",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="최대 처리 기사 수",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="미처리 기사 전체 재분석",
    )

    return parser.parse_args()


def main():

    args = parse_args()

    if not args.match and not args.all:

        print(
            "안전 중지: "
            "--match 또는 --all을 지정하세요."
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
            args.match
            .lower()
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
        f"전체 기사: "
        f"{len(articles)}개"
    )

    print(
        f"이번 처리 대상: "
        f"{len(targets)}개"
    )

    if not targets:

        print(
            "처리할 기사가 없습니다."
        )

        return 0

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
                "  -> 뉴스룸 요청 실패: "
                f"{exc}"
            )

        source = ""
        content_source = ""

        # --------------------------------------------------
        # 1. 일반 텍스트 기사
        # --------------------------------------------------
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
                "  -> 기사 본문 사용: "
                f"{len(source):,}자"
            )

        # --------------------------------------------------
        # 2. 이미지형 뉴스룸 기사
        # --------------------------------------------------
        else:

            print(
                "  -> HTML 기사 본문 부족"
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
                    "  -> 기사 이미지 처리 실패: "
                    f"{exc}"
                )

            if image_info:

                source = (
                    image_info[
                        "text"
                    ]
                )

                content_source = (
                    "article-image"
                )

                print(
                    "  -> 뉴스룸 이미지 원문 사용: "
                    f"{len(source):,}자"
                )

            else:

                print(
                    "  -> 이미지 원문도 부족"
                )

        # --------------------------------------------------
        # 원문 안전장치
        # --------------------------------------------------
        if len(source) < 300:

            failed += 1

            print(
                "  -> 처리 보류: "
                "분석 가능한 원문 부족"
            )

            continue

        # --------------------------------------------------
        # 기존 V4 요약기
        # --------------------------------------------------
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

            print(
                "  -> AI 분석 실패: "
                f"{exc}"
            )

            continue

        # --------------------------------------------------
        # 성공한 경우에만 저장
        # --------------------------------------------------
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
            "  -> 저장 완료"
        )

    print()
    print("=" * 70)

    print(
        "재분석 완료: "
        f"성공 {success}개 / "
        f"보류·실패 {failed}개"
    )

    remaining = sum(
        1
        for article in articles
        if article.get(
            "analysis_engine"
        ) != AI_ENGINE
    )

    print(
        "AI 미처리 잔여: "
        f"{remaining}개"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
