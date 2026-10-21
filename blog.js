(() => {
  function esc(s){return String(s ?? "");}
  function tags(a,r){
    const xs=["SK하이닉스","반도체",selectedRole(),...(a.tags||[]),...(r.matched_keywords||[])];
    return [...new Set(xs.map(x=>"#"+esc(x).replace(/[^\p{L}\p{N}]+/gu,"")).filter(x=>x!=="#"))].slice(0,10).join(" ");
  }
  function makeDraft(a){
    const role = selectedRole();
    const r = getRoleAnalysis(a, role);

    const title = esc(a.title)
      .replace(/\s*[-–—]\s*SK하이닉스 뉴스룸\s*$/i, "")
      .trim();

    const published = esc(a.published || "날짜 미확인");

    const main =
      a.main_point ||
      a.one_liner ||
      title;

    let pts = (a.key_points || [])
      .filter(x => String(x || "").trim())
      .slice(0, 5);

    const why =
      String(a.why_it_matters || "").trim();

    const career =
      r.what_you_get ||
      a.takeaway ||
      "기사의 핵심 내용을 직무 관점에서 연결해보면 좋습니다.";

    const keywordList = [
      ...(a.tags || []),
      ...(r.matched_keywords || [])
    ]
      .filter(Boolean)
      .filter((x, i, arr) => arr.indexOf(x) === i)
      .slice(0, 10);

    return `SK하이닉스 뉴스 기사 정리 - ${title}

[SK하이닉스 뉴스 정리] ${title}

${published} | SK하이닉스

📌 한줄 요약
${main}

✅ 핵심 내용
${pts.map((x, i) => `${i + 1}. ${x}`).join("\n")}

💡 왜 중요한가
${why}

🎯 ${role} 취준 관점
${career}

🔎 체크 키워드
${keywordList.join(" · ") || "SK하이닉스 · 반도체"}

📎 원문
[${title} – SK hynix Newsroom](${a.url})

${tags(a, r)}`;
  }

  function openDraft(text){
    document.querySelector(".blog-pop")?.remove();
    const bg=document.createElement("div");
    bg.className="blog-pop";
    bg.style.cssText="position:fixed;inset:0;background:#0008;z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px";
    const box=document.createElement("div");
    box.style.cssText="background:#fff;width:min(820px,100%);max-height:90vh;overflow:auto;border-radius:16px;padding:20px";
    const h=document.createElement("h3"); h.textContent="네이버 블로그용 자동 포맷";
    const ta=document.createElement("textarea");
    ta.value=text; ta.style.cssText="width:100%;min-height:470px;box-sizing:border-box;padding:14px;border:1px solid #ccd3dd;border-radius:10px;line-height:1.7;font:inherit";
    const row=document.createElement("div"); row.style.cssText="display:flex;justify-content:flex-end;gap:10px;margin-top:12px";
    const close=document.createElement("button"); close.textContent="닫기";
    const copy=document.createElement("button"); copy.textContent="전체 복사";
    [close,copy].forEach(b=>b.style.cssText="padding:10px 14px;border-radius:9px;border:1px solid #ccd3dd;font-weight:700;cursor:pointer");
    copy.style.cssText+=";background:#0b1730;color:white";
    close.onclick=()=>bg.remove();
    copy.onclick=async()=>{try{await navigator.clipboard.writeText(ta.value);copy.textContent="복사 완료";setTimeout(()=>copy.textContent="전체 복사",1500)}catch(e){ta.select();document.execCommand("copy");copy.textContent="복사 완료"}};
    bg.onclick=e=>{if(e.target===bg)bg.remove()};
    row.append(close,copy); box.append(h,ta,row); bg.append(box); document.body.append(bg); ta.focus();
  }
  function addButtons(){
    document.querySelectorAll("#articles .card").forEach(card=>{
      if(card.querySelector(".blog-draft-btn")) return;
      const link=card.querySelector("h2 a"); if(!link) return;
      const a=allArticles.find(x=>x.url===link.href||x.url===link.getAttribute("href")); if(!a) return;
      const btn=document.createElement("button");
      btn.className="blog-draft-btn";
      btn.type="button";

      const summaryReady =
        Array.isArray(a.key_points) &&
        a.key_points.filter(x => String(x || "").trim()).length > 0 &&
        Boolean(String(a.why_it_matters || "").trim());

      btn.textContent = summaryReady
        ? "블로그용 글"
        : "블로그용 글 · 분석 보류";

      btn.style.cssText="margin-right:10px;padding:9px 13px;border:1px solid #d5dce6;border-radius:9px;background:white;color:#0b1730;font-weight:800;cursor:pointer";

      if (summaryReady) {
        btn.onclick=()=>openDraft(makeDraft(a));
      } else {
        btn.disabled=true;
        btn.title="기사 본문을 충분히 추출하지 못해 블로그 초안을 만들지 않습니다.";
        btn.style.opacity="0.5";
        btn.style.cursor="not-allowed";
      }
      const orig=card.querySelector(".original"); orig?.parentNode?.insertBefore(btn,orig);
    });
  }
  new MutationObserver(addButtons).observe(document.getElementById("articles"),{childList:true,subtree:true});
  addButtons();
})();