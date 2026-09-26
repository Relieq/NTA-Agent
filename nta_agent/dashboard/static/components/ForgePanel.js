import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
// Recast (rèn lại) panel. Each COMMON equip gets its OWN criteria: a minimum per
// effect number (value and/or odds — an effect line can carry two numbers). The
// agent re-forges until every set minimum holds or the item's iron budget runs out.
// Exclusive (chuyên dụng) equips: effects come from THIS match's pool; once a wanted
// line meets its minimums the agent locks it, then pays fixators per recast (own budget).
export default {
 setup(){
  const v=ref({equips:[],busy:null,iron:0,fixator:0,smelting:null});
  const edit=ref({});   // uid -> {budget, mins:{"<type>.value"|"<type>.odds": string}}
  const msg=ref("");
  usePolling(async ()=>{ v.value=(await getJSON("/api/forge"))||{equips:[],busy:null,iron:0,fixator:0,smelting:null}; },3000);
  function draft(e){
   if(!edit.value[e.uid]){
    const mins={};
    const saved=(e.target&&e.target.mins)||{};
    (e.possible||[]).forEach(p=>{
     mins[p.type+".value"]= saved[p.type+".value"]!=null ? String(saved[p.type+".value"]) : "";
     if(p.odds_range.length) mins[p.type+".odds"]= saved[p.type+".odds"]!=null ? String(saved[p.type+".odds"]) : "";
    });
    edit.value={...edit.value,[e.uid]:{budget: e.target ? e.target.budget : (e.iron_cost||1)*10,
     fixator_budget: e.target ? (e.target.fixator_budget||0) : 0, mins}};
   }
   return edit.value[e.uid];
  }
  // outside the rollable range [lo,hi] of that number (blank = don't care)
  const outOf=(v,rng)=> v!=="" && v!=null && rng && rng.length===2 && (Number(v)<rng[0] || Number(v)>rng[1]);
  const bad=(e)=> (e.possible||[]).filter(p=>{
   const m=draft(e).mins;
   return outOf(m[p.type+".value"],p.value_range) || (p.odds_range.length && outOf(m[p.type+".odds"],p.odds_range));
  }).map(p=>p.label);
  async function save(e){
   const d=draft(e);
   const b=bad(e);
   if(b.length){ msg.value="Mức nằm ngoài khoảng roll được: "+b.join(", "); setTimeout(()=>{msg.value="";},5000); return; }
   const r=await postJSON("/api/forge/target",{uid:e.uid,budget:Number(d.budget),fixator_budget:Number(d.fixator_budget||0),mins:d.mins});
   msg.value=(r&&r.ok)? "Đã lưu tiêu chí cho "+e.name : ((r&&r.error)||"Lỗi");
   setTimeout(()=>{msg.value="";},3500);
  }
  async function remove(e){
   await postJSON("/api/forge/target",{uid:e.uid,remove:true});
   const n={...edit.value}; delete n[e.uid]; edit.value=n;
  }
  const missed=(e,key)=> (e.unmet||[]).includes(key);
  const status=(e)=>{
   if(!e.target) return {t:"không rèn lại", c:"var(--muted, #8b949e)"};
   if(e.met) return {t:"✅ đã đạt mọi tiêu chí", c:"#199e70"};
   if(e.exclusive && !e.pool_known) return {t:"⏸ chưa biết danh sách hiệu ứng trận này", c:"#d29922"};
   if(e.blocked) return {t:"⛔ "+e.blocked, c:"#da3633"};
   if(v.value.smelting) return {t:"⏸ đang dung luyện — chờ xong mới rèn", c:"#d29922"};
   if(e.fixator_per_recast && (e.target.fixator_budget||0) < e.fixator_per_recast)
    return {t:"⛔ hết ngân sách máy cố định ("+e.fixator_per_recast+"/lần)", c:"#da3633"};
   if(!e.next_free && e.target.budget < e.iron_cost) return {t:"⛔ hết ngân sách sắt", c:"#da3633"};
   return {t:"🔁 đang rèn lại"+(e.next_free?" · lần tới miễn phí":""), c:"#58a6ff"};
  };
  const smelted=(e,t)=> (e.effects||[]).some(x=>x.type===t && x.smelted);
  return { v, draft, save, remove, status, missed, msg, outOf, bad, smelted };
 },
 template:`<div class="card full"><h2>Rèn lại trang bị</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   Mỗi trang bị <b>thường</b> có tiêu chí riêng: đặt <b>mức tối thiểu cho từng chỉ số hiệu ứng</b> (giá trị / tỉ lệ;
   để trống = không quan tâm). Agent rèn lại tới khi <b>mọi</b> mức đã đặt đều đạt, hoặc hết ngân sách sắt của món đó.
   Hiệu ứng chưa roll ra mà có đặt mức thì tính là chưa đạt. Không khôi phục chỉ số cũ.
   Trang bị <b>chuyên dụng</b>: danh sách hiệu ứng là của <b>trận này</b>; khi một dòng mong muốn đạt mức, agent
   <b>khoá</b> dòng đó rồi mới tốn <b>máy cố định</b> để rèn dòng còn lại (1/lần + 1 cho mỗi dòng dung luyện nằm trong danh sách).
   Sắt hiện có: <b>{{ v.iron }}</b> · Máy cố định: <b>{{ v.fixator }}</b>
   <span v-if="v.busy"> · ⏳ đang rèn {{ v.busy.uid }}</span>
   <span v-if="v.smelting" style="color:#d29922"> · ⏳ đang dung luyện (không rèn được)</span></div>
  <span v-if="!v.equips.length" class="muted">Chưa có trang bị nào (cần mở khoá + chế tạo trước).</span>
  <div v-for="e in v.equips" :key="e.uid" style="border-top:1px solid var(--border, #30363d);padding:6px 0">
   <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
    <b>{{ e.name }}</b>
    <span v-if="e.exclusive" style="font-size:11px;padding:0 6px;border-radius:8px;border:1px solid #a371f7;color:#a371f7">chuyên dụng · {{ e.pawn_name || e.pawn_id }}</span>
    <span v-if="e.exclusive && e.fixator_per_recast" class="muted" style="font-size:12px">{{ e.fixator_per_recast }} máy cố định/lần</span>
    <span class="muted" style="font-size:12px">đã rèn {{ e.recast_count }} lần · {{ e.iron_cost }} sắt/lần</span>
    <span :style="{color:status(e).c,fontSize:'12px'}">{{ status(e).t }}</span></div>
   <table style="font-size:12px;margin-top:4px;border-collapse:collapse">
    <tr class="muted"><td style="padding-right:10px">Hiệu ứng</td><td style="padding-right:10px">Hiện tại</td>
     <td style="padding-right:10px">Tối thiểu giá trị</td><td>Tối thiểu tỉ lệ</td></tr>
    <tr v-for="p in (e.possible||[])" :key="p.type">
     <td style="padding-right:10px">{{ p.label }}<span v-if="e.lock_effect===p.type" title="dòng đã khoá"> 🔒</span></td>
     <td style="padding-right:10px">
      <span v-if="p.current"><template v-if="p.value_range.length">{{ p.current.value }}{{ p.suffix }}</template><span v-if="p.odds_range.length">{{ p.value_range.length ? " · " : "" }}{{ p.current.odds }}%</span><span v-if="smelted(e,p.type)" class="muted"> (dung luyện)</span></span>
      <span v-else class="muted">chưa có</span></td>
     <td style="padding-right:10px"><template v-if="p.value_range.length">
      <input type="number" style="width:64px" :min="p.value_range[0]" :max="p.value_range[1]"
       :placeholder="p.value_range.join('–')" v-model="draft(e).mins[p.type+'.value']"
       :style="outOf(draft(e).mins[p.type+'.value'],p.value_range) ? {borderColor:'#da3633',color:'#da3633'} : {}">
      <span class="muted" style="font-size:11px"> {{ p.value_range[0] }}–{{ p.value_range[1] }}{{ p.suffix }}</span>
      <span v-if="missed(e,p.type+'.value')" style="color:#da3633">✗</span></template>
      <span v-else class="muted">—</span></td>
     <td><template v-if="p.odds_range.length">
      <input type="number" style="width:56px" :min="p.odds_range[0]" :max="p.odds_range[1]"
       :placeholder="p.odds_range.join('–')" v-model="draft(e).mins[p.type+'.odds']"
       :style="outOf(draft(e).mins[p.type+'.odds'],p.odds_range) ? {borderColor:'#da3633',color:'#da3633'} : {}">%
      <span class="muted" style="font-size:11px"> {{ p.odds_range[0] }}–{{ p.odds_range[1] }}%</span>
      <span v-if="missed(e,p.type+'.odds')" style="color:#da3633">✗</span></template>
      <span v-else class="muted">—</span></td>
    </tr></table>
   <div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap;font-size:13px">
    <label>Ngân sách <input type="number" min="0" style="width:70px" v-model="draft(e).budget"> sắt</label>
    <label v-if="e.exclusive"><input type="number" min="0" style="width:56px" v-model="draft(e).fixator_budget"> máy cố định</label>
    <button @click="save(e)" :disabled="bad(e).length>0" :title="bad(e).length ? 'Có mức nằm ngoài khoảng roll được' : ''">{{ e.target ? "Cập nhật" : "Rèn lại món này" }}</button>
    <button v-if="e.target" @click="remove(e)">Bỏ</button>
    <span v-if="e.target" class="muted">còn {{ e.target.budget }} sắt<span v-if="e.exclusive"> · {{ e.target.fixator_budget||0 }} máy cố định</span></span></div>
   <div v-if="e.exclusive && !e.pool_known" class="muted" style="font-size:12px">Chưa lấy được danh sách hiệu ứng random của trận này (agent tự lấy khi chạy).</div>
  </div>
  <div v-if="msg" style="margin-top:6px;font-size:12px" :style="{color: msg.startsWith('Đã')?'#199e70':'#da3633'}">{{ msg }}</div>
 </div>`
};
