from __future__ import annotations

import re

DEFAULT_ROLE = "양산기술"

ROLE_PROFILES = {
    "양산기술": {
        "dimensions": {
            "양산 전환": {
                "weight": 3.2,
                "keywords": ["양산", "mass production", "생산", "제조", "라인", "fab", "팹"]
            },
            "수율·품질": {
                "weight": 3.0,
                "keywords": ["수율", "yield", "불량", "결함", "품질", "신뢰성", "검사"]
            },
            "공정 최적화": {
                "weight": 2.9,
                "keywords": ["공정", "process", "조건", "최적화", "미세공정", "공정기술", "공정 안정"]
            },
            "생산성·원가": {
                "weight": 2.5,
                "keywords": ["생산성", "원가", "비용", "효율", "throughput", "생산 능력", "capacity"]
            },
            "장비·현장": {
                "weight": 2.2,
                "keywords": ["장비", "equipment", "설비", "현장", "모니터링", "센서", "제어"]
            },
            "HBM·패키징": {
                "weight": 2.4,
                "keywords": [
                    "hbm", "패키징", "packaging", "mr-muf", "hybrid bonding",
                    "tsv", "적층", "bonding", "본딩"
                ]
            },
            "메모리 기술": {
                "weight": 1.5,
                "keywords": ["dram", "nand", "메모리", "3d 메모리", "cxl", "pim", "ssd"]
            },
            "데이터 기반 문제해결": {
                "weight": 1.6,
                "keywords": ["데이터", "분석", "ai", "자동화", "예측", "최적", "진단"]
            },
        },
        "low_relevance_keywords": [
            "사회공헌", "봉사", "문화", "예술", "스포츠", "캠페인", "지역사회"
        ],
    }
}


def _contains(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def score_role_relevance(
    role: str,
    *,
    title: str,
    main_point: str,
    key_points: list[str],
    body: str,
    tags: list[str],
) -> dict:
    profile = ROLE_PROFILES[role]

    title_text = title.lower()
    focus_text = f"{main_point} {' '.join(key_points)} {' '.join(tags)}".lower()
    body_text = (body or "")[:5000].lower()

    dimension_scores = {}

    for dimension, info in profile["dimensions"].items():
        hits = []
        score = 0.0

        for keyword in info["keywords"]:
            k = keyword.lower()
            local_score = 0.0

            if k in title_text:
                local_score += info["weight"] * 1.5

            if k in focus_text:
                local_score += info["weight"] * 1.15

            if k in body_text:
                local_score += info["weight"] * 0.45

            if local_score > 0:
                score += local_score
                hits.append(keyword)

        if score > 0:
            dimension_scores[dimension] = {
                "score": score,
                "keywords": hits[:4],
            }

    raw = sum(item["score"] for item in dimension_scores.values())

    whole_text = f"{title_text} {focus_text} {body_text[:1200]}"
    low_hits = sum(
        1 for keyword in profile["low_relevance_keywords"]
        if _contains(whole_text, keyword)
    )
    raw -= low_hits * 2.5

    # direct manufacturing/process terms give a stronger floor
    direct_terms = [
        "양산", "수율", "공정", "생산", "제조", "불량",
        "장비", "패키징", "mr-muf", "hybrid bonding", "tsv"
    ]
    direct_count = sum(1 for term in direct_terms if term in whole_text)

    if raw >= 18 or direct_count >= 4:
        score = 5
    elif raw >= 10 or direct_count >= 2:
        score = 4
    elif raw >= 5:
        score = 3
    elif raw >= 1.5:
        score = 2
    else:
        score = 1

    display_priority = {
        "양산 전환": 3.0,
        "수율·품질": 2.8,
        "공정 최적화": 2.6,
        "생산성·원가": 2.0,
        "장비·현장": 1.8,
        "HBM·패키징": 1.2,
        "메모리 기술": 0.6,
        "데이터 기반 문제해결": 0.4,
    }

    ranked = sorted(
        dimension_scores.items(),
        key=lambda item: item[1]["score"] + display_priority.get(item[0], 0),
        reverse=True
    )

    top_dimensions = [name for name, _ in ranked[:3]]
    top_keywords = []
    for _, info in ranked[:3]:
        for keyword in info["keywords"]:
            if keyword not in top_keywords:
                top_keywords.append(keyword)

    if top_dimensions:
        reason = " · ".join(top_dimensions)
    else:
        reason = "양산·공정 직접 연관 키워드가 적음"

    return {
        "role": role,
        "score": score,
        "reason": reason,
        "dimensions": top_dimensions,
        "matched_keywords": top_keywords[:6],
    }
