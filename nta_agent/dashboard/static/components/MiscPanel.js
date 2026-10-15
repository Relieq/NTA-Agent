import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
// Marching armies come from the agent's army list (armies.json: state 1 = marching, 2 = fighting) and
// owned cells from the territory view — GameState.marches/areas are never filled.
export default {
 setup(){
  const s=ref({}), p=ref({}), marching=ref(0), fighting=ref(0), total=ref(0), owned=ref(0);
  const free=ref({next:{},claimed:{}});
  const FREE=[["wheel","Vòng quay"],["gold","Vàng miễn phí"],["token","Token chiến"],["newbie","Gói tân thủ"]];
  // one simple fact per reward: the wheel shows today's spins out of 10 (the game's daily free
  // spins); the others show only when the next one is due
  function freeLine(k){
   if(k==="wheel"){ const n=(free.value.today||{}).wheel; return (n==null?"?":n)+"/10"; }
   const n=(free.value.next||{})[k];
   if(!n) return "—";
   const d=Math.round(n-Date.now()/1000);
   if(d<=0) return "tới lượt";
   const h=Math.floor(d/3600), m=Math.floor((d%3600)/60), sec=d%60;
   return "sau "+(h?h+"g":"")+(h||m?m+"p":"")+(h?"":sec+"s");
  }
  usePolling(async ()=>{
   const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:{}; p.value=(v&&v.player)||{};
   const a=await getJSON("/api/armies"); const rows=Array.isArray(a)?a:((a&&a.armies)||[]);
   total.value=rows.length; marching.value=rows.filter(r=>Number(r.state)===1).length;
   fighting.value=rows.filter(r=>Number(r.state)===2).length;
   const f=await getJSON("/api/forts"); owned.value=(f&&f.owned_count)||0;
   const fr=await getJSON("/api/free-rewards"); if(fr) free.value=fr;
  },4000);
  return { s, p, marching, fighting, total, owned, free, FREE, freeLine };
 },
 template:`<div class="card"><h2>Quân &amp; nhiệm vụ</h2>
  <div class="kv">Đội hành quân <b>{{ marching }}</b> · đang đánh <b>{{ fighting }}</b> / {{ total }} đội · Ô đã chiếm <b>{{ owned }}</b></div>
  <div class="kv" style="margin-top:8px">Guide <b>{{ p.guide_tasks??0 }}</b> · Other <b>{{ p.other_tasks??0 }}</b> · Today <b>{{ p.today_tasks??0 }}</b></div>
  <div class="kv" style="margin-top:8px;font-size:12px">🎁 Phần thưởng miễn phí (agent tự nhận):
   <span v-for="(f,i) in FREE" :key="f[0]">{{ i ? " · " : " " }}{{ f[1] }} <b>{{ freeLine(f[0]) }}</b></span></div></div>`
};
