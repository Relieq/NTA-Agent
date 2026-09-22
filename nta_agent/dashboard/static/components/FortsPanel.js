import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const f=ref({owned_count:0,fort_zone:[],fort_count:0,fort_cap:0});
  async function load(){ const v=await getJSON("/api/forts");
   if(v) f.value={owned_count:v.owned_count||0, fort_zone:v.fort_zone||[],
                  fort_count:v.fort_count||0, fort_cap:v.fort_cap||0}; }
  usePolling(load, 4000);
  return { f };
 },
 template:`<div class="card full"><h2>Cứ Điểm</h2>
  <div>Ô đã chiếm: <b>{{ f.owned_count||0 }}</b> · Cứ Điểm: <b>{{ f.fort_count }}</b><span v-if="f.fort_cap">/{{ f.fort_cap }}</span></div>
  <div v-if="f.fort_cap && f.fort_count>=f.fort_cap" class="muted" style="margin-top:6px;color:#e3b341">
   Đã đủ số Cứ Điểm — không cần xây thêm.</div>
  <div v-else class="muted" style="margin-top:6px;font-size:13px">
   Có <b style="color:#d95926">{{ f.fort_zone.length }}</b> ô nằm trong <b>vùng gợi ý xây Cứ Điểm</b>
   (đất mình, ngoài bán kính 6 ô quanh thành). Mở tab <b>Lãnh thổ</b> → bấm 1 ô trong vùng cam
   để agent gửi lệnh xây. Không còn danh sách chấp thuận/từ chối — cứ chọn ô bạn muốn.</div>
 </div>`
};
