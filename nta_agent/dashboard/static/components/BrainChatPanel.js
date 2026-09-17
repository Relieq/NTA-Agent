import { postJSON } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const tactics=ref(null), log=ref([]), input=ref(""), busy=ref(false);
  function say(who,text){ log.value=[...log.value,{who,text}]; }
  async function send(){
   const msg=input.value.trim(); if(!msg) return;
   input.value=""; say("Bạn",msg); busy.value=true;
   const o=await postJSON("/api/chat",{message:msg});
   if(!o){ say("Brain","⚠️ lỗi mạng"); }
   else if(!o.ok){ say("Brain","⚠️ "+(o.error||"lỗi")); }
   else{ say("Brain",(o.rationale||"đã cập nhật")+" — "+JSON.stringify(o.applied));
    tactics.value={active:o.active,presets:o.presets,notes:o.notes}; }
   busy.value=false;
  }
  return { tactics, log, input, busy, send };
 },
 template:`<div class="card full"><h2>Chiến thuật (brain)</h2>
  <div v-if="tactics" class="muted">Đội hình đang dùng: <b>{{ tactics.active||"(mặc định)" }}</b> · Presets: {{ (tactics.presets||[]).join(", ")||"—" }}
   <ul><li v-for="(n,i) in (tactics.notes||[])" :key="i">{{ n }}</li><li v-if="!(tactics.notes||[]).length" class="muted">—</li></ul></div>
  <div v-else class="muted">—</div>
  <div class="feed" style="max-height:200px;overflow:auto;margin:8px 0">
   <div v-for="(l,i) in log" :key="i"><b>{{ l.who }}:</b> {{ l.text }}</div></div>
  <div style="display:flex;gap:6px">
   <input v-model="input" @keydown.enter="send" style="flex:1"
    placeholder="Ra chỉ thị cho brain (vd: tạo đội hình 'rùa' 1 khiên 4 IMP)…"/>
   <button :disabled="busy" @click="send">Gửi</button></div></div>`
};
