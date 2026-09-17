import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
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
  <div v-for="p in ps" :key="p.pawn_id" style="margin:6px 0">
   <span class="muted">{{ p.pawn_name }}</span> — hiện: <b>{{ p.current_equip_name||"—" }}</b><br>
   <template v-for="o in (p.options||[])" :key="o.uid">
    <button :disabled="o.uid===p.current_equip_uid||sending[p.pawn_id+':'+o.uid]" @click="equip(p,o)">{{ sending[p.pawn_id+':'+o.uid]?"đã gửi…":o.name }}</button>
   </template>
   <span v-if="!(p.options||[]).length" class="muted">không có trang bị phù hợp</span>
  </div></div>`
};
