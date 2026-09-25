import { getJSON, postJSON, usePolling } from "../api.js";
const { ref, computed, onMounted } = window.Vue;

// Nâng cấp lính theo NHÓM đội: chế độ "Nâng trực tiếp" (nâng ngay trong đội ở thành)
// hoặc "Nâng bằng đội dư" (đội dư nâng ở thành rồi ra ô kề tráo lính cùng loại).
// Đề xuất đội dư do agent tính (sách/thời gian/dồn/chiêu mộ/giải tán) — người chơi Xác nhận.
const PHASE = { leveling: "đang nâng ở thành", travel: "đang tới ô kề", swap: "đang tráo lính",
                home: "đang về thành" };

export default {
 setup(){
  const cfg = ref({ enabled:false, target_lv:0, max_leveling:1 });
  const armies = ref([]);
  const pick = ref({});            // uid -> bool
  const mode = ref("direct");
  const target = ref(3);
  const lv = ref({ proposal:null, approved:false, buffers:{}, groups:[] });
  const saved = ref(""); const msg = ref("");

  async function load(){
   const p = await getJSON("/api/profile");
   if (p && p.leveling) cfg.value = Object.assign(cfg.value, p.leveling);
   const a = await getJSON("/api/armies"); if (a) armies.value = a;
   await loadLeveling(true);
  }
  async function loadLeveling(initial){
   const v = await getJSON("/api/leveling"); if (!v) return;
   lv.value = v;
   if (initial && v.groups && v.groups.length){
    const g = v.groups[0];
    pick.value = Object.fromEntries((g.armies||[]).map(u=>[u,true]));
    mode.value = g.mode || "direct"; target.value = g.target_lv || cfg.value.target_lv || 3;
   }
  }
  onMounted(load);
  usePolling(()=>loadLeveling(false), 5000);

  const nameOf = (uid) => (armies.value.find(a=>String(a.uid)===String(uid))||{}).name || uid;
  const proposal = computed(()=> lv.value.proposal);

  async function save(){
   saved.value = "";
   const group = { armies: Object.keys(pick.value).filter(u=>pick.value[u]),
                   mode: mode.value, target_lv: Number(target.value)||0 };
   const r = await postJSON("/api/profile", { leveling: {
     enabled: !!cfg.value.enabled,
     target_lv: Number(target.value) || Number(cfg.value.target_lv) || 0,
     max_leveling: Number(cfg.value.max_leveling) || 1,
     groups: group.armies.length ? [group] : [],
   }});
   saved.value = (r && r.ok) ? "Đã lưu ✓" : "Lưu lỗi";
  }
  async function confirm(){
   const r = await postJSON("/api/leveling/confirm", {});
   msg.value = (r && r.ok) ? "Đã xác nhận — agent bắt đầu sắp xếp đội dư" : ((r && r.error) || "Lỗi");
   loadLeveling(false);
  }
  const fmtMin = (s) => Math.round((s||0)/60) + " phút";
  return { cfg, armies, pick, mode, target, lv, proposal, saved, msg, save, confirm,
           nameOf, fmtMin, PHASE };
 },
 template:`<div class="card"><h2>Nâng cấp lính (sách exp)</h2>
  <label class="kv" style="display:block;margin:6px 0">
   <input type="checkbox" v-model="cfg.enabled"/> Bật tự động nâng cấp</label>

  <div class="kv" style="margin:6px 0"><b>Nhóm đội muốn nâng</b></div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;font-size:12px">
   <label v-for="a in armies" :key="a.uid"><input type="checkbox" v-model="pick[a.uid]"/>
    {{ a.name }} <span class="muted">({{ (a.pawns||[]).length }} lính)</span></label></div>

  <div class="kv" style="margin:8px 0">Chế độ:
   <label><input type="radio" value="direct" v-model="mode"/> Nâng trực tiếp</label>
   <label style="margin-left:10px"><input type="radio" value="buffer" v-model="mode"/> Nâng bằng đội dư</label></div>
  <div class="muted" style="font-size:12px">Trực tiếp: nâng ngay trong đội khi đội ở thành (đội bị giữ ở Thao Trường).
   Đội dư: đội dư nâng ở thành, rồi ra ô kề đội chính tráo lính cùng loại — đội chính vẫn farm/dig.</div>

  <label class="kv" style="display:block;margin:6px 0">Cấp mục tiêu
   <input type="number" min="1" v-model="target" style="width:70px;margin-left:6px"/></label>
  <button @click="save" style="margin-top:4px">Lưu cấu hình</button>
  <span class="kv" style="margin-left:10px;color:#199e70">{{ saved }}</span>

  <div v-if="mode==='buffer'" style="margin-top:10px;border-top:1px solid var(--border-hi);padding-top:8px">
   <div v-if="!proposal" class="muted" style="font-size:12px">Chưa có đề xuất — lưu cấu hình và bật agent để tính.</div>
   <template v-else>
    <div class="kv"><b>Đề xuất đội dư</b>
     <span v-if="lv.approved" style="color:#199e70"> · đã xác nhận</span></div>
    <div v-for="b in proposal.buffers" :key="b.name" style="font-size:12px;margin:4px 0">
     <b>{{ b.name }}</b>: {{ b.base_uid ? 'dùng lại ' + nameOf(b.base_uid) : 'tạo mới bằng chiêu mộ' }}
     <span v-if="(b.merge||[]).length"> · dồn {{ b.merge.length }} lính từ
      {{ [...new Set(b.merge.map(m=>nameOf(m.from_uid)))].join(', ') }}</span>
     <span v-if="Object.keys(b.recruit||{}).length"> · chiêu mộ
      {{ Object.values(b.recruit).reduce((x,y)=>x+y,0) }} lính</span></div>
    <div v-if="(proposal.dismiss||[]).length" style="font-size:12px;color:#da3633">
     ⚠ Giải tán (mất lính): {{ proposal.dismiss.map(nameOf).join(', ') }}</div>
    <div style="font-size:12px">Sách exp cần <b>{{ proposal.books_needed }}</b> / có {{ proposal.books_have }}
     · ước tính {{ fmtMin(proposal.time_s) }}</div>
    <div v-for="n in (proposal.notes||[])" :key="n" style="font-size:12px;color:#e3b341">{{ n }}</div>
    <button v-if="!lv.approved" @click="confirm" style="margin-top:6px">✔ Xác nhận đề xuất</button>
    <span class="kv" style="margin-left:8px">{{ msg }}</span>
   </template>
   <div v-if="Object.keys(lv.buffers||{}).length" style="margin-top:8px;font-size:12px">
    <div v-for="(b,uid) in lv.buffers" :key="uid">🛡 {{ b.name }} — {{ PHASE[b.phase] || b.phase }}
     <span v-if="b.target"> → {{ nameOf(b.target) }}</span></div></div>
  </div>
 </div>`
};
