from __future__ import annotations

import argparse

from ai_analyzer_v4 import analyze_with_ollama_v4
from media_source import find_youtube_transcript

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
        help="제목에 포함된 문자열만 처리"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="최대 처리 기사 수"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="미처리 기사 전체 재분석"
    )

    return parser.parse_args()


def main():

    args = parse_args()

    # 안전장치:
    # --match 또는 --all 없이는 절대 실행하지 않음
    if not args.match and not args.all:

        print(
            "안전 중지: --match 또는 --all을 지정하세요."
        )

        print(
            '예: py reanalyze_ai.py '
            '--match "품질보증" --limit 1'
        )

        print(
            "전체 실행: "
            "py reanalyze_ai.py --all"
        )

        return 0

    articles = load_json(
        DATA_FILE,
        []
    )

    targets = [
        article
        for article in articles
        if article.get(
            "analysis_engine"
        ) != AI_ENGINE
    ]

    if args.match:

        keyword = args.match.lower()

        targets = [
            article
            for article in targets
            if keyword
            in article.get(
                "title",
                ""
            ).lower()
        ]

    if args.limit > 0:

        targets = targets[
            :args.limit
        ]

    print(
        f"전체 기사: {len(articles)}개"
    )

    print(
        f"이번 처리 대상: {len(targets)}개"
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
        1
    ):

        title = article.get(
            "title",
            ""
        )

        url = article.get(
            "url",
            ""
        )

        tags = list(
            article.get(
                "tags",
                []
            )
            or []
        )

        print()
        print(
            "=" * 70
        )

        print(
            f"[{index}/{len(targets)}] "
            f"{title}"
        )

        description = ""
        body = ""
        page_tags = []

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
                    + (page_tags or [])
                )
            )

        except Exception as exc:

            print(
                "  -> 뉴스룸 요청 실패: "
                f"{exc}"
            )

        source = ""
        content_source = ""
        media = None

        # 1. 정상 기사 본문
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

        # 2. 본문이 없거나 미디어형 기사
        else:

            print(
                "  -> 유효 기사 본문 부족 -> 분석 보류"
            )

            try:

                media = (
                    find_youtube_transcript(
                        title,
                        tags
                    )
                )

            except Exception as exc:

                print(
                    "  -> YouTube 검색 실패: "
                    f"{exc}"
                )

                media = None

            if media:

                source = media[
                    "text"
                ]

                content_source = (
                    "youtube-caption"
                )

                print(
                    "  -> 영상: "
                    f"{media['video_title']}"
                )

                print(
                    "  -> 자막 길이: "
                    f"{len(source):,}자"
                )

        # 잘못된 title-only 분석 방지
        if len(source) < 300:

            failed += 1

            print(
                "  -> 처리 보류: "
                "분석 가능한 원문 부족"
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

            print(
                "  -> AI 분석 실패: "
                f"{exc}"
            )

            continue

        # 성공한 경우에만 기존 기사 갱신
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

        if media:

            article[
                "media_title"
            ] = media[
                "video_title"
            ]

            article[
                "media_url"
            ] = media[
                "video_url"
            ]

            article[
                "caption_language"
            ] = media[
                "caption_language"
            ]

        # 한 기사 성공할 때마다 저장
        # 중간에 종료돼도 완료분은 보존
        save_json(
            DATA_FILE,
            articles
        )

        success += 1

        print(
            "  -> 저장 완료"
        )

    print()
    print(
        "=" * 70
    )

    print(
        f"재분석 완료: "
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
        f"AI 미처리 잔여: "
        f"{remaining}개"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
