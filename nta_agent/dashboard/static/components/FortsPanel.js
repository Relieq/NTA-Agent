import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const f=ref({owned_count:0,fort_zone:[],fort_count:0,fort_cap:0,pending:[],forts:[],building:[],scanned_at:0});
  async function load(){ const v=await getJSON("/api/forts");
   if(v) f.value={owned_count:v.owned_count||0, fort_zone:v.fort_zone||[],
                  fort_count:v.fort_count||0, fort_cap:v.fort_cap||0,
                  pending:v.pending||[], forts:v.forts||[],
                  building:v.building||[], scanned_at:v.scanned_at||0}; }
  // remaining build time: surplus at the last scan minus the time since that scan
  const left=(b)=>{ const s=Math.max(0,(b.surplus_s||0)-(Date.now()/1000-(f.value.scanned_at||0)));
   return s>=60 ? Math.ceil(s/60)+" phút" : (s>0 ? "<1 phút" : "sắp xong"); };
  usePolling(load, 4000);
  return { f, left };
 },
 template:`<div class="card full"><h2>Cứ Điểm</h2>
  <div>Ô đã chiếm: <b>{{ f.owned_count||0 }}</b> · Cứ Điểm: <b>{{ f.fort_count }}</b><span v-if="f.fort_cap">/{{ f.fort_cap }}</span></div>
  <div v-if="(f.forts||[]).length" style="margin-top:6px;font-size:13px">
   🏯 <b>Cứ Điểm đã xây:</b>
   <span v-for="(c,i) in f.forts" :key="i" style="color:#8957e5">({{ c[0] }},{{ c[1] }})<span v-if="i<f.forts.length-1"> · </span></span></div>
  <div v-if="f.fort_cap && f.fort_count>=f.fort_cap" class="muted" style="margin-top:6px;color:#e3b341">
   Đã đủ số Cứ Điểm — không cần xây thêm.</div>
  <div v-else class="muted" style="margin-top:6px;font-size:13px">
   Có <b style="color:#d95926">{{ f.fort_zone.length }}</b> ô nằm trong <b>vùng gợi ý xây Cứ Điểm</b>
   (đất mình, ngoài bán kính 6 ô quanh thành). Mở tab <b>Lãnh thổ</b> → bấm 1 ô trong vùng cam
   để agent gửi lệnh xây. Không còn danh sách chấp thuận/từ chối — cứ chọn ô bạn muốn.</div>
  <div v-if="(f.building||[]).length" style="margin-top:8px;border-left:3px solid #8957e5;padding-left:8px">
   <b>🏗 Đang xây ({{ f.building.length }})</b> — lệnh đã gửi, game đang xây:
   <ul style="margin:4px 0 0 16px;padding:0">
    <li v-for="b in f.building" :key="b.index">Ô ({{ b.x }},{{ b.y }}) · còn ~{{ left(b) }}</li></ul></div>
  <div v-if="(f.pending||[]).length" style="margin-top:8px;border-left:3px solid #d98a26;padding-left:8px">
   <b>⏳ Đang chờ xây ({{ f.pending.length }})</b> — ưu tiên hơn công trình khác, xây khi đủ tài nguyên:
   <ul style="margin:4px 0;padding-left:18px">
    <li v-for="p in f.pending" :key="p.index">Ô ({{ p.x }},{{ p.y }})</li></ul></div>
 </div>`
};
