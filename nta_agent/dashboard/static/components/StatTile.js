export default {
 props:{ label:String, value:[String,Number], sub:{type:String, default:"" } },
 template:`<div class="tile"><div class="tlabel">{{ label }}</div>
  <div class="tval">{{ value }}</div><div v-if="sub" class="muted tsub">{{ sub }}</div></div>`
};
