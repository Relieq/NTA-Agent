import { getJSON, postJSON, usePolling, ago, useHidden } from "../api.js";
import ControlBar from "./ControlBar.js";
const { ref, onMounted } = window.Vue;
export default {
 components:{ ControlBar },
 setup(){
  const snap=ref("…");
  const health=ref(null);
  const alerts=ref(null);
  const upd=ref(null); const updMsg=ref("");
  const hid=useHidden("upd");   // "✖ Ẩn" on the new-version banner: hidden for that version only
  onMounted(async ()=>{ upd.value=await getJSON("/api/update/check"); });
  async function doUpdate(){
   if(!confirm("Cập nhật lên "+upd.value.update.version+"? Agent sẽ dừng, app tự khởi động lại (~1 phút).")) return;
   const r=await postJSON("/api/update/apply",{});
   if(!(r&&r.ok)){ updMsg.value=(r&&r.error)||"Lỗi"; return; }
   // follow the update instead of a blind reload: wait for the app to come back and
   // compare its version; the old version back = the update was aborted -> show why
   const want=upd.value.update.version, t0=Date.now(); let wentDown=false;
   updMsg.value="Đang cập nhật…";
   const poll=async ()=>{
    let v=null; try{ const x=await fetch("/api/app"); v=x.ok ? await x.json() : null; }catch(e){ v=null; }
    if(!v){ wentDown=true; }
    else if(v.version===want){ updMsg.value="Đã cập nhật lên "+want+" — đang tải lại…"; setTimeout(()=>location.reload(),1500); return; }
    else if(wentDown){ const lg=await getJSON("/api/update/log");
     updMsg.value="Cập nhật THẤT BẠI, app đã mở lại bản "+v.version+". "+(((lg&&lg.lines)||[]).slice(-2).join(" | ")); return; }
    if(Date.now()-t0>180000){ updMsg.value="Quá lâu chưa thấy app mở lại — xem file updater.log trong thư mục dữ liệu (%LOCALAPPDATA%/NTA-Agent/run)"; return; }
    setTimeout(poll,2000);
   };
   setTimeout(poll,2000);
  }
  // between matches: the agent waits for the match the account applied to (or for the
  // player to apply to one — never on its own)
  const lobby=ref(null); const lobbyPick=ref(null); const lobbyMsg=ref("");
  const roomName=(t)=>({0:"Tự do",1:"Tân thủ",2:"Xếp hạng"})[t] ?? String(t);
  const when=(s)=> s ? new Date(s*1000).toLocaleString("vi-VN",{hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit"}) : "?";
  const optLabel=(t)=>{
   const r=((lobby.value&&lobby.value.rooms)||[]).find(x=>x.room_type===t);
   return roomName(t)+(r&&r.opens_at ? " — mở "+when(r.opens_at) : "");
  };
  async function applyMatch(){
   const t=lobbyPick.value;
   if(t===null || t===undefined){ lobbyMsg.value="Chọn chế độ trận trước"; return; }
   if(!confirm("Đăng ký trận "+roomName(t)+"? Sau khi đăng ký, agent sẽ tự vào khi trận mở.")) return;
   const r=await postJSON("/api/lobby/apply",{room_type:t});
   lobbyMsg.value=(r&&r.ok) ? "Đã gửi — agent đăng ký ở lần kiểm tra tới (vài giây)" : ((r&&r.error)||"Lỗi");
  }
  usePolling(async ()=>{
   const lb=await getJSON("/api/lobby");
   lobby.value=lb;
   if(lb && lb.state==="not_applied" && lobbyPick.value===null && (lb.can_play||[]).length) lobbyPick.value=lb.can_play[0];
   const s=await getJSON("/api/state");
   snap.value=(s&&s.ok)? ("snapshot "+ago(s.updated_at)) : "chưa có snapshot";
   health.value=await getJSON("/api/health");
   alerts.value=await getJSON("/api/alerts");
  }, 2000);
  const hlabel=(h)=>{
   if(!h) return "";
   if(h.degraded) return "⚠ mất kết nối (thử lại…)";
   const age=Math.round(h.last_activity_age||0);
   const rc=h.recover_count?(" · đã phục hồi "+h.recover_count+"×"):"";
   return "🟢 kết nối OK · "+age+"s trước"+rc;
  };
  const hcolor=(h)=> h&&h.degraded ? "#da3633" : "#199e70";
  const eta=(s)=>{ s=Math.round(s||0); return s>=60 ? Math.floor(s/60)+"p"+(s%60)+"s" : s+"s"; };
  // between matches the alerts.json of the OLD match is stale: hide it while waiting
  const waiting=window.Vue.computed(()=>!!(lobby.value && lobby.value.agent_running && ['applied','not_applied'].includes(lobby.value.state)));
  return { waiting, snap, health, hlabel, hcolor, alerts, eta, upd, updMsg, doUpdate, hid,
           lobby, lobbyPick, lobbyMsg, roomName, when, applyMatch, optLabel };
 },
 template:`<div><header><div><h1>NTA Agent</h1>
   <div class="muted" style="font-size:12px">{{ snap }}</div>
   <div v-if="health" style="font-size:12px" :style="{color:hcolor(health)}">{{ hlabel(health) }}</div></div>
  <ControlBar/></header>
  <div v-if="upd && upd.update && !hid.isHidden(upd.update.version)" role="status"
   style="background:#0d2a45;border:1px solid #58a6ff;color:#b6d8ff;padding:6px 12px;margin:0 16px 8px;border-radius:6px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
   <b>⬆ Có bản mới {{ upd.update.version }}</b><span>(đang dùng {{ upd.current }})</span>
   <button @click="doUpdate">Cập nhật</button>
   <a v-if="upd.update.page" :href="upd.update.page" target="_blank" rel="noopener" style="color:#b6d8ff">xem thay đổi</a>
   <button @click="hid.hide(upd.update.version)" title="Ẩn thông báo này (bản mới hơn sẽ hiện lại)" style="margin-left:auto">✖ Ẩn</button>
   <span v-if="updMsg">{{ updMsg }}</span></div>
  <div v-if="lobby && lobby.agent_running && lobby.state==='applied'" role="status"
   style="background:#0d2a45;border:1px solid #58a6ff;color:#b6d8ff;padding:6px 12px;margin:0 16px 8px;border-radius:6px">
   <b>⏳ Đang chờ trận mở:</b> đã đăng ký trận <b>{{ lobby.room_name }}</b>, mở lúc <b>{{ when(lobby.opens_at) }}</b>.
   Agent tự vào trận khi mở (kiểm tra lại lúc {{ when(lobby.next_check_at) }}).</div>
  <div v-else-if="lobby && lobby.agent_running && lobby.state==='not_applied'" role="status"
   style="background:#3a2a05;border:1px solid #e3b341;color:#f5d98a;padding:6px 12px;margin:0 16px 8px;border-radius:6px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
   <b>⏸ Tài khoản chưa ở trận nào</b><span>(trận cũ đã kết thúc). Agent không tự đăng ký — chọn chế độ:</span>
   <select v-model="lobbyPick" aria-label="Chế độ trận">
    <option v-for="t in lobby.can_play" :key="t" :value="t">{{ optLabel(t) }}</option>
   </select>
   <button @click="applyMatch" :disabled="lobby.apply_pending!==undefined">Đăng ký trận</button>
   <span v-if="lobby.apply_pending!==undefined">đang gửi…</span>
   <span v-if="lobby.apply && !lobby.apply.ok">Lần trước bị từ chối: {{ lobby.apply.error }}</span>
   <span v-if="lobbyMsg">{{ lobbyMsg }}</span></div>
  <template v-if="!waiting">
  <div v-if="alerts && alerts.level==='captured'" role="alert"
   style="background:#3d0d0d;border:1px solid #da3633;color:#ffb3ad;padding:8px 12px;margin:0 16px 8px;border-radius:6px">
   <b>⛔ THÀNH CHÍNH ĐÃ BỊ CHIẾM</b> bởi người chơi <b>{{ alerts.captured.uid }}</b>.
   Agent đã tạm ngừng mọi hành động. Vào game chọn: <b>tái lập thành</b> / quyết toán / chờ.</div>
  <div v-else-if="alerts && alerts.level==='danger'" role="alert"
   style="background:#3d0d0d;border:1px solid #da3633;color:#ffb3ad;padding:8px 12px;margin:0 16px 8px;border-radius:6px">
   <b>⚔️ QUÂN ĐỊCH ĐANG TIẾN VÀO</b> ({{ alerts.incoming.length }} cánh quân):
   <span v-for="(h,i) in alerts.incoming.slice(0,4)" :key="h.uid">
    <b>{{ h.target_is_main ? 'THÀNH CHÍNH' : ('ô ('+h.target_xy[0]+','+h.target_xy[1]+')') }}</b>
    ← {{ h.owner }} · tới sau ~{{ eta(h.eta_s) }}<span v-if="i<Math.min(alerts.incoming.length,4)-1"> · </span></span></div>
  <div v-else-if="alerts && alerts.level==='warn' && alerts.approach && alerts.approach.approaching"
   role="status"
   style="background:#3a2a05;border:1px solid #e3b341;color:#f5d98a;padding:6px 12px;margin:0 16px 8px;border-radius:6px">
   <b>⚠ Địch áp sát thành chính:</b> {{ alerts.approach.near_count }} ô địch trong bán kính
   {{ alerts.approach.radius }} ô, gần nhất cách {{ alerts.approach.min_dist }} ô
   <span v-if="alerts.approach.nearest_xy">({{ alerts.approach.nearest_xy[0] }},{{ alerts.approach.nearest_xy[1] }})</span>.</div>
  </template>
 </div>`
};
