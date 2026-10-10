from __future__ import annotations

import html
import math
import re
from collections import Counter

from job_profiles import DEFAULT_ROLE, ROLE_PROFILES, list_roles, score_role_relevance

STOPWORDS = {
    "그리고","그러나","또한","대한","통해","위해","이번","관련","있는","하는","한다","했다",
    "있다","있으며","등을","등의","에서","으로","로서","보다","기반","기사","뉴스룸","기자",
    "밝혔다","전했다","설명했다","말했다","강조했다","덧붙였다",
    "SK하이닉스","하이닉스",
    "the","and","for","with","from","this","that","are","was","were","into","will","has","have"
}

CHANGE_WORDS = (
    "진화","변화","전환","확대","증가","급증","확산","고도화","달라",
    "성장","감소","이동","향상","개선","넘어","부상","도입"
)

IMPORTANCE_WORDS = (
    "핵심","중요","역할","요구","필요","병목","영향","좌우","필수",
    "관건","경쟁력","차별화","효율","성능","가치","우위"
)

FUTURE_WORDS = (
    "향후","미래","차세대","로드맵","전망","계획","목표","전략",
    "투자","양산","개발","도입","출시"
)

TECH_WORDS = (
    "AI","에이전틱","Agentic","워크로드","메모리","HBM","DRAM","NAND",
    "CXL","PIM","GPU","대역폭","용량","전력","패키징","Hybrid",
    "Bonding","MR-MUF","TSV","SSD","데이터","스토리지","인프라","수율","공정"
)

BOILERPLATE_WORDS = (
    "출처","source","사진","이미지","copyright","저작권","무단전재",
    "재배포","관련기사","구독","sns","기자="
)

TOPICS = [
    {
        "keys": ("hbm", "ai 메모리", "ai memory"),
        "category": "HBM / AI Memory",
        "impact": "AI 시스템의 성능 기준이 연산 성능뿐 아니라 메모리 용량·대역폭·전력 효율까지 확장되고 있다는 점",
    },
    {
        "keys": ("hybrid bonding", "mr-muf", "패키징", "packaging", "tsv"),
        "category": "Advanced Packaging",
        "impact": "적층 수와 인터페이스 복잡도가 커질수록 패키징 공정의 수율·열·공정 안정성이 제품 경쟁력을 좌우한다는 점",
    },
    {
        "keys": ("dram", "3d 메모리", "3d memory"),
        "category": "DRAM",
        "impact": "미세화 한계 이후에는 구조 변화와 집적 방식 자체가 성능·수율·원가 경쟁력을 좌우한다는 점",
    },
    {
        "keys": ("nand", "ssd", "hbf"),
        "category": "NAND / Storage",
        "impact": "스토리지 수요 변화가 제품 구조·용량·성능 요구와 생산 전략까지 바꾼다는 점",
    },
    {
        "keys": ("양산", "생산", "제조", "수율", "공정"),
        "category": "Manufacturing",
        "impact": "기술 우위를 실제 제품 경쟁력으로 만들기 위해서는 공정 안정성·수율·생산성 확보가 필수라는 점",
    },
    {
        "keys": ("미래포럼", "사업 방향", "기술 방향", "전략"),
        "category": "Strategy",
        "impact": "회사가 어떤 기술을 우선순위에 두는지가 향후 투자·개발·양산 로드맵과 연결된다는 점",
    },
    {
        "keys": ("실적", "매출", "영업이익", "ir", "투자"),
        "category": "Business / IR",
        "impact": "실적과 투자 방향이 실제 시장 수요와 회사의 기술 우선순위를 동시에 보여준다는 점",
    },
    {
        "keys": ("ai", "ax", "인공지능", "에이전틱", "agentic"),
        "category": "AI / Infrastructure",
        "impact": "AI 워크로드 변화가 메모리의 역할과 요구 사양을 직접 바꾸고 있다는 점",
    },
]


def clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 뉴스룸 섹션 레이블은 내용이 아니므로 제거
    text = re.sub(
        r"^(?:PRESS|STORY|FACT|MEDIA)\s*[:|\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def trim(text: str, limit: int) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    return text[:limit - 3].rstrip(" ,.;:") + "..."


def is_junk(text: str) -> bool:
    raw = text or ""
    text = clean(raw)
    low = text.lower()

    # v8: 뉴스룸 이미지 캡션/페이지 레이블 제외
    if re.match(r"^(story|fact|press|media)\b", low):
        return True

    if (
        re.search(r"[▲△■●◆◇▶▷]", text)
        and (
            len(text) <= 220
            or "행사 현장" in text
        )
    ):
        return True

    if not text or low in {
        "source", "출처", "media", "press",
        "story", "fact", "ir"
    }:
        return True

    if re.search(
        r"</?[a-z][^>]*>",
        raw,
        flags=re.IGNORECASE,
    ):
        return True

    if (
        len(text) <= 180
        and re.match(r"^[▲△■●◆◇▶▷]", text)
    ):
        return True

    if (
        len(text) <= 120
        and any(
            word in low
            for word in ("출처", "사진", "이미지")
        )
    ):
        return True

    if any(
        word.lower() in low
        for word in BOILERPLATE_WORDS
    ):
        return True

    if "http://" in low or "https://" in low:
        return True

    return False


def sentences(text: str) -> list[str]:
    text = clean(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?。！？])\s+",
        text
    )

    result = []

    for part in parts:
        part = clean(
            part.strip(" •-\t")
        )

        # 지나치게 짧거나 긴 문장은 핵심 요약 후보에서 제외
        if len(part) < 30 or len(part) > 320:
            continue

        if is_junk(part):
            continue

        if part not in result:
            result.append(part)

    return result


def tokens(text: str) -> list[str]:
    words = re.findall(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9+\-]{1,}", text or "")
    return [
        word for word in words
        if word not in STOPWORDS
        and word.lower() not in STOPWORDS
        and len(word) >= 2
    ]


def count_signals(sentence: str, words: tuple[str, ...]) -> int:
    low = sentence.lower()
    return sum(1 for word in words if word.lower() in low)


def semantic_score(sentence: str) -> float:
    score = 0.0
    score += count_signals(sentence, CHANGE_WORDS) * 1.45
    score += count_signals(sentence, IMPORTANCE_WORDS) * 1.30
    score += count_signals(sentence, FUTURE_WORDS) * 0.85
    score += count_signals(sentence, TECH_WORDS) * 0.35

    if any(marker in sentence for marker in ("하면서", "따라", "때문", "이에", "따라서", "동시에", "넘어")):
        score += 1.15
    if re.search(r"\d", sentence):
        score += 0.25

    return score


def jaccard(a: str, b: str) -> float:
    aa = set(tokens(a))
    bb = set(tokens(b))
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def rewrite_point(sentence: str) -> str:
    text = clean(sentence)

    # 문장 앞의 불필요한 접속 표현 제거
    text = re.sub(
        r"^(한편|또한|아울러|특히|이날|이어|그러면서|그는|회사는)"
        r"\s*[,，]?\s*",
        "",
        text,
    )

    # 기사 문체의 발언 표기 제거
    text = re.sub(
        r"\s*[”\"'’]?\s*"
        r"(?:이라고|라고|고)\s*"
        r"(?:밝혔다|말했다|설명했다|강조했다|전했다|덧붙였다)"
        r"\.?\s*$",
        "",
        text,
    )

    text = text.strip(
        " \"'“”‘’"
    )

    # 핵심 원칙:
    # 긴 문장을 중간에서 자르지 않는다.
    # 너무 길다면 해당 문장은 핵심 후보에서 제외한다.
    if len(text) < 30 or len(text) > 220:
        return ""

    # 표시 시 마침표만 제거
    return text.rstrip(".")


def ranked_points(
    title: str,
    body: str,
    description: str
) -> list[tuple[float, str]]:

    source = (
        body
        if len(clean(body)) >= 120
        else description
    )

    pool = sentences(source)

    if not pool:
        return []

    freq = Counter(
        tokens(" ".join(pool))
    )

    title_words = set(
        tokens(title)
    )

    ranked = []

    for index, sentence in enumerate(pool):
        ws = tokens(sentence)

        if not ws:
            continue

        content_score = (
            sum(
                math.log1p(freq[w])
                for w in ws
            )
            / len(ws)
        )

        # 제목과 연결되는 내용은 중요도를 높임
        title_score = (
            len(
                title_words.intersection(ws)
            )
            * 0.60
        )

        # 기사 앞부분을 약간 우선
        position_score = max(
            0.0,
            0.30 - index * 0.007
        )

        score = (
            semantic_score(sentence)
            + content_score
            + title_score
            + position_score
        )

        point = rewrite_point(sentence)

        if (
            len(point) < 30
            or is_junk(point)
        ):
            continue

        # 읽기 좋은 길이의 완전한 문장 우선
        if 45 <= len(point) <= 155:
            score += 0.70
        elif len(point) <= 190:
            score += 0.30
        else:
            score -= 0.60

        # 행사성·의례성 표현은 핵심도 하향
        low = point.lower()

        if any(
            word in low
            for word in (
                "감사드린",
                "기념촬영",
                "행사 현장",
                "축사를",
                "환영사를",
            )
        ):
            score -= 1.20

        ranked.append(
            (score, point)
        )

    ranked.sort(
        reverse=True
    )

    deduped = []

    for score, point in ranked:

        if any(
            jaccard(
                point,
                existing
            ) > 0.52
            for _, existing in deduped
        ):
            continue

        deduped.append(
            (score, point)
        )

    return deduped


def extract_key_points(
    title: str,
    body: str,
    description: str,
    limit: int = 3
) -> list[str]:

    ranked = ranked_points(
        title,
        body,
        description
    )

    selected = []

    # 제목과 거의 같은 문장은 MAIN POINT와 중복되므로 제외
    for _, point in ranked:

        if jaccard(
            point,
            title
        ) > 0.72:
            continue

        if any(
            jaccard(
                point,
                existing
            ) > 0.52
            for existing in selected
        ):
            continue

        selected.append(point)

        if len(selected) >= limit:
            break

    # 제목과 비슷한 문장을 제외해서 너무 적어진 경우에는
    # 다음으로 좋은 완전한 문장을 보충
    if len(selected) < min(2, limit):

        for _, point in ranked:

            if point in selected:
                continue

            if any(
                jaccard(
                    point,
                    existing
                ) > 0.52
                for existing in selected
            ):
                continue

            selected.append(point)

            if len(selected) >= limit:
                break

    return selected[:limit]


def build_main_point(
    title: str,
    body: str,
    description: str,
    key_points: list[str]
) -> str:

    text = clean(title)

    # [미래인재 CLASS] 등 시리즈 표시는 요약 문장에서 제거
    text = re.sub(
        r"^\[[^\]]+\]\s*",
        "",
        text,
    )

    # 제목 뒤 뉴스룸 표기 제거
    text = re.sub(
        r"\s*[-–—]\s*SK하이닉스 뉴스룸\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = text.strip(
        " -–—,，:;.…"
    )

    # 제목 자체가 가장 안정적인 '무슨 기사인가' 설명
    if 15 <= len(text) <= 190:
        return text

    ranked = ranked_points(
        title,
        body,
        description
    )

    if ranked:
        return ranked[0][1]

    if key_points:
        return key_points[0]

    return text


def detect_topic(title: str, tags: list[str], body: str, key_points: list[str]) -> dict:
    title_text = title.lower()
    focus_text = f"{' '.join(tags)} {' '.join(key_points)}".lower()
    body_text = body[:3000].lower()

    best_topic = None
    best_score = 0.0

    for topic in TOPICS:
        score = 0.0
        for key in topic["keys"]:
            k = key.lower()
            if k in title_text:
                score += 4.0
            if k in focus_text:
                score += 2.2
            if k in body_text:
                score += 0.7

        if topic["category"] == "Manufacturing":
            direct = ("양산", "수율", "공정", "생산", "제조", "불량")
            score += sum(2.2 for word in direct if word in title_text)
            score += sum(1.2 for word in direct if word in focus_text)

        if score > best_score:
            best_score = score
            best_topic = topic

    if best_topic is not None:
        return best_topic

    return {
        "category": "Company / General",
        "impact": "회사가 중요하게 보는 이슈가 향후 기술·사업 우선순위를 판단하는 단서가 된다는 점",
    }


def build_why_it_matters(
    *,
    main_point: str,
    key_points: list[str],
    topic: dict
) -> str:

    # MAIN POINT / KEY POINTS를 반복하지 않고 의미만 전달
    impact = clean(
        topic.get(
            "impact",
            ""
        )
    )

    if impact:
        return (
            f"핵심 의미는 {impact}입니다."
        )

    return (
        "기사에서 나타난 변화가 "
        "SK하이닉스의 기술·사업 방향과 "
        "어떻게 연결되는지 확인할 필요가 있습니다."
    )


def build_role_takeaway(*, main_point: str, role_relevance: dict) -> str:
    role = role_relevance["role"]
    score = role_relevance["score"]
    dimensions = role_relevance.get("dimensions", [])
    lens = role_relevance.get("lens", ROLE_PROFILES[role]["lens"])
    dimension_text = "·".join(dimensions[:3]) if dimensions else "직접 연관 신호"

    if score >= 4:
        return (
            f"{role} 관점에서는 {dimension_text}가 핵심 연결점입니다. "
            f"'{trim(main_point, 88)}'이라는 내용을 {lens} 관점으로 연결하면 "
            f"직무 이해와 면접 답변의 근거로 활용할 수 있습니다."
        )

    if score == 3:
        return (
            f"{role} 실무와 중간 정도의 관련성이 있습니다. "
            f"{dimension_text}를 중심으로 '{trim(main_point, 82)}'이 "
            f"{lens}에 어떤 영향을 줄지 연결해서 보는 것이 핵심입니다."
        )

    return (
        f"{role} 직접 관련성은 낮은 편입니다. "
        f"다만 '{trim(main_point, 88)}'을 회사와 산업의 배경지식으로 이해해두면 좋습니다."
    )


def build_all_role_analysis(
    *,
    title: str,
    main_point: str,
    key_points: list[str],
    body: str,
    tags: list[str],
) -> dict:
    results = {}

    for role in list_roles():
        relevance = score_role_relevance(
            role,
            title=title,
            main_point=main_point,
            key_points=key_points,
            body=body,
            tags=tags,
        )
        relevance["what_you_get"] = build_role_takeaway(
            main_point=main_point,
            role_relevance=relevance,
        )
        results[role] = relevance

    return results


def refresh_saved_role_analysis(article: dict, body: str = "") -> dict:
    """
    기존 articles.json에 직무별 관련성을 추가한다.
    body가 전달되면 본문까지 사용하고, 없으면 저장된 핵심 정보만 사용한다.
    """
    role_analysis = build_all_role_analysis(
        title=article.get("title", ""),
        main_point=article.get("main_point") or article.get("one_liner", ""),
        key_points=article.get("key_points", []),
        body=body,
        tags=article.get("tags", []),
    )

    article["role_analysis"] = role_analysis
    default = role_analysis[DEFAULT_ROLE]

    # 이전 프론트엔드와의 호환성 유지
    article["job_relevance"] = {
        k: v for k, v in default.items() if k != "what_you_get"
    }
    article["takeaway"] = default["what_you_get"]
    article["importance"] = default["score"]

    return article


def analyze_article(title: str, description: str, body: str, tags: list[str]) -> dict:
    key_points = extract_key_points(title, body, description, 3)
    main_point = build_main_point(title, body, description, key_points)
    topic = detect_topic(title, tags, body, key_points)

    why_it_matters = build_why_it_matters(
        main_point=main_point,
        key_points=key_points,
        topic=topic,
    )

    role_analysis = build_all_role_analysis(
        title=title,
        main_point=main_point,
        key_points=key_points,
        body=body,
        tags=tags,
    )

    default = role_analysis[DEFAULT_ROLE]

    return {
        "main_point": main_point,
        "key_points": key_points,
        "category": topic["category"],
        "why_it_matters": why_it_matters,
        "role_analysis": role_analysis,

        # 기본값은 양산기술. 화면에서 직무를 바꾸면 role_analysis를 사용함.
        "takeaway": default["what_you_get"],
        "job_relevance": {k: v for k, v in default.items() if k != "what_you_get"},

        # old frontend compatibility
        "one_liner": main_point,
        "importance": default["score"],
    }

# === V11 SUMMARY OVERRIDE ===

def _v11_clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    text = re.sub(
        r"^(?:(?:PRESS|STORY|FACT|MEDIA)\s*)+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def _v11_split_sentences(text: str) -> list[str]:
    text = _v11_clean_text(text)

    if not text:
        return []

    text = re.sub(
        r'([.!?])[”"]\s+',
        r"\1\n",
        text
    )

    text = re.sub(
        r"([.!?])\s+",
        r"\1\n",
        text
    )

    out = []

    for part in text.splitlines():
        part = _v11_clean_text(part).strip(" -•")

        if 35 <= len(part) <= 220 and part not in out:
            out.append(part)

    return out


def _v11_key_points(
    title: str,
    body: str,
    description: str,
    limit: int = 3
) -> list[str]:

    source = (
        body
        if len(_v11_clean_text(body)) >= 120
        else description
    )

    source = _v11_clean_text(source)
    clean_title = _v11_clean_text(title)

    for _ in range(2):

        source = re.sub(
            r"^(?:(?:PRESS|STORY|FACT|MEDIA)\s*)+",
            "",
            source,
            flags=re.IGNORECASE,
        ).strip()

        if (
            clean_title
            and source.startswith(clean_title)
        ):
            source = source[
                len(clean_title):
            ].strip()

    candidates = []

    title_words = set(
        tokens(clean_title)
    )

    action_words = (
        "추진", "투자", "확대", "개발",
        "양산", "생산", "구축", "지원",
        "공급", "수요", "건설", "확보",
        "계획", "목표", "출시", "성장",
        "증가", "절감", "개선", "전환"
    )

    for idx, sentence in enumerate(
        _v11_split_sentences(source)
    ):

        low = sentence.lower()

        if any(
            x in low
            for x in (
                "copyright",
                "무단전재",
                "재배포",
                "관련기사",
                "구독하기"
            )
        ):
            continue

        if "http://" in low or "https://" in low:
            continue

        if re.search(
            r"[▲△■●◆◇▶▷]",
            sentence
        ):
            continue

        if any(
            x in sentence
            for x in (
                "행사 현장",
                "기념촬영",
                "환영사",
                "축사"
            )
        ):
            continue

        words = set(
            tokens(sentence)
        )

        overlap = (
            len(title_words & words)
            * 0.45
        )

        action = sum(
            0.35
            for word in action_words
            if word in sentence
        )

        position = max(
            0.0,
            0.5 - idx * 0.02
        )

        length_bonus = (
            0.6
            if 45 <= len(sentence) <= 145
            else 0.2
        )

        quote_penalty = (
            1.8
            if any(
                x in sentence
                for x in (
                    "“", "”",
                    "라며", "이라며",
                    "말했다", "밝혔다"
                )
            )
            else 0.0
        )

        ceremony_penalty = (
            2.0
            if any(
                x in sentence
                for x in (
                    "감사드린다",
                    "특별시민을 대표"
                )
            )
            else 0.0
        )

        score = (
            semantic_score(sentence)
            + overlap
            + action
            + position
            + length_bonus
            - quote_penalty
            - ceremony_penalty
        )

        candidates.append(
            (
                score,
                sentence.rstrip(".")
            )
        )

    candidates.sort(
        reverse=True
    )

    selected = []

    for quoted_allowed in (
        False,
        True
    ):

        for _, point in candidates:

            if point in selected:
                continue

            if jaccard(
                point,
                clean_title
            ) > 0.62:
                continue

            if (
                not quoted_allowed
                and any(
                    x in point
                    for x in (
                        "“", "”",
                        "라며", "이라며",
                        "말했다", "밝혔다"
                    )
                )
            ):
                continue

            if any(
                jaccard(
                    point,
                    old
                ) > 0.50
                for old in selected
            ):
                continue

            selected.append(point)

            if len(selected) >= limit:
                return selected

    return selected[:limit]


def analyze_article(
    title: str,
    description: str,
    body: str,
    tags: list[str]
) -> dict:

    main_point = _v11_clean_text(
        title
    )

    main_point = re.sub(
        r"^\[[^\]]+\]\s*",
        "",
        main_point
    )

    main_point = re.sub(
        r"\s*[-–—]\s*SK하이닉스 뉴스룸\s*$",
        "",
        main_point,
        flags=re.IGNORECASE,
    ).strip()

    key_points = _v11_key_points(
        title,
        body,
        description,
        3
    )

    topic = detect_topic(
        title,
        tags,
        body,
        key_points
    )

    impact = _v11_clean_text(
        topic.get(
            "impact",
            ""
        )
    )

    why_it_matters = (
        f"이 기사의 핵심 의미는 {impact}입니다."
        if impact
        else
        "이 기사는 SK하이닉스의 기술·사업 방향을 이해하는 데 의미가 있습니다."
    )

    role_analysis = build_all_role_analysis(
        title=title,
        main_point=main_point,
        key_points=key_points,
        body=body,
        tags=tags,
    )

    default = role_analysis[
        DEFAULT_ROLE
    ]

    return {
        "main_point": main_point,
        "key_points": key_points,
        "category": topic["category"],
        "why_it_matters": why_it_matters,
        "role_analysis": role_analysis,
        "takeaway": default["what_you_get"],
        "job_relevance": {
            k: v
            for k, v in default.items()
            if k != "what_you_get"
        },
        "one_liner": main_point,
        "importance": default["score"],
    }

# === V12 SUMMARY OVERRIDE ===

_V12_BUCKETS = {
    "market": (
        "AI", "ai", "수요", "시장", "성장", "경쟁",
        "고객", "주문", "판매"
    ),
    "investment": (
        "투자", "클러스터", "공장", "생산", "양산",
        "구축", "추진", "건설", "증설", "생산거점"
    ),
    "infra": (
        "부지", "전력", "용수", "기반시설",
        "인프라", "지자체", "지원"
    ),
    "technology": (
        "HBM", "DRAM", "NAND", "패키징",
        "공정", "수율", "기술", "제품",
        "MR-MUF", "TSV", "본딩"
    ),
    "performance": (
        "매출", "영업이익", "실적", "점유율",
        "절감", "효율", "생산성"
    ),
}


def _v12_clean(text: str) -> str:
    text = clean(text)

    text = re.sub(
        r"^(이에 따라|한편|또한|아울러|특히|이날|이어)\s*[,，]?\s*",
        "",
        text
    )

    return text.strip()


def _v12_split(text: str) -> list[str]:
    text = _v12_clean(text)

    if not text:
        return []

    text = re.sub(
        r'([.!?][”]?)\s+',
        r"\1\n",
        text
    )

    out = []

    for part in text.splitlines():
        part = _v12_clean(part)

        if 30 <= len(part) <= 240:
            if part not in out and not is_junk(part):
                out.append(part)

    return out


def _v12_quote_fact(text: str) -> str:
    text = _v12_clean(text)

    quotes = re.findall(
        r"“([^”]{20,220})”",
        text
    )

    if not quotes:
        return text.rstrip(".")

    signals = (
        "AI", "수요", "시장", "성장", "투자",
        "생산", "양산", "공장", "클러스터",
        "부지", "전력", "용수", "기반시설",
        "공정", "수율", "HBM", "패키징"
    )

    def qscore(q):
        score = sum(
            1
            for word in signals
            if word.lower() in q.lower()
        )

        if "감사드린" in q:
            score -= 4

        return score

    best = max(
        quotes,
        key=qscore
    )

    if qscore(best) >= 1:
        return _v12_clean(best).rstrip(".")

    return text.rstrip(".")


def _v12_bucket(text: str) -> str:
    low = text.lower()

    best_name = "general"
    best_score = 0

    for name, words in _V12_BUCKETS.items():
        score = sum(
            1
            for word in words
            if word.lower() in low
        )

        if score > best_score:
            best_score = score
            best_name = name

    return best_name


def _v12_key_points(
    title: str,
    body: str,
    description: str,
    limit: int = 3
) -> list[str]:

    source = (
        body
        if len(_v12_clean(body)) >= 120
        else description
    )

    source = _v12_clean(source)
    clean_title = _v12_clean(title)

    for _ in range(2):
        if (
            clean_title
            and source.startswith(clean_title)
        ):
            source = source[
                len(clean_title):
            ].strip()

    title_words = set(
        tokens(clean_title)
    )

    candidates = []

    for index, raw in enumerate(
        _v12_split(source)
    ):
        point = _v12_quote_fact(raw)
        point = _v12_clean(point)

        if not (
            30 <= len(point) <= 200
        ):
            continue

        if any(
            word in point
            for word in (
                "기념촬영",
                "행사 현장",
                "환영사",
                "축사"
            )
        ):
            continue

        words = set(
            tokens(point)
        )

        score = semantic_score(point)

        score += (
            len(title_words & words)
            * 0.35
        )

        score += max(
            0.0,
            0.35 - index * 0.01
        )

        bucket = _v12_bucket(point)

        if bucket != "general":
            score += 1.2

        if 45 <= len(point) <= 145:
            score += 0.7

        # 단순 현장 방문·동선 설명은 중요도 하향
        if any(
            word in point
            for word in (
                "직접 찾아",
                "현장을 찾아",
                "살폈다",
                "방문했다",
                "일대를 직접"
            )
        ):
            score -= 2.5

        # 실질적인 사업·기술 정보 우대
        if any(
            word in point
            for word in (
                "투자", "수요", "생산", "양산",
                "공장", "전력", "용수", "수율",
                "공급", "구축", "확대"
            )
        ):
            score += 1.0

        candidates.append(
            (
                score,
                bucket,
                point
            )
        )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    selected = []
    used_buckets = set()

    # 먼저 서로 다른 종류의 핵심정보를 하나씩 선택
    for score, bucket, point in candidates:

        if bucket == "general":
            continue

        if bucket in used_buckets:
            continue

        if any(
            jaccard(point, old) > 0.48
            for old in selected
        ):
            continue

        selected.append(point)
        used_buckets.add(bucket)

        if len(selected) >= limit:
            return selected

    # 부족하면 남은 높은 점수 문장으로 보충
    for score, bucket, point in candidates:

        if point in selected:
            continue

        if any(
            jaccard(point, old) > 0.48
            for old in selected
        ):
            continue

        selected.append(point)

        if len(selected) >= limit:
            break

    return selected[:limit]


def _v12_why(
    title: str,
    points: list[str]
) -> str:

    text = (
        title
        + " "
        + " ".join(points)
    )

    low = text.lower()

    ai_signal = (
        "ai" in low
        or "메모리 수요" in text
    )

    investment_signal = any(
        word in text
        for word in (
            "투자", "클러스터", "공장",
            "생산", "양산", "증설"
        )
    )

    infra_signal = any(
        word in text
        for word in (
            "전력", "용수", "부지",
            "기반시설", "인프라"
        )
    )

    if ai_signal and investment_signal:
        return (
            "AI 메모리 수요 확대가 실제 생산거점 투자와 "
            "공급 역량 확대 전략으로 이어지고 있다는 점이 핵심입니다."
        )

    if investment_signal and infra_signal:
        return (
            "반도체 생산거점 확대가 부지·전력·용수 등 "
            "필수 인프라 확보와 함께 실제 실행 단계로 "
            "넘어가고 있다는 점이 핵심입니다."
        )

    if investment_signal:
        return (
            "회사의 중장기 전략이 실제 투자·생산 확대 계획으로 "
            "구체화되고 있다는 점이 핵심입니다."
        )

    return (
        "이 기사가 보여주는 변화가 SK하이닉스의 "
        "기술·사업 방향에 어떤 영향을 주는지가 핵심입니다."
    )


def analyze_article(
    title: str,
    description: str,
    body: str,
    tags: list[str]
) -> dict:

    key_points = _v12_key_points(
        title,
        body,
        description,
        3
    )

    clean_title = _v12_clean(title)

    # 제목 복사 대신 가장 핵심적인 사실을 MAIN으로 사용
    main_point = (
        key_points[0]
        if key_points
        else clean_title
    )

    topic = detect_topic(
        title,
        tags,
        body,
        key_points
    )

    joined = (
        title
        + " "
        + " ".join(key_points)
    )

    if (
        any(
            word in joined
            for word in (
                "투자",
                "클러스터",
                "생산거점",
                "공장"
            )
        )
        and any(
            word in joined
            for word in (
                "생산",
                "공장",
                "클러스터",
                "부지",
                "전력",
                "용수"
            )
        )
    ):
        category = (
            "Investment / Manufacturing Strategy"
        )
    else:
        category = topic["category"]

    why_it_matters = _v12_why(
        title,
        key_points
    )

    role_analysis = build_all_role_analysis(
        title=title,
        main_point=main_point,
        key_points=key_points,
        body=body,
        tags=tags,
    )

    default = role_analysis[
        DEFAULT_ROLE
    ]

    return {
        "main_point": main_point,
        "key_points": key_points,
        "category": category,
        "why_it_matters": why_it_matters,
        "role_analysis": role_analysis,
        "takeaway": default["what_you_get"],
        "job_relevance": {
            k: v
            for k, v in default.items()
            if k != "what_you_get"
        },
        "one_liner": main_point,
        "importance": default["score"],
    }

