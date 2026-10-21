from __future__ import annotations

import json
import os
import re

import requests


OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:4b"
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://127.0.0.1:11434/api/generate"
)


class OllamaAnalysisError(RuntimeError):
    pass


def clean_text(text: str) -> str:
    text = str(text or "")

    text = re.sub(
        r"\[(?:음악|웃음|박수)\]",
        " ",
        text
    )

    text = text.replace(">>", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    text = re.sub(
        r"SK하이닉(?:스)?",
        "SK하이닉스",
        text
    )

    replacements = {
        "SK하닉스": "SK하이닉스",
        "출화": "출하",
        "분량": "불량",
        "고객 추락": "고객 출하",
        "양선": "양산",
        "손질": "품질",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def call_ollama(
    prompt: str,
    *,
    num_ctx: int = 8192,
    num_predict: int = 1200,
    timeout: int = 300,
) -> dict:

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "think": False,
                "options": {
                    "temperature": 0.0,
                    "num_ctx": num_ctx,
                    "num_predict": num_predict,
                    "repeat_penalty": 1.10,
                },
            },
            timeout=(5, timeout),
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise OllamaAnalysisError(
            f"Ollama 연결 실패: {exc}"
        ) from exc

    try:
        raw = response.json().get(
            "response",
            ""
        )
    except Exception as exc:
        raise OllamaAnalysisError(
            "Ollama 응답을 읽지 못했습니다."
        ) from exc

    start = raw.find("{")
    end = raw.rfind("}")

    if start < 0 or end < start:
        raise OllamaAnalysisError(
            "AI 응답에서 JSON을 찾지 못했습니다."
        )

    try:
        return json.loads(
            raw[start:end + 1]
        )
    except json.JSONDecodeError as exc:
        raise OllamaAnalysisError(
            f"AI JSON 해석 실패: {exc}"
        ) from exc


def split_source(
    text: str,
    target_size: int = 2600,
) -> list[str]:

    text = clean_text(text)

    if len(text) <= target_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = min(
            len(text),
            start + target_size
        )

        # 가능한 경우 단어 중간에서 자르지 않음
        if end < len(text):
            space = text.rfind(
                " ",
                start,
                end
            )

            if space > start + 1500:
                end = space

        chunk = text[
            start:end
        ].strip()

        if chunk:
            chunks.append(chunk)

        start = end

    return chunks



def extract_facts_from_chunk(
    chunk: str,
    index: int,
    total: int,
    title: str = "",
    description: str = "",
) -> list[str]:

    first_chunk_rule = """
이번 구간은 첫 번째 구간이다.

제목이나 설명에 다음 내용이 있으면
반드시 최소 1개의 FACT로 보존한다.

- 이 기사의 핵심 사건
- 행사/발표/협약/프로젝트의 목적
- 누구를 대상으로 하는지
- 왜 이 일을 했는지

단, 제목이나 설명에 실제로 적힌 내용만 사용한다.
""" if index == 1 else """
이번 구간에서는 앞부분에서 이미 다뤘을 가능성이 높은
일반적인 행사 소개보다 새로운 구체 사실을 우선한다.
"""

    prompt = f"""
너는 SK하이닉스 뉴스룸 콘텐츠에서
독자가 기사 전체를 이해하는 데 필요한
구체적 사실만 추출하는 분석기다.

전체 원문의 {index}/{total} 구간이다.

[기사 제목]
{title}

[기사 설명]
{description}

{first_chunk_rule}

최대 8개의 중요한 FACT를 추출한다.

[우선순위]

1. 기사에서 실제로 무엇이 일어났는지
2. 행사·발표·협약·기술개발 등의 목적
3. 대상 또는 주요 참여 주체
4. 핵심 기술·제품·조직
5. 실제 업무·공정·운영 방식
6. 구체적인 숫자·성능·규모·날짜
7. 평가·검증·판정 방법
8. 고객·양산·협력사·사업과 직접 관련된 의미
9. 직무에 필요한 구체적인 역량
10. 반도체 지식을 이해하는 데 도움이 되는 구체 사례

[중요한 구분]

기사 유형에 따라 중요한 사실은 다르다.

기술 기사:
- 기술명
- 제품
- 성능
- 공정
- 평가방법
- 고객 활용

행사/조직문화 기사:
- 무엇을 개최했는지
- 왜 개최했는지
- 누구를 초청했는지
- 규모
- 대표적인 프로그램
- 회사와 구성원/협력사의 관계에서 어떤 의미인지

협력/사업 기사:
- 누구와 무엇을 협력하는지
- 목적
- 구체적인 협력 범위
- 기술 또는 제품
- 고객/시장과의 관계

[절대 규칙]

- 제목, 설명, 원문에 있는 내용만 사용한다.
- 일반 상식을 추가하지 않는다.
- 결과나 효과를 추측하지 않는다.
- 사람 이름 자체는 중요한 사실로 뽑지 않는다.
- 사람보다 그 사람이 수행한 행동이나 역할을 중심으로 쓴다.
- 인사말, 농담, 장면 묘사만 있는 내용은 우선순위를 낮춘다.
- 행사 장식, 음식, 풍경 같은 주변 묘사는
  기사 핵심을 이해하는 데 필요하지 않으면 제외한다.
- 서로 다른 사실을 억지로 하나로 합치지 않는다.
- 기술, 제도, 조직, 평가방법의 주체를 반드시 보존한다.
- 어떤 판정 기준이나 숫자가 특정 기술 설명에서 나온 경우
  그 기술명을 생략하거나 다른 제도에 붙이지 않는다.
- 서로 다른 제도나 기법의 속성을 서로 섞지 않는다.
- 예를 들어 SPC의 통계 판정 규칙을
  PCCB나 일반적인 공정 변경 평가 규칙으로 바꾸지 않는다.
- PCCB와 SPC처럼 원문에서 별도로 설명되는 개념은
  각각 독립적인 FACT로 유지한다.
- 숫자와 기술 용어는 가능한 한 보존한다.
- 약어의 영문 풀네임을 추측하지 않는다.

[현재 원문 구간]
{chunk}

JSON만 출력한다.

{{
  "facts": [
    "구체적인 사실 1",
    "구체적인 사실 2"
  ]
}}
"""

    data = call_ollama(
        prompt,
        num_ctx=8192,
        num_predict=1100,
    )

    raw_facts = data.get(
        "facts",
        []
    )

    if not isinstance(raw_facts, list):
        return []

    result = []

    for fact in raw_facts:

        fact = clean_text(fact)

        if len(fact) < 15:
            continue

        if fact not in result:
            result.append(fact)

    return result[:8]



def extract_supplemental_facts(
    source: str,
    title: str,
    description: str,
    existing_facts: list[str],
) -> list[str]:

    existing_text = "\n".join(
        f"- {x}"
        for x in existing_facts
    )

    prompt = f"""
너는 SK하이닉스 뉴스룸 기사에서
이미 추출된 FACT에 없는 추가 핵심 정보를 찾는 분석기다.

[기사 제목]
{title}

[기사 설명]
{description}

[이미 추출된 FACT]
{existing_text}

[전체 원문]
{source}

이미 추출된 FACT와 중복되지 않는
추가 FACT를 최대 6개 추출한다.

우선순위:
1. 대표적인 프로그램이나 실제 활동
2. 구체적인 숫자, 규모, 날짜
3. 기술·제품·공정 관련 설명
4. 참석자가 실제로 체험한 내용
5. 고객·협력사·구성원과 직접 관련된 내용
6. 기사 전체를 이해하는 데 도움이 되는 구체 사례

행사 기사라면:
- 행사 목적
- 대상과 규모
- 대표 프로그램
- 체험 콘텐츠
- 회사와 참석자의 관계를 보여주는 구체적 활동

기술 기사라면:
- 기술명
- 제품
- 성능
- 실제 구현 방식
- 평가 방법
- 고객 활용

절대 규칙:
- 제목, 설명, 원문에 있는 사실만 사용한다.
- 이미 추출된 FACT를 표현만 바꿔 반복하지 않는다.
- 결과나 효과를 추측하지 않는다.
- 사람 이름 자체는 우선하지 않는다.
- 불꽃놀이, 음식, 장식, 풍경 같은 단순 묘사는
  더 중요한 FACT가 있을 경우 제외한다.
- 숫자와 기술 용어는 보존한다.
- 서로 다른 사실을 억지로 합치지 않는다.

JSON만 출력한다.

{{
  "facts": [
    "추가 FACT 1",
    "추가 FACT 2"
  ]
}}
"""

    data = call_ollama(
        prompt,
        num_ctx=8192,
        num_predict=900,
    )

    raw = data.get(
        "facts",
        []
    )

    if not isinstance(raw, list):
        return []

    result = []

    for fact in raw:

        fact = clean_text(fact)

        if len(fact) < 15:
            continue

        if fact in existing_facts:
            continue

        if fact not in result:
            result.append(fact)

    return result[:6]


def collect_facts(
    source: str,
    title: str = "",
    description: str = "",
) -> list[str]:

    chunks = split_source(
        source
    )

    collected = []

    for i, chunk in enumerate(
        chunks,
        1
    ):

        print(
            f"  -> AI 사실 추출 "
            f"{i}/{len(chunks)}"
        )

        facts = extract_facts_from_chunk(
            chunk,
            i,
            len(chunks),
            title,
            description,
        )

        for fact in facts:

            if fact not in collected:
                collected.append(fact)

    # 너무 적게 추출됐을 때만 전체 원문으로 보충
    if len(collected) < 6:

        print(
            f"  -> FACT 부족({len(collected)}개), "
            "보충 추출 실행"
        )

        supplemental = (
            extract_supplemental_facts(
                source,
                title,
                description,
                collected,
            )
        )

        for fact in supplemental:

            if fact not in collected:
                collected.append(fact)

    return collected


def sanitize_fact(
    fact: str
) -> str:

    fact = clean_text(fact)

    fact = fact.replace(
        "공전 변경",
        "공정 변경"
    )

    # AI가 임의로 붙인 영문 약어 풀네임 제거.
    # SPC처럼 원문에서 설명된 경우도 최종 KEY에는
    # 약어 자체만 있어도 충분하다.
    fact = re.sub(
        r"\b([A-Z]{2,})\s*\([A-Za-z][A-Za-z\s\-\/&]+\)",
        r"\1",
        fact
    )

    return clean_text(fact)



def fact_specificity_score(
    fact: str
) -> float:

    score = 0.0

    if re.search(r"\d", fact):
        score += 4.0

    if len(fact) >= 35:
        score += 1.0

    if len(fact) >= 60:
        score += 1.0

    for word in (
        "분석",
        "평가",
        "검증",
        "적용",
        "개발",
        "생산",
        "양산",
        "관리",
        "판정",
        "테스트",
        "공급",
        "구축",
        "도입",
        "공개",
        "출시",
        "협력",
        "제조",
        "설계",
    ):
        if word in fact:
            score += 0.6

    for bad in (
        "근무하는",
        "엠버서더",
        "본인 소개",
        "MC를 맡",
        "대학생",
    ):
        if bad in fact:
            score -= 10.0

    return score


def keyword_score(
    fact: str,
    keywords: dict[str, float]
) -> float:

    low = fact.lower()
    score = 0.0

    for keyword, weight in keywords.items():
        if keyword.lower() in low:
            score += weight

    return score


def token_overlap(
    a: str,
    b: str
) -> float:

    ta = set(
        re.findall(
            r"[0-9A-Za-z가-힣]+",
            a.lower()
        )
    )

    tb = set(
        re.findall(
            r"[0-9A-Za-z가-힣]+",
            b.lower()
        )
    )

    if not ta or not tb:
        return 0.0

    return len(ta & tb) / len(ta | tb)


def select_for_slot(
    facts: list[str],
    keywords: dict[str, float],
    used: set[int],
    *,
    require_number: bool = False,
) -> int | None:

    candidates = []

    for i, fact in enumerate(facts):

        if i in used:
            continue

        if (
            require_number
            and not re.search(r"\d", fact)
        ):
            continue

        kscore = keyword_score(
            fact,
            keywords
        )

        if (
            not require_number
            and kscore <= 0
        ):
            continue

        score = (
            kscore
            + fact_specificity_score(fact)
        )

        for selected_index in used:

            if token_overlap(
                fact,
                facts[selected_index]
            ) >= 0.55:
                score -= 8.0

        candidates.append(
            (score, i)
        )

    if not candidates:
        return None

    candidates.sort(
        reverse=True
    )

    return candidates[0][1]


def select_key_facts(
    facts: list[str],
) -> list[str]:

    facts = [
        sanitize_fact(f)
        for f in facts
    ]

    core_keywords = {
        "발표": 8,
        "공개": 8,
        "출시": 8,
        "개발": 6,
        "개최": 7,
        "체결": 8,
        "협력": 6,
        "공급": 7,
        "생산": 5,
        "양산": 6,
        "구축": 6,
        "도입": 6,
        "확대": 5,
        "전환": 5,
        "목표": 4,
        "역할": 5,
        "업무": 5,
        "리스크": 4,
    }

    technology_keywords = {
        "HBM": 10,
        "DRAM": 9,
        "LPDDR": 9,
        "NAND": 9,
        "SSD": 9,
        "CXL": 9,
        "AI": 6,
        "메모리": 6,
        "반도체": 4,
        "제품": 5,
        "기술": 7,
        "솔루션": 6,
        "시스템": 5,
        "공정": 5,
        "패키징": 7,
        "패키지": 6,
        "SPC": 10,
        "PCCB": 10,
        "리플로우": 9,
        "서버": 5,
        "데이터센터": 5,
    }

    process_keywords = {
        "공정": 7,
        "프로세스": 7,
        "방식": 6,
        "방법": 6,
        "적용": 6,
        "활용": 6,
        "관리": 6,
        "분석": 6,
        "평가": 6,
        "검증": 6,
        "판정": 6,
        "테스트": 6,
        "제조": 5,
        "설계": 5,
        "운영": 5,
        "제어": 5,
        "양산": 5,
        "협의체": 5,
    }

    impact_keywords = {
        "고객": 7,
        "수율": 7,
        "성능": 7,
        "전력": 6,
        "비용": 6,
        "생산성": 7,
        "신뢰성": 7,
        "리스크": 7,
        "공급망": 7,
        "협력사": 7,
        "시장": 5,
        "효율": 5,
        "품질": 6,
        "직무": 5,
        "역량": 5,
        "소통": 5,
        "설득": 5,
        "생태계": 5,
    }

    selected = []
    used = set()

    slots = (
        (core_keywords, False),
        (technology_keywords, False),
        (process_keywords, False),
        ({}, True),
        (impact_keywords, False),
    )

    for keywords, require_number in slots:

        index = select_for_slot(
            facts,
            keywords,
            used,
            require_number=require_number,
        )

        if index is not None:
            selected.append(index)
            used.add(index)

    while len(selected) < 5:

        candidates = []

        for i, fact in enumerate(facts):

            if i in used:
                continue

            score = fact_specificity_score(
                fact
            )

            for selected_index in used:

                if token_overlap(
                    fact,
                    facts[selected_index]
                ) >= 0.55:
                    score -= 8.0

            candidates.append(
                (score, i)
            )

        if not candidates:
            break

        candidates.sort(
            reverse=True
        )

        index = candidates[0][1]

        selected.append(index)
        used.add(index)

    if len(selected) != 5:
        raise OllamaAnalysisError(
            "핵심 FACT 5개를 선택하지 못했습니다."
        )

    return [
        facts[i]
        for i in selected
    ]



def category_override(
    title: str,
    tags: list[str],
) -> str:

    text = (
        title
        + " "
        + " ".join(tags or [])
    ).lower()

    if any(
        x in text
        for x in (
            "품질보증",
            "품질 보증",
            "신뢰성",
            "reliability",
            "quality",
        )
    ):
        return "Quality / Reliability"

    # CXL / 서버 / OCP 계열은
    # 단순 AI/HBM 태그보다 우선
    if any(
        x in text
        for x in (
            "cxl",
            "ocp",
            "ai 인프라",
            "ai infrastructure",
            "메모리 중심 서버",
            "메모리 중심 ai",
            "랙 시스템",
            "rack system",
            "메모리 풀링",
        )
    ):
        return "AI Infrastructure / CXL"

    if any(
        x in text
        for x in (
            "thanksfull",
            "파트너스데이",
            "협력사",
            "동반성장",
            "공급망",
            "상생",
        )
    ):
        return "Supply Chain / Partnership"

    if any(
        x in text
        for x in (
            "hbm",
            "고대역폭메모리",
            "ai 메모리",
        )
    ):
        return "HBM / AI Memory"

    if any(
        x in text
        for x in (
            "nand",
            "ssd",
            "fenand",
        )
    ):
        return "NAND / Storage"

    return "Company / General"



def strip_fact_label(
    text: str
) -> str:

    text = clean_text(text)

    text = re.sub(
        r"^[^:]{1,30}:\s*",
        "",
        text
    )

    return clean_text(text)


def ensure_period(
    text: str
) -> str:

    text = clean_text(text)

    if not text:
        return ""

    if text[-1] not in ".!?。":
        text += "."

    return text


def select_main_facts(
    key_points: list[str],
) -> list[str]:

    if len(key_points) < 2:
        return key_points

    event_words = (
        "개최",
        "발표",
        "공개",
        "출시",
        "체결",
        "협약",
        "도입",
        "공급",
    )

    first_index = None

    for i, fact in enumerate(
        key_points
    ):

        if any(
            word in fact
            for word in event_words
        ):
            first_index = i
            break

    # 명확한 사건 FACT가 없으면
    # 기존 구조대로 1번 + 3번 사용
    if first_index is None:

        second_index = (
            2
            if len(key_points) >= 3
            else 1
        )

        return [
            key_points[0],
            key_points[second_index],
        ]

    # 세 번째 KEY가 다른 FACT라면
    # 두 번째 MAIN FACT로 우선 사용.
    # ThanksFULL: 개최 + 3만 명
    # OCP: 제품 공개 + 협력/활용
    preferred = (
        2
        if len(key_points) >= 3
        else 0
    )

    if preferred == first_index:
        preferred = 0

    if preferred == first_index:
        preferred = 1

    return [
        key_points[first_index],
        key_points[preferred],
    ]


def why_fact_score(
    fact: str
) -> float:

    low = fact.lower()
    score = 0.0

    weighted = {
        "리스크": 10,
        "병목": 10,
        "해소": 9,
        "트레이드오프": 9,
        "감사": 9,
        "효율": 8,
        "개선": 8,
        "수율": 8,
        "신뢰성": 8,
        "절감": 8,
        "성능": 7,
        "대역폭": 7,
        "생산성": 7,
        "고객": 6,
        "협력사": 6,
        "전력": 6,
        "비용": 6,
        "협력": 5,
        "활용": 5,
        "체험": 5,
        "품질": 5,
        "용량": 3,
    }

    for word, weight in weighted.items():

        if word in low:
            score += weight

    if re.search(
        r"\d",
        fact
    ):
        score += 2.0

    # 제품명이 너무 많이 나열된 FACT는
    # WHY보다는 KEY POINT에 더 적합
    product_count = len(
        re.findall(
            r"\b[A-Z]{2,}[A-Z0-9._-]*\b",
            fact
        )
    )

    if product_count >= 4:
        score -= 8.0

    for word in (
        "불꽃놀이",
        "푸드트럭",
        "파라솔",
        "의자",
        "선물 세트",
    ):
        if word in fact:
            score -= 8.0

    return score


def select_why_facts(
    all_facts: list[str],
    key_points: list[str],
) -> list[str]:

    candidates = []

    for fact in all_facts:

        cleaned = strip_fact_label(
            sanitize_fact(fact)
        )

        score = why_fact_score(
            cleaned
        )

        if score <= 0:
            continue

        candidates.append(
            (
                score,
                cleaned,
            )
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = []

    for score, fact in candidates:

        if any(
            token_overlap(
                fact,
                chosen
            ) >= 0.55
            for chosen in selected
        ):
            continue

        selected.append(
            fact
        )

        if len(selected) == 3:
            break

    # WHY용 FACT가 너무 부족하면
    # KEY POINT에서 의미가 큰 내용을 보충
    if len(selected) < 2:

        for fact in reversed(
            key_points
        ):

            fact = strip_fact_label(
                fact
            )

            if fact in selected:
                continue

            if any(
                token_overlap(
                    fact,
                    chosen
                ) >= 0.55
                for chosen in selected
            ):
                continue

            selected.append(
                fact
            )

            if len(selected) == 3:
                break

    return selected[:3]


def generate_main_and_why(
    title: str,
    key_points: list[str],
    all_facts: list[str] | None = None,
) -> tuple[str, str]:

    if len(key_points) < 5:
        raise OllamaAnalysisError(
            "KEY FACT가 5개 미만입니다."
        )

    main_facts = select_main_facts(
        key_points
    )

    main = clean_text(
        " ".join(
            ensure_period(
                strip_fact_label(fact)
            )
            for fact in main_facts
        )
    )

    source_facts = (
        all_facts
        if all_facts
        else key_points
    )

    why_facts = select_why_facts(
        source_facts,
        key_points,
    )

    why = clean_text(
        " ".join(
            ensure_period(fact)
            for fact in why_facts
        )
    )

    return main, why


def analyze_with_ollama(
    title: str,
    description: str,
    body: str,
    tags: list[str],
) -> dict:

    source = clean_text(
        body or description
    )

    if len(source) < 300:
        raise OllamaAnalysisError(
            "분석할 원문이 너무 짧습니다."
        )

    print(
        f"  -> 원문 길이: "
        f"{len(source):,}자"
    )

    facts = collect_facts(
        source,
        title,
        description,
    )

    print(
        f"  -> 추출 사실: "
        f"{len(facts)}개"
    )

    if len(facts) < 5:
        raise OllamaAnalysisError(
            "충분한 사실을 추출하지 못했습니다."
        )

    key_points = select_key_facts(
        facts
    )

    print(
        "  -> 규칙 기반 핵심 FACT 5개 선택"
    )

    main, why = generate_main_and_why(
        title,
        key_points,
        facts,
    )

    return {
        "main_point": main,
        "key_points": key_points,
        "why_it_matters": why,
        "category": category_override(
            title,
            tags
        ),
    }
