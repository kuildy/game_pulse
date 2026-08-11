const state = { section:"hot", games:[], mode:"demo" };

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const copy = {
  hot: ["TRENDING NOW","近日熱門","跨來源訊號計算出的 GAME PULSE 熱門榜。"],
  new: ["NEW RELEASES","近日新上市","過去 30 天內推出的跨平台遊戲。"],
  upcoming: ["COMING SOON","即將推出","未來 90 天預計推出的遊戲。"]
};

function escapeHtml(str=""){
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function platformClass(platforms=[]){
  const text = platforms.join(" ").toLowerCase();
  const set = [];
  if(/pc|windows|linux|mac/.test(text)) set.push("pc");
  if(/playstation|ps5|ps4/.test(text)) set.push("playstation");
  if(/xbox/.test(text)) set.push("xbox");
  if(/switch|nintendo/.test(text)) set.push("nintendo");
  return set;
}

function dateText(d){
  if(!d) return "日期未定";
  const dt = new Date(`${d}T00:00:00`);
  return new Intl.DateTimeFormat("zh-TW",{year:"numeric",month:"2-digit",day:"2-digit"}).format(dt);
}

function card(game, index){
  const image = game.cover_url
    ? `<img src="${escapeHtml(game.cover_url)}" alt="${escapeHtml(game.title)}" loading="lazy" onerror="this.style.display='none'">`
    : `<div class="cover-fallback">${escapeHtml(game.title)}</div>`;

  const genreChips = (game.genres||[]).slice(0,3).map(x=>`<span class="chip">${escapeHtml(x)}</span>`).join("");
  const platformChips = (game.platforms||[]).slice(0,2).map(x=>`<span class="chip">${escapeHtml(x)}</span>`).join("");
  const sourceChips = (game.sources||[]).slice(0,2).map(x=>`<span class="chip source-chip">${escapeHtml(x)}</span>`).join("");

  const stores = (game.stores||[]).slice(0,4).map(s =>
    `<a class="${s.direct?'direct':''}" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.name)} ↗</a>`
  ).join("");

  const metaRight = state.section === "hot"
    ? (game.twitch_rank ? `Twitch #${game.twitch_rank}` : "跨平台")
    : dateText(game.release_date);

  const steamPlayers = game.steam_players !== null && game.steam_players !== undefined
    ? `<div class="player-count"><span class="player-dot"></span><span>Steam</span><strong>${Number(game.steam_players).toLocaleString("zh-TW")}</strong><span>人在線</span></div>`
    : "";

  const detailUrl = `/game/${encodeURIComponent(game.slug || game.game_key)}`;

  return `<article class="game-card" data-index="${index}" data-platform="${platformClass(game.platforms).join(" ")}">
    <div class="game-cover">${image}
      <span class="rank">#${String(index+1).padStart(2,"0")}</span>
      <span class="score">PULSE <b>${Math.round(game.pulse_score||0)}</b></span>
    </div>
    <div class="card-body">
      <div class="meta"><span>${escapeHtml((game.platforms||[])[0] || "Multi-platform")}</span><span>${escapeHtml(metaRight)}</span></div>
      <h3>${escapeHtml(game.title)}</h3>
      ${steamPlayers}
      <div class="summary">${escapeHtml(game.summary || "暫無介紹。")}</div>
      <div class="chips">${genreChips}${platformChips}${sourceChips}</div>
      <div class="store-row">${stores || "<span class='chip'>商店資料整理中</span>"}</div>
      <a class="more-btn detail-link" href="${detailUrl}">查看完整資訊</a>
    </div>
  </article>`;
}

function filteredGames(){
  const q = $("#searchInput").value.trim().toLowerCase();
  const platform = $("#platformFilter").value;
  return state.games.filter(g => {
    const hay = [g.title,...(g.genres||[]),...(g.platforms||[])].join(" ").toLowerCase();
    const p = platformClass(g.platforms);
    return (!q || hay.includes(q)) && (platform==="all" || p.includes(platform));
  });
}

function render(){
  const games = filteredGames();
  $("#gameGrid").innerHTML = games.length
    ? games.map((g,i)=>card(g,i)).join("")
    : `<div class="empty">目前沒有符合搜尋條件的遊戲。</div>`;
  if(state.games[0]) $("#heroScore").textContent = Math.round(state.games[0].pulse_score || 0);
}

function setSectionUI(section){
  const [eye,title,desc] = copy[section];
  $("#sectionEyebrow").textContent = eye;
  $("#sectionTitle").textContent = title;
  $("#sectionDescription").textContent = desc;
  $$("[data-section]").forEach(b=>b.classList.toggle("active", b.dataset.section===section));
}

async function loadSection(section){
  state.section = section;
  setSectionUI(section);
  $("#gameGrid").innerHTML = `<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>`;
  try{
    const r = await fetch(`/api/games?section=${encodeURIComponent(section)}&limit=50`);
    const data = await r.json();
    state.games = data.games || [];
    state.mode = data.mode || "demo";
    render();
  }catch(e){
    $("#gameGrid").innerHTML = `<div class="empty">資料讀取失敗，請確認 Flask 是否正在執行。</div>`;
  }
}

async function loadStatus(){
  try{
    const r = await fetch("/api/status");
    const data = await r.json();
    const live = data.mode === "live";
    $("#modeBadge").textContent = live ? "● LIVE DATA" : "● DEMO MODE";
    $("#modeBadge").className = `mode-badge ${live?"live":"demo"}`;
    const rows = data.sources || [];
    $("#sourceStatus").innerHTML = rows.length ? rows.map(s=>`
      <div class="source-card">
        <div class="head"><b>${escapeHtml(s.source)}</b><i class="status-dot ${escapeHtml(s.status)}"></i></div>
        <p>${escapeHtml(s.message || s.status)}</p>
      </div>`).join("") : `<div class="source-card"><b>尚無更新紀錄</b><p>執行一次更新程式後會顯示來源狀態。</p></div>`;
    $("#lastStatus").textContent = live ? "LIVE SOURCES" : "DEMO DATA";
  }catch(e){}
}

function bindModalButtons(games){
  $$("[data-open]").forEach(btn => btn.addEventListener("click",()=>{
    const g = games[Number(btn.dataset.open)];
    if(!g) return;
    const stores = (g.stores||[]).map(s=>`<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.name)} ↗</a>`).join("");
    $("#modalContent").innerHTML = `
      <span class="micro">GAME DETAILS</span>
      <h2 class="modal-title">${escapeHtml(g.title)}</h2>
      <div class="chips">
        ${(g.platforms||[]).map(x=>`<span class="chip">${escapeHtml(x)}</span>`).join("")}
        ${(g.genres||[]).map(x=>`<span class="chip">${escapeHtml(x)}</span>`).join("")}
      </div>
      <p class="modal-summary">${escapeHtml(g.summary || "暫無詳細介紹。")}</p>
      <div class="formula-row"><b>${Math.round(g.pulse_score||0)}</b><span>GAME PULSE SCORE</span></div>
      ${g.release_date?`<div class="formula-row"><b>◷</b><span>發售日 ${dateText(g.release_date)}</span></div>`:""}
      ${g.steam_players!=null?`<div class="formula-row"><b>PC</b><span>Steam 目前玩家 ${Number(g.steam_players).toLocaleString()}</span></div>`:""}
      <div class="modal-stores">${stores}</div>`;
    $("#modal").classList.add("open");
    $("#modal").setAttribute("aria-hidden","false");
  }));
}

function closeModal(){
  $("#modal").classList.remove("open");
  $("#modal").setAttribute("aria-hidden","true");
}

$$("[data-section]").forEach(b=>b.addEventListener("click",()=>loadSection(b.dataset.section)));
$("#searchInput").addEventListener("input",render);
$("#platformFilter").addEventListener("change",render);
$$("[data-close-modal]").forEach(x=>x.addEventListener("click",closeModal));
$("[data-go-hot]").addEventListener("click",()=>{ loadSection("hot"); $("#games").scrollIntoView({behavior:"smooth"}); });
document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeModal(); });

loadStatus();
loadSection("hot");
