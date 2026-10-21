let allArticles = [];

const ROLE_INFO = {
  "?묒궛湲곗닠": "怨듭젙 ?덉젙?굿룹닔?㉱룹깮?곗꽦쨌?묒궛 ?꾪솚",
  "?묒궛湲곗닠 P&T": "HBM쨌?⑦궎吏빧룻뀒?ㅽ듃 ?묒궛쨌?섏쑉쨌怨듭젙 ?덉젙??,
  "?묒궛愿由?: "TAT쨌WIP쨌蹂묐ぉ쨌?앹궛怨꾪쉷쨌?⑷린",
  "怨듭젙湲곗닠": "怨듭젙 議곌굔쨌Process Window쨌寃고븿쨌誘몄꽭??,
  "?ㅻ퉬湲곗닠": "?λ퉬 媛?숇쪧쨌PM쨌怨좎옣 吏꾨떒쨌?ㅻ퉬 ?덉젙??,
  "?덉쭏/?좊ː??: "遺덈웾 ?먯씤쨌寃??룹떊猶곗꽦쨌?덉쭏 媛쒖꽑",
  "?쒗뭹/?뚯옄": "硫붾え由?援ъ“쨌?깅뒫쨌?꾨젰쨌?쒗뭹 濡쒕뱶留?,
  "IT": "MES쨌?쒖뒪???곌퀎쨌?명봽?셋룸낫?댟룹뾽臾??먮룞??,
  "Data/AI": "?곗씠??遺꾩꽍쨌ML쨌?덉륫쨌理쒖쟻?붋텮I ?쒕퉬??
};

function selectedRole() {
  return document.getElementById("role-filter").value || "?묒궛湲곗닠";
}

function getRoleAnalysis(article, role) {
  const roleData = article.role_analysis?.[role];
  if (roleData) return roleData;

  // v5.0 migration ???곗씠?곌? ?좉퉸 蹂댁씠??寃쎌슦???덉쟾??fallback
  if (role === "?묒궛湲곗닠" && article.job_relevance) {
    return {
      ...article.job_relevance,
      what_you_get: article.takeaway || ""
    };
  }

  return {
    role,
    score: 1,
    reason: "吏곷Т蹂?遺꾩꽍 ?곗씠??媛깆떊 ?湲?,
    dimensions: [],
    matched_keywords: [],
    what_you_get: "Daily News Update媛 ??踰??ㅽ뻾?섎㈃ ??吏곷Т 湲곗? 遺꾩꽍???앹꽦?⑸땲??"
  };
}

async function loadEverything() {
  const status = document.getElementById("status");

  try {
    const [articlesResponse, stateResponse] = await Promise.all([
      fetch("data/articles.json?ts=" + Date.now()),
      fetch("data/state.json?ts=" + Date.now())
    ]);

    if (!articlesResponse.ok) throw new Error("articles.json???쎌? 紐삵뻽?듬땲??");

    allArticles = await articlesResponse.json();
    const state = stateResponse.ok ? await stateResponse.json() : {};

    updateDashboard(state);
    applyFilters();

    status.textContent =
      `?꾩쟻 湲곗궗 ${allArticles.length}媛?쨌 ?좏깮 吏곷Т???곕씪 愿?⑥꽦/WHAT YOU GET??蹂寃쎈맗?덈떎.`;
  } catch (err) {
    status.textContent = "?곗씠?곕? 遺덈윭?ㅼ? 紐삵뻽?듬땲?? " + err.message;
  }
}

function updateDashboard(state) {
  document.getElementById("last-check").textContent =
    formatDateTime(state.last_checked_at) || "?꾩쭅 ?놁쓬";

  document.getElementById("new-count").textContent =
    `${state.last_new_count ?? 0}媛?;

  document.getElementById("total-count").textContent =
    `${state.total_articles ?? allArticles.length}媛?;
}

function updateRoleSummary() {
  const role = selectedRole();
  document.getElementById("role-current").textContent = role;
  document.getElementById("role-description").textContent =
    `${ROLE_INFO[role] || "吏곷Т ?듭떖 ??웾"} 以묒떖?쇰줈 湲곗궗 愿?⑥꽦???됯??⑸땲??`;
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
  return "??.repeat(safe) + "??.repeat(5 - safe);
}

function render(items) {
  const root = document.getElementById("articles");
  const role = selectedRole();
  root.innerHTML = "";

  if (!items.length) {
    root.innerHTML = `<div class="empty">?꾩옱 議곌굔??留욌뒗 湲곗궗媛 ?놁뒿?덈떎.</div>`;
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
      .slice(0, 5)
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
          <span class="date">${escapeHtml(article.published || "?좎쭨 誘명솗??)}</span>
          <span class="category">${escapeHtml(article.category || "General")}</span>
        </div>

        <div class="job-fit">
          <div class="job-fit-label">${escapeHtml(role)} 愿?⑥꽦</div>
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
          <ul>${points || "<li>?듭떖 ?댁슜??異⑸텇??異붿텧?섏? 紐삵뻽?듬땲??</li>"}</ul>
        </section>

        <section class="panel">
          <div class="label">WHY IT MATTERS</div>
          <p>${escapeHtml(article.why_it_matters || "")}</p>
        </section>

        <section class="panel gain-panel">
          <div class="label">WHAT YOU GET 쨌 ${escapeHtml(role)}</div>
          <p>${escapeHtml(relevance.what_you_get || article.takeaway || "")}</p>
          ${matched ? `<div class="match-tags">${matched}</div>` : ""}
        </section>
      </div>

      <div class="bottom">
        <div class="tags">${tags}</div>
        <a class="original" href="${escapeAttr(article.url)}" target="_blank" rel="noopener noreferrer">
          ?먮Ц ?쎄린 ??
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
    `${role} 湲곗? ${filtered.length}媛??쒖떆 쨌 ?꾩쟻 ${allArticles.length}媛?;
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

