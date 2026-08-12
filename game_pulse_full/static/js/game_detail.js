(() => {
  const identifier = document.body.dataset.gameIdentifier;
  if(!identifier) return;
  const enc = encodeURIComponent(identifier);
  const $ = s => document.querySelector(s);

  let history = [];
  let range = "24h";
  let metric = "pulse_score";
  let watching = false;

  function formatValue(value, key=metric){
    if(value == null || !Number.isFinite(Number(value))) return "—";
    if(key === "pulse_score") return Number(value).toFixed(1);
    return Number(value).toLocaleString("zh-TW");
  }

  function drawChart(){
    const line = $("#historyLine");
    const empty = $("#historyEmpty");
    const svg = $("#historyChart");
    if(!line || !svg) return;
    const rows = history.filter(p => p[metric] != null && Number.isFinite(Number(p[metric])));
    if(rows.length < 2){
      line.setAttribute("points", "");
      empty.style.display = "grid";
      $("#trendCurrent").textContent = rows.length ? formatValue(rows.at(-1)[metric]) : "--";
      $("#trendSummary").textContent = "歷史資料累積中";
      return;
    }
    empty.style.display = "none";
    const values = rows.map(p=>Number(p[metric]));
    const min = Math.min(...values), max = Math.max(...values);
    const spread = Math.max(1, max-min);
    const left=48, right=876, top=20, bottom=242;
    const points = values.map((v,i)=>{
      const x = left + (i/(values.length-1))*(right-left);
      const y = bottom - ((v-min)/spread)*(bottom-top);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    line.setAttribute("points", points);
    const first = values[0], last = values.at(-1), delta = last-first;
    $("#trendCurrent").textContent = formatValue(last);
    const label = metric === "pulse_score" ? "PULSE" : metric === "twitch_viewers" ? "Twitch viewers" : "Steam players";
    $("#trendSummary").textContent = `${range.toUpperCase()} ${label} ${delta>0?"↑":delta<0?"↓":"→"} ${delta>0?"+":""}${formatValue(delta, metric)}`;
  }

  async function loadHistory(){
    try{
      const r = await fetch(`/api/game/${enc}/history?range=${range}`);
      const data = await r.json();
      history = data.points || [];
      drawChart();
    }catch(e){ history=[]; drawChart(); }
  }

  document.querySelectorAll("#trendRange [data-range]").forEach(btn => btn.addEventListener("click",()=>{
    range = btn.dataset.range;
    document.querySelectorAll("#trendRange button").forEach(x=>x.classList.toggle("active",x===btn));
    loadHistory();
  }));
  document.querySelectorAll("#trendMetric [data-metric]").forEach(btn => btn.addEventListener("click",()=>{
    metric = btn.dataset.metric;
    document.querySelectorAll("#trendMetric button").forEach(x=>x.classList.toggle("active",x===btn));
    drawChart();
  }));

  async function loadNews(){
    const target = $("#newsList");
    if(!target) return;
    try{
      const r = await fetch(`/api/game/${enc}/news`);
      const data = await r.json();
      if(!r.ok && data.error) throw new Error(data.error);
      const rows = data.news || [];
      $("#newsSource").textContent = data.source || "News";
      if(!rows.length){
        const publishers = Array.isArray(data.publishers) ? data.publishers : [];
        const publisherNames = publishers.map(p=>p?.name).filter(Boolean);
        const publisherCards = publishers.filter(p=>p?.url).map(p=>`
          <a class="publisher-source-card" href="${escapeHtml(p.url)}" target="_blank" rel="noopener noreferrer">
            <span>發行商官方來源</span>
            <b>${escapeHtml(p.name)}</b>
            <em>前往官方網站 ↗</em>
          </a>`).join("");
        const gameOfficial = data.official_game_url ? `
          <a class="publisher-source-card" href="${escapeHtml(data.official_game_url)}" target="_blank" rel="noopener noreferrer">
            <span>遊戲官方來源</span>
            <b>${escapeHtml(document.querySelector("h1")?.textContent || "官方網站")}</b>
            <em>前往官方網站 ↗</em>
          </a>` : "";
        const publisherLine = publisherNames.length
          ? `<p class="publisher-fallback-copy">發行商：<strong>${escapeHtml(publisherNames.join("、"))}</strong></p>`
          : `<p class="publisher-fallback-copy">目前尚未取得可靠的發行商網站資料。</p>`;
        target.innerHTML = `
          <div class="publisher-fallback">
            <div class="publisher-fallback-head"><span>OFFICIAL SOURCE</span><h3>目前尚無可顯示的 Steam 最新消息</h3></div>
            ${publisherLine}
            <p>GAME PULSE 已改為提供發行商或遊戲官方來源，不會用不明第三方新聞填補空缺。</p>
            <div class="publisher-source-grid">${publisherCards}${gameOfficial}</div>
          </div>`;
        return;
      }
      target.innerHTML = rows.map(n=>{
        const dt = n.published_at ? new Date(n.published_at).toLocaleString("zh-TW",{year:"numeric",month:"2-digit",day:"2-digit"}) : "";
        return `<article class="news-card"><div class="news-meta"><span>${escapeHtml(n.feedlabel||"Steam")}</span><time>${escapeHtml(dt)}</time></div><h3>${escapeHtml(n.title||"Steam News")}</h3><p>${escapeHtml(n.contents||"")}</p><a href="${escapeHtml(n.url||"#")}" target="_blank" rel="noopener noreferrer">閱讀原文 ↗</a></article>`;
      }).join("");
    }catch(e){ target.innerHTML = `<div class="detail-notice">新聞暫時讀取失敗，稍後再試。</div>`; }
  }

  function escapeHtml(str=""){
    return String(str).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  function prefs(){
    return {
      notify_release: $("#notifyRelease")?.checked ?? true,
      notify_pulse: $("#notifyPulse")?.checked ?? true,
      notify_steam: $("#notifySteam")?.checked ?? true,
      notify_news: $("#notifyNews")?.checked ?? true,
    };
  }

  function setWatchUI(sub){
    watching = !!sub;
    const btn = $("#watchToggle");
    if(!btn) return;
    btn.textContent = watching ? "已追蹤・儲存設定" : "追蹤通知";
    btn.classList.toggle("watching", watching);
    const removeBtn = $("#watchRemove");
    if(removeBtn) removeBtn.hidden = !watching;
    if(sub){
      $("#notifyRelease").checked = !!sub.notify_release;
      $("#notifyPulse").checked = !!sub.notify_pulse;
      $("#notifySteam").checked = !!sub.notify_steam;
      $("#notifyNews").checked = !!sub.notify_news;
    }
  }

  async function loadWatch(){
    if(!window.GamePulseNotify) return;
    const device = GamePulseNotify.deviceId();
    try{
      const r = await fetch(`/api/watch/${enc}?device_id=${encodeURIComponent(device)}`);
      const data = await r.json();
      setWatchUI(data.watching ? data.subscription : null);
    }catch(e){}
  }

  $("#watchToggle")?.addEventListener("click", async ()=>{
    if(!window.GamePulseNotify) return;
    const device_id = GamePulseNotify.deviceId();
    try{
      const r = await fetch(`/api/watch/${enc}`,{
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({device_id,...prefs()})
      });
      if(r.ok){ watching=true; setWatchUI({...prefs()}); await GamePulseNotify.refresh(); }
    }catch(e){}
  });

  $("#watchRemove")?.addEventListener("click", async ()=>{
    if(!watching || !window.GamePulseNotify) return;
    const device_id = GamePulseNotify.deviceId();
    const r = await fetch(`/api/watch/${enc}`,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id})});
    if(r.ok){ setWatchUI(null); await GamePulseNotify.refresh(); }
  });

  loadHistory();
  loadNews();
  loadWatch();
})();
