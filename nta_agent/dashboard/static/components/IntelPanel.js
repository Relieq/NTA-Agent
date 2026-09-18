import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;

// Phase I — Thông tin & cố vấn: đọc /api/intel và hiển thị cho người chơi quyết.
const TYPE_LABEL = { defense:"Phòng thủ", fort:"Cứ Điểm", expansion:"Mở rộng",
                     economy:"Kinh tế", farm:"Farm" };

export default {
 setup(){
  const r=ref({});
  usePolling(async ()=>{ const v=await getJSON("/api/intel"); r.value=v||{}; },3000);
  return { r, TYPE_LABEL };
 },
 template:`<div class="card"><h2>Cố vấn — Thông tin &amp; khuyến nghị</h2>
  <div class="kv" style="margin-bottom:8px">{{ r.status || 'Đang chờ dữ liệu…' }}</div>

  <template v-if="r.threats && r.threats.summary && r.threats.summary.count">
   <div class="kv" style="color:#da3633;font-weight:600">
    ⚠ {{ r.threats.summary.count }} địch chạm biên
    <span v-if="r.threats.summary.has_enemy_city"> · có thành địch</span>
    <span v-if="r.threats.summary.inside_count"> · {{ r.threats.summary.inside_count }} đã lọt vào</span>
    <span v-if="r.threats.summary.directions && r.threats.summary.directions.length">
     · hướng: {{ r.threats.summary.directions.join(', ') }}</span>
   </div>
  </template>
  <div v-else class="kv" style="color:#199e70">✓ Biên giới an toàn</div>

  <h3 style="margin:12px 0 6px">Khuyến nghị</h3>
  <ul style="margin:0;padding-left:18px">
   <li v-for="(x,i) in (r.recommendations||[])" :key="i" style="margin:4px 0">
    <b>[{{ TYPE_LABEL[x.type]||x.type }}]</b> {{ x.text }}
    <span v-if="x.why" style="color:#8b949e"> — {{ x.why }}</span>
   </li>
   <li v-if="!(r.recommendations||[]).length" style="color:#8b949e">Chưa có khuyến nghị.</li>
  </ul>

  <template v-if="r.economy">
   <h3 style="margin:12px 0 6px">Kinh tế</h3>
   <div v-for="w in (r.economy.warnings||[])" :key="w" class="kv" style="color:#d98a26">⚠ {{ w }}</div>
   <div class="kv" style="color:#8b949e" v-if="r.economy.forecasts_hours">
    Dự báo đầy kho (giờ):
    <span v-for="(h,k) in r.economy.forecasts_hours" :key="k"> {{ k }}~{{ h }}h</span>
   </div>
  </template>

  <div class="kv" style="margin-top:10px;color:#8b949e">
   Cơ hội: biên hở <b>{{ (r.opportunities&&r.opportunities.open_frontier)??0 }}</b> ô ·
   địch quanh <b>{{ (r.opportunities&&r.opportunities.enemy_nearby)??0 }}</b> ô</div>
 </div>`
};
