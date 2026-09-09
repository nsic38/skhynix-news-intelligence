from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

from analyzer import analyze_article

BASE_URL = "https://news.skhynix.co.kr/"
RSS_URL = urljoin(BASE_URL, "feed/")
ALL_URL = urljoin(BASE_URL, "all/")

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "articles.json"
STATE_FILE = ROOT / "data" / "state.json"

BOOTSTRAP_COUNT = 10
DAILY_LIST_LIMIT = 25
TIMEOUT = 15

KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

session = requests.Session()
session.headers.update(HEADERS)


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def clean_html(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url)
    return urlunsplit((p.scheme or "https", p.netloc.lower(), p.path.rstrip("/"), "", ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", clean_html(title).lower(), flags=re.UNICODE)


def is_article_url(url: str) -> bool:
    p = urlsplit(url)
    if p.netloc.lower() not in {"news.skhynix.co.kr", "www.news.skhynix.co.kr"}:
        return False

    path = p.path.lower()

    blocked = (
        "/tag/", "/category/", "/author/", "/page/", "/feed/",
        "/all/", "/search", "/shorts/", "/wp-", "/media-library"
    )

    return bool(path.strip("/")) and not any(part in path for part in blocked)


def is_shorts(title: str, url: str, tags: list[str]) -> bool:
    text = f"{title} {url} {' '.join(tags)}".lower()
    return "shorts" in text


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
        encoding="utf-8"
    )


def parse_date(value: str) -> str:
    if not value:
        return ""

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d")
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).strftime("%Y-%m-%d")
    except Exception:
        pass

    m = re.search(r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})", value)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return ""


def rss_items() -> list[dict]:
    feed = feedparser.parse(RSS_URL)
    items = []
    seen_urls = set()
    seen_titles = set()

    for entry in getattr(feed, "entries", [])[:DAILY_LIST_LIMIT]:
        title = clean_html(getattr(entry, "title", ""))
        url = normalize_url(getattr(entry, "link", ""))
        tags = [
            getattr(tag, "term", "")
            for tag in (getattr(entry, "tags", []) or [])
            if getattr(tag, "term", "")
        ]

        if not title or not url or not is_article_url(url):
            continue

        if is_shorts(title, url, tags):
            continue

        ntitle = normalize_title(title)

        if url in seen_urls or ntitle in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(ntitle)

        published = ""
        parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if parsed:
            dt = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(KST)
            published = dt.strftime("%Y-%m-%d")
        else:
            published = parse_date(
                getattr(entry, "published", "") or getattr(entry, "updated", "")
            )

        items.append({
            "title": title,
            "url": url,
            "published": published,
            "tags": tags,
            "description": clean_html(
                getattr(entry, "summary", "") or getattr(entry, "description", "")
            ),
            "discovered_by": "rss",
        })

    return items


def archive_items() -> list[dict]:
    """
    뉴스룸 전체보기 한 페이지만 읽는다.
    기사 100개를 여는 게 아니라 '목록 페이지 1개'에서 최신 URL을 확보한다.
    """
    try:
        r = session.get(ALL_URL, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"전체보기 목록 확인 실패: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    seen_urls = set()
    seen_titles = set()

    for a in soup.find_all("a", href=True):
        url = normalize_url(urljoin(BASE_URL, a.get("href", "")))

        if not is_article_url(url):
            continue

        raw_text = clean_html(a.get_text(" ", strip=True))
        parent_text = clean_html(a.parent.get_text(" ", strip=True)) if a.parent else raw_text

        # 제목/날짜가 같은 링크 텍스트 안에 붙는 경우와 부모 카드에 나뉘는 경우 모두 대응
        date_match = re.search(
            r"(20\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})",
            f"{raw_text} {parent_text}"
        )
        published = ""
        if date_match:
            published = (
                f"{int(date_match.group(1)):04d}-"
                f"{int(date_match.group(2)):02d}-"
                f"{int(date_match.group(3)):02d}"
            )

        title = re.sub(
            r"\s*20\d{2}[-./]\s*\d{1,2}[-./]\s*\d{1,2}\s*$",
            "",
            raw_text
        ).strip()

        # 링크 텍스트가 비어 있으면 카드 내부 h2/h3 등을 사용
        if len(title) < 8 and a.parent:
            heading = a.parent.find(["h1", "h2", "h3", "h4"])
            if heading:
                title = clean_html(heading.get_text(" ", strip=True))
                title = re.sub(
                    r"\s*20\d{2}[-./]\s*\d{1,2}[-./]\s*\d{1,2}\s*$",
                    "",
                    title
                ).strip()

        if len(title) < 8:
            continue

        # 메뉴성/카테고리성 링크 배제
        if title.lower() in {
            "homepage", "press", "story", "fact", "ir", "tech&ai",
            "기사 더 보기", "전체보기"
        }:
            continue

        tags = []
        if a.parent:
            text = parent_text.lower()
            if "shorts" in text:
                continue

        ntitle = normalize_title(title)

        if url in seen_urls or ntitle in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(ntitle)

        items.append({
            "title": title,
            "url": url,
            "published": published,
            "tags": tags,
            "description": "",
            "discovered_by": "all",
        })

        if len(items) >= DAILY_LIST_LIMIT:
            break

    return items


def latest_candidates() -> list[dict]:
    """
    RSS + 전체보기 한 페이지의 '목록 정보'만 합친다.
    여기서는 기사 본문을 열지 않는다.
    """
    merged = rss_items() + archive_items()
    unique = {}
    title_keys = set()

    for item in merged:
        url = normalize_url(item["url"])
        title_key = normalize_title(item["title"])

        if url in unique or title_key in title_keys:
            continue

        unique[url] = item
        title_keys.add(title_key)

    items = list(unique.values())

    # 날짜가 있는 글을 우선 최신순, 같은 날짜면 RSS가 앞
    items.sort(
        key=lambda x: (
            x.get("published", ""),
            1 if x.get("discovered_by") == "rss" else 0
        ),
        reverse=True
    )

    return items


def meta_text(soup: BeautifulSoup, key: str, *, prop=False) -> str:
    attrs = {"property": key} if prop else {"name": key}
    node = soup.find("meta", attrs=attrs)
    return clean_html(node.get("content", "")) if node and node.get("content") else ""


def jsonld_article_body(soup: BeautifulSoup) -> str:
    """
    일부 WordPress/SEO 구성은 JSON-LD에 articleBody를 넣는다.
    있으면 이 값을 가장 우선한다.
    """
    bodies = []

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

            body = obj.get("articleBody")
            if isinstance(body, str) and len(clean_html(body)) > 200:
                bodies.append(clean_html(body))

    return max(bodies, key=len) if bodies else ""


def text_blocks(node) -> list[str]:
    result = []
    seen = set()

    for child in node.find_all(["p", "h2", "h3", "li"], recursive=True):
        text = clean_html(child.get_text(" ", strip=True))

        if len(text) < 28:
            continue

        low = text.lower()

        if low in {"source", "출처"}:
            continue

        if any(
            junk in low
            for junk in (
                "copyright", "무단전재", "재배포", "개인정보처리방침",
                "구독하기", "related article"
            )
        ):
            continue

        if text in seen:
            continue

        seen.add(text)
        result.append(text)

    return result


def best_content_container(soup: BeautifulSoup) -> str:
    """
    특정 CSS 클래스 하나에 의존하지 않고,
    article/main/section/div 중 실제 본문 텍스트가 가장 풍부한 컨테이너를 선택.
    """
    candidates = []

    priority_selectors = [
        "article",
        "[class*='article']",
        "[class*='content']",
        "[class*='view']",
        "[class*='post']",
        "main",
    ]

    checked_ids = set()

    for selector in priority_selectors:
        for node in soup.select(selector):
            ident = id(node)
            if ident in checked_ids:
                continue
            checked_ids.add(ident)

            blocks = text_blocks(node)
            joined = " ".join(blocks)
            if len(joined) < 120:
                continue

            links_text = " ".join(
                clean_html(a.get_text(" ", strip=True))
                for a in node.find_all("a")
            )

            link_ratio = len(links_text) / max(len(joined), 1)

            # 긴 본문 + 낮은 링크 비율 선호
            score = len(joined) - (len(joined) * min(link_ratio, 1.0) * 0.6)
            candidates.append((score, joined))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # 최후 fallback: 페이지 전체의 p 중 유효한 문장만
    blocks = text_blocks(soup)
    return " ".join(blocks)


def fetch_article(item: dict) -> tuple[str, str, list[str]]:
    try:
        r = session.get(item["url"], timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"  -> 본문 요청 실패: {exc}")
        return "", "", []

    soup = BeautifulSoup(r.text, "html.parser")

    description_candidates = [
        meta_text(soup, "og:description", prop=True),
        meta_text(soup, "description"),
        item.get("description", ""),
    ]

    description = ""
    for value in description_candidates:
        value = clean_html(value)

        # 'Source' 같은 메타값을 설명으로 인정하지 않음
        if len(value) >= 45 and value.lower() not in {"source", "출처"}:
            description = value
            break

    tags = list(item.get("tags", []))
    for node in soup.find_all("meta", attrs={"property": "article:tag"}):
        value = clean_html(node.get("content", ""))
        if value and value not in tags:
            tags.append(value)

    # 비본문 영역 제거
    for node in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "aside"]):
        node.decompose()

    body = jsonld_article_body(soup)

    if len(body) < 200:
        body = best_content_container(soup)

    # 'Source' 한 단어만 남은 식의 잘못된 추출 방지
    if len(body) < 120 or body.strip().lower() in {"source", "출처"}:
        body = ""

    return description, body, tags


def make_record(item: dict) -> dict:
    description, body, tags = fetch_article(item)
    analysis = analyze_article(
        item["title"],
        description,
        body,
        tags
    )

    return {
        "id": hashlib.sha1(item["url"].encode("utf-8")).hexdigest()[:12],
        "title": item["title"],
        "url": item["url"],
        "published": item.get("published", ""),
        "source": "SK hynix Newsroom",
        "tags": tags,
        "created_at": now_iso(),
        "content_source": "article" if len(body) >= 120 else "meta",
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
        }
    )

    candidates = latest_candidates()

    if not candidates:
        print("최신 기사 목록을 찾지 못했습니다.")
        return 1

    existing_urls = {normalize_url(a.get("url", "")) for a in articles}
    existing_titles = {normalize_title(a.get("title", "")) for a in articles}

    is_bootstrap = len(articles) == 0

    if is_bootstrap:
        # 최초 1회만 최신 고유 기사 10개
        targets = candidates[:BOOTSTRAP_COUNT]
        print(f"최초 실행: 최신 고유 기사 {len(targets)}개를 초기 DB로 구축합니다.")
    else:
        # 이후에는 목록 페이지에서 기존 DB와 비교만 하고 새 글만 본문 요청
        targets = [
            item for item in candidates
            if normalize_url(item["url"]) not in existing_urls
            and normalize_title(item["title"]) not in existing_titles
        ]

        print(f"기존 누적 기사: {len(articles)}개")
        print(f"새 기사 후보: {len(targets)}개")

    added = []

    # 오래된 것부터 추가해 최종 정렬 시에도 안정적으로 유지
    for i, item in enumerate(reversed(targets), start=1):
        print(f"[{i}/{len(targets)}] 새 기사 처리: {item['title']}")

        try:
            record = make_record(item)
        except Exception as exc:
            print(f"  -> 처리 실패: {exc}")
            continue

        if (
            normalize_url(record["url"]) in existing_urls
            or normalize_title(record["title"]) in existing_titles
        ):
            continue

        articles.append(record)
        added.append(record)
        existing_urls.add(normalize_url(record["url"]))
        existing_titles.add(normalize_title(record["title"]))

    articles.sort(
        key=lambda x: (x.get("published", ""), x.get("created_at", "")),
        reverse=True
    )

    checked_at = now_iso()

    if added or is_bootstrap:
        save_json(DATA_FILE, articles)

    state["last_checked_at"] = checked_at
    state["last_new_count"] = len(added)
    state["total_articles"] = len(articles)

    if added:
        state["last_updated_at"] = checked_at

    save_json(STATE_FILE, state)

    print()
    print("=" * 64)
    print(f"확인 완료: {checked_at}")
    print(f"이번에 추가: {len(added)}개")
    print(f"누적 기사: {len(articles)}개")
    print("평소 실행 시 RSS + 전체보기 목록 1페이지만 확인하고, 새 기사만 본문을 읽습니다.")
    print("=" * 64)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
