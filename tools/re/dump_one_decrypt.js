'use strict';
function waitForModule(name, cb){
  var m=Process.findModuleByName(name); if(m){cb(m);return;}
  var done=false, dl;
  try{dl=Module.getGlobalExportByName('android_dlopen_ext');}catch(e){dl=Module.getGlobalExportByName('dlopen');}
  Interceptor.attach(dl,{onLeave:function(){ if(done)return; var mm=Process.findModuleByName(name); if(mm){done=true;cb(mm);} }});
}
function install(mod){
  var dec=mod.enumerateExports().find(function(e){return e.name.indexOf('xxtea_decrypt')>=0;});
  var grabbed=false;
  Interceptor.attach(dec.address,{
    onEnter:function(a){ this.data=a[0]; this.len=a[1].toInt32(); this.outp=a[4]; },
    onLeave:function(ret){
      if(grabbed||this.len>2000) return;   // grab first small one
      grabbed=true;
      var enc=this.data.readByteArray(this.len);
      var outlen=this.outp.readU32();
      var out=ret.readByteArray(outlen);
      var f1=new File('/data/data/twgame.global.acers/cache/enc.bin','wb'); f1.write(enc); f1.close();
      var f2=new File('/data/data/twgame.global.acers/cache/dec.bin','wb'); f2.write(out); f2.close();
      send({enc_len:this.len, dec_len:outlen});
    }
  });
  send({hooked:true});
}
setImmediate(function(){ waitForModule('libcocos2djs.so', install); });
