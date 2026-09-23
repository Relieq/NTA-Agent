import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const ds=ref([]); const gold=ref(0);
  usePolling(async ()=>{
   ds.value=(await getJSON("/api/decisions"))||[];
   const s=await getJSON("/api/state"); gold.value=(s&&s.ok&&s.resources&&s.resources.gold)||0;
  },2000);
  const sending=ref({});
  const skey=(d,o)=> d.track+":"+d.lv+":"+(o?o.ceri_id:"reroll");
  // The first reroll (reset_count 0) is free; later ones cost RESET_STUDY_SLOT_GOLD
  // (engine constant = 50 gold). Gold is the USER's currency (fixed: it used to read
  // player.gold = 0, which blocked every paid reroll).
  const REROLL_GOLD=50;
  const canReroll=(d)=> (d.reset_count||0)===0 || gold.value>=REROLL_GOLD;
  async function act(d, o){
   const key=skey(d,o);
   sending.value={...sending.value,[key]:true};
   const cmd=o? {action:"select",track:d.track,lv:d.lv,ceri_id:o.ceri_id}
             : {action:"reroll",track:d.track,lv:d.lv};
   await postJSON("/api/command", cmd);
  }
  const TRACK={pawn:"Binh chủng",equip:"Trang bị",policy:"Chính sách"};
  const tname=(t)=> TRACK[t]||t;
  return { ds, act, sending, skey, canReroll, tname, gold, REROLL_GOLD };
 },
 template:`<div class="card full"><h2>Quyết định đang chờ (chọn 1 trong 3)</h2>
  <span v-if="!ds.length" class="muted">—</span>
  <div v-for="d in ds" :key="d.track+d.lv" style="margin:10px 0">
   <div class="muted" style="margin-bottom:3px">{{ tname(d.track) }} · Lv{{ d.lv }}</div>
   <div v-for="o in (d.options||[])" :key="o.ceri_id" style="display:flex;align-items:center;gap:8px;margin:2px 0">
    <button :disabled="sending[skey(d,o)]" @click="act(d,o)" style="min-width:130px">{{ sending[skey(d,o)]?"đã gửi…":o.name }}</button>
    <span v-if="o.desc" class="muted" style="font-size:12px">{{ o.desc }}</span></div>
   <button :disabled="sending[skey(d,null)]||!canReroll(d)" :title="canReroll(d)?'':'Không đủ '+REROLL_GOLD+' vàng để làm mới'" @click="act(d,null)">{{ sending[skey(d,null)]?"đã gửi…":("Làm mới"+(d.reset_count?(" ("+REROLL_GOLD+" vàng)"):" (miễn phí)")) }}</button>
   <span v-if="!canReroll(d)" class="muted" style="font-size:12px">· cần {{ REROLL_GOLD }} vàng (đang có {{ gold }})</span>
  </div></div>`
};
