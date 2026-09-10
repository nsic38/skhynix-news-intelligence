let allArticles = [];

const ROLE_INFO = {
  "양산기술": "공정 안정성·수율·생산성·양산 전환",
  "양산관리": "TAT·WIP·병목·생산계획·납기",
  "공정기술": "공정 조건·Process Window·결함·미세화",
  "설비기술": "장비 가동률·PM·고장 진단·설비 안정화",
  "품질/신뢰성": "불량 원인·검사·신뢰성·품질 개선",
  "제품/소자": "메모리 구조·성능·전력·제품 로드맵",
  "IT": "MES·시스템 연계·인프라·보안·업무 자동화",
  "Data/AI": "데이터 분석·ML·예측·최적화·AI 서비스"
};

function selectedRole() {
  return document.getElementById("role-filter").value || "양산기술";
}

function getRoleAnalysis(article, role) {
  const roleData = article.role_analysis?.[role];
  if (roleData) return roleData;

  // v5.0 migration 전 데이터가 잠깐 보이는 경우의 안전한 fallback
  if (role === "양산기술" && article.job_relevance) {
    return {
      ...article.job_relevance,
      what_you_get: article.takeaway || ""
    };
  }

  return {
    role,
    score: 1,
    reason: "직무별 분석 데이터 갱신 대기",
    dimensions: [],
    matched_keywords: [],
    what_you_get: "Daily News Update가 한 번 실행되면 이 직무 기준 분석이 생성됩니다."
  };
}

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

    status.textContent =
      `누적 기사 ${allArticles.length}개 · 선택 직무에 따라 관련성/WHAT YOU GET이 변경됩니다.`;
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

function updateRoleSummary() {
  const role = selectedRole();
  document.getElementById("role-current").textContent = role;
  document.getElementById("role-description").textContent =
    `${ROLE_INFO[role] || "직무 핵심 역량"} 중심으로 기사 관련성을 평가합니다.`;
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
  const role = selectedRole();
  root.innerHTML = "";

  if (!items.length) {
    root.innerHTML = `<div class="empty">현재 조건에 맞는 기사가 없습니다.</div>`;
    return;
  }

  for (const article of items) {
    const relevance = getRoleAnalysis(article, role);

    const tags = (article.tags || [])
      .filter(tag => !["media", "source"].includes(String(tag).toLowerCase()))
      .slice(0, 7)
      .map(tag => `<span class="tag">${escapeHtml(tag)}</span>`)
      .join("");

    const points = (article.key_points || [])
      .slice(0, 3)
      .map(point => `<li>${escapeHtml(point)}</li>`)
      .join("");

    const matched = (relevance.matched_keywords || [])
      .slice(0, 5)
      .map(keyword => `<span class="match-tag">${escapeHtml(keyword)}</span>`)
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
          <div class="job-fit-label">${escapeHtml(role)} 관련성</div>
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
          <div class="label">WHAT YOU GET · ${escapeHtml(role)}</div>
          <p>${escapeHtml(relevance.what_you_get || article.takeaway || "")}</p>
          ${matched ? `<div class="match-tags">${matched}</div>` : ""}
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
  updateRoleSummary();

  const role = selectedRole();
  const q = document.getElementById("search").value.trim().toLowerCase();
  const minimum = Number(document.getElementById("importance-filter").value || 0);
  const sortMode = document.getElementById("sort-filter").value || "latest";

  const filtered = allArticles.filter(article => {
    const relevance = getRoleAnalysis(article, role);
    const relevanceScore = Number(relevance.score || 0);

    const haystack = [
      article.title,
      article.main_point,
      article.why_it_matters,
      relevance.what_you_get,
      relevance.reason,
      article.category,
      ...(relevance.matched_keywords || []),
      ...(article.tags || []),
      ...(article.key_points || [])
    ].join(" ").toLowerCase();

    return (!q || haystack.includes(q)) &&
           (!minimum || relevanceScore >= minimum);
  });

  filtered.sort((a, b) => {
    if (sortMode === "relevance") {
      const scoreA = Number(getRoleAnalysis(a, role).score || 0);
      const scoreB = Number(getRoleAnalysis(b, role).score || 0);
      if (scoreB !== scoreA) return scoreB - scoreA;
    }

    const dateA = `${a.published || ""} ${a.created_at || ""}`;
    const dateB = `${b.published || ""} ${b.created_at || ""}`;
    return dateB.localeCompare(dateA);
  });

  render(filtered);

  document.getElementById("status").textContent =
    `${role} 기준 ${filtered.length}개 표시 · 누적 ${allArticles.length}개`;
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

const savedRole = localStorage.getItem("skhynix-role");
if (savedRole && ROLE_INFO[savedRole]) {
  document.getElementById("role-filter").value = savedRole;
}

document.getElementById("search").addEventListener("input", applyFilters);
document.getElementById("role-filter").addEventListener("change", (event) => {
  localStorage.setItem("skhynix-role", event.target.value);
  applyFilters();
});
document.getElementById("importance-filter").addEventListener("change", applyFilters);
document.getElementById("sort-filter").addEventListener("change", applyFilters);
document.getElementById("reload").addEventListener("click", loadEverything);

loadEverything();
