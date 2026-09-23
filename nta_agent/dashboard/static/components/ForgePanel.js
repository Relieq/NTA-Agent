import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
// Recast (rèn lại) panel: per COMMON equip, the agent re-forges until its EFFECT
// quality reaches the user's threshold or the item's iron budget runs out.
export default {
 setup(){
  const v=ref({equips:[],busy:null,iron:0});
  const edit=ref({});   // uid -> {pct, budget} being edited
  const msg=ref("");
  usePolling(async ()=>{ v.value=(await getJSON("/api/forge"))||{equips:[],busy:null,iron:0}; },3000);
  const pct=(q)=> q==null ? "—" : Math.round(q*100)+"%";
  function draft(e){
   if(!edit.value[e.uid]) edit.value={...edit.value,[e.uid]:{
     pct: e.target ? Math.round(e.target.threshold*100) : 80,
     budget: e.target ? e.target.budget : (e.iron_cost||1)*10 }};
   return edit.value[e.uid];
  }
  async function save(e){
   const d=draft(e);
   const r=await postJSON("/api/forge/target",{uid:e.uid,threshold_pct:Number(d.pct),budget:Number(d.budget)});
   msg.value=(r&&r.ok)? "Đã lưu mục tiêu cho "+e.name : ((r&&r.error)||"Lỗi");
   setTimeout(()=>{msg.value="";},3000);
  }
  async function remove(e){
   await postJSON("/api/forge/target",{uid:e.uid,remove:true});
   const n={...edit.value}; delete n[e.uid]; edit.value=n;
  }
  const status=(e)=>{
   if(!e.target) return {t:"không rèn lại", c:"var(--muted, #8b949e)"};
   if(e.quality!=null && e.quality>=e.target.threshold) return {t:"✅ đã đạt ngưỡng", c:"#199e70"};
   if(!e.next_free && e.target.budget < e.iron_cost) return {t:"⛔ hết ngân sách sắt", c:"#da3633"};
   return {t:"🔁 đang rèn lại"+(e.next_free?" · lần tới miễn phí":""), c:"#58a6ff"};
  };
  return { v, pct, draft, save, remove, status, msg };
 },
 template:`<div class="card full"><h2>Rèn lại trang bị</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   Agent rèn lại trang bị <b>thường</b> tới khi <b>điểm hiệu ứng</b> (vị trí trong dải của giá trị + tỉ lệ
   từng hiệu ứng; không tính công/máu) đạt ngưỡng, hoặc hết ngân sách sắt của món đó. Không khôi phục chỉ số cũ.
   Sắt hiện có: <b>{{ v.iron }}</b><span v-if="v.busy"> · ⏳ đang rèn {{ v.busy.uid }}</span></div>
  <span v-if="!v.equips.length" class="muted">Chưa có trang bị thường nào (cần mở khoá + chế tạo trước).</span>
  <div v-for="e in v.equips" :key="e.uid" style="border-top:1px solid var(--border, #30363d);padding:6px 0">
   <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
    <b>{{ e.name }}</b>
    <span>Điểm hiệu ứng: <b>{{ pct(e.quality) }}</b></span>
    <span class="muted" style="font-size:12px">đã rèn {{ e.recast_count }} lần · {{ e.iron_cost }} sắt/lần</span>
    <span :style="{color:status(e).c,fontSize:'12px'}">{{ status(e).t }}</span></div>
   <div v-for="(f,i) in e.effects" :key="i" class="muted" style="font-size:12px">
    • {{ f.text || ('hiệu ứng #'+f.type) }}
    <span v-if="f.value_range.length">(giá trị {{ f.value_range[0] }}–{{ f.value_range[1] }}<span v-if="f.odds_range.length">, tỉ lệ {{ f.odds_range[0] }}–{{ f.odds_range[1] }}%</span>)</span></div>
   <div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap;font-size:13px">
    <label>Ngưỡng <input type="number" min="0" max="100" style="width:60px" v-model="draft(e).pct">%</label>
    <label>Ngân sách <input type="number" min="0" style="width:70px" v-model="draft(e).budget"> sắt</label>
    <button @click="save(e)">{{ e.target ? "Cập nhật" : "Rèn lại món này" }}</button>
    <button v-if="e.target" @click="remove(e)">Bỏ</button>
    <span v-if="e.target" class="muted">còn {{ e.target.budget }} sắt</span></div>
  </div>
  <div v-if="msg" style="margin-top:6px;color:#199e70;font-size:12px">{{ msg }}</div>
 </div>`
};
