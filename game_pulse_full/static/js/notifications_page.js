(() => {
  const $ = s => document.querySelector(s);
  const esc = (str="") => String(str).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  if(!window.GamePulseNotify) return;
  const device = GamePulseNotify.deviceId();

  async function load(){
    const [nr,wr] = await Promise.all([
      fetch(`/api/notifications?device_id=${encodeURIComponent(device)}&limit=80`),
      fetch(`/api/watchlist?device_id=${encodeURIComponent(device)}`)
    ]);
    const ndata = nr.ok ? await nr.json() : {notifications:[]};
    const wdata = wr.ok ? await wr.json() : {items:[]};
    renderNotifications(ndata.notifications || []);
    renderWatchlist(wdata.items || []);
    await GamePulseNotify.refresh();
  }

  function renderNotifications(rows){
    const unread = rows.filter(x=>!x.read_at).length;
    $("#unreadCount").textContent = `${unread} 未讀`;
    $("#notificationList").innerHTML = rows.length ? rows.map(n=>`<article class="notification-item ${n.read_at?'':'unread'}" data-id="${n.id}"><div class="notification-kind">${esc(n.kind.toUpperCase())}</div><div><h3>${esc(n.title)}</h3><p>${esc(n.message)}</p><time>${new Date(n.created_at).toLocaleString("zh-TW")}</time></div>${n.link?`<a href="${esc(n.link)}">查看 →</a>`:""}</article>`).join("") : `<div class="notify-empty">目前沒有通知。</div>`;
    document.querySelectorAll(".notification-item.unread").forEach(el=>el.addEventListener("click",()=>markOne(el.dataset.id)));
  }

  function renderWatchlist(rows){
    $("#watchCount").textContent = `${rows.length} 款`;
    $("#watchList").innerHTML = rows.length ? rows.map(row=>{
      const g=row.game||{}; const link=g.slug||g.game_key||row.game_key;
      return `<div class="watch-item"><a href="/game/${encodeURIComponent(link)}"><b>${esc(g.title||row.title)}</b><span>${g.release_date?`上市 ${esc(g.release_date)}`:"追蹤中"}</span></a><div class="watch-flags"><span>${row.notify_release?'上市':''}</span><span>${row.notify_pulse?'PULSE':''}</span><span>${row.notify_steam?'Steam':''}</span><span>${row.notify_news?'News':''}</span></div><button data-unwatch="${esc(row.game_key)}">移除</button></div>`;
    }).join("") : `<div class="notify-empty">尚未追蹤遊戲。到遊戲詳細頁按「追蹤通知」即可加入。</div>`;
    document.querySelectorAll("[data-unwatch]").forEach(btn=>btn.addEventListener("click",()=>unwatch(btn.dataset.unwatch)));
  }

  async function markOne(id){
    await fetch("/api/notifications/read",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:device,id:Number(id)})});
    load();
  }
  async function unwatch(gameKey){
    await fetch(`/api/watch/${encodeURIComponent(gameKey)}`,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:device})});
    load();
  }

  $("#markAllRead").addEventListener("click",async()=>{ await fetch("/api/notifications/read",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:device,all:true})}); load(); });
  $("#enableBrowserNotifications").addEventListener("click",async()=>{ const result=await GamePulseNotify.requestPermission(); $("#enableBrowserNotifications").textContent = result === "granted" ? "瀏覽器通知已允許" : result === "denied" ? "瀏覽器已拒絕通知" : "此瀏覽器不支援"; });
  load();
})();
