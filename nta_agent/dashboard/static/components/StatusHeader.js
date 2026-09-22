import { getJSON, usePolling, ago } from "../api.js";
import ControlBar from "./ControlBar.js";
const { ref } = window.Vue;
export default {
 components:{ ControlBar },
 setup(){
  const snap=ref("…");
  const health=ref(null);
  usePolling(async ()=>{
   const s=await getJSON("/api/state");
   snap.value=(s&&s.ok)? ("snapshot "+ago(s.updated_at)) : "chưa có snapshot";
   health.value=await getJSON("/api/health");
  }, 2000);
  const hlabel=(h)=>{
   if(!h) return "";
   if(h.degraded) return "⚠ mất kết nối (thử lại…)";
   const age=Math.round(h.last_activity_age||0);
   const rc=h.recover_count?(" · đã phục hồi "+h.recover_count+"×"):"";
   return "🟢 kết nối OK · "+age+"s trước"+rc;
  };
  const hcolor=(h)=> h&&h.degraded ? "#da3633" : "#199e70";
  return { snap, health, hlabel, hcolor };
 },
 template:`<header><div><h1>NTA Agent</h1>
   <div class="muted" style="font-size:12px">{{ snap }}</div>
   <div v-if="health" style="font-size:12px" :style="{color:hcolor(health)}">{{ hlabel(health) }}</div></div>
  <ControlBar/></header>`
};
