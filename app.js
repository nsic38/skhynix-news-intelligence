let allArticles = [];

async function loadEverything() {
  const status = document.getElementById("status");

  try {
    const [articlesResponse, stateResponse] = await Promise.all([
      fetch("data/articles.json?ts=" + Date.now()),
      fetch("data/state.json?ts=" + Date.now())
    ]);

    if (!articlesResponse.ok) throw new Error("articles.json을 읽지 못했습니다.");

    allArticles = await articlesResponse.json();
    const state = stateResponse.ok ? await stateResponse.json() : {};

    updateDashboard(state);
    applyFilters();

    status.textContent = `누적 기사 ${allArticles.length}개 · 동일 URL/제목 중복 및 Shorts 제외`;
  } catch (err) {
    status.textContent = "데이터를 불러오지 못했습니다: " + err.message;
  }
}

function updateDashboard(state) {
  document.getElementById("last-check").textContent =
    formatDateTime(state.last_checked_at) || "아직 없음";

  document.getElementById("new-count").textContent =
    `${state.last_new_count ?? 0}개`;

  document.getElementById("total-count").textContent =
    `${state.total_articles ?? allArticles.length}개`;
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function stars(score) {
  const safe = Math.max(1, Math.min(5, Number(score || 1)));
  return "★".repeat(safe) + "☆".repeat(5 - safe);
}

function render(items) {
  const root = document.getElementById("articles");
  root.innerHTML = "";

  if (!items.length) {
    root.innerHTML = `<div class="empty">조건에 맞는 기사가 없습니다.</div>`;
    return;
  }

  for (const article of items) {
    const relevance = article.job_relevance || {
      role: "양산기술",
      score: article.importance || 1,
      reason: ""
    };

    const tags = (article.tags || [])
      .filter(tag => !["media", "source"].includes(String(tag).toLowerCase()))
      .slice(0, 7)
      .map(tag => `<span class="tag">${escapeHtml(tag)}</span>`)
      .join("");

    const points = (article.key_points || [])
      .slice(0, 3)
      .map(point => `<li>${escapeHtml(point)}</li>`)
      .join("");

    const card = document.createElement("article");
    card.className = "card";

    card.innerHTML = `
      <div class="topline">
        <div class="meta-group">
          <span class="date">${escapeHtml(article.published || "날짜 미확인")}</span>
          <span class="category">${escapeHtml(article.category || "General")}</span>
        </div>

        <div class="job-fit">
          <div class="job-fit-label">${escapeHtml(relevance.role)} 관련성</div>
          <div class="job-fit-stars">${stars(relevance.score)}</div>
          <div class="job-fit-reason">${escapeHtml(relevance.reason || "")}</div>
        </div>
      </div>

      <h2>
        <a href="${escapeAttr(article.url)}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(article.title)}
        </a>
      </h2>

      <div class="main-point">
        <span class="main-point-label">MAIN POINT</span>
        <span>${escapeHtml(article.main_point || article.one_liner || "")}</span>
      </div>

      <div class="insights">
        <section class="panel key-panel">
          <div class="label">KEY POINTS</div>
          <ul>${points || "<li>핵심 내용을 충분히 추출하지 못했습니다.</li>"}</ul>
        </section>

        <section class="panel">
          <div class="label">WHY IT MATTERS</div>
          <p>${escapeHtml(article.why_it_matters || "")}</p>
        </section>

        <section class="panel gain-panel">
          <div class="label">WHAT YOU GET · ${escapeHtml(relevance.role)}</div>
          <p>${escapeHtml(article.takeaway || "")}</p>
        </section>
      </div>

      <div class="bottom">
        <div class="tags">${tags}</div>
        <a class="original" href="${escapeAttr(article.url)}" target="_blank" rel="noopener noreferrer">
          원문 읽기 →
        </a>
      </div>
    `;

    root.appendChild(card);
  }
}

function applyFilters() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const importance = Number(document.getElementById("importance-filter").value || 0);

  const filtered = allArticles.filter(article => {
    const relevanceScore = Number(
      article.job_relevance?.score ?? article.importance ?? 0
    );

    const haystack = [
      article.title,
      article.main_point,
      article.why_it_matters,
      article.takeaway,
      article.category,
      article.job_relevance?.reason,
      ...(article.tags || []),
      ...(article.key_points || [])
    ].join(" ").toLowerCase();

    const textMatch = !q || haystack.includes(q);
    const relevanceMatch = !importance || relevanceScore >= importance;

    return textMatch && relevanceMatch;
  });

  render(filtered);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

document.getElementById("search").addEventListener("input", applyFilters);
document.getElementById("importance-filter").addEventListener("change", applyFilters);
document.getElementById("reload").addEventListener("click", loadEverything);

loadEverything();
