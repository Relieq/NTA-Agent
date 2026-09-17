import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){ const armies=ref([]);
  usePolling(async ()=>{ armies.value=(await getJSON("/api/armies"))||[]; },2000);
  return { armies }; },
 template:`<div class="card full"><h2>Đội quân</h2>
  <span v-if="!armies.length" class="muted">—</span>
  <div v-for="a in armies" :key="a.uid" style="margin:8px 0">
   <b>{{ a.name||a.uid }}</b> <span class="muted">· {{ a.state_label }} · tốc hành quân {{ a.march_speed }}</span>
   <ul><li v-for="(p,i) in (a.pawns||[])" :key="i">{{ i+1 }}. {{ p.name }} <b>Lv{{ p.lv }}</b> · tốc {{ p.attack_speed }} · {{ p.equip_name||"—" }}</li>
    <li v-if="!(a.pawns||[]).length" class="muted">trống</li></ul></div></div>`
};
