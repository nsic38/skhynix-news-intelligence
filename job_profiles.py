from __future__ import annotations

import re

DEFAULT_ROLE = "양산기술"

ROLE_PROFILES = {
    "양산기술": {
        "label": "양산기술",
        "lens": "공정 안정성·수율·생산성·양산 전환",
        "dimensions": {
            "양산 전환": (3.2, ["양산", "mass production", "생산", "제조", "라인", "fab", "팹"]),
            "수율·품질": (3.0, ["수율", "yield", "불량", "결함", "품질", "신뢰성", "검사"]),
            "공정 최적화": (2.9, ["공정", "process", "조건", "최적화", "recipe", "공정 안정"]),
            "생산성·원가": (2.5, ["생산성", "원가", "비용", "효율", "throughput", "capacity", "생산 능력"]),
            "HBM·패키징": (2.3, ["hbm", "패키징", "packaging", "mr-muf", "hybrid bonding", "tsv", "적층", "본딩"]),
            "데이터 기반 개선": (1.5, ["데이터", "분석", "ai", "자동화", "예측", "진단"]),
        },
        "direct": ["양산", "수율", "공정", "생산", "제조", "불량", "mr-muf", "hybrid bonding", "tsv"],
    },

    "양산관리": {
        "label": "양산관리",
        "lens": "TAT·WIP·병목·생산계획·납기",
        "dimensions": {
            "TAT·Cycle Time": (3.4, ["tat", "turn-around time", "cycle time", "리드타임", "소요시간"]),
            "WIP·물류": (3.1, ["wip", "재공", "물류", "lot", "로트", "공정 흐름"]),
            "병목 관리": (3.0, ["병목", "bottleneck", "대기", "지연", "정체"]),
            "생산계획·CAPA": (2.8, ["생산계획", "생산 계획", "capa", "capacity", "생산 능력", "증산"]),
            "생산성": (2.4, ["생산성", "throughput", "효율", "가동", "납기", "생산"]),
            "데이터·자동화": (1.8, ["데이터", "모니터링", "자동화", "ai", "예측", "최적화"]),
        },
        "direct": ["tat", "wip", "재공", "병목", "생산계획", "capa", "throughput", "납기"],
    },

    "공정기술": {
        "label": "공정기술",
        "lens": "공정 조건·Process Window·결함·미세화",
        "dimensions": {
            "공정 조건": (3.3, ["공정", "process", "recipe", "조건", "공정 조건", "process window"]),
            "수율·결함": (3.0, ["수율", "yield", "결함", "defect", "불량", "uniformity", "균일도"]),
            "미세화": (2.8, ["미세화", "선폭", "euv", "high-na", "pattern", "패터닝"]),
            "Etch·Depo·Litho": (2.8, ["etch", "식각", "deposition", "증착", "lithography", "노광", "photo"]),
            "계측·분석": (2.1, ["계측", "metrology", "분석", "검사", "sem", "cd", "두께"]),
            "패키징 공정": (2.0, ["mr-muf", "hybrid bonding", "tsv", "본딩", "패키징"]),
        },
        "direct": ["공정", "recipe", "수율", "결함", "etch", "식각", "증착", "euv", "미세화"],
    },

    "설비기술": {
        "label": "설비기술",
        "lens": "장비 가동률·PM·고장 진단·설비 안정화",
        "dimensions": {
            "장비·설비": (3.3, ["장비", "equipment", "설비", "tool", "챔버", "chamber"]),
            "가동률": (3.0, ["가동률", "uptime", "availability", "가동", "down time", "downtime"]),
            "PM·유지보수": (3.0, ["pm", "preventive maintenance", "유지보수", "정비", "maintenance"]),
            "고장·진단": (2.9, ["고장", "장애", "알람", "fault", "진단", "troubleshooting", "트러블슈팅"]),
            "센서·제어": (2.4, ["센서", "sensor", "제어", "control", "모니터링", "신호"]),
            "자동화": (1.8, ["자동화", "automation", "데이터", "예지보전", "predictive"]),
        },
        "direct": ["장비", "설비", "pm", "유지보수", "고장", "fault", "센서", "제어", "가동률"],
    },

    "품질/신뢰성": {
        "label": "품질/신뢰성",
        "lens": "불량 원인·검사·신뢰성·품질 개선",
        "dimensions": {
            "품질·불량": (3.3, ["품질", "quality", "불량", "defect", "결함", "품질 개선"]),
            "신뢰성": (3.2, ["신뢰성", "reliability", "수명", "열화", "내구", "failure"]),
            "검사·계측": (2.8, ["검사", "inspection", "계측", "test", "테스트", "측정"]),
            "원인 분석": (2.8, ["원인", "분석", "failure analysis", "fa", "root cause", "rca"]),
            "수율": (2.3, ["수율", "yield", "스크랩", "재작업", "rework"]),
            "고객 품질": (2.0, ["고객", "qualification", "인증", "spec", "스펙"]),
        },
        "direct": ["품질", "불량", "신뢰성", "검사", "failure", "수율", "root cause"],
    },

    "제품/소자": {
        "label": "제품/소자",
        "lens": "메모리 구조·성능·전력·제품 로드맵",
        "dimensions": {
            "DRAM·HBM": (3.0, ["dram", "hbm", "ddr", "lpddr", "gddr", "메모리"]),
            "NAND·Storage": (2.8, ["nand", "ssd", "ufs", "스토리지", "storage"]),
            "소자 구조": (2.8, ["소자", "device", "cell", "셀", "transistor", "트랜지스터", "3d"]),
            "성능·전력": (2.6, ["성능", "performance", "전력", "power", "대역폭", "bandwidth", "latency"]),
            "제품 로드맵": (2.4, ["차세대", "roadmap", "로드맵", "제품", "출시", "세대"]),
            "AI 메모리": (2.2, ["ai", "pim", "cxl", "hbf", "gpu"]),
        },
        "direct": ["dram", "hbm", "nand", "소자", "cell", "성능", "전력", "대역폭", "제품"],
    },

    "IT": {
        "label": "IT",
        "lens": "MES·시스템 연계·인프라·보안·업무 자동화",
        "dimensions": {
            "MES·제조 IT": (3.2, ["mes", "manufacturing execution", "제조 시스템", "생산 시스템", "스마트팩토리"]),
            "시스템·플랫폼": (2.9, ["시스템", "platform", "플랫폼", "application", "서비스", "erp"]),
            "Cloud·Infra": (2.7, ["cloud", "클라우드", "infra", "인프라", "server", "서버", "network", "네트워크"]),
            "보안": (2.8, ["보안", "security", "cyber", "사이버", "정보보호"]),
            "자동화·DX": (2.4, ["자동화", "automation", "dx", "ax", "디지털 전환"]),
            "데이터 연계": (2.0, ["데이터", "database", "db", "api", "통합", "연계"]),
        },
        "direct": ["mes", "시스템", "플랫폼", "cloud", "클라우드", "보안", "network", "자동화"],
    },

    "Data/AI": {
        "label": "Data/AI",
        "lens": "데이터 분석·ML·예측·최적화·AI 서비스",
        "dimensions": {
            "AI·ML": (3.3, ["ai", "인공지능", "machine learning", "머신러닝", "ml", "딥러닝", "agentic", "에이전틱"]),
            "데이터 분석": (3.0, ["데이터", "분석", "analytics", "빅데이터", "통계"]),
            "예측·진단": (2.8, ["예측", "prediction", "진단", "이상탐지", "anomaly"]),
            "최적화": (2.7, ["최적화", "optimization", "추천", "의사결정"]),
            "AI Infra": (2.2, ["gpu", "hbm", "ai 인프라", "data center", "데이터센터", "워크로드"]),
            "자동화": (1.9, ["자동화", "automation", "agent", "에이전트"]),
        },
        "direct": ["ai", "머신러닝", "ml", "데이터", "예측", "최적화", "에이전틱", "agentic"],
    },
}

COMMON_LOW_RELEVANCE = ["사회공헌", "봉사", "문화", "예술", "스포츠", "캠페인", "지역사회"]


def list_roles() -> list[str]:
    return list(ROLE_PROFILES.keys())


def _hit(text: str, keyword: str) -> bool:
    text = text.lower()
    keyword = keyword.lower()

    # AI, ML, PM, FA처럼 짧은 영문 키워드는 단어 경계로 판정
    if keyword.isascii() and keyword.replace("-", "").isalnum() and len(keyword) <= 3:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text))

    return keyword in text


def score_role_relevance(
    role: str,
    *,
    title: str,
    main_point: str,
    key_points: list[str],
    body: str,
    tags: list[str],
) -> dict:
    if role not in ROLE_PROFILES:
        raise KeyError(f"Unknown role: {role}")

    profile = ROLE_PROFILES[role]
    title_text = title or ""
    focus_text = f"{main_point} {' '.join(key_points)} {' '.join(tags)}"
    body_text = (body or "")[:6000]

    dimension_scores = {}

    for dimension, (weight, keywords) in profile["dimensions"].items():
        hits = []
        dim_score = 0.0

        for keyword in keywords:
            local = 0.0
            if _hit(title_text, keyword):
                local += weight * 1.55
            if _hit(focus_text, keyword):
                local += weight * 1.10
            if _hit(body_text, keyword):
                local += weight * 0.35

            if local > 0:
                dim_score += local
                hits.append(keyword)

        if dim_score > 0:
            dimension_scores[dimension] = {
                "score": round(dim_score, 3),
                "keywords": hits[:4],
            }

    whole_text = f"{title_text} {focus_text} {body_text[:1600]}"
    direct_hits = [kw for kw in profile["direct"] if _hit(whole_text, kw)]

    ranked = sorted(
        dimension_scores.items(),
        key=lambda item: item[1]["score"],
        reverse=True,
    )

    # 관련성은 상위 축이 강한지를 중심으로 평가하여 키워드 개수가 많은 직무가 유리해지는 것을 방지
    raw = sum(info["score"] for _, info in ranked[:4])
    low_hits = sum(1 for kw in COMMON_LOW_RELEVANCE if _hit(whole_text, kw))
    raw = max(0.0, raw - low_hits * 2.8)

    if raw >= 18:
        score = 5
    elif raw >= 10:
        score = 4
    elif raw >= 5:
        score = 3
    elif raw >= 1.8:
        score = 2
    else:
        score = 1

    # 직무 핵심 키워드가 기사 중심부에 직접 나타나면 최소 관련성 보정
    focus_direct_count = sum(1 for kw in profile["direct"] if _hit(f"{title_text} {focus_text}", kw))
    if focus_direct_count >= 3:
        score = max(score, 5)
    elif focus_direct_count >= 2:
        score = max(score, 4)
    elif focus_direct_count >= 1:
        score = max(score, 3)

    top_dimensions = [name for name, _ in ranked[:3]]
    top_keywords = []
    for _, info in ranked[:3]:
        for keyword in info["keywords"]:
            if keyword not in top_keywords:
                top_keywords.append(keyword)

    return {
        "role": role,
        "score": int(score),
        "reason": " · ".join(top_dimensions) if top_dimensions else "직접 연관 신호가 적음",
        "dimensions": top_dimensions,
        "matched_keywords": top_keywords[:6],
        "lens": profile["lens"],
    }
