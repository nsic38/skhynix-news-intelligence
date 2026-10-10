from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests

from analyzer import analyze_article, refresh_saved_role_analysis

BASE_URL = "https://news.skhynix.co.kr/"
RSS_URL = "https://news.skhynix.co.kr/feed/"
ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "articles.json"
STATE_FILE = ROOT / "data" / "state.json"

RSS_SCAN_LIMIT = 30
BOOTSTRAP_COUNT = 10
TIMEOUT = 20
REPAIR_VERSION = 13
KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
    "Referer": BASE_URL,
}

BLOCKED_PATHS = {
    "", "/", "/all", "/all/", "/policy", "/policy/", "/privacy", "/privacy/",
    "/guide", "/guide/", "/about", "/about/", "/terms", "/terms/",
}
BLOCKED_TITLE_WORDS = (
    "뉴스룸 운영정책", "뉴스룸 이용안내", "개인정보처리방침",
    "개인정보 처리방침", "이용약관", "저작권 정책", "Heritage",
)
JUNK_BODY_WORDS = (
    "copyright", "무단전재", "재배포", "개인정보처리방침", "뉴스룸 이용안내",
    "뉴스룸 운영정책", "관련기사", "구독하기", "쿠키", "cookie", "이용약관",
    "sk하이닉스 뉴스룸은", "다양한 소식과 반도체 시장의 변화하는 트렌드를 전달",
    "sk hynix newsroom", "출처", "사진", "이미지",
)

session = requests.Session()
session.headers.update(HEADERS)


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def html_to_text(value: str) -> str:
    if not value:
        return ""

    from bs4 import BeautifulSoup

    text = clean_text(
        BeautifulSoup(
            str(value),
            "html.parser"
        ).get_text(
            " ",
            strip=True
        )
    )

    # PRESS / STORY 등은 뉴스룸 분류 레이블
    text = re.sub(
        r"^(?:PRESS|STORY|FACT|MEDIA)\s*[:|\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def is_junk_summary_text(text: str) -> bool:
    cleaned = html_to_text(text)
    low = cleaned.lower()

    # v8: 뉴스룸 이미지 캡션/페이지 레이블 제외
    if re.match(r"^(story|fact|press|media)\b", low):
        return True

    if (
        re.search(r"[▲△■●◆◇▶▷]", cleaned)
        and (
            len(cleaned) <= 220
            or "행사 현장" in cleaned
        )
    ):
        return True

    if not cleaned or is_generic_newsroom_text(cleaned):
        return True

    if low in {
        "source",
        "출처",
        "사진",
        "이미지",
    }:
        return True

    if (
        len(cleaned) <= 180
        and re.match(
            r"^[▲△■●◆◇▶▷]",
            cleaned
        )
    ):
        return True

    if (
        len(cleaned) <= 120
        and any(
            word in low
            for word in (
                "출처",
                "사진",
                "이미지",
            )
        )
    ):
        return True

    return False


def extract_rss_text(entry) -> str:
    candidates = []

    for item in (
        getattr(entry, "content", []) or []
    ):
        if isinstance(item, dict):
            raw = item.get("value", "")
        else:
            raw = getattr(item, "value", "")

        text = html_to_text(raw)

        if (
            len(text) >= 25
            and not is_junk_summary_text(raw)
        ):
            candidates.append(text)

    for raw in (
        getattr(entry, "summary", ""),
        getattr(entry, "description", ""),
    ):
        text = html_to_text(raw)

        if (
            len(text) >= 25
            and not is_junk_summary_text(raw)
        ):
            candidates.append(text)

    if not candidates:
        return ""

    return max(candidates, key=len)


def is_generic_newsroom_text(text: str) -> bool:
    low = clean_text(text).lower()
    if not low:
        return False
    return any(
        marker in low
        for marker in (
            "sk하이닉스 뉴스룸은",
            "다양한 소식과 반도체 시장의 변화하는 트렌드를 전달",
            "sk hynix newsroom",
            "반도체 시장의 변화하는 트렌드를 전달",
        )
    )


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url)
    return urlunsplit((p.scheme or "https", p.netloc.lower(), p.path.rstrip("/"), "", ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", clean_text(title).lower(), flags=re.UNICODE)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def is_blocked_item(title: str, url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    # 실제 SK hynix Newsroom 기사만 유지한다.
    # 과거 Google News fallback이 만든 프록시/검색/태그/목록 결과는 제외한다.
    if host != "news.skhynix.co.kr":
        return True

    if re.search(r"페이지\s*\d+", title, flags=re.IGNORECASE) and "SK하이닉스 뉴스룸" in title:
        return True

    if path in BLOCKED_PATHS or any(word in title for word in BLOCKED_TITLE_WORDS):
        return True

    return any(part in path for part in (
        "/tag/", "/category/", "/author/", "/page/", "/feed/", "/search",
        "/shorts/", "/wp-", "/media-library",
    ))


def parse_rss_date(entry) -> str:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        dt = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(KST)
        return dt.strftime("%Y-%m-%d")
    raw = getattr(entry, "published", "") or getattr(entry, "updated", "")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(KST).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


def normalize_page_date(value: str) -> str:
    value = clean_text(value)
    for pattern in (
        r"\b(20\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})\b",
        r"\b(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\b",
    ):
        m = re.search(pattern, value)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return ""


def fetch_rss_entries() -> list:
    response = session.get(RSS_URL, timeout=TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if not getattr(feed, "entries", []):
        raise RuntimeError("RSS에서 기사를 찾지 못했습니다.")

    result, seen_urls, seen_titles = [], set(), set()
    cutoff = datetime.now(KST) - timedelta(days=7)
    for entry in feed.entries[:RSS_SCAN_LIMIT]:
        parsed = getattr(entry, "published_parsed", None)
        if not parsed:
            continue
        rss_dt = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(KST)
        if rss_dt < cutoff:
            continue

        title = clean_text(getattr(entry, "title", ""))
        url = normalize_url(getattr(entry, "link", ""))
        tags = [
            getattr(x, "term", "")
            for x in (getattr(entry, "tags", []) or [])
            if getattr(x, "term", "")
        ]
        if not title or not url or is_blocked_item(title, url) or "shorts" in " ".join(tags).lower():
            continue

        ntitle = normalize_title(title)
        if url in seen_urls or ntitle in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(ntitle)
        result.append(entry)
    return result


def iter_json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_objects(child)


def fetch_article_data(url: str) -> tuple[str, str, list[str], str]:
    from bs4 import BeautifulSoup

    response = session.get(url, timeout=TIMEOUT, headers={
        **HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    description = ""
    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ):
        node = soup.find("meta", attrs=attrs)
        if node and node.get("content"):
            value = clean_text(node["content"])
            if len(value) >= 30 and not is_generic_newsroom_text(value):
                description = value
                break

    tags = []
    for node in soup.find_all("meta", attrs={"property": "article:tag"}):
        value = clean_text(node.get("content", ""))
        if value and value not in tags:
            tags.append(value)

    body, page_date = "", ""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for obj in iter_json_objects(data):
            if not page_date:
                page_date = normalize_page_date(str(obj.get("datePublished", "")))
            article_body = obj.get("articleBody")
            if isinstance(article_body, str):
                candidate = clean_text(article_body)
                if not is_generic_newsroom_text(candidate) and len(candidate) > len(body):
                    body = candidate
            if not description and isinstance(obj.get("description"), str):
                candidate_desc = clean_text(obj["description"])
                if not is_generic_newsroom_text(candidate_desc):
                    description = candidate_desc

    if not page_date:
        for attrs in (
            {"property": "article:published_time"}, {"property": "og:published_time"},
            {"name": "date"}, {"name": "pubdate"}, {"name": "publish-date"},
            {"itemprop": "datePublished"},
        ):
            node = soup.find("meta", attrs=attrs)
            if node and node.get("content"):
                page_date = normalize_page_date(node.get("content", ""))
                if page_date:
                    break

    if not page_date:
        for node in soup.find_all("time"):
            page_date = normalize_page_date(node.get("datetime", "") or node.get_text(" ", strip=True))
            if page_date:
                break

    if not page_date:
        for selector in (
            ".date", ".post-date", ".article-date", ".view-date",
            ".view_date", ".publish-date", ".published",
        ):
            for node in soup.select(selector):
                page_date = normalize_page_date(node.get_text(" ", strip=True))
                if page_date:
                    break
            if page_date:
                break

    if len(body) < 200:
        for bad in soup([
            "script", "style", "noscript", "nav", "footer", "header",
            "aside", "form", "button", "svg", "figure", "figcaption",
        ]):
            bad.decompose()

        selectors = (
            "article p", ".article-content p", ".article_content p",
            ".article-body p", ".article_body p", ".entry-content p",
            ".post-content p", ".post_content p", ".view_cont p",
            ".view-content p", ".view_content p", ".news-content p",
            ".news_content p", ".newsroom-content p", ".contents p",
            ".content p", ".content-area p", "main p",
            "[class*='article'] p", "[class*='content'] p",
        )
        container_selectors = (
            "article",
            "main",
            ".article-content",
            ".article_content",
            ".article-body",
            ".article_body",
            ".entry-content",
            ".post-content",
            ".post_content",
            ".view_cont",
            ".view-content",
            ".view_content",
            ".news-content",
            ".news_content",
            ".newsroom-content",
            ".contents",
            ".content",
            ".content-area",
            "[class*='article-body']",
            "[class*='article_content']",
            "[class*='post-content']",
            "[class*='entry-content']",
            "[class*='view-content']",
            "[class*='news-content']",
        )

        for csel in container_selectors:
            for node in soup.select(csel):
                candidate = clean_text(
                    node.get_text(
                        " ",
                        strip=True
                    )
                )

                if (
                    len(candidate) >= 120
                    and len(candidate) > len(body)
                    and not is_junk_summary_text(candidate)
                ):
                    body = candidate

        for selector in selectors:
            paragraphs, seen = [], set()
            for p in soup.select(selector):
                text = clean_text(p.get_text(" ", strip=True))
                if (
                    len(text) < 20
                    or text in seen
                    or is_junk_summary_text(text)
                    or any(j in text.lower() for j in JUNK_BODY_WORDS)
                ):
                    continue
                seen.add(text)
                paragraphs.append(text)
            joined = " ".join(paragraphs)
            if len(joined) > len(body):
                body = joined

    if len(body) < 200:
        paragraphs, seen = [], set()
        for p in soup.find_all("p"):
            text = clean_text(p.get_text(" ", strip=True))
            if (
                len(text) < 20
                or text in seen
                or is_generic_newsroom_text(text)
                or any(j in text.lower() for j in JUNK_BODY_WORDS)
            ):
                continue
            seen.add(text)
            paragraphs.append(text)
        joined = " ".join(paragraphs)
        if len(joined) > len(body):
            body = joined

    return description, body, tags, page_date


def title_fallback_points(
    title: str
) -> list[str]:

    text = html_to_text(title)

    text = re.sub(
        r"\s*[-–—]\s*SK하이닉스 뉴스룸\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^\[[^\]]+\]\s*",
        "",
        text,
    )

    text = clean_text(
        text.strip(
            " -–—,，:;.…"
        )
    )

    if len(text) >= 12:
        return [text]

    return []


def fallback_key_points(
    title: str,
    description: str,
    body: str
) -> list[str]:

    source = html_to_text(
        body
        if len(
            html_to_text(body)
        ) >= 80
        else description
    )

    if (
        source
        and not is_junk_summary_text(source)
    ):
        points = []

        for chunk in re.split(
            r"(?<=[.!?。！？])\s+",
            source
        ):

            chunk = html_to_text(
                chunk
            )

            # 완전한 문장만 사용하고 절대 중간 자르지 않음
            if (
                30 <= len(chunk) <= 220
                and chunk not in points
                and not is_junk_summary_text(chunk)
                and not any(
                    j in chunk.lower()
                    for j in JUNK_BODY_WORDS
                )
            ):
                points.append(
                    chunk.rstrip(".")
                )

            if len(points) == 3:
                break

        if points:
            return points

    return title_fallback_points(
        title
    )


def run_analysis(
    title: str,
    description: str,
    body: str,
    tags: list[str]
) -> dict:

    description = html_to_text(description)
    body = html_to_text(body)

    if is_junk_summary_text(description):
        description = ""

    analysis = analyze_article(
        title,
        description,
        body,
        tags
    )

    points = []

    for point in (
        analysis.get("key_points") or []
    ):
        point = html_to_text(point)

        if (
            point
            and not is_junk_summary_text(point)
            and not any(
                j in point.lower()
                for j in JUNK_BODY_WORDS
            )
        ):
            points.append(point)

    analysis["key_points"] = points[:3]

    main = html_to_text(
        analysis.get(
            "main_point",
            ""
        )
    )

    if is_junk_summary_text(main):
        main = ""

    if not analysis["key_points"]:
        analysis["key_points"] = (
            fallback_key_points(
                title,
                description,
                body
            )[:3]
        )

    if not main:
        if analysis["key_points"]:
            main = analysis["key_points"][0]
        else:
            main = title

    analysis["main_point"] = main
    analysis["one_liner"] = (
        analysis["main_point"]
    )

    temp = {
        "title": title,
        "main_point": analysis["main_point"],
        "one_liner": analysis["one_liner"],
        "key_points": analysis["key_points"],
        "tags": tags,
    }

    refresh_saved_role_analysis(
        temp,
        body
    )

    for k in (
        "role_analysis",
        "job_relevance",
        "takeaway",
        "importance",
    ):
        analysis[k] = temp[k]

    why = html_to_text(
        analysis.get(
            "why_it_matters",
            ""
        )
    )

    if (
        not why
        or is_junk_summary_text(why)
    ):
        why = (
            f"{analysis['main_point']}. "
            "이 내용은 기사에서 다루는 "
            "기술·사업 변화의 방향을 "
            "파악하는 데 중요합니다."
        )

    analysis["why_it_matters"] = why

    return analysis


def build_record(entry) -> dict:

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

    rss_text = extract_rss_text(entry)

    rss_tags = [
        getattr(x, "term", "")
        for x in (
            getattr(
                entry,
                "tags",
                []
            ) or []
        )
        if getattr(x, "term", "")
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
            page_date
        ) = fetch_article_data(url)

    except Exception as exc:
        print(
            "  -> 본문 요청 실패, "
            f"RSS 정보로 분석: {exc}"
        )

    tags = list(
        dict.fromkeys(
            [
                x
                for x
                in rss_tags + page_tags
                if x
            ]
        )
    )

    if len(body) >= 120:
        analysis_body = body

    elif len(rss_text) >= 120:
        analysis_body = rss_text

    else:
        analysis_body = ""

    analysis = run_analysis(
        title,
        description or rss_text,
        analysis_body,
        tags
    )

    return {
        "id": hashlib.sha1(
            url.encode("utf-8")
        ).hexdigest()[:12],

        "title": title,
        "url": url,

        "published":
            page_date
            or parse_rss_date(entry),

        "date_source":
            "page"
            if page_date
            else "rss",

        "source": "SK hynix Newsroom",
        "tags": tags,
        "created_at": now_iso(),

        "content_source":
            "article"
            if len(body) >= 120
            else (
                "rss/content"
                if len(rss_text) >= 120
                else "title/meta"
            ),

        "repair_version":
            REPAIR_VERSION,

        **analysis,
    }


def clean_existing_articles(articles: list[dict]) -> tuple[list[dict], int]:
    cleaned, seen_urls, seen_titles, removed = [], set(), set(), 0

    for article in articles:
        title = clean_text(article.get("title", ""))
        url = normalize_url(article.get("url", ""))
        published = clean_text(article.get("published", ""))
        ntitle = normalize_title(title)

        if (
            not title or not url or is_blocked_item(title, url)
            or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", published)
            or url in seen_urls or ntitle in seen_titles
        ):
            removed += 1
            continue

        seen_urls.add(url)
        seen_titles.add(ntitle)
        cleaned.append(article)

    return cleaned, removed


def article_needs_repair(
    article: dict
) -> bool:

    if (
        int(
            article.get(
                "repair_version",
                0
            ) or 0
        )
        >= REPAIR_VERSION
    ):
        return False

    points = (
        article.get("key_points")
        or []
    )

    return (
        any(
            is_junk_summary_text(x)
            for x in points
        )
        or not points
        or is_junk_summary_text(
            article.get(
                "main_point",
                ""
            )
        )
        or article.get(
            "date_source"
        ) != "page"
        or article.get(
            "content_source"
        ) in {
            "rss/meta",
            "title/meta",
        }
    )


def repair_existing_articles(
    articles: list[dict]
) -> tuple[int, int]:

    repaired = 0
    failed = 0

    for i, article in enumerate(
        articles,
        1
    ):
        current_version = int(
            article.get(
                "repair_version",
                0
            ) or 0
        )

        if (
            current_version
            >= REPAIR_VERSION
        ):
            continue

        # 정상 기존 기사라도
        # 새 P&T 분석을 추가
        if not article_needs_repair(
            article
        ):
            refresh_saved_role_analysis(
                article
            )

            article[
                "repair_version"
            ] = REPAIR_VERSION

            repaired += 1
            continue

        url = normalize_url(
            article.get(
                "url",
                ""
            )
        )

        title = clean_text(
            article.get(
                "title",
                ""
            )
        )

        try:
            (
                description,
                body,
                page_tags,
                page_date
            ) = fetch_article_data(
                url
            )

        except Exception as exc:
            failed += 1

            print(
                "  -> 기존 기사 "
                "재검증 실패 "
                f"[{i}/{len(articles)}]: "
                f"{title} / {exc}"
            )

            tags = list(
                article.get(
                    "tags",
                    []
                )
            )

            article.update(
                run_analysis(
                    title,
                    "",
                    "",
                    tags
                )
            )

            refresh_saved_role_analysis(
                article
            )

            article[
                "content_source"
            ] = "title/meta"

            article[
                "repair_version"
            ] = REPAIR_VERSION

            continue

        tags = list(
            dict.fromkeys(
                [
                    x
                    for x in (
                        list(
                            article.get(
                                "tags",
                                []
                            )
                        )
                        + page_tags
                    )
                    if x
                ]
            )
        )

        article.update(
            run_analysis(
                title,
                description,
                body,
                tags
            )
        )

        article["tags"] = tags

        if page_date:
            article[
                "published"
            ] = page_date

            article[
                "date_source"
            ] = "page"

        else:
            article.setdefault(
                "date_source",
                "rss"
            )

        article[
            "content_source"
        ] = (
            "article"
            if len(body) >= 120
            else "title/meta"
        )

        article[
            "repair_version"
        ] = REPAIR_VERSION

        repaired += 1

    return repaired, failed


def main() -> int:
    articles = load_json(DATA_FILE, [])
    state = load_json(STATE_FILE, {
        "last_checked_at": None,
        "last_updated_at": None,
        "last_new_count": 0,
        "total_articles": len(articles),
    })

    articles, removed = clean_existing_articles(articles)
    repaired, repair_failed = repair_existing_articles(articles)

    if repaired or repair_failed:
        print(f"기존 기사 재검증: 성공 {repaired}개 / 실패 {repair_failed}개")

    try:
        entries = fetch_rss_entries()
        print(f"RSS 정상: 기사 {len(entries)}개 확인")
    except Exception as exc:
        print(f"RSS 확인 실패: {exc}")
        return 1

    existing_urls = {normalize_url(a.get("url", "")) for a in articles}
    existing_titles = {normalize_title(a.get("title", "")) for a in articles}

    if not articles:
        targets = entries[:BOOTSTRAP_COUNT]
    else:
        targets = [
            e for e in entries
            if normalize_url(getattr(e, "link", "")) not in existing_urls
            and normalize_title(getattr(e, "title", "")) not in existing_titles
        ]

    print(f"기존 기사 {len(articles)}개 / 새 기사 {len(targets)}개")

    added = []
    for i, entry in enumerate(reversed(targets), 1):
        title = clean_text(getattr(entry, "title", ""))
        print(f"[{i}/{len(targets)}] 새 기사 처리: {title}")

        try:
            record = build_record(entry)
        except Exception as exc:
            print(f"  -> 처리 실패: {exc}")
            continue

        url_key = normalize_url(record["url"])
        title_key = normalize_title(record["title"])

        if (
            is_blocked_item(record["title"], record["url"])
            or url_key in existing_urls
            or title_key in existing_titles
        ):
            continue

        articles.append(record)
        added.append(record)
        existing_urls.add(url_key)
        existing_titles.add(title_key)

    articles.sort(
        key=lambda x: (x.get("published", ""), x.get("created_at", "")),
        reverse=True,
    )
    save_json(DATA_FILE, articles)

    checked_at = now_iso()
    state["last_checked_at"] = checked_at
    state["last_new_count"] = len(added)
    state["total_articles"] = len(articles)

    if added or repaired:
        state["last_updated_at"] = checked_at

    save_json(STATE_FILE, state)

    print()
    print(
        f"완료: 새 기사 {len(added)}개 / 누적 {len(articles)}개 / "
        f"기존 기사 재검증 {repaired}개 / 실패 {repair_failed}개 / "
        f"비기사/프록시 항목 제거 {removed}개"
    )
    return 0


# === V11 UPDATE OVERRIDE ===

def fallback_key_points(
    title: str,
    description: str,
    body: str
) -> list[str]:

    source = html_to_text(
        body
        if len(html_to_text(body)) >= 80
        else description
    )

    source = re.sub(
        r"^(?:(?:PRESS|STORY|FACT|MEDIA)\s*)+",
        "",
        source,
        flags=re.IGNORECASE,
    ).strip()

    clean_title = html_to_text(
        title
    )

    if (
        clean_title
        and source.startswith(clean_title)
    ):
        source = source[
            len(clean_title):
        ].strip()

    source = re.sub(
        r'([.!?])[”"]\s+',
        r"\1\n",
        source
    )

    source = re.sub(
        r"([.!?])\s+",
        r"\1\n",
        source
    )

    points = []

    for chunk in source.splitlines():

        chunk = html_to_text(
            chunk
        ).strip()

        if not (
            35 <= len(chunk) <= 220
        ):
            continue

        if is_junk_summary_text(
            chunk
        ):
            continue

        if any(
            j in chunk.lower()
            for j in JUNK_BODY_WORDS
        ):
            continue

        points.append(
            chunk.rstrip(".")
        )

        if len(points) >= 3:
            break

    return (
        points
        or title_fallback_points(title)
    )


def article_needs_repair(
    article: dict
) -> bool:

    current_version = int(
        article.get(
            "repair_version",
            0
        ) or 0
    )

    return (
        current_version
        < REPAIR_VERSION
    )


if __name__ == "__main__":
    raise SystemExit(main())
