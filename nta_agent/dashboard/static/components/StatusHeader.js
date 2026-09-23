import { getJSON, usePolling, ago } from "../api.js";
import ControlBar from "./ControlBar.js";
const { ref } = window.Vue;
export default {
 components:{ ControlBar },
 setup(){
  const snap=ref("…");
  const health=ref(null);
  const alerts=ref(null);
  usePolling(async ()=>{
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
  return { snap, health, hlabel, hcolor, alerts, eta };
 },
 template:`<div><header><div><h1>NTA Agent</h1>
   <div class="muted" style="font-size:12px">{{ snap }}</div>
   <div v-if="health" style="font-size:12px" :style="{color:hcolor(health)}">{{ hlabel(health) }}</div></div>
  <ControlBar/></header>
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
 </div>`
};
