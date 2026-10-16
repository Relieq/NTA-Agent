import { getJSON, usePolling, useHidden } from "../api.js";
const { ref } = window.Vue;

// Phase I — Thông tin & cố vấn: đọc /api/intel và hiển thị cho người chơi quyết.
const TYPE_LABEL = { defense:"Phòng thủ", fort:"Cứ Điểm", expansion:"Mở rộng",
                     economy:"Kinh tế", farm:"Farm" };

export default {
 setup(){
  const r=ref({});
  usePolling(async ()=>{ const v=await getJSON("/api/intel"); r.value=v||{}; },3000);
  // "✖ Ẩn" per notice (remembered in this browser, expires after a week; "hiện lại" brings them back)
  const hid=useHidden("intel");
  const spKey=()=>"spares:"+((r.value.spares&&r.value.spares.armies)||[]).join(",");
  const recs=()=>(r.value.recommendations||[]).filter(x=>!hid.isHidden(x.type+"|"+x.text));
  const warns=()=>((r.value.economy&&r.value.economy.warnings)||[]).filter(w=>!hid.isHidden("eco|"+w));
  const advice=()=>(r.value.brain_advice||[]).filter(a=>!hid.isHidden("brain|"+a.text));
  return { r, TYPE_LABEL, hid, spKey, recs, warns, advice };
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
   <li v-for="(x,i) in recs()" :key="x.type+'|'+x.text" style="margin:4px 0">
    <b>[{{ TYPE_LABEL[x.type]||x.type }}]</b> {{ x.text }}
    <span v-if="x.why" style="color:#8b949e"> — {{ x.why }}</span>
    <button @click="hid.hide(x.type+'|'+x.text)" title="Ẩn khuyến nghị này" style="padding:0 6px;margin-left:6px">✖</button>
   </li>
   <li v-if="!recs().length" style="color:#8b949e">Chưa có khuyến nghị.</li>
  </ul>

  <template v-if="r.economy">
   <h3 style="margin:12px 0 6px">Kinh tế</h3>
   <div v-for="w in warns()" :key="w" class="kv" style="color:#d98a26">⚠ {{ w }}
    <button @click="hid.hide('eco|'+w)" title="Ẩn cảnh báo này" style="padding:0 6px;margin-left:6px">✖</button></div>
   <div class="kv" style="color:#8b949e" v-if="r.economy.forecasts_hours">
    Dự báo đầy kho (giờ):
    <span v-for="(h,k) in r.economy.forecasts_hours" :key="k"> {{ k }}~{{ h }}h</span>
   </div>
  </template>

  <div v-if="r.spares && r.spares.status==='stuck' && !hid.isHidden(spKey())" style="margin-top:10px;border-left:3px solid #e3b341;padding-left:8px">
   <button @click="hid.hide(spKey())" title="Ẩn cảnh báo này" style="float:right;padding:0 6px">✖</button>
   <b>⚠ Đội lẻ không đánh được</b>: {{ (r.spares.armies||[]).join(', ') }} — gộp lại vẫn không đánh sạch
   được ô biên nào theo mọi thứ tự.
   <div class="muted" style="font-size:12px">Thành phần:
    <span v-for="(n,k) in (r.spares.composition||{})" :key="k"> {{ n }}× {{ k }}</span></div>
   <div class="muted" style="font-size:12px">Chat với brain để chỉnh đội hình (dồn/chiêu mộ/nâng cấp các đội này).</div>
  </div>

  <template v-if="advice().length">
   <h3 style="margin:12px 0 6px">Cố vấn từ bộ não 🧠</h3>
   <ul style="margin:0;padding-left:18px">
    <li v-for="a in advice()" :key="a.text" style="margin:4px 0">
     {{ a.text }}<span v-if="a.why" style="color:#8b949e"> — {{ a.why }}</span>
     <button @click="hid.hide('brain|'+a.text)" title="Ẩn lời khuyên này" style="padding:0 6px;margin-left:6px">✖</button></li>
   </ul>
  </template>

  <div v-if="hid.hiddenCount()" class="kv" style="margin-top:10px;color:#8b949e">
   Đã ẩn {{ hid.hiddenCount() }} thông báo · <a href="#" @click.prevent="hid.showAll()" style="color:#58a6ff">hiện lại</a></div>

  <div class="kv" style="margin-top:10px;color:#8b949e">
   Cơ hội: biên hở <b>{{ (r.opportunities&&r.opportunities.open_frontier)??0 }}</b> ô ·
   địch quanh <b>{{ (r.opportunities&&r.opportunities.enemy_nearby)??0 }}</b> ô</div>
 </div>`
};
