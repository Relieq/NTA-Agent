import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const RES=[["cereal","L.Thực"],["timber","Gỗ"],["stone","Đá"],["iron","Sắt"],
 ["gold","Vàng"],["exp_book","Sách EXP"],["up_scroll","Quyển Trục"],["fixator","Máy Cố Định"]];
export default {
 setup(){
  const res=ref({});
  usePolling(async ()=>{ const s=await getJSON("/api/state"); res.value=(s&&s.ok&&s.resources)||{}; },2000);
  return { RES, res };
 },
 template:`<div class="card"><h2>Tài nguyên</h2>
  <div class="kv"><span v-for="[k,l] in RES" :key="k">{{ l }} <b>{{ res[k]??0 }}</b></span></div></div>`
};
