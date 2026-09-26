import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
// Dung luyện (smelting) — the PLAYER decides: pick an exclusive equip (main) and the
// common equips to smelt into it (1 per open slot), look at the preview, confirm.
// The agent only sends that confirmed command; it never smelts/restores by itself.
export default {
 setup(){
  const v=ref({mains:[],slots:0,need_lv:[14,20],smithy_lv:0,fixator:0,smelting:null,forging:null});
  const pick=ref({});      // main uid -> [vice id | "" per slot]
  const prev=ref({});      // main uid -> preview reply
  const msg=ref({});       // main uid -> {t, ok}
  usePolling(async ()=>{ const r=await getJSON("/api/smelt"); if(r) v.value={...v.value,...r}; },4000);
  function sel(m){
   if(!pick.value[m.uid]) pick.value={...pick.value,[m.uid]:Array.from({length:Math.max(v.value.slots,0)},()=>"")};
   const a=pick.value[m.uid];
   while(a.length<v.value.slots) a.push("");
   return a;
  }
  const chosen=(m)=> sel(m).filter(x=>x!=="").map(Number);
  const say=(m,t,ok)=>{ msg.value={...msg.value,[m.uid]:{t,ok}}; setTimeout(()=>{ const n={...msg.value}; delete n[m.uid]; msg.value=n; },6000); };
  const clearPrev=(m)=>{ const n={...prev.value}; delete n[m.uid]; prev.value=n; };
  async function preview(m){
   const r=await postJSON("/api/smelt/preview",{main_uid:m.uid,vice_ids:chosen(m)});
   if(r&&r.ok) prev.value={...prev.value,[m.uid]:r}; else say(m,(r&&r.error)||"Lỗi",false);
  }
  async function confirmSmelt(m){
   const r=await postJSON("/api/smelt/command",{action:"smelt",main_uid:m.uid,vice_ids:chosen(m)});
   if(r&&r.ok){ clearPrev(m); say(m,"Đã gửi lệnh dung luyện — agent thực hiện ở lượt tới",true); }
   else say(m,(r&&r.error)||"Lỗi",false);
  }
  async function restore(m){
   if(!window.confirm("Khôi phục "+m.name+" về trước khi dung luyện? Các hiệu ứng dung luyện sẽ mất.")) return;
   const r=await postJSON("/api/smelt/command",{action:"restore_smelt",main_uid:m.uid});
   say(m, r&&r.ok ? "Đã gửi lệnh khôi phục" : ((r&&r.error)||"Lỗi"), !!(r&&r.ok));
  }
  const busy=()=> v.value.smelting ? "đang dung luyện" : (v.value.forging ? "đang rèn" : "");
  const candName=(m,id)=> ((m.candidates||[]).find(c=>c.id===id)||{}).name || ("#"+id);
  return { v, sel, chosen, preview, confirmSmelt, restore, prev, msg, busy, candName, clearPrev };
 },
 template:`<div class="card full"><h2>Dung luyện trang bị chuyên dụng</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   <b>Bạn tự quyết</b>: chọn món phụ cho từng ô, xem trước rồi xác nhận — agent chỉ gửi đúng lệnh đó.
   Món chính giữ mọi thuộc tính và thêm hiệu ứng + ½ chỉ số của món phụ; mỗi món phụ tốn 1 máy cố định.
   Hiệu ứng dung luyện thuộc danh sách random của trận này sẽ làm <b>mỗi lần rèn lại</b> tốn thêm 1 máy cố định.
   <br>Tiệm Rèn Lv <b>{{ v.smithy_lv }}</b> → mở <b>{{ v.slots }}</b>/2 ô (Lv{{ v.need_lv[0] }} / Lv{{ v.need_lv[1] }}) ·
   Máy cố định: <b>{{ v.fixator }}</b>
   <span v-if="busy()" style="color:#d29922"> · ⏳ {{ busy() }}</span></div>
  <span v-if="!v.mains.length" class="muted">Chưa có trang bị chuyên dụng nào.</span>
  <div v-for="m in v.mains" :key="m.uid" style="border-top:1px solid var(--border, #30363d);padding:6px 0">
   <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
    <b>{{ m.name }}</b>
    <span style="font-size:11px;padding:0 6px;border-radius:8px;border:1px solid #a371f7;color:#a371f7">chuyên dụng · {{ m.pawn_name }}</span></div>
   <div style="font-size:12px;margin-top:2px">
    <div v-for="(e,i) in m.effects" :key="i">• {{ e.text }}
     <span v-if="e.smelted" class="muted">(dung luyện từ {{ candName(m,e.from) }}<span v-if="m.pool.includes(e.type)"> · trong danh sách → +1 máy cố định/lần rèn</span>)</span></div></div>
   <div v-if="!v.slots" class="muted" style="font-size:12px;margin-top:4px">Tiệm Rèn cần Lv{{ v.need_lv[0] }} để dung luyện.</div>
   <div v-else style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:4px;font-size:13px">
    <label v-for="(x,i) in sel(m)" :key="i">Ô {{ i+1 }}
     <select v-model="sel(m)[i]" @change="clearPrev(m)">
      <option value="">— trống —</option>
      <option v-for="c in m.candidates" :key="c.uid" :value="String(c.id)"
       :disabled="sel(m).some((y,j)=>j!==i && y===String(c.id))">
       {{ c.name }}{{ c.in_pool ? " ★" : "" }} — {{ c.effects.map(e=>e.text).join("; ") }}</option>
     </select></label>
    <button @click="preview(m)" :disabled="!chosen(m).length">Xem trước</button>
    <button v-if="m.smelted_from.length" @click="restore(m)" :disabled="!!busy()">Khôi phục</button></div>
   <div v-if="prev[m.uid]" style="font-size:12px;margin-top:4px;padding:6px;border:1px dashed var(--border, #30363d);border-radius:6px">
    <div><b>Sau khi dung luyện</b> (thay các hiệu ứng dung luyện cũ):</div>
    <div v-for="(a,i) in prev[m.uid].added" :key="i">+ {{ a.text }}
     <span v-if="a.in_pool" style="color:#d29922">(trong danh sách random → +1 máy cố định/lần rèn)</span></div>
    <div v-if="prev[m.uid].stats.hp || prev[m.uid].stats.attack" class="muted">
     + chỉ số: <span v-if="prev[m.uid].stats.hp">Máu +{{ prev[m.uid].stats.hp }} </span><span v-if="prev[m.uid].stats.attack">Công +{{ prev[m.uid].stats.attack }}</span></div>
    <div>Tốn ngay: <b>{{ prev[m.uid].fixator_cost }}</b> máy cố định · mỗi lần rèn lại sau đó: <b>{{ prev[m.uid].fixator_per_recast }}</b></div>
    <div v-if="prev[m.uid].unchanged" style="color:#d29922">Giống hệt dung luyện hiện tại — không đổi gì.</div>
    <div style="margin-top:4px;display:flex;gap:8px">
     <button @click="confirmSmelt(m)" :disabled="!!busy() || prev[m.uid].unchanged">Xác nhận dung luyện</button>
     <button @click="clearPrev(m)">Huỷ</button></div></div>
   <div v-if="msg[m.uid]" style="font-size:12px;margin-top:4px" :style="{color: msg[m.uid].ok ? '#199e70' : '#da3633'}">{{ msg[m.uid].t }}</div>
  </div>
 </div>`
};
