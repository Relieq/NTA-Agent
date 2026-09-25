import { postJSON } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const tactics=ref(null), log=ref([]), input=ref(""), busy=ref(false);
  const pending=ref(null);   // proposed renames awaiting the player's confirmation
  const strike=ref(null);    // proposed strike group awaiting confirmation
  function say(who,text){ log.value=[...log.value,{who,text}]; }
  async function send(){
   const msg=input.value.trim(); if(!msg) return;
   input.value=""; say("Bạn",msg); busy.value=true; pending.value=null; strike.value=null;
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
  function cancelStrike(){ strike.value=null; say("Brain","Đã huỷ tạo nhóm quân."); }
  return { tactics, log, input, busy, send, pending, confirm, cancel, strike, confirmStrike, cancelStrike };
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
  <div v-if="pending" style="border:1px solid #d98a26;border-radius:6px;padding:8px;margin:6px 0">
   <ul style="margin:0 0 6px;padding-left:18px">
    <li v-for="(r,i) in pending" :key="i">
     <b>{{ r.current_name||r.uid }}</b> <span class="muted">({{ r.troops }})</span> → <b>{{ r.name }}</b></li></ul>
   <button :disabled="busy" @click="confirm">Xác nhận</button>
   <button :disabled="busy" @click="cancel" style="margin-left:6px">Huỷ</button></div>
  <div style="display:flex;gap:6px">
   <input v-model="input" @keydown.enter="send" style="flex:1"
    placeholder="Ra chỉ thị cho brain (vd: đổi tên 4 đội IMP thành Đội 1..4)…"/>
   <button :disabled="busy" @click="send">Gửi</button></div></div>`
};
