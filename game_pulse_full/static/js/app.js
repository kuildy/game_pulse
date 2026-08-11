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

function trendSparkline(points=[]){
  const values = (points || [])
    .map(p => Number(p.pulse_score))
    .filter(Number.isFinite);
  if(values.length < 2) return "";

  const width = 112;
  const height = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1, max - min);
  const coords = values.map((value, i) => {
    const x = values.length === 1 ? 0 : (i / (values.length - 1)) * width;
    const y = height - ((value - min) / range) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return `<svg class="trend-sparkline" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${coords}"></polyline></svg>`;
}

function trend24h(game){
  if(state.section !== "hot") return "";

  if(!game.trend_ready){
    const samples = (game.trend_points || []).length;
    return `<div class="trend-box pending"><div><span>24H PULSE</span><strong>建立中</strong></div>${samples > 1 ? trendSparkline(game.trend_points) : `<small>累積更多更新快照後顯示</small>`}</div>`;
  }

  const delta = Number(game.trend_24h_delta || 0);
  const direction = game.trend_24h_direction || "flat";
  const arrow = direction === "up" ? "↑" : direction === "down" ? "↓" : "→";
  const sign = delta > 0 ? "+" : "";
  const pct = game.trend_24h_percent != null
    ? `<small>${Number(game.trend_24h_percent) > 0 ? "+" : ""}${Number(game.trend_24h_percent).toFixed(1)}%</small>`
    : "";

  return `<div class="trend-box ${direction}"><div><span>24H PULSE</span><strong>${arrow} ${sign}${delta.toFixed(1)}</strong>${pct}</div>${trendSparkline(game.trend_points)}</div>`;
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

  const twitchViewers = game.twitch_viewers !== null && game.twitch_viewers !== undefined
    ? `<div class="player-count twitch"><span class="player-dot"></span><span>Twitch</span><strong>${Number(game.twitch_viewers).toLocaleString("zh-TW")}</strong><span>人觀看</span>${game.twitch_channels != null ? `<em>${Number(game.twitch_channels).toLocaleString("zh-TW")} 頻道</em>` : ""}</div>`
    : "";

  const steamPlayers = game.steam_players !== null && game.steam_players !== undefined
    ? `<div class="player-count steam"><span class="player-dot"></span><span>Steam</span><strong>${Number(game.steam_players).toLocaleString("zh-TW")}</strong><span>人在線</span></div>`
    : "";

  const liveSignals = twitchViewers || steamPlayers
    ? `<div class="live-signal-stack">${twitchViewers}${steamPlayers}</div>`
    : "";

  const trendSignal = trend24h(game);
  const detailUrl = `/game/${encodeURIComponent(game.slug || game.game_key)}`;

  return `<article class="game-card" data-index="${index}" data-platform="${platformClass(game.platforms).join(" ")}">
    <div class="game-cover">${image}
      <span class="rank">#${String(index+1).padStart(2,"0")}</span>
      <span class="score">PULSE <b>${Math.round(game.pulse_score||0)}</b></span>
    </div>
    <div class="card-body">
      <div class="meta"><span>${escapeHtml((game.platforms||[])[0] || "Multi-platform")}</span><span>${escapeHtml(metaRight)}</span></div>
      <h3>${escapeHtml(game.title)}</h3>
      ${liveSignals}
      ${trendSignal}
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


function radarGrowth(value, suffix="%"){
  if(value === null || value === undefined || !Number.isFinite(Number(value))){
    return `<span class="radar-metric muted">資料建立中</span>`;
  }
  const n = Number(value);
  const arrow = n > 0 ? "↑" : n < 0 ? "↓" : "→";
  const sign = n > 0 ? "+" : "";
  return `<span class="radar-metric ${n > 0 ? "up" : n < 0 ? "down" : "flat"}">${arrow} ${sign}${n.toFixed(1)}${suffix}</span>`;
}

function radarCard(item, index){
  const image = item.cover_url
    ? `<img src="${escapeHtml(item.cover_url)}" alt="${escapeHtml(item.title)}" loading="lazy" onerror="this.style.display='none'">`
    : `<div class="radar-cover-fallback">${escapeHtml(item.title)}</div>`;
  const detailUrl = `/game/${encodeURIComponent(item.slug || item.game_key)}`;
  const pulseDelta = Number(item.pulse_delta || 0);
  const pulseSign = pulseDelta > 0 ? "+" : "";
  return `<article class="radar-card ${escapeHtml((item.level || "watch").toLowerCase())}">
    <a class="radar-cover" href="${detailUrl}">${image}<span class="radar-order">#${index + 1}</span></a>
    <div class="radar-body">
      <div class="radar-topline"><span class="radar-level">${escapeHtml(item.level_zh || item.level || "WATCH")}</span><strong>RADAR ${Number(item.radar_score || 0).toFixed(0)}</strong></div>
      <h3><a href="${detailUrl}">${escapeHtml(item.title)}</a></h3>
      <p>${escapeHtml(item.reason || "近期訊號正在升溫")}</p>
      <div class="radar-pulse-row"><span>PULSE ${Number(item.pulse_score || 0).toFixed(0)}</span><b>${pulseDelta > 0 ? "↑" : pulseDelta < 0 ? "↓" : "→"} ${pulseSign}${pulseDelta.toFixed(1)}</b><small>${Number(item.window_hours || 0).toFixed(1)}h</small></div>
      <div class="radar-signals">
        <div><span>Twitch</span>${radarGrowth(item.twitch_growth_percent)}</div>
        <div><span>Steam</span>${radarGrowth(item.steam_growth_percent)}</div>
      </div>
    </div>
  </article>`;
}

async function loadRadar(){
  const grid = $("#radarGrid");
  const note = $("#radarNote");
  if(!grid || !note) return;
  try{
    const r = await fetch("/api/radar?limit=6&window=12");
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const items = data.items || [];
    if(items.length){
      grid.innerHTML = items.map(radarCard).join("");
      note.textContent = data.disclaimer || "RADAR 依近期多來源成長訊號計算。";
    }else{
      grid.innerHTML = `<div class="radar-empty">📡 PULSE RADAR 正在累積歷史快照。至少需要兩次、間隔約 1 小時以上的更新資料後，才會開始判斷升溫訊號。</div>`;
      note.textContent = data.pending_games ? `目前有 ${data.pending_games} 款遊戲等待更多歷史資料。` : "目前沒有明顯的早期升溫訊號。";
    }
  }catch(e){
    grid.innerHTML = `<div class="radar-empty">RADAR 暫時無法讀取，熱門榜仍可正常使用。</div>`;
    note.textContent = "";
  }
}


function whyMetric(metric){
  const dir = metric.direction || "flat";
  return `<div class="why-metric ${escapeHtml(dir)}"><span>${escapeHtml(metric.label || "")}</span><strong>${escapeHtml(metric.value || "—")}</strong></div>`;
}

function whyCard(item){
  const detailUrl = `/game/${encodeURIComponent(item.slug || item.game_key || "")}`;
  const image = item.cover_url
    ? `<img src="${escapeHtml(item.cover_url)}" alt="${escapeHtml(item.title)}" loading="lazy">`
    : `<div class="why-cover-fallback">${escapeHtml(item.title)}</div>`;
  const evidence = (item.evidence || []).slice(0,4).map(whyMetric).join("");
  return `<article class="why-card ${escapeHtml((item.why_code || "steady").toLowerCase())}">
    <a class="why-cover" href="${detailUrl}">${image}<span class="why-icon">${escapeHtml(item.icon || "◆")}</span></a>
    <div class="why-body">
      <div class="why-topline"><span class="why-type">${escapeHtml(item.type_zh || "熱度解讀")}</span><strong>可信度 ${Number(item.confidence || 0).toFixed(0)}%</strong></div>
      <h3><a href="${detailUrl}">${escapeHtml(item.title)}</a></h3>
      <h4>${escapeHtml(item.headline || "近期熱度出現變化")}</h4>
      <p>${escapeHtml(item.explanation || "GAME PULSE 正在分析多來源訊號。")}</p>
      <div class="why-evidence">${evidence}</div>
    </div>
  </article>`;
}

async function loadWhy(){
  const grid = $("#whyGrid");
  const note = $("#whyNote");
  if(!grid || !note) return;
  try{
    const r = await fetch("/api/why?limit=6&window=24");
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const items = data.items || [];
    if(items.length){
      grid.innerHTML = items.map(whyCard).join("");
      note.textContent = data.disclaimer || "PULSE WHY 依近期歷史訊號解讀熱度型態。";
    }else{
      grid.innerHTML = `<div class="why-empty">🔥 PULSE WHY 正在累積比較資料。至少需要兩次、間隔約 1 小時以上的歷史快照後，才會開始解讀熱度來源。</div>`;
      note.textContent = data.pending_games ? `目前有 ${data.pending_games} 款遊戲等待更多歷史資料。` : "目前沒有足夠的變化可解讀。";
    }
  }catch(e){
    grid.innerHTML = `<div class="why-empty">PULSE WHY 暫時無法讀取，其他排行榜與 RADAR 不受影響。</div>`;
    note.textContent = "";
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
loadRadar();
loadWhy();
loadSection("hot");
