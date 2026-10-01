import { getJSON, postJSON, usePolling } from "../api.js";
const { ref, computed } = window.Vue;
// Recast (rèn lại) panel, compact: one summary row per equip (click to edit), a
// filter bar (group + search, remembered), and an editor listing only the WISHED
// effects (+ add one). Minimums form a wish list: the agent stops once every random
// line (2 on an exclusive, 1 on a common) is any wished effect meeting its minimums.
// Exclusive: effects come from THIS match's pool; a met wished line is locked, then
// each recast of the other line costs fixators (own per-item budget).
const FKEY = "nta.forge.filter";
const GROUPS = [["all","Tất cả"],["active","Đang rèn"],["met","Đã đạt"],["none","Chưa đặt"],
                ["excl","Chuyên dụng"],["common","Thường"]];
function loadFilter(){ try{ return JSON.parse(localStorage.getItem(FKEY))||{g:"all",q:""}; }catch(e){ return {g:"all",q:""}; } }
export default {
 setup(){
  const v=ref({equips:[],busy:null,iron:0,fixator:0,smelting:null});
  const edit=ref({});   // uid -> {budget, fixator_budget, wish:[type], mins:{"<type>.value"|"<type>.odds": string}}
  const open=ref({});   // uid -> expanded
  const msg=ref("");
  const help=ref(false);
  const filter=ref(loadFilter());
  const saveFilter=()=>{ try{ localStorage.setItem(FKEY, JSON.stringify(filter.value)); }catch(e){} };
  usePolling(async ()=>{ v.value=(await getJSON("/api/forge"))||{equips:[],busy:null,iron:0,fixator:0,smelting:null}; },3000);
  const typeOf=(k)=> Number(String(k).split(".")[0]);
  function draft(e){
   if(!edit.value[e.uid]){
    const saved=(e.target&&e.target.mins)||{};
    const mins={}; Object.keys(saved).forEach(k=>{ mins[k]=String(saved[k]); });
    const wish=[...new Set(Object.keys(saved).map(typeOf))];
    edit.value={...edit.value,[e.uid]:{budget: e.target ? e.target.budget : (e.iron_cost||1)*10,
     fixator_budget: e.target ? (e.target.fixator_budget||0) : 0, wish, mins, add:""}};
   }
   return edit.value[e.uid];
  }
  const poss=(e,t)=> (e.possible||[]).find(p=>p.type===t)||{type:t,label:"hiệu ứng #"+t,value_range:[],odds_range:[]};
  const wished=(e)=> draft(e).wish.map(t=>poss(e,t));
  const addable=(e)=> (e.possible||[]).filter(p=>!draft(e).wish.includes(p.type));
  function addWish(e){
   const d=draft(e); const t=Number(d.add); d.add="";
   if(t && !d.wish.includes(t)) d.wish.push(t);
  }
  function dropWish(e,t){
   const d=draft(e); d.wish=d.wish.filter(x=>x!==t);
   delete d.mins[t+".value"]; delete d.mins[t+".odds"];
  }
  // outside the rollable range [lo,hi] of that number (blank = don't care)
  const outOf=(x,rng)=> x!=="" && x!=null && rng && rng.length===2 && (Number(x)<rng[0] || Number(x)>rng[1]);
  const bad=(e)=> wished(e).filter(p=>{
   const m=draft(e).mins;
   return outOf(m[p.type+".value"],p.value_range) || (p.odds_range.length && outOf(m[p.type+".odds"],p.odds_range));
  }).map(p=>p.label);
  // a wish with no number set would never count as met -> must set at least one
  const empty=(e)=> wished(e).filter(p=>{ const m=draft(e).mins;
   return !(m[p.type+".value"]||"")&&!(m[p.type+".odds"]||""); }).map(p=>p.label);
  const say=(t)=>{ msg.value=t; setTimeout(()=>{ msg.value=""; },4500); };
  async function save(e){
   const d=draft(e);
   if(bad(e).length) return say("Mức nằm ngoài khoảng roll được: "+bad(e).join(", "));
   if(empty(e).length) return say("Đặt ít nhất một mức cho: "+empty(e).join(", "));
   const mins={}; d.wish.forEach(t=>{ ["value","odds"].forEach(s=>{ const x=d.mins[t+"."+s]; if(x!==""&&x!=null) mins[t+"."+s]=x; }); });
   const r=await postJSON("/api/forge/target",{uid:e.uid,budget:Number(d.budget),fixator_budget:Number(d.fixator_budget||0),mins});
   say((r&&r.ok)? "Đã lưu tiêu chí cho "+e.name : ((r&&r.error)||"Lỗi"));
  }
  async function remove(e){
   await postJSON("/api/forge/target",{uid:e.uid,remove:true});
   const n={...edit.value}; delete n[e.uid]; edit.value=n;
  }
  const missed=(e,key)=> (e.unmet||[]).includes(key);
  const need=(e)=> e.exclusive ? 2 : 1;
  const status=(e)=>{
   if(!e.target) return {k:"none", t:"chưa đặt", c:"var(--muted, #8b949e)"};
   if(e.met) return {k:"met", t:"✅ đã đạt", c:"#199e70"};
   if(e.exclusive && !e.pool_known) return {k:"active", t:"⏸ chưa biết danh sách hiệu ứng trận này", c:"#d29922"};
   if(e.blocked) return {k:"active", t:"⛔ "+e.blocked, c:"#da3633"};
   if(v.value.smelting) return {k:"active", t:"⏸ đang dung luyện", c:"#d29922"};
   if(e.fixator_per_recast && (e.target.fixator_budget||0) < e.fixator_per_recast)
    return {k:"active", t:"⛔ hết ngân sách máy cố định", c:"#da3633"};
   if(!e.next_free && e.target.budget < e.iron_cost) return {k:"active", t:"⛔ hết ngân sách sắt", c:"#da3633"};
   return {k:"active", t:"🔁 đang rèn"+(e.next_free?" · lần tới miễn phí":""), c:"#58a6ff"};
  };
  const smelted=(e,t)=> (e.effects||[]).some(x=>x.type===t && x.smelted);
  const randomLines=(e)=> (e.effects||[]).filter(x=>!x.smelted);
  const smeltLines=(e)=> (e.effects||[]).filter(x=>x.smelted);
  const shown=computed(()=>{
   const g=filter.value.g, q=(filter.value.q||"").trim().toLowerCase();
   return (v.value.equips||[]).filter(e=>{
    const k=status(e).k;
    if(g==="active"&&k!=="active") return false;
    if(g==="met"&&k!=="met") return false;
    if(g==="none"&&k!=="none") return false;
    if(g==="excl"&&!e.exclusive) return false;
    if(g==="common"&&e.exclusive) return false;
    if(!q) return true;
    const hay=[e.name,e.pawn_name||"",...(e.effects||[]).map(x=>x.text),...(e.possible||[]).map(p=>p.label)].join(" ").toLowerCase();
    return hay.includes(q);
   });
  });
  const count=(g)=> (v.value.equips||[]).filter(e=>{ const k=status(e).k;
   return g==="all"||(g==="excl"?e.exclusive:g==="common"?!e.exclusive:k===g); }).length;
  const toggle=(e)=>{ open.value={...open.value,[e.uid]:!open.value[e.uid]}; };
  return { v, draft, save, remove, status, missed, msg, outOf, bad, smelted, help, filter, saveFilter,
           GROUPS, shown, count, open, toggle, wished, addable, addWish, dropWish, randomLines, smeltLines, need };
 },
 template:`<div class="card full">
  <div style="display:flex;align-items:center;gap:8px"><h2 style="margin:0">Rèn lại trang bị</h2>
   <button @click="help=!help" title="Cách agent rèn lại" style="padding:0 7px">?</button>
   <span class="muted" style="font-size:12px;margin-left:auto">Sắt <b>{{ v.iron }}</b> · Máy cố định <b>{{ v.fixator }}</b>
    <span v-if="v.busy"> · ⏳ đang rèn</span><span v-if="v.smelting" style="color:#d29922"> · ⏳ đang dung luyện</span></span></div>
  <div v-if="(v.craft_waiting||[]).length" style="font-size:12px;margin:6px 0;color:#d29922">
   ⏳ Chờ chế tạo:
   <span v-for="(w,i) in v.craft_waiting" :key="w.uid">{{ i ? " · " : "" }}<b>{{ w.name }}</b> thiếu
    {{ Object.entries(w.missing||{}).map(([k,n])=>n+" "+({timber:"gỗ",stone:"đá",iron:"sắt",cereal:"lương",gold:"vàng"}[k]||k)).join(", ") }}
    <span class="muted">{{ w.yield_builds ? "(xây dựng tạm nhường)" : "(xây dựng vẫn chạy)" }}</span></span>
   <span v-if="v.recast_held" class="muted"> · ⏸ vòng rèn lại tạm dừng để nhường tài nguyên cho món mới</span></div>
  <div v-if="help" class="muted" style="font-size:12px;margin:6px 0">
   Chọn các <b>hiệu ứng mong muốn</b> và mức tối thiểu (giá trị / tỉ lệ). Agent dừng khi <b>mọi hàng ngẫu nhiên</b> của món
   (2 hàng với món chuyên dụng, 1 hàng với món thường) đều là hiệu ứng trong danh sách và đạt mức — hiệu ứng nào cũng được.
   Hàng <b>dung luyện</b> cố định, không tính. Món chuyên dụng: danh sách hiệu ứng là của <b>trận này</b>; hàng mong muốn
   đầu tiên đạt mức được <b>khoá</b> 🔒 rồi mỗi lần rèn hàng còn lại tốn <b>máy cố định</b> (1 + 1 cho mỗi hàng dung luyện
   thuộc danh sách), trong ngân sách riêng của món. Không khôi phục chỉ số cũ.</div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:8px 0">
   <button v-for="g in GROUPS" :key="g[0]" @click="filter.g=g[0];saveFilter()"
    :style="filter.g===g[0] ? {borderColor:'#58a6ff',color:'#58a6ff'} : {}">{{ g[1] }} <span class="muted">{{ count(g[0]) }}</span></button>
   <input v-model="filter.q" @input="saveFilter()" placeholder="Tìm tên / hiệu ứng…" style="flex:1;min-width:140px"></div>
  <span v-if="!v.equips.length" class="muted">Chưa có trang bị nào (cần mở khoá + chế tạo trước).</span>
  <span v-else-if="!shown.length" class="muted">Không có món nào khớp bộ lọc.</span>
  <div v-for="e in shown" :key="e.uid" style="border-top:1px solid var(--border, #30363d);padding:5px 0">
   <div @click="toggle(e)" style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;cursor:pointer">
    <span class="muted" style="width:10px">{{ open[e.uid] ? "▾" : "▸" }}</span>
    <b>{{ e.name }}</b>
    <span v-if="e.exclusive" style="font-size:11px;padding:0 6px;border-radius:8px;border:1px solid #a371f7;color:#a371f7">chuyên dụng · {{ e.pawn_name || e.pawn_id }}</span>
    <span :style="{color:status(e).c,fontSize:'12px'}">{{ status(e).t }}</span>
    <span v-if="e.target" class="muted" style="font-size:12px;margin-left:auto">còn {{ e.target.budget }} sắt<span v-if="e.exclusive"> · {{ e.target.fixator_budget||0 }} máy cố định</span></span></div>
   <div style="font-size:12px;margin-left:18px;display:flex;flex-direction:column;gap:1px">
    <span v-for="(x,i) in randomLines(e)" :key="'r'+i" :title="x.text"
     style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%">
     <span v-if="e.lock_effect===x.type" title="hàng đã khoá">🔒 </span>{{ x.text }}</span>
    <span v-for="(x,i) in smeltLines(e)" :key="'s'+i" :title="x.text" class="muted"
     style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%">⧉ {{ x.text }} (dung luyện)</span></div>
   <div v-if="open[e.uid]" style="margin:6px 0 4px 18px;padding:6px;border:1px dashed var(--border, #30363d);border-radius:6px">
    <div v-if="e.exclusive && !e.pool_known" class="muted" style="font-size:12px">Chưa lấy được danh sách hiệu ứng random của trận này (agent tự lấy khi chạy).</div>
    <div class="muted" style="font-size:12px;margin-bottom:4px">Hiệu ứng mong muốn — dừng khi đủ {{ need(e) }} hàng ngẫu nhiên thuộc danh sách và đạt mức
     <span v-if="e.exclusive && e.fixator_per_recast"> · {{ e.fixator_per_recast }} máy cố định/lần rèn</span></div>
    <table style="font-size:12px;border-collapse:collapse;width:100%">
     <tr v-for="p in wished(e)" :key="p.type">
      <td style="padding-right:8px;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" :title="p.label">
       {{ p.label }}<span v-if="e.lock_effect===p.type"> 🔒</span></td>
      <td style="padding-right:8px;white-space:nowrap">
       <span v-if="p.current"><template v-if="p.value_range.length">{{ p.current.value }}{{ p.suffix }}</template><span v-if="p.odds_range.length">{{ p.value_range.length ? " · " : "" }}{{ p.current.odds }}%</span><span v-if="smelted(e,p.type)" class="muted"> (dung luyện)</span></span>
       <span v-else class="muted">chưa có</span></td>
      <td style="padding-right:8px;white-space:nowrap"><template v-if="p.value_range.length">≥
       <input type="number" style="width:60px" :min="p.value_range[0]" :max="p.value_range[1]"
        :placeholder="p.value_range.join('–')" v-model="draft(e).mins[p.type+'.value']"
        :style="outOf(draft(e).mins[p.type+'.value'],p.value_range) ? {borderColor:'#da3633',color:'#da3633'} : {}">{{ p.suffix }}
       <span v-if="missed(e,p.type+'.value')" style="color:#da3633">✗</span></template></td>
      <td style="white-space:nowrap"><template v-if="p.odds_range.length">≥
       <input type="number" style="width:52px" :min="p.odds_range[0]" :max="p.odds_range[1]"
        :placeholder="p.odds_range.join('–')" v-model="draft(e).mins[p.type+'.odds']"
        :style="outOf(draft(e).mins[p.type+'.odds'],p.odds_range) ? {borderColor:'#da3633',color:'#da3633'} : {}">%
       <span v-if="missed(e,p.type+'.odds')" style="color:#da3633">✗</span></template></td>
      <td><button @click="dropWish(e,p.type)" title="Bỏ khỏi danh sách" style="padding:0 6px">×</button></td>
     </tr></table>
    <div v-if="addable(e).length" style="margin-top:4px">
     <select v-model="draft(e).add" @change="addWish(e)" style="max-width:100%;background:var(--panel, #161b22);color:inherit;border:1px solid var(--border, #30363d)">
      <option value="">＋ Thêm hiệu ứng mong muốn…</option>
      <option v-for="p in addable(e)" :key="p.type" :value="String(p.type)">{{ p.label }}</option></select></div>
    <div style="display:flex;gap:8px;align-items:center;margin-top:6px;flex-wrap:wrap;font-size:13px">
     <label>Ngân sách <input type="number" min="0" style="width:64px" v-model="draft(e).budget"> sắt</label>
     <label v-if="e.exclusive"><input type="number" min="0" style="width:52px" v-model="draft(e).fixator_budget"> máy cố định</label>
     <button @click="save(e)" :disabled="bad(e).length>0 || !draft(e).wish.length">{{ e.target ? "Cập nhật" : "Rèn lại món này" }}</button>
     <button v-if="e.target" @click="remove(e)">Bỏ</button></div>
   </div>
  </div>
  <div v-if="msg" style="margin-top:6px;font-size:12px" :style="{color: msg.startsWith('Đã')?'#199e70':'#da3633'}">{{ msg }}</div>
 </div>`
};
