const FAVORITES_KEY = "gamePulse:favorites:v1";
const state = { section:"hot", games:[], mode:"demo", favorites:new Set(), favoritesOnly:false };

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const copy = {
  hot: ["03 · TRENDING NOW","近日熱門","跨來源訊號計算出的 GAME PULSE 熱門榜。"],
  new: ["03 · NEW RELEASES","近日新上市","過去 30 天內推出的跨平台遊戲。"],
  upcoming: ["03 · COMING SOON","即將推出","未來 90 天預計推出的遊戲。"]
};

function escapeHtml(str=""){
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function loadFavorites(){
  try{
    const raw = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
    state.favorites = new Set(Array.isArray(raw) ? raw : []);
  }catch(e){
    state.favorites = new Set();
  }
  updateFavoriteUI();
}

function saveFavorites(){
  try{
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites]));
  }catch(e){}
  updateFavoriteUI();
}

function favoriteKey(game){
  if(game?.game_key) return String(game.game_key);
  if(game?.igdb_id) return `igdb:${game.igdb_id}`;
  if(game?.slug) return `slug:${game.slug}`;
  return `title:${String(game?.title || "").trim().toLowerCase()}`;
}

function isFavorite(game){
  return state.favorites.has(favoriteKey(game));
}

function updateFavoriteUI(){
  $$(".favorite-count").forEach(el => el.textContent = String(state.favorites.size));
  const filter = $("#favoriteFilter");
  if(filter){
    filter.classList.toggle("active", state.favoritesOnly);
    filter.setAttribute("aria-pressed", state.favoritesOnly ? "true" : "false");
  }
}

let favoriteToastTimer = null;
function showFavoriteToast(message){
  const toast = $("#favoriteToast");
  if(!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(favoriteToastTimer);
  favoriteToastTimer = setTimeout(()=>toast.classList.remove("show"), 1800);
}

function toggleFavorite(game){
  const key = favoriteKey(game);
  if(state.favorites.has(key)){
    state.favorites.delete(key);
    showFavoriteToast(`已取消收藏：${game.title}`);
  }else{
    state.favorites.add(key);
    showFavoriteToast(`已收藏：${game.title}`);
  }
  saveFavorites();
  render();
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

function compactNumber(value){
  const n = Number(value);
  if(!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("zh-TW", { notation:"compact", maximumFractionDigits:1 }).format(n);
}

function detailUrl(game){
  return `/game/${encodeURIComponent(game?.slug || game?.game_key || "")}`;
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

function card(game, index, rankNumber){
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
  const gameDetailUrl = detailUrl(game);
  const favorite = isFavorite(game);

  return `<article class="game-card" data-index="${index}" data-platform="${platformClass(game.platforms).join(" ")}">
    <div class="game-cover">${image}
      <span class="rank">#${String(rankNumber || index+1).padStart(2,"0")}</span>
      <button class="favorite-button ${favorite ? "active" : ""}" type="button" data-favorite-key="${escapeHtml(favoriteKey(game))}" aria-label="${favorite ? "取消收藏" : "收藏"}${escapeHtml(game.title)}" title="${favorite ? "取消收藏" : "加入收藏"}">${favorite ? "♥" : "♡"}</button>
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
      <a class="more-btn detail-link" href="${gameDetailUrl}">查看完整資訊</a>
    </div>
  </article>`;
}

function populateGenreFilter(){
  const select = $("#genreFilter");
  if(!select) return;
  const current = select.value || "all";
  const genres = [...new Set(state.games.flatMap(g => g.genres || []).filter(Boolean))]
    .sort((a,b)=>String(a).localeCompare(String(b), "zh-Hant"));
  select.innerHTML = `<option value="all">全部類型</option>` + genres.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join("");
  select.value = genres.includes(current) ? current : "all";
}

function filteredGames(){
  const q = $("#searchInput").value.trim().toLowerCase();
  const platform = $("#platformFilter").value;
  const genre = $("#genreFilter")?.value || "all";
  return state.games.filter(g => {
    const hay = [g.title,...(g.genres||[]),...(g.platforms||[])].join(" ").toLowerCase();
    const p = platformClass(g.platforms);
    const genreMatch = genre === "all" || (g.genres || []).includes(genre);
    const favoriteMatch = !state.favoritesOnly || isFavorite(g);
    return (!q || hay.includes(q)) && (platform === "all" || p.includes(platform)) && genreMatch && favoriteMatch;
  });
}

function render(){
  const games = filteredGames();
  $("#gameGrid").innerHTML = games.length
    ? games.map(g => {
        const originalIndex = state.games.indexOf(g);
        return card(g, originalIndex, originalIndex + 1);
      }).join("")
    : `<div class="empty">${state.favoritesOnly && state.favorites.size === 0 ? "你還沒有收藏任何遊戲。點卡片上的 ♡ 就能加入收藏。" : "目前沒有符合搜尋條件的遊戲。"}</div>`;

  const count = $("#resultCount");
  if(count) count.textContent = `顯示 ${games.length} / ${state.games.length} 款`;
  if(state.games[0]) $("#heroScore").textContent = Math.round(state.games[0].pulse_score || 0);
  updateFavoriteUI();
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
    populateGenreFilter();
    render();
  }catch(e){
    $("#gameGrid").innerHTML = `<div class="empty">資料讀取失敗，請確認 Flask 是否正在執行。</div>`;
  }
}


function summaryItem({eyebrow, icon, title, value, note, game}){
  const href = game ? detailUrl(game) : "#games";
  return `<a class="today-summary-card" href="${href}">
    <div class="today-summary-top"><span>${escapeHtml(icon)}</span><small>${escapeHtml(eyebrow)}</small></div>
    <h3>${escapeHtml(title)}</h3>
    <strong>${escapeHtml(value)}</strong>
    <p>${escapeHtml(note)}</p>
  </a>`;
}

async function loadTodaySummary(){
  const grid = $("#todaySummaryGrid");
  const meta = $("#todaySummaryMeta");
  if(!grid || !meta) return;
  try{
    const [hotResponse, radarResponse] = await Promise.all([
      fetch("/api/games?section=hot&limit=50"),
      fetch("/api/radar?limit=1&window=12")
    ]);
    if(!hotResponse.ok) throw new Error(`HTTP ${hotResponse.status}`);
    const hotData = await hotResponse.json();
    const radarData = radarResponse.ok ? await radarResponse.json() : {items:[]};
    const games = hotData.games || [];
    if(!games.length) throw new Error("No games");

    const hottest = games[0];
    const twitchTop = games.filter(g => Number.isFinite(Number(g.twitch_viewers)))
      .sort((a,b)=>Number(b.twitch_viewers)-Number(a.twitch_viewers))[0];
    const steamTop = games.filter(g => Number.isFinite(Number(g.steam_players)) && Number(g.steam_players) > 0)
      .sort((a,b)=>Number(b.steam_players)-Number(a.steam_players))[0];
    const radarTop = (radarData.items || [])[0];

    const items = [
      summaryItem({
        eyebrow:"HOT NOW", icon:"🔥", title:hottest.title,
        value:`PULSE ${Math.round(hottest.pulse_score || 0)}`,
        note:"目前 GAME PULSE 熱度最高", game:hottest
      }),
      radarTop ? summaryItem({
        eyebrow:"RADAR PICK", icon:"📡", title:radarTop.title,
        value:`RADAR ${Math.round(radarTop.radar_score || 0)}`,
        note:radarTop.reason || "近期訊號正在加速", game:radarTop
      }) : summaryItem({
        eyebrow:"RADAR PICK", icon:"📡", title:"RADAR 資料累積中",
        value:"觀察中", note:"累積更多歷史快照後顯示黑馬"
      }),
      twitchTop ? summaryItem({
        eyebrow:"TWITCH WATCH", icon:"👀", title:twitchTop.title,
        value:`${compactNumber(twitchTop.twitch_viewers)} viewers`,
        note:twitchTop.twitch_channels != null ? `${compactNumber(twitchTop.twitch_channels)} 個直播頻道` : "目前 Twitch 關注最高", game:twitchTop
      }) : summaryItem({eyebrow:"TWITCH WATCH",icon:"👀",title:"Twitch 資料整理中",value:"—",note:"即時觀看資料暫缺"}),
      steamTop ? summaryItem({
        eyebrow:"STEAM ACTIVE", icon:"🎮", title:steamTop.title,
        value:`${compactNumber(steamTop.steam_players)} players`,
        note:"目前 Steam 在線最高", game:steamTop
      }) : summaryItem({eyebrow:"STEAM ACTIVE",icon:"🎮",title:"Steam 資料整理中",value:"—",note:"即時玩家資料暫缺"})
    ];

    grid.innerHTML = items.join("");
    const updatedTimes = games.map(g => Date.parse(g.updated_at || "")).filter(Number.isFinite);
    const updated = updatedTimes.length ? new Date(Math.max(...updatedTimes)) : new Date();
    const day = new Intl.DateTimeFormat("zh-TW", {month:"long", day:"numeric", weekday:"short"}).format(new Date());
    const time = new Intl.DateTimeFormat("zh-TW", {hour:"2-digit", minute:"2-digit", hour12:false}).format(updated);
    meta.textContent = `${day} · 資料 ${time} 更新`;
  }catch(e){
    grid.innerHTML = `<div class="today-summary-empty">今日摘要暫時無法整理，熱門榜與其他功能仍可正常使用。</div>`;
    meta.textContent = "稍後再試";
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

    // 首頁只顯示一般使用者需要知道的三個主要來源。
    // IGDB Match / Twitch Filter / Steam CCU 等完整技術狀態仍保留在 Admin。
    const sourceDefs = [
      { key:"IGDB", label:"IGDB", description:"遊戲資訊・發售日期・平台資料" },
      { key:"Twitch", label:"Twitch", description:"即時觀看・熱門趨勢" },
      { key:"Steam", label:"Steam", description:"即時玩家・遊戲消息" },
    ];

    const statusText = status => ({
      ok: "正常",
      partial: "部分可用",
      error: "暫時異常",
      demo: "示範資料",
      optional: "部分功能未啟用",
    }[status] || "待確認");

    const mainSources = sourceDefs.map(def => {
      const source = rows.find(s => s.source === def.key)
        || rows.find(s => String(s.source || "").startsWith(def.key));
      return {
        ...def,
        status: source?.status || "unknown",
      };
    });

    $("#sourceStatus").innerHTML = mainSources.map(s=>`
      <div class="source-card">
        <div class="head">
          <b>${escapeHtml(s.label)}</b>
          <i class="status-dot ${escapeHtml(s.status)}"></i>
        </div>
        <p>${escapeHtml(s.description)} · ${escapeHtml(statusText(s.status))}</p>
      </div>`).join("");

    $("#lastStatus").textContent = live ? "3 MAIN SOURCES" : "DEMO DATA";
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
$("#genreFilter")?.addEventListener("change",render);
$("#favoriteFilter")?.addEventListener("click",()=>{
  state.favoritesOnly = !state.favoritesOnly;
  render();
});
$("#clearFilters")?.addEventListener("click",()=>{
  $("#searchInput").value = "";
  $("#platformFilter").value = "all";
  if($("#genreFilter")) $("#genreFilter").value = "all";
  state.favoritesOnly = false;
  render();
});
$("#gameGrid")?.addEventListener("click", e => {
  const button = e.target.closest("[data-favorite-key]");
  if(!button) return;
  e.preventDefault();
  e.stopPropagation();
  const game = state.games.find(g => favoriteKey(g) === button.dataset.favoriteKey);
  if(game) toggleFavorite(game);
});
$$("[data-close-modal]").forEach(x=>x.addEventListener("click",closeModal));


// Collapsible PULSE RADAR / PULSE WHY
const FEATURE_COLLAPSE_KEY = "gamePulseFeatureCollapseV1";

function readFeatureCollapseState(){
  try{
    return JSON.parse(localStorage.getItem(FEATURE_COLLAPSE_KEY) || "{}");
  }catch(_){
    return {};
  }
}

function saveFeatureCollapseState(state){
  try{ localStorage.setItem(FEATURE_COLLAPSE_KEY, JSON.stringify(state)); }catch(_){}
}

function setFeatureExpanded(name, expanded, persist=true){
  const section = document.querySelector(`[data-collapsible="${name}"]`);
  const button = document.querySelector(`[data-toggle-feature="${name}"]`);
  if(!section || !button) return;
  section.classList.toggle("is-collapsed", !expanded);
  button.setAttribute("aria-expanded", expanded ? "true" : "false");
  if(persist){
    const state = readFeatureCollapseState();
    state[name] = expanded;
    saveFeatureCollapseState(state);
  }
}

function initFeatureCollapsibles(){
  const saved = readFeatureCollapseState();
  ["radar", "why"].forEach(name => {
    const expanded = saved[name] !== false;
    setFeatureExpanded(name, expanded, false);
    document.querySelector(`[data-toggle-feature="${name}"]`)?.addEventListener("click", () => {
      const button = document.querySelector(`[data-toggle-feature="${name}"]`);
      const next = button?.getAttribute("aria-expanded") !== "true";
      setFeatureExpanded(name, next, true);
    });
  });
}

function expandFeatureForNavigation(name){
  setFeatureExpanded(name, true, true);
}

function scrollToSection(selector){
  const target = $(selector);
  if(target) target.scrollIntoView({behavior:"smooth", block:"start"});
}

const hotButton = $("[data-go-hot]");
if(hotButton){
  hotButton.addEventListener("click",()=>{
    loadSection("hot");
    scrollToSection("#games");
  });
}

const radarButton = $("[data-go-radar]");
if(radarButton){
  radarButton.addEventListener("click",()=>{
    expandFeatureForNavigation("radar");
    scrollToSection("#radar");
  });
}

function openFavorites(){
  state.favoritesOnly = true;
  updateFavoriteUI();
  scrollToSection("#games");
  render();
}

$("#favoriteNavButton")?.addEventListener("click", openFavorites);
$$("[data-favorites-nav]").forEach(button => button.addEventListener("click", openFavorites));

document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeModal(); });


$$('a[href="#radar"]').forEach(link => link.addEventListener("click",()=>expandFeatureForNavigation("radar")));
$$('a[href="#why"]').forEach(link => link.addEventListener("click",()=>expandFeatureForNavigation("why")));

initFeatureCollapsibles();

loadFavorites();
loadStatus();
loadTodaySummary();
loadRadar();
loadWhy();
loadSection("hot");
