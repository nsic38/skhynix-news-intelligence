(() => {
  function esc(s){return String(s ?? "");}
  function tags(a,r){
    const xs=["SK하이닉스","반도체",selectedRole(),...(a.tags||[]),...(r.matched_keywords||[])];
    return [...new Set(xs.map(x=>"#"+esc(x).replace(/[^\p{L}\p{N}]+/gu,"")).filter(x=>x!=="#"))].slice(0,10).join(" ");
  }
  function makeDraft(a){
    const role=selectedRole(), r=getRoleAnalysis(a,role);
    const title=esc(a.title).replace(/\s*[-–—]\s*SK하이닉스 뉴스룸\s*$/i,"").trim();
    const main=a.main_point||a.one_liner||title;
    let pts=(a.key_points||[]).filter(Boolean).slice(0,3);
    if(!pts.length&&main) pts=[main];
    return `[SK하이닉스 뉴스 정리] ${title}

SK하이닉스 뉴스룸의 최신 기사 중 취업 준비와 직무 이해에 참고할 만한 내용을 정리했습니다.

📌 한줄 요약
${main}

✅ 핵심 내용
${pts.map((x,i)=>`${i+1}. ${x}`).join("\n")}

💡 왜 중요한가
${a.why_it_matters||main}

🎯 ${role} 취준 관점
${r.what_you_get||a.takeaway||"기사의 핵심 내용을 직무 관점에서 연결해보면 좋습니다."}

🔎 체크 키워드
${[...(a.tags||[]),...(r.matched_keywords||[])].filter(Boolean).slice(0,8).join(" · ")||"SK하이닉스 · 반도체"}

📎 원문
${a.url}

${tags(a,r)}`;
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
      btn.className="blog-draft-btn"; btn.type="button"; btn.textContent="블로그용 글";
      btn.style.cssText="margin-right:10px;padding:9px 13px;border:1px solid #d5dce6;border-radius:9px;background:white;font-weight:800;cursor:pointer";
      btn.onclick=()=>openDraft(makeDraft(a));
      const orig=card.querySelector(".original"); orig?.parentNode?.insertBefore(btn,orig);
    });
  }
  new MutationObserver(addButtons).observe(document.getElementById("articles"),{childList:true,subtree:true});
  addButtons();
})();