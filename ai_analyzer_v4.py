from __future__ import annotations

import re
from typing import Any

from ai_analyzer import (
    OllamaAnalysisError,
    call_ollama,
    clean_text,
)


KINDS = (
    "core",
    "technology",
    "process",
    "metric",
    "impact",
)


def safe_display_cleanup(text: str) -> str:

    text = clean_text(text)

    replacements = {
        "고객에 추화": "고객에 출하",
        "고객 추화": "고객 출하",
        "공전 변경": "공정 변경",
        "양선 품질": "양산 품질",
        "제조, 추락": "제조, 출하",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    if (
        "SBC" in text
        and (
            "스태티스티컬 프로세스 컨트롤" in text
            or "통계적으로 공정" in text
        )
    ):
        text = text.replace(
            "SBC",
            "SPC"
        )

    return clean_text(text)


def call_v4(
    prompt: str,
    attempts: int = 3,
) -> dict:

    last_error = None

    for attempt in range(
        1,
        attempts + 1
    ):

        current = prompt

        if attempt > 1:

            current += """

이전 응답에서 JSON 형식 오류가 발생했다.

이번에는:
- 설명문을 JSON 밖에 쓰지 않는다.
- 요구한 key만 사용한다.
- 유효한 JSON 객체 하나만 출력한다.
- 문자열을 새로 길게 작성하지 않는다.
- 원문은 출력하지 않고 번호만 출력한다.
"""

        try:

            return call_ollama(
                current,
                num_ctx=8192,
                num_predict=800,
            )

        except OllamaAnalysisError as exc:

            last_error = exc

            print(
                f"    ! V4 JSON 재시도 "
                f"{attempt}/{attempts}"
            )

    raise OllamaAnalysisError(
        f"V4 AI 호출 실패: {last_error}"
    )


def make_units(
    source: str,
) -> list[dict[str, Any]]:

    text = clean_text(source)

    # ".다음문장"처럼 붙어 있는 자동자막도 분리
    text = re.sub(
        r"([.!?])(?=[0-9A-Za-z가-힣])",
        r"\1 ",
        text,
    )

    raw_parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    parts = []
    pending = ""

    for raw in raw_parts:

        part = clean_text(raw)

        if not part:
            continue

        if pending:
            part = (
                pending
                + " "
                + part
            )
            pending = ""

        # 너무 짧은 발화는 다음 문장과 합침
        if len(part) < 25:
            pending = part
            continue

        parts.append(part)

    if pending:

        if parts:
            parts[-1] = (
                parts[-1]
                + " "
                + pending
            )
        else:
            parts.append(pending)

    units = []

    for index, text in enumerate(
        parts,
        1
    ):

        units.append(
            {
                "id": f"S{index}",
                "text": text,
            }
        )

    return units


def make_chunks(
    units: list[dict[str, Any]],
    target_chars: int = 2400,
) -> list[list[dict[str, Any]]]:

    chunks = []
    current = []
    size = 0

    for unit in units:

        length = len(
            unit["text"]
        ) + 10

        if (
            current
            and size + length
            > target_chars
        ):
            chunks.append(current)
            current = []
            size = 0

        current.append(unit)
        size += length

    if current:
        chunks.append(current)

    return chunks


def extract_chunk_ids(
    chunk: list[dict[str, Any]],
    index: int,
    total: int,
    title: str,
    description: str,
) -> list[dict[str, Any]]:

    numbered = "\n".join(
        f'[{item["id"]}] {item["text"]}'
        for item in chunk
    )

    prompt = f"""
너는 SK하이닉스 뉴스룸 기사에서
핵심 근거 문장을 찾는 편집자다.

중요:
원문을 복사하거나 요약하지 않는다.
아래 문장 번호만 선택한다.

[제목]
{title}

[기사 설명]
{description}

[원문 {index}/{total}]
{numbered}

이 구간에서 기사 전체 이해에 중요한 문장을
최대 7개 선택한다.

다음 정보를 우선한다.

- 기사의 핵심 사건, 역할, 목적
- 핵심 기술, 제품, 시스템
- 실제 업무, 공정, 평가, 관리 방식
- 숫자, 성능, 규모, 온도, 통계 기준
- 고객, 양산, 협력사, 사업상 의미

직무 기사라면:
실제 업무 프로세스, 고객/양산 리스크,
통계적 방법, 평가 기준, 필요한 역량을 우선한다.

행사 기사라면:
행사 개최 목적, 참석 대상과 규모,
대표 프로그램, 협력 의미를 우선한다.

기술 기사라면:
핵심 기술, 시스템 구조, 성능 수치,
고객 검증이나 적용 사례를 우선한다.

단순 인사말, 음식, 장식, 풍경,
진행 멘트는 더 중요한 내용이 있으면 제외한다.

kind는 아래 중 하나만 사용한다.

core
technology
process
metric
impact

importance는 1~5다.

반드시 JSON만 출력한다.

{{
  "items": [
    {{
      "id": "S1",
      "kind": "core",
      "importance": 5
    }}
  ]
}}
"""

    result = call_v4(prompt)

    raw = result.get(
        "items",
        []
    )

    if not isinstance(raw, list):
        return []

    allowed = {
        item["id"]
        for item in chunk
    }

    output = []

    for item in raw:

        if not isinstance(
            item,
            dict
        ):
            continue

        sid = str(
            item.get(
                "id",
                ""
            )
        ).strip()

        if sid not in allowed:
            continue

        kind = str(
            item.get(
                "kind",
                "core"
            )
        ).lower()

        if kind not in KINDS:
            kind = "core"

        try:
            importance = int(
                item.get(
                    "importance",
                    3
                )
            )
        except Exception:
            importance = 3

        output.append(
            {
                "id": sid,
                "kind": kind,
                "importance": max(
                    1,
                    min(
                        5,
                        importance
                    )
                ),
            }
        )

    return output


def text_tokens(
    text: str,
) -> set[str]:

    return set(
        re.findall(
            r"[0-9A-Za-z가-힣]+",
            text.lower(),
        )
    )


def similarity(
    a: str,
    b: str,
) -> float:

    aa = text_tokens(a)
    bb = text_tokens(b)

    if not aa or not bb:
        return 0.0

    return (
        len(aa & bb)
        / len(aa | bb)
    )


def deterministic_score(
    text: str,
    title: str,
) -> float:

    low = text.lower()

    score = 0.0

    if re.search(
        r"\d",
        text
    ):
        score += 4.0

    if re.search(
        r"\b[A-Z]{2,}[A-Z0-9.-]*\b",
        text
    ):
        score += 3.0

    keywords = (
        "공정",
        "고객",
        "리스크",
        "품질",
        "통계",
        "판정",
        "평가",
        "관리",
        "데이터",
        "룰",
        "컨트롤",
        "온도",
        "성능",
        "대역폭",
        "효율",
        "용량",
        "시스템",
        "기술",
        "메모리",
        "협력사",
        "초청",
        "개최",
        "열고",
        "발표",
        "공개",
        "출시",
        "목표",
        "체험",
        "프로그램",
        "SPC",
        "PCCB",
        "CXL",
        "HBM",
    )

    for word in keywords:

        if word.lower() in low:
            score += 1.5

    title_words = [
        word
        for word in re.findall(
            r"[0-9A-Za-z가-힣]+",
            title.lower(),
        )
        if len(word) >= 2
    ]

    for word in title_words:

        if word in low:
            score += 1.0

    return score


def build_candidates(
    source: str,
    title: str,
    description: str = "",
) -> list[dict[str, Any]]:

    units = make_units(source)
    chunks = make_chunks(units)

    by_id = {
        item["id"]: item
        for item in units
    }

    ai_meta = {}

    for index, chunk in enumerate(
        chunks,
        1
    ):

        print(
            f"  -> V4 번호 추출 "
            f"{index}/{len(chunks)}"
        )

        picks = extract_chunk_ids(
            chunk,
            index,
            len(chunks),
            title,
            description,
        )

        for pick in picks:

            sid = pick["id"]

            previous = ai_meta.get(sid)

            if (
                previous is None
                or pick["importance"]
                > previous["importance"]
            ):
                ai_meta[sid] = pick

    ranked = []

    for unit in units:

        sid = unit["id"]
        text = unit["text"]

        score = deterministic_score(
            text,
            title,
        )

        if sid in ai_meta:

            score += (
                12
                + ai_meta[sid][
                    "importance"
                ] * 4
            )

            kind = ai_meta[sid][
                "kind"
            ]

            importance = ai_meta[sid][
                "importance"
            ]

        else:

            kind = "core"
            importance = 1

        ranked.append(
            {
                "id": sid,
                "text": text,
                "display":
                    safe_display_cleanup(
                        text
                    ),
                "kind": kind,
                "importance":
                    importance,
                "_score": score,
            }
        )

    ranked.sort(
        key=lambda x: x["_score"],
        reverse=True,
    )

    # 너무 많은 후보는 다시 4B 모델이 흔들리므로
    # 상위 30개까지만 최종 선택기에 전달
    candidates = ranked[:40]

    # 읽기 편하게 원문 순으로 정렬
    candidates.sort(
        key=lambda x: int(
            x["id"][1:]
        )
    )

    return candidates


def fallback_five(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    ranked = sorted(
        candidates,
        key=lambda x: x["_score"],
        reverse=True,
    )

    selected = []

    for item in ranked:

        if any(
            similarity(
                item["display"],
                previous["display"],
            ) >= 0.50
            for previous in selected
        ):
            continue

        selected.append(item)

        if len(selected) == 5:
            break

    if len(selected) != 5:
        raise OllamaAnalysisError(
            "V4 fallback 선택 실패"
        )

    return selected




def infer_article_type(
    title: str,
    description: str,
) -> str:

    text = (
        title
        + " "
        + description
    ).lower()

    if any(
        word in text
        for word in (
            "job리포트",
            "직무",
            "품질보증",
            "엔지니어",
            "n잡러",
        )
    ):
        return "job"

    if any(
        word in text
        for word in (
            "thanksfull",
            "day",
            "행사",
            "초청",
            "가족",
            "협력사",
        )
    ):
        return "event"

    if any(
        word in text
        for word in (
            "ocp",
            "cxl",
            "hbm",
            "ai",
            "메모리",
            "기술",
            "솔루션",
            "설루션",
        )
    ):
        return "technology"

    return "general"


def has_any(
    text: str,
    words: tuple[str, ...],
) -> bool:

    low = text.lower()

    return any(
        word.lower() in low
        for word in words
    )


def keyword_bonus(
    text: str,
    weights: dict[str, float],
) -> float:

    low = text.lower()
    score = 0.0

    for word, weight in weights.items():

        if word.lower() in low:
            score += weight

    return score


def slot_rank_score(
    item: dict[str, Any],
    slot: str,
    article_type: str,
    title: str,
) -> float:

    text = item["display"]
    low = text.lower()

    # 기존 후보 중요도는 참고만 하고
    # 슬롯 목적을 더 강하게 반영
    score = (
        float(
            item.get(
                "_score",
                0
            )
        )
        * 0.20
    )

    score += (
        item.get(
            "importance",
            1
        )
        * 1.5
    )

    # 정보량 낮은 문장 감점
    if len(text) < 25:
        score -= 4.0

    generic_bad = (
        "오늘 알아볼",
        "오늘 알아볼 잡",
        "tech&ai",
        "가을의 풍족한 수확",
        "무엇일까요",
        "문제입니다",
        "퀴즈",
        "푸드트럭",
        "파라솔",
        "불꽃놀이",
    )

    for bad in generic_bad:

        if bad in low:
            score -= 18.0

    if slot == "core":

        score += keyword_bonus(
            text,
            {
                "업무": 6,
                "역할": 5,
                "책임": 5,
                "분석": 5,
                "판별": 6,
                "관리": 4,
                "개최": 10,
                "열고": 10,
                "참가해": 9,
                "공개": 9,
                "발표": 8,
                "제시": 7,
                "출시": 9,
                "협약": 8,
                "체결": 8,
            }
        )

        if article_type == "job":

            score += keyword_bonus(
                text,
                {
                    "양산": 7,
                    "공정 변경": 10,
                    "고객": 5,
                    "출하": 5,
                    "리스크": 10,
                    "사전에": 3,
                }
            )

            # 단순 직무 소개문은 강하게 감점
            if (
                "직무입니다" in text
                and not has_any(
                    text,
                    (
                        "업무",
                        "분석",
                        "판별",
                        "관리",
                        "리스크",
                    )
                )
            ):
                score -= 18.0

        elif article_type == "event":

            score += keyword_bonus(
                text,
                {
                    "행사": 5,
                    "thanksfull": 8,
                    "감사": 5,
                    "서울랜드": 3,
                }
            )

        elif article_type == "technology":

            score += keyword_bonus(
                text,
                {
                    "차세대": 4,
                    "메모리": 4,
                    "ai": 4,
                    "설루션": 5,
                    "솔루션": 5,
                    "시스템": 4,
                }
            )

    elif slot == "detail":

        score += keyword_bonus(
            text,
            {
                "spc": 24,
                "pccb": 20,
                "cxl": 13,
                "hbm": 12,
                "mars": 13,
                "리플로우": 12,
                "공정": 7,
                "관리": 6,
                "평가": 6,
                "분석": 6,
                "시스템": 8,
                "메모리 풀링": 10,
                "제로카피": 10,
                "체험": 10,
                "프로그램": 7,
                "반도체가 만들어지는": 9,
            }
        )

        if article_type == "event":

            score += keyword_bonus(
                text,
                {
                    "아이들": 10,
                    "놀이처럼": 14,
                    "체험": 10,
                    "반도체가 만들어지는": 16,
                    "아이들의 눈높이": 14,
                }
            )

        if article_type == "job":

            if has_any(
                text,
                (
                    "볼드",
                    "축볼",
                    "깊판",
                    "볼트를",
                )
            ):
                score -= 25.0

    elif slot == "concrete":

        if re.search(
            r"\d",
            text
        ):
            score += 14.0

        score += keyword_bonus(
            text,
            {
                "20가지 룰": 16,
                "룰": 10,
                "컨트롤 리밋": 13,
                "ucl": 12,
                "lcl": 12,
                "80gb/s": 16,
                "30%": 14,
                "256gb": 12,
                "260도": 14,
                "3만여 명": 16,
                "수십만": 12,
                "수백만": 12,
                "대역폭": 9,
                "에너지 효율": 9,
                "용량": 7,
            }
        )

    elif slot == "impact":

        score += keyword_bonus(
            text,
            {
                "고객": 8,
                "리스크": 9,
                "원하는 품질": 12,
                "원하는 시점": 10,
                "협력사": 7,
                "상생협력": 11,
                "동반성장": 11,
                "성과": 8,
                "결실": 8,
                "병목": 9,
                "해결": 8,
                "응답": 7,
                "효율": 6,
                "실제 시스템": 8,
                "작동": 6,
            }
        )

        if article_type == "job":

            score += keyword_bonus(
                text,
                {
                    "품질보증의": 7,
                    "캐치 프레이즈": 7,
                }
            )

    elif slot == "extra":

        score += keyword_bonus(
            text,
            {
                "데이터 분석": 12,
                "데이터 기반": 12,
                "판단력": 11,
                "소통": 9,
                "설득": 10,
                "주관": 8,
                "협력사": 6,
                "상생협력": 8,
                "동반성장": 8,
                "데모": 8,
                "poc": 8,
                "서비스": 6,
                "응답 지연": 9,
                "제로카피": 7,
                "가속": 6,
                "실제": 4,
            }
        )

        # 직무 기사 extra에서는 특수 사례보다 역량/실무 우선
        if article_type == "job":

            if has_any(
                text,
                (
                    "우주",
                    "가혹 환경",
                    "가혹한 환경",
                )
            ):
                score -= 15.0

        # 행사 기사 extra에서는 단순 환영 장면 감점
        if article_type == "event":

            if has_any(
                text,
                (
                    "입구에 자리를 잡고",
                    "환영",
                    "첫 순서부터 감사 인사",
                )
            ):
                score -= 12.0

    # 제목 키워드와 맞는 문장은 core에서 약간 우대
    if slot == "core":

        title_words = [
            x
            for x in re.findall(
                r"[0-9A-Za-z가-힣]+",
                title.lower(),
            )
            if len(x) >= 3
        ]

        for word in title_words:

            if word in low:
                score += 0.8

    return score


def select_five(
    candidates: list[dict[str, Any]],
    title: str,
    description: str,
) -> list[dict[str, Any]]:

    if len(candidates) < 5:
        raise OllamaAnalysisError(
            "V4 후보가 5개 미만입니다."
        )

    article_type = infer_article_type(
        title,
        description,
    )

    slots = (
        "core",
        "detail",
        "concrete",
        "impact",
        "extra",
    )

    selected = []
    used = set()
    debug = []

    for slot in slots:

        ranked = []

        for index, item in enumerate(
            candidates
        ):

            if index in used:
                continue

            score = slot_rank_score(
                item,
                slot,
                article_type,
                title,
            )

            # 앞에서 뽑힌 문장과 지나치게 비슷하면 감점
            for previous in selected:

                overlap = similarity(
                    item["display"],
                    previous["display"],
                )

                if overlap >= 0.55:
                    score -= 25.0

                elif overlap >= 0.35:
                    score -= 7.0

            ranked.append(
                (
                    score,
                    index,
                    item,
                )
            )

        ranked.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        if not ranked:
            raise OllamaAnalysisError(
                f"V4 {slot} 선택 실패"
            )

        score, index, item = ranked[0]

        selected.append(item)
        used.add(index)

        debug.append(
            f'{slot}={item["id"]}'
        )

    print(
        "  -> V4 deterministic 슬롯: "
        + ", ".join(debug)
    )

    return selected


def analyze_evidence_v4(
    title: str,
    description: str,
    source: str,
) -> dict[str, Any]:

    source = clean_text(source)

    print(
        f"  -> V4 원문 길이: "
        f"{len(source):,}자"
    )

    candidates = build_candidates(
        source,
        title,
        description,
    )

    print(
        f"  -> V4 후보 문장: "
        f"{len(candidates)}개"
    )

    selected = select_five(
        candidates,
        title,
        description,
    )

    return {
        "selected": selected,
        "key_points": [
            item["display"]
            for item in selected
        ],
    }


def extract_numbers_v4(
    text: str,
) -> set[str]:

    return set(
        re.findall(
            r"\d+(?:\.\d+)?",
            text
        )
    )


def extract_acronyms_v4(
    text: str,
) -> set[str]:

    return set(
        re.findall(
            r"\b[A-Z]{2,}[A-Z0-9.-]*\b",
            text
        )
    )


def rewrite_supported(
    source_text: str,
    rewritten: str,
) -> bool:

    source_numbers = extract_numbers_v4(
        source_text
    )

    new_numbers = extract_numbers_v4(
        rewritten
    )

    if not new_numbers.issubset(
        source_numbers
    ):
        return False

    source_acronyms = extract_acronyms_v4(
        source_text
    )

    new_acronyms = extract_acronyms_v4(
        rewritten
    )

    if not new_acronyms.issubset(
        source_acronyms
    ):
        return False

    return True


def rewrite_key_point_v4(
    evidence: str,
) -> str:

    prompt = f"""
다음 문장은 뉴스 기사 원문에서 직접 가져온 근거다.

[원문 근거]
{evidence}

이 문장을 뉴스 요약의 KEY POINT 한 문장으로 다듬어라.

절대 규칙:
- 원문에 없는 사실을 추가하지 않는다.
- 다른 문장과 내용을 합치지 않는다.
- 원문의 의미와 인과관계를 바꾸지 않는다.
- 숫자, 기술명, 약어는 원문에 있는 것만 사용한다.
- 자동자막의 말버릇, 반복, 어색한 조사만 자연스럽게 정리한다.
- 원문에서 정확히 확정할 수 없는 단어를 추측해서 고치지 않는다.
- 1문장으로 작성한다.
- 약 35~100자 정도로 작성한다.

반드시 JSON만 출력한다.

{{
  "text": "정리된 한 문장"
}}
"""

    try:

        result = call_v4(
            prompt
        )

        text = clean_text(
            result.get(
                "text",
                ""
            )
        )

        if (
            len(text) >= 15
            and rewrite_supported(
                evidence,
                text,
            )
        ):
            return text

    except Exception:
        pass

    return safe_display_cleanup(
        evidence
    )


def category_v4(
    title: str,
    description: str,
    key_points: list[str],
) -> str:

    text = (
        title
        + " "
        + description
        + " "
        + " ".join(key_points)
    ).lower()

    if any(
        word in text
        for word in (
            "품질보증",
            "품질 보증",
            "신뢰성",
            "quality",
            "reliability",
        )
    ):
        return "Quality / Reliability"

    if any(
        word in text
        for word in (
            "cxl",
            "ocp",
            "mars",
            "메모리 중심",
            "메모리 풀링",
            "ai 인프라",
        )
    ):
        return "AI Infrastructure / CXL"

    if any(
        word in text
        for word in (
            "thanksfull",
            "협력사",
            "파트너스데이",
            "동반성장",
            "상생협력",
        )
    ):
        return "Supply Chain / Partnership"

    if any(
        word in text
        for word in (
            "hbm",
            "ai memory",
        )
    ):
        return "HBM / AI Memory"

    if any(
        word in text
        for word in (
            "nand",
            "ssd",
            "storage",
            "스토리지",
        )
    ):
        return "NAND / Storage"

    return "Company / General"


def make_main_point_v4(
    title: str,
    key_points: list[str],
) -> str:

    # 핵심 + 대표 기술/프로세스까지만 사용
    evidence = (
        "[핵심]\n"
        + key_points[0]
        + "\n\n[대표 내용]\n"
        + key_points[1]
    )

    prompt = f"""
기사 제목:
{title}

아래 두 문장만 근거로 MAIN POINT를 작성한다.

{evidence}

규칙:
- 새로운 사실을 추가하지 않는다.
- 두 근거의 의미를 왜곡하지 않는다.
- 기사 전체를 빠르게 이해할 수 있도록 1~2문장으로 작성한다.
- 숫자와 약어는 근거에 있는 것만 사용한다.
- 과장 표현을 쓰지 않는다.
- '경쟁력을 강화한다', '미래를 선도한다' 같은
  근거 없는 일반론을 추가하지 않는다.

반드시 JSON만 출력한다.

{{
  "text": "MAIN POINT"
}}
"""

    try:

        result = call_v4(
            prompt
        )

        text = clean_text(
            result.get(
                "text",
                ""
            )
        )

        if (
            len(text) >= 20
            and rewrite_supported(
                " ".join(
                    key_points[:2]
                ),
                text,
            )
        ):
            return text

    except Exception:
        pass

    return (
        key_points[0]
        + " "
        + key_points[1]
    )


def make_why_v4(
    key_points: list[str],
) -> str:

    # concrete + impact + extra만 사용
    support = "\n".join(
        (
            key_points[2],
            key_points[3],
            key_points[4],
        )
    )

    prompt = f"""
다음 세 문장은 기사에서 검증된 핵심 근거다.

[근거]
{support}

이 근거만 사용해 WHY IT MATTERS를 작성한다.

규칙:
- 왜 이 내용이 실무, 고객, 기술 또는 사업 측면에서 중요한지
  원문 근거 범위 안에서 설명한다.
- 새로운 사실이나 일반론을 만들지 않는다.
- 원문에 없는 원인과 결과를 연결하지 않는다.
- 숫자와 약어는 근거에 있는 것만 사용한다.
- KEY POINT를 그대로 나열하지 말고 2~3문장으로 정리한다.
- '경쟁력 강화', '미래 선도', '혁신 가속' 같은
  근거 없는 상투적 표현을 추가하지 않는다.

반드시 JSON만 출력한다.

{{
  "text": "WHY IT MATTERS"
}}
"""

    try:

        result = call_v4(
            prompt
        )

        text = clean_text(
            result.get(
                "text",
                ""
            )
        )

        if (
            len(text) >= 25
            and rewrite_supported(
                support,
                text,
            )
        ):
            return text

    except Exception:
        pass

    return (
        key_points[3]
        + " "
        + key_points[4]
    )



def conservative_display_v4(
    text: str,
) -> str:

    text = safe_display_cleanup(
        text
    )

    # 의미를 바꾸지 않는 말버릇만 제거
    prefixes = (
        "그죠? ",
        "아니, ",
        "아니 ",
        "혹 ",
        "이제 ",
    )

    changed = True

    while changed:

        changed = False

        for prefix in prefixes:

            if text.startswith(prefix):

                text = text[
                    len(prefix):
                ].strip()

                changed = True

    # 명백한 구어체만 최소 정리
    replacements = {
        "시키면은": "하면",
        "하게 됩니다": "합니다",
        "하고 있습니다": "합니다",
        "할 수 있을지를": "할 수 있는지를",

        "우종티님 쪽에서 ": "",
        "그이 통계적": "통계적",
        "트렌드 이탈이라는 거는이": "트렌드 이탈은",
        "판정을 하고 있는데 일단": "판정을 하며,",
        "페일이다라는 판정을": "페일로 판정하고",
        "능력을 갖추고 있어요": "능력이 필요합니다",

        "저희 양산 품질 엔지니어들이 하는 역할은":
            "양산 품질 엔지니어는",

        "SPC가 총계적 영인데 아시는 분 있으신 스태티스티컬 프로세스 컨트롤이라는 의미고 그 통계적으로 공정 관리한다는 의미입니다.":
            "SPC는 Statistical Process Control을 의미하며, 통계적으로 공정을 관리하는 방식입니다.",

        "20가지 룰 정도로 통계적 판정을 하며, 직관적으로 트렌드 이탈은 컨트롤 리밋 선을 자재가 벗어났을 때 통계적으로 페일로 판정하고 하고 자재의 적절한 조치를 취합니다.":
            "약 20가지 룰로 통계적 판정을 하며, 자재가 컨트롤 리밋을 벗어나면 통계적으로 Fail로 판정해 적절한 조치를 취합니다.",

        "고객이 원하는 품질을 자사가 만들어서 고객에게 원하는 시점에 가져다 준다.":
            "품질보증의 목표는 고객이 원하는 품질을 만들어 원하는 시점에 제공하는 것입니다.",

        "설득을 하는 건 결국 데이터 기반으로 되어야 하거든요.":
            "내부 설득은 데이터 기반으로 이루어져야 합니다.",
    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

    return clean_text(text)



def readable_key_points_v4(
    selected,
) -> list[str]:

    originals = [
        conservative_display_v4(
            item["display"]
        )
        for item in selected
    ]

    if len(originals) != 5:
        return originals

    evidence = "\n".join(
        f"E{i + 1}: {text}"
        for i, text in enumerate(originals)
    )

    prompt = f"""
아래 E1~E5는 한 기사에서 이미 검증된 핵심 근거 문장이다.

각 문장의 의미를 유지하면서
독자가 빠르게 이해할 수 있는 자연스러운 한국어 한 문장으로
짧게 정리하라.

중요:
- E1은 E1만 사용한다.
- E2는 E2만 사용한다.
- E3은 E3만 사용한다.
- E4는 E4만 사용한다.
- E5는 E5만 사용한다.
- 서로 다른 근거의 내용을 섞지 않는다.
- 원문에 없는 사실을 추가하지 않는다.
- 원인, 효과, 전망을 새로 추론하지 않는다.
- 숫자, 단위, 제품명, 기술명, 약어를 새로 만들지 않는다.
- 원문의 중요한 기술 정보는 삭제하지 않는다.
- 인터뷰 말버릇, 중복 표현, 불필요하게 긴 표현만 정리한다.
- 각 항목은 1문장으로 작성한다.
- 반드시 JSON만 반환한다.

형식:
{{
  "points": [
    "E1 정리",
    "E2 정리",
    "E3 정리",
    "E4 정리",
    "E5 정리"
  ]
}}

근거:
{evidence}
"""

    try:
        result = call_v4(prompt)

        points = result.get(
            "points",
            []
        )

        if (
            not isinstance(points, list)
            or len(points) != 5
        ):
            return originals

        final = []

        from difflib import SequenceMatcher

        for source, rewritten in zip(
            originals,
            points,
        ):

            rewritten = clean_text(
                rewritten
            )

            if not rewritten:
                final.append(source)
                continue

            # 숫자/약어가 새로 생기면 원문으로 복귀
            if not rewrite_supported(
                source,
                rewritten,
            ):
                final.append(source)
                continue

            # 요약인데 원문보다 지나치게 길어지면 거부
            if len(rewritten) > (
                len(source) * 1.15 + 15
            ):
                final.append(source)
                continue

            src_norm = re.sub(
                r"[^0-9A-Za-z가-힣]+",
                "",
                source.lower(),
            )

            out_norm = re.sub(
                r"[^0-9A-Za-z가-힣]+",
                "",
                rewritten.lower(),
            )

            similarity = SequenceMatcher(
                None,
                src_norm,
                out_norm,
            ).ratio()

            src_words = set(
                re.findall(
                    r"[0-9A-Za-z가-힣]{2,}",
                    source.lower(),
                )
            )

            out_words = set(
                re.findall(
                    r"[0-9A-Za-z가-힣]{2,}",
                    rewritten.lower(),
                )
            )

            overlap = (
                len(src_words & out_words)
                / max(
                    1,
                    len(out_words)
                )
            )

            # 원문에 없는데 자주 생성되는 일반론 차단
            risky_phrases = (
                "경쟁력 강화",
                "시장 확대",
                "수익성 향상",
                "고객 만족도",
                "비용 절감",
                "성능 극대화",
                "실시간 대응",
                "미래를 선도",
                "혁신을 가속",
            )

            unsafe = any(
                phrase in rewritten
                and phrase not in source
                for phrase in risky_phrases
            )

            if unsafe:
                final.append(source)
                continue

            # 원문에 없던 새로운 개념이 여러 개 추가되면 거부.
            # 조사/어미 변화는 허용하고, 새로운 내용 추가만 차단한다.
            source_lower = source.lower()

            output_words = re.findall(
                r"[A-Za-z가-힣]{2,}",
                rewritten.lower(),
            )

            harmless_words = {
                "수행합니다",
                "설명합니다",
                "의미합니다",
                "구성했다",
                "구성했습니다",
                "밝혔다",
                "밝혔습니다",
                "전했다",
                "전했습니다",
            }

            new_concepts = []

            for word in output_words:

                if word in harmless_words:
                    continue

                if word in source_lower:
                    continue

                # 한국어 조사/어미가 달라진 경우를 허용
                stem = word[:2]

                if stem in source_lower:
                    continue

                new_concepts.append(word)

            # 새로운 개념이 2개 이상이면
            # AI 문장을 버리고 검증된 원문 기반 문장으로 복귀
            if len(set(new_concepts)) >= 2:
                final.append(source)
                continue

            # 단순 조사 오류 보정
            rewritten = rewritten.replace(
                "SK하이닉스을",
                "SK하이닉스는",
            )

            # 원문과 너무 멀어졌으면 사용하지 않음
            if (
                similarity < 0.35
                and overlap < 0.50
            ):
                final.append(source)
                continue

            final.append(
                rewritten
            )

        return final

    except Exception:
        return originals


def analyze_with_ollama_v4(
    title: str,
    description: str,
    source: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:

    evidence_result = analyze_evidence_v4(
        title,
        description,
        source,
    )

    selected = evidence_result[
        "selected"
    ]

    # 검증된 5개 근거만 이용해 읽기 쉽게 정리
    # 검증에 실패한 항목은 원문 기반 문장으로 자동 복귀
    key_points = readable_key_points_v4(
        selected
    )

    # MAIN POINT:
    # core + detail을 그대로 사용.
    # 새로운 사실을 생성하지 않는다.
    main_parts = [
        key_points[0],
        key_points[1],
    ]

    main_point = " ".join(
        part
        for part in main_parts
        if part
    )

    # WHY IT MATTERS:
    # 선택기의 impact + extra 슬롯만 사용.
    # AI 해석을 추가하지 않는다.
    why_parts = [
        key_points[3],
        key_points[4],
    ]

    why_it_matters = " ".join(
        part
        for part in why_parts
        if part
    )

    category = category_v4(
        title,
        description,
        key_points,
    )

    return {
        "main_point":
            main_point,

        "key_points":
            key_points,

        "why_it_matters":
            why_it_matters,

        "category":
            category,

        "_evidence": [
            {
                "id": item["id"],
                "text": item["display"],
            }
            for item in selected
        ],
    }

