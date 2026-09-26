import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
// Marching armies come from the agent's army list (armies.json: state 1 = marching, 2 = fighting) and
// owned cells from the territory view — GameState.marches/areas are never filled.
export default {
 setup(){
  const s=ref({}), p=ref({}), marching=ref(0), fighting=ref(0), total=ref(0), owned=ref(0);
  usePolling(async ()=>{
   const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:{}; p.value=(v&&v.player)||{};
   const a=await getJSON("/api/armies"); const rows=Array.isArray(a)?a:((a&&a.armies)||[]);
   total.value=rows.length; marching.value=rows.filter(r=>Number(r.state)===1).length;
   fighting.value=rows.filter(r=>Number(r.state)===2).length;
   const f=await getJSON("/api/forts"); owned.value=(f&&f.owned_count)||0;
  },4000);
  return { s, p, marching, fighting, total, owned };
 },
 template:`<div class="card"><h2>Quân &amp; nhiệm vụ</h2>
  <div class="kv">Đội hành quân <b>{{ marching }}</b> · đang đánh <b>{{ fighting }}</b> / {{ total }} đội · Ô đã chiếm <b>{{ owned }}</b></div>
  <div class="kv" style="margin-top:8px">Guide <b>{{ p.guide_tasks??0 }}</b> · Other <b>{{ p.other_tasks??0 }}</b> · Today <b>{{ p.today_tasks??0 }}</b></div></div>`
};
