from __future__ import annotations

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
    return re.sub(r"\s+", " ", text or "").strip()


def trim(text: str, limit: int) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    return text[:limit - 3].rstrip(" ,.;:") + "..."


def is_junk(text: str) -> bool:
    text = clean(text)
    low = text.lower()

    if not text or low in {"source", "출처", "media", "press", "story", "fact", "ir"}:
        return True
    if any(word.lower() in low for word in BOILERPLATE_WORDS):
        return True
    if "http://" in low or "https://" in low:
        return True
    return False


def sentences(text: str) -> list[str]:
    text = clean(text)
    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", text)
    result = []

    for part in parts:
        part = clean(part.strip(" •-\t"))
        if len(part) < 28 or len(part) > 380:
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
    text = re.sub(
        r"^(한편|또한|아울러|특히|이날|이어|그러면서|그는|회사는)\s*[,，]?\s*",
        "",
        text,
    )
    text = re.sub(
        r"\s*(?:라고|고)\s*(?:밝혔다|말했다|설명했다|강조했다|전했다|덧붙였다)\.?\s*$",
        "",
        text,
    )
    text = text.strip(" \"'“”‘’")
    text = trim(text, 150)
    if text.endswith("."):
        text = text[:-1]
    return text


def ranked_points(title: str, body: str, description: str) -> list[tuple[float, str]]:
    source = body if len(clean(body)) >= 120 else description
    pool = sentences(source)
    if not pool:
        return []

    freq = Counter(tokens(" ".join(pool)))
    title_words = set(tokens(title))
    ranked = []

    for index, sentence in enumerate(pool):
        ws = tokens(sentence)
        if not ws:
            continue

        content_score = sum(math.log1p(freq[w]) for w in ws) / len(ws)
        title_score = len(title_words.intersection(ws)) * 0.48
        position_score = max(0.0, 0.30 - index * 0.007)
        score = semantic_score(sentence) + content_score + title_score + position_score

        point = rewrite_point(sentence)
        if len(point) < 25 or is_junk(point):
            continue

        ranked.append((score, point))

    ranked.sort(reverse=True)

    deduped = []
    for score, point in ranked:
        if any(jaccard(point, existing) > 0.62 for _, existing in deduped):
            continue
        deduped.append((score, point))

    return deduped


def extract_key_points(title: str, body: str, description: str, limit: int = 3) -> list[str]:
    return [point for _, point in ranked_points(title, body, description)[:limit]]


def build_main_point(title: str, body: str, description: str, key_points: list[str]) -> str:
    ranked = ranked_points(title, body, description)
    if ranked:
        return trim(ranked[0][1], 125)
    if key_points:
        return trim(key_points[0], 125)
    return trim(title, 125)


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


def build_why_it_matters(*, main_point: str, key_points: list[str], topic: dict) -> str:
    second = next((point for point in key_points if point != main_point), "")

    if second:
        return (
            f"{main_point}. "
            f"또한 {trim(second, 115)}. "
            f"이 두 변화는 {topic['impact']}에서 중요합니다."
        )

    return f"{main_point}. 이 변화는 {topic['impact']}에서 중요합니다."


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
