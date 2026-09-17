import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){ const f=ref({owned_count:0,recommendations:[]});
  usePolling(async ()=>{ f.value=(await getJSON("/api/forts"))||{owned_count:0,recommendations:[]}; },4000);
  return { f }; },
 template:`<div class="card full"><h2>Cứ Điểm — gợi ý</h2>
  <div>Ô đã chiếm: <b>{{ f.owned_count||0 }}</b></div>
  <div style="margin-top:6px">
   <div v-for="(r,i) in (f.recommendations||[])" :key="i">{{ i+1 }}. Xây Cứ Điểm @{{ r.index }} ({{ r.x }},{{ r.y }}) — {{ r.reason||"" }}</div>
   <div v-if="!(f.recommendations||[]).length">Chưa có gợi ý</div></div></div>`
};
