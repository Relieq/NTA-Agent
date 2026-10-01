import { postJSON } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const tactics=ref(null), log=ref([]), input=ref(""), busy=ref(false);
  const pending=ref(null);   // proposed renames awaiting the player's confirmation
  const strike=ref(null);    // proposed strike group awaiting confirmation
  const dismiss=ref(null);   // proposed dismissals awaiting confirmation (irreversible)
  const moves=ref(null);     // proposed pawn swaps/moves/reorders awaiting confirmation
  function say(who,text){ log.value=[...log.value,{who,text}]; }
  async function send(){
   const msg=input.value.trim(); if(!msg) return;
   input.value=""; say("Bạn",msg); busy.value=true; pending.value=null; strike.value=null; dismiss.value=null; moves.value=null;
   const o=await postJSON("/api/chat",{message:msg});
   if(!o){ say("Brain","⚠️ lỗi mạng"); }
   else if(!o.ok){ say("Brain","⚠️ "+(o.error||"lỗi")); }
   else{
    if(o.question) say("Brain","❓ "+o.question);   // hỏi lại khi chưa chắc
    (o.notices||[]).forEach(n=>say("Brain","⚠️ "+n));
    if(o.strike && (o.strike.targets||[]).length){
     strike.value=o.strike;                         // chờ Xác nhận
     say("Brain","Đề xuất tạo nhóm quân (xác nhận để thực hiện): "+o.strike.summary);
    }
    if((o.dismissals||[]).length){
     dismiss.value=o.dismissals;                    // chờ Xác nhận (không hoàn tác được)
     say("Brain","Đề xuất giải tán (KHÔNG hoàn tác được — xác nhận để thực hiện):");
    }
    if((o.pawn_moves||[]).length){
     moves.value=o.pawn_moves;                      // chờ Xác nhận
     say("Brain","Đề xuất tráo/chuyển lính (xác nhận để thực hiện):");
    }
    if(o.needs_confirm && (o.renames||[]).length){
     pending.value=o.renames;                       // chờ Xác nhận
     say("Brain","Đề xuất đổi tên (xác nhận để thực hiện):");
    }
    if(o.rationale) say("Brain", o.rationale);
    if((o.applied_text||[]).length) say("Brain","Đã áp dụng: "+o.applied_text.join("; "));
    tactics.value={active:o.active,presets:o.presets,notes:o.notes}; }
   busy.value=false;
  }
  async function confirm(){
   busy.value=true;
   const o=await postJSON("/api/chat/confirm",{renames:pending.value.map(r=>({uid:r.uid,name:r.name}))});
   say("Brain", (o&&o.ok)? ("✔ Đã xếp lệnh đổi tên "+(o.queued||[]).length+" đội — agent đổi khi đội rảnh (đội đang đánh/hành quân sẽ được đổi sau).")
                         : ("⚠️ "+((o&&o.error)||"lỗi")));
   pending.value=null; busy.value=false;
  }
  function cancel(){ pending.value=null; say("Brain","Đã huỷ đổi tên."); }
  async function confirmStrike(){
   busy.value=true;
   const o=await postJSON("/api/chat/confirm",{strike_target:strike.value.targets});
   say("Brain", (o&&o.ok)? ("✔ Đã giao mục tiêu gom quân: "+o.summary+". Agent sẽ dồn/chiêu mộ rồi đặt tên khi xong.")
                         : ("⚠️ "+((o&&o.error)||"lỗi")));
   strike.value=null; busy.value=false;
  }
  async function confirmDismiss(){
   const n=dismiss.value.reduce((s,d)=>s+d.count,0);
   if(!window.confirm("Giải tán "+n+" lính ở "+dismiss.value.length+" đội? Không hoàn tác được.")) return;
   busy.value=true;
   const o=await postJSON("/api/chat/confirm",{dismissals:dismiss.value.map(d=>({uid:d.uid,scope:d.scope,pawn_id:d.pawn_id,count:d.count}))});
   say("Brain", (o&&o.ok)? ("✔ Đã xếp lệnh giải tán "+(o.queued||[]).length+" đội — agent thực hiện khi đội rảnh (đội đang đánh/hành quân sẽ chờ).")
                         : ("⚠️ "+((o&&o.error)||"lỗi")));
   dismiss.value=null; busy.value=false;
  }
  async function confirmMoves(){
   const conflict=moves.value.some(m=>(m.conflict||[]).length);
   if(conflict && !window.confirm("Việc này làm hỏng mục tiêu đội hình đang chạy — xác nhận sẽ HỦY mục tiêu đó. Tiếp tục?")) return;
   busy.value=true;
   const o=await postJSON("/api/chat/confirm",{pawn_moves:moves.value.map(m=>m.spec)});
   say("Brain", (o&&o.ok)? ("✔ Đã xếp lệnh cho "+(o.queued||[]).length+" thao tác — agent làm khi các đội rảnh và ở cùng ô."
                          +(o.cancelled_goal?" Đã huỷ mục tiêu đội hình để composer không đổi ngược.":""))
                         : ("⚠️ "+((o&&o.error)||"lỗi")));
   moves.value=null; busy.value=false;
  }
  function cancelMoves(){ moves.value=null; say("Brain","Đã huỷ tráo lính."); }
  function cancelDismiss(){ dismiss.value=null; say("Brain","Đã huỷ giải tán."); }
  function cancelStrike(){ strike.value=null; say("Brain","Đã huỷ tạo nhóm quân."); }
  return { tactics, log, input, busy, send, pending, confirm, cancel, strike, confirmStrike, cancelStrike,
           dismiss, confirmDismiss, cancelDismiss, moves, confirmMoves, cancelMoves };
 },
 template:`<div class="card full"><h2>Chiến thuật (brain)</h2>
  <div v-if="tactics" class="muted">Đội hình đang dùng: <b>{{ tactics.active||"(mặc định)" }}</b> · Presets: {{ (tactics.presets||[]).join(", ")||"—" }}
   <ul><li v-for="(n,i) in (tactics.notes||[])" :key="i">{{ n }}</li><li v-if="!(tactics.notes||[]).length" class="muted">—</li></ul></div>
  <div v-else class="muted">—</div>
  <div class="feed" style="max-height:200px;overflow:auto;margin:8px 0">
   <div v-for="(l,i) in log" :key="i"><b>{{ l.who }}:</b> {{ l.text }}</div></div>
  <div v-if="strike" style="border:1px solid #58a6ff;border-radius:6px;padding:8px;margin:6px 0">
   <div style="margin-bottom:4px"><b>Tạo nhóm quân</b> <span class="muted">(dồn lính, chiêu mộ phần thiếu, giải tán lính cấp thấp thừa)</span></div>
   <ul style="margin:0 0 6px;padding-left:18px">
    <li v-for="(t,i) in strike.targets" :key="i">
     <b>{{ t.armies }} đội × {{ t.size }} {{ t.name }}</b>
     <span v-if="(t.names||[]).length" class="muted"> → {{ t.names.join(", ") }}</span></li></ul>
   <button :disabled="busy" @click="confirmStrike">Xác nhận</button>
   <button :disabled="busy" @click="cancelStrike" style="margin-left:6px">Huỷ</button></div>
  <div v-if="dismiss" style="border:1px solid #da3633;border-radius:6px;padding:8px;margin:6px 0">
   <div style="margin-bottom:4px"><b style="color:#da3633">Giải tán</b> <span class="muted">(không hoàn tác được; chỉ lính thường, không đụng tướng)</span></div>
   <ul style="margin:0 0 6px;padding-left:18px">
    <li v-for="(d,i) in dismiss" :key="i">
     <b>{{ d.name }}</b> <span class="muted">({{ d.troops }})</span> →
     <b v-if="d.scope==='army'">giải tán cả đội ({{ d.count }} lính)</b>
     <b v-else>giải tán {{ d.count }} lính{{ d.pawn_name ? " "+d.pawn_name : "" }} cấp thấp nhất</b>
     <span v-for="w in (d.warn||[])" :key="w" style="color:#d29922"> ⚠ {{ w }}</span></li></ul>
   <button :disabled="busy" @click="confirmDismiss" style="border-color:#da3633;color:#da3633">Xác nhận giải tán</button>
   <button :disabled="busy" @click="cancelDismiss" style="margin-left:6px">Huỷ</button></div>
  <div v-if="moves" style="border:1px solid #3fb950;border-radius:6px;padding:8px;margin:6px 0">
   <div style="margin-bottom:4px"><b>Tráo / chuyển lính</b> <span class="muted">(chọn lính cấp thấp nhất, không đụng tướng; chờ đội rảnh và cùng ô)</span></div>
   <ul style="margin:0 0 6px;padding-left:18px">
    <li v-for="(m,i) in moves" :key="i">{{ m.label }}
     <span v-for="c in (m.conflict||[])" :key="c" style="color:#d29922"> ⚠ {{ c }} — composer sẽ đổi ngược; xác nhận sẽ huỷ mục tiêu đội hình</span></li></ul>
   <button :disabled="busy" @click="confirmMoves">Xác nhận</button>
   <button :disabled="busy" @click="cancelMoves" style="margin-left:6px">Huỷ</button></div>
  <div v-if="pending" style="border:1px solid #d98a26;border-radius:6px;padding:8px;margin:6px 0">
   <ul style="margin:0 0 6px;padding-left:18px">
    <li v-for="(r,i) in pending" :key="i">
     <b>{{ r.current_name||r.uid }}</b> <span class="muted">({{ r.troops }})</span> → <b>{{ r.name }}</b></li></ul>
   <button :disabled="busy" @click="confirm">Xác nhận</button>
   <button :disabled="busy" @click="cancel" style="margin-left:6px">Huỷ</button></div>
  <div style="display:flex;gap:6px">
   <input v-model="input" @keydown.enter="send" style="flex:1"
    placeholder="Ra chỉ thị cho brain (vd: đổi tên 4 đội IMP thành Đội 1..4, hoặc giải tán 2 lính thấp cấp của Đội 1)…"/>
   <button :disabled="busy" @click="send">Gửi</button></div></div>`
};
