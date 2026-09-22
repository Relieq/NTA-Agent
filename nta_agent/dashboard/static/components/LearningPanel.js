import { getJSON, postJSON, usePolling, hms } from "../api.js";
const { ref } = window.Vue;

// Học-từ-thất-bại: hiển thị failures (ledger, do hands ghi) + lessons (brain chưng cất).
const KIND_LABEL = { battle_loss: "Tổn thất trận", res_depletion: "Cạn tài nguyên",
                     stuck_goal: "Mục tiêu kẹt" };

function cellXY(idx) {
  if (idx == null) return "";
  return `(${idx % 600},${Math.floor(idx / 600)})`;
}

export default {
  setup() {
    const fails = ref([]);
    const lessons = ref([]);
    const load = async () => {
      const f = await getJSON("/api/failures"); fails.value = (f && f.failures) || [];
      const l = await getJSON("/api/lessons"); lessons.value = (l && l.lessons) || [];
    };
    usePolling(load, 4000);
    const retire = async (id) => { const r = await postJSON("/api/lessons/retire", { id }); if (r) lessons.value = r.lessons || []; };
    const pin = async (id) => { const r = await postJSON("/api/lessons/pin", { id }); if (r) lessons.value = r.lessons || []; };
    const resText = (res) => {
      if (!res) return "";
      if (res.advice) return "💬 " + res.advice;
      if (res.lever_edits) return "⚙ " + JSON.stringify(res.lever_edits);
      return "";
    };
    return { fails, lessons, KIND_LABEL, cellXY, hms, retire, pin, resText };
  },
  template: `<div class="card"><h2>Học từ thất bại 🧠</h2>

    <h3 style="margin:8px 0 6px">Bài học đã rút ra</h3>
    <ul style="margin:0;padding-left:0;list-style:none">
      <li v-for="l in lessons.filter(x=>x.status!=='retired')" :key="l.id"
          style="margin:6px 0;border-left:3px solid #199e70;padding-left:8px">
        <div><b>{{ KIND_LABEL[l.trigger&&l.trigger.kind]||(l.trigger&&l.trigger.kind) }}</b>
          <span v-if="l.trigger&&l.trigger.match" style="color:#8b949e"> · {{ JSON.stringify(l.trigger.match) }}</span>
          <span v-if="l.pinned" title="pinned">📌</span>
          <span style="color:#8b949e"> ×{{ l.times_seen }}</span></div>
        <div>{{ l.diagnosis }}</div>
        <div style="color:#58a6ff">{{ resText(l.resolution) }}</div>
        <div v-if="l.validated_by" style="color:#199e70;font-size:12px">✓ {{ l.validated_by }}</div>
        <div style="margin-top:2px">
          <button @click="pin(l.id)" style="font-size:12px">Ghim</button>
          <button @click="retire(l.id)" style="font-size:12px">Bỏ</button></div>
      </li>
      <li v-if="!lessons.filter(x=>x.status!=='retired').length" style="color:#8b949e">Chưa có bài học.</li>
    </ul>

    <h3 style="margin:12px 0 6px">Thất bại gần đây</h3>
    <ul style="margin:0;padding-left:18px">
      <li v-for="(e,i) in fails" :key="e.id||i" style="margin:4px 0">
        <b>{{ KIND_LABEL[e.kind]||e.kind }}</b>
        <span v-if="e.context&&e.context.cell!=null"> {{ cellXY(e.context.cell) }}</span>
        <span v-if="e.context&&e.context.self_dead"> · tử trận {{ e.context.self_dead }}</span>
        <span v-if="e.context&&e.context.aoe" style="color:#d98a26"> · AoE</span>
        <span v-if="e.context&&e.context.rule"> · {{ e.context.rule }}</span>
        <span v-if="e.context&&e.context.resource"> ({{ e.context.resource }})</span>
        <span v-if="e.context&&e.context.counterfactual" style="color:#58a6ff">
          → nên: {{ e.context.counterfactual.best_order }} (chết {{ e.context.counterfactual.self_dead }})</span>
        <span style="color:#8b949e;font-size:12px"> · {{ hms(e.ts) }}</span>
      </li>
      <li v-if="!fails.length" style="color:#8b949e">Chưa có sự cố nào.</li>
    </ul>
  </div>`
};
