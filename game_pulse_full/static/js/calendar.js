(() => {
  const $ = s => document.querySelector(s);
  let cursor = new Date(); cursor.setDate(1); cursor.setHours(0,0,0,0);
  const escapeHtml = (str="") => String(str).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const key = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;

  function title(){ return new Intl.DateTimeFormat("zh-TW",{year:"numeric",month:"long"}).format(cursor); }
  function dateLink(g){ return `/game/${encodeURIComponent(g.slug || g.game_key)}`; }

  async function load(){
    $("#monthTitle").textContent = title();
    const platform = $("#calendarPlatform").value;
    const r = await fetch(`/api/calendar?month=${key(cursor)}&platform=${encodeURIComponent(platform)}`);
    const data = await r.json();
    render(data.games || []);
  }

  function render(games){
    const year=cursor.getFullYear(), month=cursor.getMonth();
    const firstDay = new Date(year,month,1).getDay();
    const days = new Date(year,month+1,0).getDate();
    const byDay = {};
    games.forEach(g=>{ const d=Number((g.release_date||"").slice(8,10)); if(d) (byDay[d] ||= []).push(g); });
    const cells=[];
    for(let i=0;i<firstDay;i++) cells.push(`<div class="calendar-day muted"></div>`);
    for(let d=1;d<=days;d++){
      const items = byDay[d] || [];
      cells.push(`<div class="calendar-day ${items.length?'has-games':''}"><div class="day-number">${d}</div><div class="day-games">${items.slice(0,3).map(g=>`<a href="${dateLink(g)}" title="${escapeHtml(g.title)}">${g.cover_url?`<img src="${escapeHtml(g.cover_url)}" alt="">`:''}<span>${escapeHtml(g.title)}</span></a>`).join("")}${items.length>3?`<small>+${items.length-3} 款</small>`:""}</div></div>`);
    }
    $("#calendarGrid").innerHTML = cells.join("");
    $("#calendarCount").textContent = `${games.length} 款`;
    $("#calendarList").innerHTML = games.length ? games.map(g=>`<a class="calendar-game-row" href="${dateLink(g)}"><div>${g.cover_url?`<img src="${escapeHtml(g.cover_url)}" alt="">`:''}</div><div><b>${escapeHtml(g.title)}</b><span>${escapeHtml(g.release_date||"日期未定")}</span><small>${escapeHtml((g.platforms||[]).slice(0,4).join(" · "))}</small></div></a>`).join("") : `<div class="calendar-empty">這個月份目前沒有已同步的發售資料。</div>`;
  }

  $("#prevMonth").addEventListener("click",()=>{ cursor.setMonth(cursor.getMonth()-1); load(); });
  $("#nextMonth").addEventListener("click",()=>{ cursor.setMonth(cursor.getMonth()+1); load(); });
  $("#calendarPlatform").addEventListener("change",load);
  load();
})();
