import { getJSON, postJSON, usePolling } from "../api.js";
import Collapsible from "./Collapsible.js";
const { ref } = window.Vue;
export default {
 components:{ Collapsible },
 setup(){
  const ps=ref([]); const sending=ref({});
  usePolling(async ()=>{ ps.value=(await getJSON("/api/equipment"))||[]; },2000);
  async function equip(p, o){
   const key=p.pawn_id+":"+o.uid; sending.value={...sending.value,[key]:true};
   await postJSON("/api/command",{action:"equip",pawn_id:p.pawn_id,equip_uid:o.uid,
    skin_id:p.skin_id,attack_speed:p.attack_speed});
  }
  return { ps, equip, sending };
 },
 template:`<div class="card full"><h2>Trang bị lính</h2>
  <span v-if="!ps.length" class="muted">—</span>
  <Collapsible v-for="p in ps" :key="p.pawn_id" :id="'equip-'+p.pawn_id" :title="p.pawn_name"
   :summary="'hiện: '+(p.current_equip_name||'—')+' · '+(p.options||[]).length+' món để chọn'">
   <div v-if="p.current_equip_desc" class="muted" style="font-size:12px;margin-bottom:3px">Đang đeo: {{ p.current_equip_desc }}</div>
   <div v-for="o in (p.options||[])" :key="o.uid" style="display:flex;align-items:flex-start;gap:8px;margin:3px 0">
    <button :disabled="o.uid===p.current_equip_uid||sending[p.pawn_id+':'+o.uid]" @click="equip(p,o)">{{ sending[p.pawn_id+':'+o.uid]?"đã gửi…":o.name }}</button>
    <div style="font-size:12px;display:flex;flex-direction:column;gap:1px;min-width:0">
     <span v-if="o.exclusive" style="align-self:flex-start;font-size:11px;padding:0 6px;border-radius:8px;border:1px solid #a371f7;color:#a371f7">chuyên dụng</span>
     <template v-if="(o.lines||[]).length">
      <span v-for="(l,i) in o.lines" :key="i" :class="{muted:l.smelted}" :title="l.text"
       style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ l.locked ? "🔒 " : (l.smelted ? "⧉ " : "• ") }}{{ l.text }}{{ l.smelted ? " (dung luyện)" : "" }}</span></template>
     <span v-else-if="o.desc" class="muted">{{ o.desc }}</span></div></div>
   <span v-if="!(p.options||[]).length" class="muted">không có trang bị phù hợp</span>
  </Collapsible></div>`
};
