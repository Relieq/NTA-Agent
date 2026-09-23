import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
// Recast (rèn lại) panel. Each COMMON equip gets its OWN criteria: a minimum per
// effect number (value and/or odds — an effect line can carry two numbers). The
// agent re-forges until every set minimum holds or the item's iron budget runs out.
export default {
 setup(){
  const v=ref({equips:[],busy:null,iron:0});
  const edit=ref({});   // uid -> {budget, mins:{"<type>.value"|"<type>.odds": string}}
  const msg=ref("");
  usePolling(async ()=>{ v.value=(await getJSON("/api/forge"))||{equips:[],busy:null,iron:0}; },3000);
  function draft(e){
   if(!edit.value[e.uid]){
    const mins={};
    const saved=(e.target&&e.target.mins)||{};
    (e.possible||[]).forEach(p=>{
     mins[p.type+".value"]= saved[p.type+".value"]!=null ? String(saved[p.type+".value"]) : "";
     if(p.odds_range.length) mins[p.type+".odds"]= saved[p.type+".odds"]!=null ? String(saved[p.type+".odds"]) : "";
    });
    edit.value={...edit.value,[e.uid]:{budget: e.target ? e.target.budget : (e.iron_cost||1)*10, mins}};
   }
   return edit.value[e.uid];
  }
  async function save(e){
   const d=draft(e);
   const r=await postJSON("/api/forge/target",{uid:e.uid,budget:Number(d.budget),mins:d.mins});
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
   if(!e.next_free && e.target.budget < e.iron_cost) return {t:"⛔ hết ngân sách sắt", c:"#da3633"};
   return {t:"🔁 đang rèn lại"+(e.next_free?" · lần tới miễn phí":""), c:"#58a6ff"};
  };
  return { v, draft, save, remove, status, missed, msg };
 },
 template:`<div class="card full"><h2>Rèn lại trang bị</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   Mỗi trang bị <b>thường</b> có tiêu chí riêng: đặt <b>mức tối thiểu cho từng chỉ số hiệu ứng</b> (giá trị / tỉ lệ;
   để trống = không quan tâm). Agent rèn lại tới khi <b>mọi</b> mức đã đặt đều đạt, hoặc hết ngân sách sắt của món đó.
   Hiệu ứng chưa roll ra mà có đặt mức thì tính là chưa đạt. Không khôi phục chỉ số cũ.
   Sắt hiện có: <b>{{ v.iron }}</b><span v-if="v.busy"> · ⏳ đang rèn {{ v.busy.uid }}</span></div>
  <span v-if="!v.equips.length" class="muted">Chưa có trang bị thường nào (cần mở khoá + chế tạo trước).</span>
  <div v-for="e in v.equips" :key="e.uid" style="border-top:1px solid var(--border, #30363d);padding:6px 0">
   <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
    <b>{{ e.name }}</b>
    <span class="muted" style="font-size:12px">đã rèn {{ e.recast_count }} lần · {{ e.iron_cost }} sắt/lần</span>
    <span :style="{color:status(e).c,fontSize:'12px'}">{{ status(e).t }}</span></div>
   <table style="font-size:12px;margin-top:4px;border-collapse:collapse">
    <tr class="muted"><td style="padding-right:10px">Hiệu ứng</td><td style="padding-right:10px">Hiện tại</td>
     <td style="padding-right:10px">Tối thiểu giá trị</td><td>Tối thiểu tỉ lệ</td></tr>
    <tr v-for="p in (e.possible||[])" :key="p.type">
     <td style="padding-right:10px">{{ p.label }}</td>
     <td style="padding-right:10px">
      <span v-if="p.current">{{ p.current.value }}{{ p.suffix }}<span v-if="p.odds_range.length"> · {{ p.current.odds }}%</span></span>
      <span v-else class="muted">chưa có</span></td>
     <td style="padding-right:10px">
      <input type="number" style="width:64px" :placeholder="p.value_range.join('–')" v-model="draft(e).mins[p.type+'.value']">
      <span v-if="missed(e,p.type+'.value')" style="color:#da3633">✗</span></td>
     <td><template v-if="p.odds_range.length">
      <input type="number" style="width:56px" :placeholder="p.odds_range.join('–')" v-model="draft(e).mins[p.type+'.odds']">%
      <span v-if="missed(e,p.type+'.odds')" style="color:#da3633">✗</span></template>
      <span v-else class="muted">—</span></td>
    </tr></table>
   <div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap;font-size:13px">
    <label>Ngân sách <input type="number" min="0" style="width:70px" v-model="draft(e).budget"> sắt</label>
    <button @click="save(e)">{{ e.target ? "Cập nhật" : "Rèn lại món này" }}</button>
    <button v-if="e.target" @click="remove(e)">Bỏ</button>
    <span v-if="e.target" class="muted">còn {{ e.target.budget }} sắt</span></div>
  </div>
  <div v-if="msg" style="margin-top:6px;font-size:12px" :style="{color: msg.startsWith('Đã')?'#199e70':'#da3633'}">{{ msg }}</div>
 </div>`
};
