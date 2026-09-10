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

from analyzer import analyze_article

BASE_URL = "https://news.skhynix.co.kr/"
RSS_URL = "https://news.skhynix.co.kr/feed/"

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "articles.json"
STATE_FILE = ROOT / "data" / "state.json"

BOOTSTRAP_COUNT = 10
RSS_SCAN_LIMIT = 30
TIMEOUT = 20

KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Referer": BASE_URL,
}

# 기사로 절대 취급하면 안 되는 고정 페이지
BLOCKED_PATHS = {
    "",
    "/",
    "/all",
    "/all/",
    "/policy",
    "/policy/",
    "/privacy",
    "/privacy/",
    "/guide",
    "/guide/",
    "/about",
    "/about/",
    "/terms",
    "/terms/",
}

BLOCKED_TITLE_WORDS = (
    "뉴스룸 운영정책",
    "뉴스룸 이용안내",
    "개인정보처리방침",
    "개인정보 처리방침",
    "이용약관",
    "저작권 정책",
)

session = requests.Session()
session.headers.update(HEADERS)


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_blocked_item(title: str, url: str) -> bool:
    p = urlsplit(url)
    path = p.path.lower()

    if path in BLOCKED_PATHS:
        return True

    if any(word in title for word in BLOCKED_TITLE_WORDS):
        return True

    if any(
        part in path
        for part in (
            "/tag/",
            "/category/",
            "/author/",
            "/page/",
            "/feed/",
            "/search",
            "/shorts/",
            "/wp-",
            "/media-library",
        )
    ):
        return True

    return False


def clean_existing_articles(articles: list[dict]) -> tuple[list[dict], int]:
    cleaned = []
    seen_urls = set()
    seen_titles = set()
    removed = 0

    for article in articles:
        title = clean_text(article.get("title", ""))
        url = normalize_url(article.get("url", ""))

        if not title or not url:
            removed += 1
            continue

        if is_blocked_item(title, url):
            removed += 1
            continue

        ntitle = normalize_title(title)

        if url in seen_urls or ntitle in seen_titles:
            removed += 1
            continue

        seen_urls.add(url)
        seen_titles.add(ntitle)
        cleaned.append(article)

    return cleaned, removed


def parse_date(entry) -> str:
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


def fetch_rss_entries() -> list:
    """
    GitHub Actions에서 feedparser가 URL을 직접 열면 차단될 수 있어
    requests.Session + 브라우저형 헤더로 XML을 먼저 받는다.
    """
    response = session.get(RSS_URL, timeout=TIMEOUT)
    response.raise_for_status()

    feed = feedparser.parse(response.content)

    if not getattr(feed, "entries", []):
        raise RuntimeError("RSS에서 기사를 찾지 못했습니다.")

    unique = []
    seen_urls = set()
    seen_titles = set()

    for entry in feed.entries[:RSS_SCAN_LIMIT]:
        title = clean_text(getattr(entry, "title", ""))
        url = normalize_url(getattr(entry, "link", ""))

        tags = [
            getattr(tag, "term", "")
            for tag in (getattr(entry, "tags", []) or [])
            if getattr(tag, "term", "")
        ]

        if not title or not url:
            continue

        if is_blocked_item(title, url):
            continue

        if "shorts" in " ".join(tags).lower():
            continue

        ntitle = normalize_title(title)

        if url in seen_urls or ntitle in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(ntitle)
        unique.append(entry)

    return unique


def fetch_article_text(url: str) -> tuple[str, str, list[str]]:
    """
    새 기사만 본문을 읽는다.
    페이지 전체가 아니라 본문 문단 위주로 수집해 메뉴/관련기사 오염을 줄인다.
    """
    from bs4 import BeautifulSoup

    response = session.get(
        url,
        timeout=TIMEOUT,
        headers={
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    description = ""
    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
    ):
        node = soup.find("meta", attrs=attrs)
        if node and node.get("content"):
            value = clean_text(node["content"])
            if len(value) >= 40 and value.lower() not in {"source", "출처"}:
                description = value
                break

    tags = []
    for node in soup.find_all("meta", attrs={"property": "article:tag"}):
        value = clean_text(node.get("content", ""))
        if value and value not in tags:
            tags.append(value)

    # JSON-LD articleBody 우선
    body = ""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        stack = data if isinstance(data, list) else [data]

        for obj in stack:
            if not isinstance(obj, dict):
                continue
            graph = obj.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)

            article_body = obj.get("articleBody")
            if isinstance(article_body, str) and len(clean_text(article_body)) > len(body):
                body = clean_text(article_body)

    # articleBody가 없을 때는 실제 문단을 모은다.
    if len(body) < 200:
        for bad in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
            bad.decompose()

        selectors = (
            "article p",
            ".article-content p",
            ".entry-content p",
            ".post-content p",
            ".view_cont p",
            ".view-content p",
            ".news-content p",
            "main p",
        )

        candidates = []

        for selector in selectors:
            paragraphs = []
            seen = set()

            for p in soup.select(selector):
                text = clean_text(p.get_text(" ", strip=True))

                if len(text) < 35:
                    continue

                low = text.lower()
                if any(
                    junk in low
                    for junk in (
                        "copyright",
                        "무단전재",
                        "재배포",
                        "개인정보처리방침",
                        "뉴스룸 이용안내",
                        "뉴스룸 운영정책",
                        "관련기사",
                        "구독하기",
                    )
                ):
                    continue

                if text in seen:
                    continue

                seen.add(text)
                paragraphs.append(text)

            joined = " ".join(paragraphs)
            if len(joined) > len(body):
                body = joined

    return description, body, tags


def build_record(entry) -> dict:
    title = clean_text(getattr(entry, "title", ""))
    url = normalize_url(getattr(entry, "link", ""))

    rss_description = clean_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "")
    )

    rss_tags = [
        getattr(tag, "term", "")
        for tag in (getattr(entry, "tags", []) or [])
        if getattr(tag, "term", "")
    ]

    description = ""
    body = ""
    page_tags = []

    try:
        description, body, page_tags = fetch_article_text(url)
    except Exception as exc:
        print(f"  -> 본문 요청 실패, RSS 정보로 분석: {exc}")

    tags = []
    for tag in rss_tags + page_tags:
        if tag and tag not in tags:
            tags.append(tag)

    analysis = analyze_article(
        title,
        description or rss_description,
        body,
        tags,
    )

    return {
        "id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:12],
        "title": title,
        "url": url,
        "published": parse_date(entry),
        "source": "SK hynix Newsroom",
        "tags": tags,
        "created_at": now_iso(),
        "content_source": "article" if len(body) >= 120 else "rss/meta",
        **analysis,
    }


def main() -> int:
    articles = load_json(DATA_FILE, [])
    state = load_json(
        STATE_FILE,
        {
            "last_checked_at": None,
            "last_updated_at": None,
            "last_new_count": 0,
            "total_articles": len(articles),
        },
    )

    # 1) 기존 DB 청소
    articles, removed = clean_existing_articles(articles)
    if removed:
        print(f"비기사/중복 기존 데이터 {removed}개 제거")

    try:
        entries = fetch_rss_entries()
    except Exception as exc:
        print(f"RSS 확인 실패: {exc}")

        # 기존 데이터 청소 결과는 저장
        save_json(DATA_FILE, articles)

        checked_at = now_iso()
        state["last_checked_at"] = checked_at
        state["last_new_count"] = 0
        state["total_articles"] = len(articles)
        save_json(STATE_FILE, state)

        # 자동화 전체 실패 대신 0으로 종료해 다음 날 다시 시도
        return 0

    existing_urls = {normalize_url(a.get("url", "")) for a in articles}
    existing_titles = {normalize_title(a.get("title", "")) for a in articles}

    if not articles:
        targets = entries[:BOOTSTRAP_COUNT]
        print(f"최초 구축: 최신 고유 기사 최대 {BOOTSTRAP_COUNT}개")
    else:
        targets = []
        for entry in entries:
            title = clean_text(getattr(entry, "title", ""))
            url = normalize_url(getattr(entry, "link", ""))

            if url in existing_urls or normalize_title(title) in existing_titles:
                continue

            targets.append(entry)

        print(f"기존 기사 {len(articles)}개 / 새 기사 {len(targets)}개")

    added = []

    for i, entry in enumerate(reversed(targets), start=1):
        title = clean_text(getattr(entry, "title", ""))
        print(f"[{i}/{len(targets)}] 새 기사 처리: {title}")

        try:
            record = build_record(entry)
        except Exception as exc:
            print(f"  -> 처리 실패: {exc}")
            continue

        if is_blocked_item(record["title"], record["url"]):
            continue

        url_key = normalize_url(record["url"])
        title_key = normalize_title(record["title"])

        if url_key in existing_urls or title_key in existing_titles:
            continue

        articles.append(record)
        added.append(record)
        existing_urls.add(url_key)
        existing_titles.add(title_key)

    articles.sort(
        key=lambda x: (x.get("published", ""), x.get("created_at", "")),
        reverse=True,
    )

    checked_at = now_iso()

    save_json(DATA_FILE, articles)

    state["last_checked_at"] = checked_at
    state["last_new_count"] = len(added)
    state["total_articles"] = len(articles)

    if added:
        state["last_updated_at"] = checked_at

    save_json(STATE_FILE, state)

    print()
    print(f"완료: 새 기사 {len(added)}개 / 누적 {len(articles)}개 / 기존 잘못된 항목 제거 {removed}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
