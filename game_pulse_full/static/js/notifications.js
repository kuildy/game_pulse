(() => {
  const STORAGE_KEY = "game_pulse_device_id";
  const SHOWN_KEY = "game_pulse_last_browser_notification_id";

  function deviceId(){
    let id = localStorage.getItem(STORAGE_KEY);
    if(!id){
      id = (crypto && crypto.randomUUID)
        ? crypto.randomUUID().replace(/[^A-Za-z0-9_-]/g, "-")
        : `gp-${Date.now()}-${Math.random().toString(36).slice(2,12)}`;
      localStorage.setItem(STORAGE_KEY, id);
    }
    return id;
  }

  async function unread(){
    const r = await fetch(`/api/notifications?device_id=${encodeURIComponent(deviceId())}&unread=1&limit=50`);
    if(!r.ok) return [];
    const data = await r.json();
    return data.notifications || [];
  }

  function updateBadges(count){
    document.querySelectorAll("#notificationBadge,.notification-badge").forEach(el => {
      el.textContent = count > 99 ? "99+" : String(count);
      el.classList.toggle("show", count > 0);
    });
  }

  async function showBrowser(items){
    if(!("Notification" in window) || Notification.permission !== "granted") return;
    const lastShown = Number(localStorage.getItem(SHOWN_KEY) || 0);
    const fresh = items.filter(x => Number(x.id) > lastShown).sort((a,b)=>Number(a.id)-Number(b.id));
    let maxId = lastShown;
    fresh.slice(-3).forEach(item => {
      const n = new Notification(item.title || "GAME PULSE", {body:item.message || "", tag:`gp-${item.id}`});
      n.onclick = () => { window.focus(); if(item.link) window.location.href = item.link; };
      maxId = Math.max(maxId, Number(item.id));
    });
    if(maxId > lastShown) localStorage.setItem(SHOWN_KEY, String(maxId));
  }

  async function refresh(){
    try{
      const items = await unread();
      updateBadges(items.length);
      await showBrowser(items);
      return items;
    }catch(e){ return []; }
  }

  async function requestPermission(){
    if(!("Notification" in window)) return "unsupported";
    const result = await Notification.requestPermission();
    if(result === "granted") await refresh();
    return result;
  }

  window.GamePulseNotify = { deviceId, refresh, requestPermission, updateBadges };
  document.addEventListener("DOMContentLoaded", refresh);
  setInterval(refresh, 60000);
})();
